// ui-v2: the in-game L3+R3 overlay, replacing port/perf-r28/src/cheats-r28.cpp (the title's cheats.o).
//
// Kept unchanged from r28: the hooks the game calls (za_cheat_spec_before/after, za_cheat_capture_score, through
// port/randomizer/cheat_policy.hpp), the chord (L3+R3) and release-gate input logic, cheats.txt v2 per run, the FPS
// readout's clock discipline (one clock read per 15 presented frames), and every glue call: za_money_*, za_items_*,
// za_hebrew_trial_*, za_performance_*. New: the drawing. The UI thread (menu_handle_event / menu_apply_window_requests)
// runs the state machine (ui_overlay::press) and draws the panel into a 1920x1080 canvas; the render thread
// (menu_render, inside backend_present's window rendering after the game's own present) uploads the canvas when it
// changed and blends it as one quad (ui_quad). The FPS readout and the toasts are small layers of their own, drawn
// on the render thread. Favourites of the item picker are GLOBAL (items-ui.txt in the title's writable root).
#include <SDL3/SDL.h>

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <unistd.h>
#include <vector>

#include "cheat_policy.hpp"
#include "fonts_embedded.h"
#include "hebrew_trial.h"
#include "items_picker.h"
#include "ui_canvas.h"
#include "ui_overlay.h"
#include "ui_pad.h"
#include "ui_platform.h"
#include "ui_quad.h"
#include "ui_widgets.h"
#include "za_items.h"
#include "za_money.h"

extern "C" uint64_t renderer_present_count(void);   // runtime/nvn/vulkan/device.c: frames presented so far
extern "C" int za_performance_status(void);         // port/performance-r16: 0 original (30), 1 trial (60), 2 fallback
extern "C" void za_performance_request(int trial);

namespace {
using namespace ui;

// ---- the cheat state the game's hooks read (as cheats-r28.cpp: atomics, read on the game's threads)
std::atomic<unsigned> shiny{0}, capture{0}, specs{0}, catches{0};
std::atomic<bool> opened{false}, releaseGate{false};
uint32_t held = 0;
bool combo = false;
std::string settingsPath;
std::atomic<bool> saved{true};
std::atomic<bool> fpsCounter{false};
std::atomic<unsigned> moneyAdds{0};  // legacy v2 field, retained for backward compatibility only
std::atomic<bool> moneyRequestFailed{false};
bool forced60 = false, dynActive = false;

// ---- the UI (main / UI thread), published to the render thread as a canvas copy
std::mutex uiLock;                 // the state and the UI thread's canvas
overlay::State g_ui;
Fonts g_fonts;
std::mutex fontLock;               // glyph caches are mutable; panel and render-thread layers share the faces
bool fontsLoaded = false;
Canvas* panelCanvas = nullptr;     // drawn by the UI thread
std::mutex pubLock;                // the published copy
std::vector<uint8_t> published;
std::atomic<uint32_t> publishedGen{0};
pad::State padState;
uint64_t lastPollMs = 0;
pad::Script overlayScript;         // PC proof: ZA_UI_OVERLAY_SCRIPT (frames = presented frames)
bool overlayScriptLoaded = false;
std::atomic<unsigned> lastRequestedItem{0};
bool itemsUiDirty = false;

// ---- the render thread's own things
UiQuadLayer* panelLayer = nullptr;
UiQuadLayer* readoutLayer = nullptr;
UiQuadLayer* toastLayer = nullptr;
uint32_t uploadedGen = 0;
Canvas* readoutCanvas = nullptr;
Canvas* toastCanvas = nullptr;
std::string readoutText;
Rect readoutRectCanvas;
std::mutex toastLock;
Toast pendingToast;
bool toastPending = false;
Toast shownToast;
bool toastShown = false;
uint64_t toastUntilNs = 0;
unsigned lastApplied = 0;
std::string lastItemStatus;
UiQuadLayer* handoffLayer = nullptr;
float handoffDst[4] = {0, 0, 0, 0};
uint64_t handoffStartNs = 0;
bool handoffDone = false;

void logSettings() {
    platform::logf("[za-cheats] shiny_mode=%u capture_mode=%u changed_specs=%u changed_scores=%u fps_counter=%u money_adds=%u\n", shiny.load(),
                   capture.load(), specs.load(), catches.load(), unsigned(fpsCounter.load()), moneyAdds.load());
}

// cheats.txt v2 ("za-cheats-v2\n<shiny> <capture> <fps> <money_adds>\n"), written as before: .new, fsync, rename
void saveSettings() {
    if (settingsPath.empty()) { saved = false; return; }
    auto temp = settingsPath + ".new";
    FILE* f = std::fopen(temp.c_str(), "wb");
    if (!f) { saved = false; return; }
    bool ok = std::fprintf(f, "za-cheats-v2\n%u %u %u %u\n", shiny.load(), capture.load(), unsigned(fpsCounter.load()), moneyAdds.load()) > 0;
    if (std::fflush(f) || fsync(fileno(f))) ok = false;
    if (std::fclose(f)) ok = false;
    saved = ok && !std::rename(temp.c_str(), settingsPath.c_str());
    logSettings();
}

// Loads a v1 ("za-cheats-v1\n<shiny> <capture>") or v2 file. Unknown version / malformed: nothing changes.
void loadSettingsText(const char* text, unsigned& s, unsigned& c, unsigned& fps, unsigned& adds, bool& haveFps) {
    unsigned a = 0, b = 0, d = 0, e = 0;
    haveFps = false;
    if (std::sscanf(text, "za-cheats-v1\n%u %u", &a, &b) == 2) { if (a <= 4 && b <= 4) { s = a; c = b; } return; }
    int n = std::sscanf(text, "za-cheats-v2\n%u %u %u %u", &a, &b, &d, &e);
    if (n >= 2 && a <= 4 && b <= 4) { s = a; c = b; if (n >= 3 && d <= 1) { fps = d; haveFps = true; } if (n >= 4) adds = e; }
}

// items-ui.txt (za-items-ui-v1: favourites, recent additions, amount presets), global to the player
void saveItemsUi() {
    std::string text = g_ui.picker.serialize();
    std::string path = platform::itemsUiPath(), temp = path + ".new";
    FILE* f = std::fopen(temp.c_str(), "wb");
    if (!f) { platform::log("[ui-v2] items-ui.txt could not be written\n"); return; }
    bool ok = std::fwrite(text.data(), 1, text.size(), f) == text.size();
    if (std::fflush(f) || fsync(fileno(f))) ok = false;
    if (std::fclose(f)) ok = false;
    if (!ok || std::rename(temp.c_str(), path.c_str())) platform::log("[ui-v2] items-ui.txt could not be written\n");
}
void loadItemsUi() {
    FILE* f = std::fopen(platform::itemsUiPath().c_str(), "rb");
    if (!f) return;
    std::string text;
    char buf[4096];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) text.append(buf, n);
    std::fclose(f);
    if (!g_ui.picker.deserialize(text)) platform::log("[ui-v2] items-ui.txt ignored (unknown format)\n");
}

void requestToast(Toast::Kind kind, const std::string& text, const std::string& detail = "") {
    std::lock_guard<std::mutex> g(toastLock);
    pendingToast = {kind, text, detail};
    toastPending = true;
}

std::string u2s(unsigned v) { char b[16]; std::snprintf(b, sizeof b, "%u", v); return b; }

// The live state the rows show (UI thread). Returns true when something changed.
bool refreshCheatState() {
    overlay::CheatState& cs = g_ui.cheats;
    overlay::CheatState before = cs;
    std::string beforeItems = g_ui.itemStatus;
    unsigned beforeAdded = g_ui.itemsAdded;
    cs.shiny = int(shiny.load());
    cs.capture = int(capture.load());
    cs.fpsCounter = fpsCounter.load();
    g_ui.fpsCounter = cs.fpsCounter;
    cs.settingsSaved = saved.load();
    cs.fpsMode = (forced60 || dynActive) ? -1 : za_performance_status();
    cs.hebrewMode = za_hebrew_trial_status();
#ifdef ZA_MONEY_HOOK
    cs.moneyAvailable = true;
    if (za_money_pending()) cs.moneyStatus = "QUEUED - SAVE IN GAME";
    else if (!za_money_ready()) cs.moneyStatus = "LOAD SAVE FIRST";
    else if (moneyRequestFailed.load()) cs.moneyStatus = "RETRY";
    else if (za_money_applied()) cs.moneyStatus = "ADDED " + u2s(za_money_applied()) + "\xC3\x97";
    else cs.moneyStatus.clear();
#else
    cs.moneyAvailable = false;
    cs.moneyStatus.clear();
#endif
    g_ui.itemStatus = za_items_status();
    g_ui.itemsAdded = za_items_applied();
    return cs.shiny != before.shiny || cs.capture != before.capture || cs.fpsCounter != before.fpsCounter || cs.settingsSaved != before.settingsSaved ||
           cs.fpsMode != before.fpsMode || cs.hebrewMode != before.hebrewMode || cs.moneyStatus != before.moneyStatus || g_ui.itemStatus != beforeItems ||
           g_ui.itemsAdded != beforeAdded;
}

// Draws the panel canvas and publishes it (UI thread, uiLock held).
void redrawPanel() {
    if (!fontsLoaded || !panelCanvas) return;
    panelCanvas->clear(Color{0, 0, 0, 0});
    overlay::State view = g_ui;  // (a copy: the picker is small)
    view.drawReadout = false;
    view.drawToast = false;
    {
        std::lock_guard<std::mutex> g(fontLock);
        overlay::draw(*panelCanvas, g_fonts, view);
    }
    {
        std::lock_guard<std::mutex> g(pubLock);
        published.assign(panelCanvas->data(), panelCanvas->data() + panelCanvas->bytes());
    }
    publishedGen.fetch_add(1, std::memory_order_release);
}

void closeMenu() {
    opened = false;
    releaseGate = true;
    pad::clear(padState);
    logSettings();
}

// One press on the open menu (UI thread, uiLock held): the state machine, then the game-side effects.
void handlePress(pad::Button b) {
    overlay::Action a = overlay::press(g_ui, b);
    switch (a.kind) {
        case overlay::Action::None: break;
        case overlay::Action::Close: closeMenu(); break;
        case overlay::Action::SettingsChanged:
        case overlay::Action::Reset:
            shiny = unsigned(g_ui.cheats.shiny);
            capture = unsigned(g_ui.cheats.capture);
            fpsCounter = g_ui.cheats.fpsCounter;
            saveSettings();
            if (a.kind == overlay::Action::Reset) requestToast(Toast::Ok, "Shiny and capture back to normal");
            break;
        case overlay::Action::MoneyQueue: {
#ifdef ZA_MONEY_HOOK
            // Repeated X while queued is not a new failed request. Keep the pending request's acknowledgment visible when it lands.
            if (za_money_pending()) { requestToast(Toast::Warn, "Still queued", "Save in the game, or open the money display, to apply it"); break; }
            bool accepted = za_money_set_enabled(1) && za_money_request(a.amount);
            moneyRequestFailed = !accepted;
            platform::logf("[za-cheats] money request amount=%u accepted=%u applied=%u\n", a.amount, unsigned(accepted), za_money_applied());
            if (accepted) requestToast(Toast::Ok, "+" + u2s(a.amount) + " queued", "It lands when the game saves or shows your money");
            else requestToast(Toast::Err, za_money_ready() ? "Money request rejected" : "Load a save first", za_money_ready() ? "Press Cross to retry" : "The money component is not live yet");
#endif
            break;
        }
        case overlay::Action::MoneyCancel:
#ifdef ZA_MONEY_HOOK
            za_money_set_enabled(0);
            moneyRequestFailed = false;
#endif
            break;
        case overlay::Action::FpsTrial:
            if (forced60 || dynActive) { requestToast(Toast::Info, "FPS is controlled by the config file"); break; }
            {
                int status = za_performance_status();
                za_performance_request(status != 1);
                requestToast(Toast::Info, status != 1 ? "60 FPS trial started" : "Back to 30 FPS", status != 1 ? "Returns to 30 automatically when 60 cannot be held" : "");
            }
            break;
        case overlay::Action::Hebrew: {
            int before = za_hebrew_trial_status();
            if (before < 0) { requestToast(Toast::Warn, "Hebrew pack not available"); break; }
            int rc = za_hebrew_trial_request();
            if (rc > 0) { requestToast(Toast::Info, before ? "Hebrew trial off" : "Hebrew trial on", "Reloading the last saved progress"); closeMenu(); }
            else if (rc == 0) requestToast(Toast::Warn, "Hebrew switch already pending");
            else requestToast(Toast::Err, "Hebrew switch rejected", "Save first, then try again");
            break;
        }
        case overlay::Action::ItemRequest: {
            const items::Item& it = items::catalog()[a.index];
            std::string name = std::string(it.name) + " \xC3\x97" + u2s(a.amount);
            if (za_items_pending()) { requestToast(Toast::Warn, "Still queued", "Open the satchel in the game to add the previous item"); break; }
            if (!za_items_ready()) { requestToast(Toast::Warn, "Open the satchel first", "Adding works once the game has shown the bag"); break; }
            int ok = za_items_request(a.index, a.amount);
            platform::logf("[za-cheats] item request index=%u id=%u amount=%u accepted=%d status=%s\n", a.index, it.id, a.amount, ok, za_items_status());
            if (ok) {
                lastRequestedItem = a.index;
                g_ui.picker.noteAdded(a.index);
                itemsUiDirty = true;
                requestToast(Toast::Ok, name + " queued", "Open the satchel in the game to add it");
            } else {
                requestToast(Toast::Err, "Request rejected", za_items_status());
            }
            break;
        }
        case overlay::Action::FavouritesChanged: itemsUiDirty = true; break;
    }
    if (itemsUiDirty) { saveItemsUi(); itemsUiDirty = false; }
    refreshCheatState();
    redrawPanel();
}

// ---- the FPS readout (render thread only): the clock is read every 15 presented frames, as in r26p/r28
struct FpsReadout {
    uint64_t lastFrame = 0, lastNs = 0;
    unsigned fpsX10 = 0, msX10 = 0;
    int mode = -1;
    void tick() {
        uint64_t frame = renderer_present_count();
        if (!lastNs) { lastNs = SDL_GetTicksNS(); lastFrame = frame; return; }
        if (frame - lastFrame < 15) return;
        uint64_t now = SDL_GetTicksNS(), dt = now - lastNs;
        unsigned frames = unsigned(frame - lastFrame);
        lastNs = now;
        lastFrame = frame;
        if (dt == 0 || frames == 0) return;
        fpsX10 = unsigned((uint64_t(frames) * 10000000000ull + dt / 2) / dt);
        msX10 = unsigned((dt / frames + 50000) / 100000);
        mode = forced60 ? -2 : dynActive ? -3 : za_performance_status();
    }
    const char* modeText() const { return mode == -2 ? "60 FORCED" : mode == -3 ? "DYN SAFE" : mode == 1 ? "60 MODE" : mode == 2 ? "FALLBACK" : "30 MODE"; }
};
FpsReadout readout;

float windowScale(uint32_t h) { return float(h) / 1080.0f; }

void drawReadoutLayer(void* cmd, uint32_t w, uint32_t h) {
    if (!fontsLoaded) return;
    overlay::State view;
    view.readout.fpsX10 = readout.fpsX10;
    view.readout.msX10 = readout.msX10;
    view.readout.mode = readout.modeText();
    std::string text = std::to_string(view.readout.fpsX10) + "|" + std::to_string(view.readout.msX10) + "|" + view.readout.mode;
    if (!readoutCanvas) readoutCanvas = new Canvas(640, 48);
    if (!readoutLayer) readoutLayer = ui_quad_create(640, 48);
    if (!readoutLayer) return;
    if (text != readoutText) {
        readoutText = text;
        readoutCanvas->clear(Color{0, 0, 0, 0});
        {
            std::lock_guard<std::mutex> g(fontLock);
            overlay::drawReadoutOnly(*readoutCanvas, g_fonts, view);
            readoutRectCanvas = overlay::readoutRect(g_fonts, view);
        }
        ui_quad_upload(readoutLayer, cmd, readoutCanvas->data(), 640 * 4, 0, 0, 640, 48, true);
    }
    float s = windowScale(h);
    float rw = readoutRectCanvas.w, rh = readoutRectCanvas.h;
    float dst[4] = {float(w) - (1920.0f - readoutRectCanvas.x) * s, readoutRectCanvas.y * s, rw * s, rh * s};
    float uv[4] = {0, 0, rw / 640.0f, rh / 48.0f};
    ui_quad_draw(readoutLayer, cmd, dst, uv, 1.0f);
}

void drawToastLayer(void* cmd, uint32_t w, uint32_t h, uint64_t nowNs) {
    if (!fontsLoaded) return;
    {
        std::lock_guard<std::mutex> g(toastLock);
        if (toastPending) {
            shownToast = pendingToast;
            toastPending = false;
            toastShown = true;
            toastUntilNs = nowNs + 2500000000ull;
            if (!toastCanvas) toastCanvas = new Canvas(1200, 160);
            if (!toastLayer) toastLayer = ui_quad_create(1200, 160);
            if (toastLayer) {
                toastCanvas->clear(Color{0, 0, 0, 0});
                {
                    std::lock_guard<std::mutex> g(fontLock);
                    overlay::drawToastOnly(*toastCanvas, g_fonts, shownToast);
                }
                ui_quad_upload(toastLayer, cmd, toastCanvas->data(), 1200 * 4, 0, 0, 1200, 160, true);
            }
        }
    }
    if (!toastShown || !toastLayer) return;
    if (nowNs >= toastUntilNs) { toastShown = false; return; }
    // the toast canvas (1200x160) is centred at the bottom, as drawToast places it in the 1080p frame
    float s = windowScale(h);
    float dst[4] = {(float(w) - 1200.0f * s) * 0.5f, (1080.0f - 36.0f - 20.0f - (shownToast.detail.empty() ? 64.0f : 84.0f)) * s, 1200.0f * s, 160.0f * s};
    float uv[4] = {0, 0, 1, 1};
    ui_quad_draw(toastLayer, cmd, dst, uv, 1.0f);
}

}  // namespace

// ------------------------------------------------------------------------------------------ the game's hooks (as r28)
extern "C" uint32_t za_cheat_spec_before(uint64_t ptr) {
    if (!ptr) return 0;
    auto* p = reinterpret_cast<uint8_t*>(uintptr_t(ptr));
    uint8_t old = p[0x28], next = za::native::cheats::trials(old, shiny.load(std::memory_order_relaxed));
    p[0x28] = next;
    return uint32_t(old) | (uint32_t(next) << 8);
}
extern "C" void za_cheat_spec_after(uint64_t ptr, uint32_t token) {
    if (!ptr) return;
    auto* p = reinterpret_cast<uint8_t*>(uintptr_t(ptr));
    if (p[0x28] == uint8_t(token >> 8)) p[0x28] = uint8_t(token);
    if (shiny.load(std::memory_order_relaxed) == 4) {
        uint32_t tid, pid;
        std::memcpy(&tid, p + 0x18, 4);
        std::memcpy(&pid, p + 0x20, 4);
        uint32_t next = za::native::cheats::shinyPID(tid, pid);
        std::memcpy(p + 0x20, &next, 4);
        specs.fetch_add(next != pid, std::memory_order_relaxed);
    }
}
extern "C" uint32_t za_cheat_capture_score(uint32_t bits, uint64_t ptr) {
    if (!ptr) return bits;
    auto* p = reinterpret_cast<const uint8_t*>(uintptr_t(ptr));
    uint64_t target;
    std::memcpy(&target, p + 0x10, 8);
    auto next = za::native::cheats::captureScore(bits, capture.load(std::memory_order_relaxed), p[0x2e] != 0 || !target);
    if (next != bits) catches.fetch_add(1, std::memory_order_relaxed);
    return next;
}

// ------------------------------------------------------------------------------------------ init (after the run is chosen)
extern "C" void za_cheats_init() {
    std::lock_guard<std::mutex> g(uiLock);
    za_items_reset();
    za_money_lifecycle_reset();
    moneyRequestFailed = false;
    (void)za_hebrew_trial_status();  // one-time disk probe; later reads are cached
    const char* fpsEnv = std::getenv("ZA_PERF_FPS_COUNTER");
    bool fpsDefault = fpsEnv && !std::strcmp(fpsEnv, "1");
    fpsCounter = fpsDefault;
    const char* f60 = std::getenv("ZA_PERF_FORCE60");
    forced60 = f60 && !std::strcmp(f60, "1");
    const char* dyn = std::getenv("ZA_DT_POLICY");
    dynActive = dyn && *dyn;
    if (!fontsLoaded) fontsLoaded = fonts::load(g_fonts);
    if (!panelCanvas) panelCanvas = new Canvas(1920, 1080);
    g_ui = overlay::State{};
    g_ui.open = false;
    loadItemsUi();
    opened = false;
    releaseGate = false;
    held = 0;
    combo = false;
    shiny = 0;
    capture = 0;
    settingsPath.clear();
    saved = true;
    const char* id = std::getenv("LARECOMP_RANDO_SEED");
    std::string run = id ? id : "";
    bool validRun = !run.empty() && run.size() <= 80;
    for (char c : run)
        if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-')) validRun = false;
    if (validRun) {
        settingsPath = platform::runRoot() + "/" + run + "/cheats.txt";
        FILE* f = std::fopen(settingsPath.c_str(), "rb");
        if (f) {
            char text[96] = {0};
            size_t n = std::fread(text, 1, sizeof text - 1, f);
            std::fclose(f);
            text[n] = 0;
            unsigned s = shiny.load(), c = capture.load(), fps = unsigned(fpsCounter.load()), adds = 0;
            bool haveFps = false;
            loadSettingsText(text, s, c, fps, adds, haveFps);
            shiny = s;
            capture = c;
            moneyAdds = adds;
            if (haveFps) fpsCounter = fps != 0;
        }
    }
    platform::log("[za-cheats] native menu ready; L3+R3; defaults OFF; settings scoped to selected run; ui-v2 overlay (tabs, item picker, toasts)"
#ifdef ZA_MONEY_HOOK
                  ", r27 MONEY live-object hook; one request at a time\n"
#else
                  ", MONEY row not available\n"
#endif
    );
    refreshCheatState();
    redrawPanel();
    logSettings();
}

// ------------------------------------------------------------------------------------------ input (UI thread)
extern "C" bool menu_handle_event(const SDL_Event* e) {
    bool wasOpen = opened.load(), wasGate = releaseGate.load();
    if (e->type == SDL_EVENT_GAMEPAD_REMOVED) {
        opened = false; releaseGate = false; held = 0; combo = false;
        std::lock_guard<std::mutex> g(uiLock);
        pad::clear(padState);
        return false;
    }
    if (e->type == SDL_EVENT_GAMEPAD_AXIS_MOTION) {
        if (!wasOpen) return false;
        std::lock_guard<std::mutex> g(uiLock);
        pad::Button pressed;
        if (pad::triggerEvent(padState, e->gaxis.axis, e->gaxis.value, platform::nowMs(), pressed)) handlePress(pressed);
        return true;
    }
    if (e->type != SDL_EVENT_GAMEPAD_BUTTON_DOWN && e->type != SDL_EVENT_GAMEPAD_BUTTON_UP) return false;
    if (e->gbutton.button >= 32) return wasOpen || wasGate;
    uint32_t bit = 1u << e->gbutton.button;
    bool down = e->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN;
    if (down) held |= bit; else held &= ~bit;
    constexpr uint32_t chord = (1u << SDL_GAMEPAD_BUTTON_LEFT_STICK) | (1u << SDL_GAMEPAD_BUTTON_RIGHT_STICK);
    bool nowCombo = (held & chord) == chord;
    if (nowCombo && !combo) {
        std::lock_guard<std::mutex> g(uiLock);
        if (wasOpen) closeMenu();
        else {
            opened = true;
            releaseGate = true;
            g_ui.open = true;
            g_ui.row = 0;
            pad::clear(padState);
            refreshCheatState();
            redrawPanel();
            platform::log("[za-cheats] overlay opened\n");
        }
    }
    combo = nowCombo;
    if (!held) releaseGate = false;
    if (!wasOpen || nowCombo) return wasOpen || wasGate || opened.load();
    std::lock_guard<std::mutex> g(uiLock);
    pad::Button b, pressed;
    if (pad::fromSdlButton(e->gbutton.button, b) && pad::buttonEvent(padState, b, down, platform::nowMs(), pressed)) handlePress(pressed);
    return true;
}

extern "C" bool menu_is_open() { return opened.load(); }
extern "C" bool menu_input_captured() { return opened.load() || releaseGate.load(); }

// The UI thread's tick (runtime/nvn/vulkan/device.c ui_run calls it every loop, ~16 ms): held D-pad repeats, the
// live status rows, the PC proof's scripted presses.
extern "C" void menu_apply_window_requests(void* window) {
    (void)window;
    std::lock_guard<std::mutex> g(uiLock);
    uint64_t nowMs = platform::nowMs();
    if (!overlayScriptLoaded) {
        overlayScriptLoaded = true;
        const char* s = std::getenv("ZA_UI_OVERLAY_SCRIPT");
        if (s && !overlayScript.parse(s)) platform::log("[ui-v2] ZA_UI_OVERLAY_SCRIPT is malformed; ignored\n");
    }
    std::vector<pad::Button> due;
    overlayScript.due(renderer_present_count(), due);
    for (pad::Button b : due) {
        if (!opened.load()) { opened = true; releaseGate = false; g_ui.open = true; g_ui.row = 0; refreshCheatState(); redrawPanel(); platform::log("[za-cheats] overlay opened (script)\n"); }
        handlePress(b);
    }
    if (!opened.load()) return;
    pad::Button pressed;
    while (pad::repeat(padState, nowMs, pressed)) handlePress(pressed);
    if (nowMs - lastPollMs >= 100) {
        lastPollMs = nowMs;
        if (refreshCheatState()) redrawPanel();
    }
}

extern "C" void menu_test_open() {  // LARECOMP_MENU_AT (device.c): opens the menu at a frame (tests)
    std::lock_guard<std::mutex> g(uiLock);
    opened = true;
    g_ui.open = true;
    refreshCheatState();
    redrawPanel();
}

// The launcher's last frame: crossfaded into the game's first frames (ui_quad "fade"), then released.
extern "C" void za_ui_overlay_handoff(UiQuadLayer* layer, const float dst[4]) {
    handoffLayer = layer;
    std::memcpy(handoffDst, dst, sizeof handoffDst);
    handoffStartNs = 0;
    handoffDone = false;
}

// ------------------------------------------------------------------------------------------ render thread
extern "C" void menu_render(void* command, uint32_t w, uint32_t h) {
    if (!command || !w || !h) return;
    uint64_t nowNs = SDL_GetTicksNS();
    static bool announced = false;
    if (!announced) {
        announced = true;
        platform::logf("[ui-v2] overlay: first game frame presented at t=%.3f s (window %ux%u)\n", double(nowNs) / 1e9, w, h);
    }
    // 1. the launcher's frame fading into the game (400 ms), only after the launcher handed one over
    if (handoffLayer && !handoffDone) {
        if (!handoffStartNs) handoffStartNs = nowNs;
        float t = float(double(nowNs - handoffStartNs) / 0.4e9);
        if (t >= 1.0f) { handoffDone = true; platform::log("[ui-v2] launcher frame faded out\n"); }
        else {
            float dst[4];
            float sx = float(w) / 1920.0f, sy = float(h) / 1080.0f, s = sx < sy ? sx : sy;
            dst[2] = 1920.0f * s; dst[3] = 1080.0f * s; dst[0] = (float(w) - dst[2]) * 0.5f; dst[1] = (float(h) - dst[3]) * 0.5f;
            static const float uv[4] = {0, 0, 1, 1};
            ui_quad_draw(handoffLayer, command, dst, uv, 1.0f - t);
        }
    }
    // 2. items landing while the menu is closed: "Rare Candy ×99 added"
    unsigned applied = za_items_applied();
    std::string status = za_items_status();
    if (applied != lastApplied) {
        if (applied > lastApplied) {
            const unsigned requestedItem = lastRequestedItem.load(std::memory_order_relaxed);
            const items::Item* it = requestedItem < items::catalog().size() ? &items::catalog()[requestedItem] : nullptr;
            unsigned count = za_items_last_count();
            requestToast(Toast::Ok, std::string(it ? it->name : "Item") + " added", "Now " + u2s(count) + " in the bag; save in the game to keep it");
        }
        lastApplied = applied;
    } else if (status != lastItemStatus && (status.rfind("ITEM / POCKET FULL", 0) == 0 || status.rfind("ITEM UNAVAILABLE", 0) == 0 || status.rfind("REQUEST REJECTED", 0) == 0)) {
        requestToast(Toast::Err, status.rfind("ITEM / POCKET FULL", 0) == 0 ? "Pocket full" : status, "");
    }
    lastItemStatus = status;
    // 3. the panel
    if (opened.load()) {
        if (!panelLayer) panelLayer = ui_quad_create(1920, 1080);
        uint32_t gen = publishedGen.load(std::memory_order_acquire);
        if (panelLayer && gen != uploadedGen) {
            std::lock_guard<std::mutex> g(pubLock);
            if (published.size() == size_t(1920) * 1080 * 4) {
                ui_quad_upload(panelLayer, command, published.data(), 1920 * 4, 0, 0, 1920, 1080, true);
                uploadedGen = gen;
            }
        }
        if (panelLayer && uploadedGen) {
            float sx = float(w) / 1920.0f, sy = float(h) / 1080.0f, s = sx < sy ? sx : sy;
            float dst[4] = {(float(w) - 1920.0f * s) * 0.5f, (float(h) - 1080.0f * s) * 0.5f, 1920.0f * s, 1080.0f * s};
            static const float uv[4] = {0, 0, 1, 1};
            ui_quad_draw(panelLayer, command, dst, uv, 1.0f);
        }
    }
    // 4. the FPS readout (own layer, uploaded when its text changes)
    if (fpsCounter.load(std::memory_order_relaxed)) {
        readout.tick();
        drawReadoutLayer(command, w, h);
    }
    // 5. toasts (own layer)
    drawToastLayer(command, w, h, nowNs);
}

#ifdef ZA_UI_HOST_TEST  // host test hooks (test/test_overlay_glue.cpp)
extern "C" void za_cheats_test_load(const char* text, unsigned* s, unsigned* c, unsigned* fps, unsigned* adds, bool* haveFps) { loadSettingsText(text, *s, *c, *fps, *adds, *haveFps); }
extern "C" int za_cheats_test_tab() { std::lock_guard<std::mutex> g(uiLock); return g_ui.tab; }
extern "C" int za_cheats_test_row() { std::lock_guard<std::mutex> g(uiLock); return g_ui.row; }
extern "C" unsigned za_cheats_test_shiny() { return shiny.load(); }
extern "C" unsigned za_cheats_test_capture() { return capture.load(); }
extern "C" bool za_cheats_test_fps() { return fpsCounter.load(); }
extern "C" unsigned za_cheats_test_published_gen() { return publishedGen.load(); }
extern "C" const char* za_cheats_test_picker_current() { std::lock_guard<std::mutex> g(uiLock); const items::Item* it = g_ui.picker.current(); return it ? it->name : ""; }
extern "C" unsigned za_cheats_test_picker_amount() { std::lock_guard<std::mutex> g(uiLock); const auto& v = g_ui.picker.visible(); return v.empty() ? 0 : g_ui.picker.amount(v[size_t(g_ui.picker.cursor())]); }
extern "C" bool za_cheats_test_toast(char* text, size_t cap) {
    std::lock_guard<std::mutex> g(toastLock);
    if (!toastPending && !toastShown) return false;
    std::snprintf(text, cap, "%s", (toastPending ? pendingToast : shownToast).text.c_str());
    return true;
}
extern "C" const uint8_t* za_cheats_test_published(size_t* bytes) { *bytes = published.size(); return published.data(); }
#endif
