// ui-v2: launcher_run() - the randomizer launcher INSIDE the game's Vulkan window (the design's option C).
//
// runtime/main.c calls launcher_run(root) before boot() when the start screen is on (LARECOMP_PS5_LAUNCHER=1 keeps it
// on for Z-A: port/ui-v2/tools/apply-runtime-launcher.py). This opens the window, the Vulkan device and the swapchain
// once (device.c ui_window_init, as the desktop launcher.mm does), then draws the launcher's 1920x1080 canvas as one
// quad per frame (ui_quad) while the controller (launcher_core) runs the menu. On a selection it sets
// LARECOMP_RANDO_SEED, hands its last frame to the overlay (which crossfades it into the game's first frames) and
// returns: boot() loads the game into the same window - no VideoOut teardown, no black screen.
//
// Replaces port/rando-music/native_menu_music.cpp (bootMenu + Display). The title's title_entry (title_entry_uiv2.c)
// no longer calls za_randomizer_boot; za_cheats_init runs here, after the run is chosen.
#include <SDL3/SDL.h>

#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fcntl.h>
#include <string>
#include <sys/stat.h>
#include <unistd.h>

#include "fonts_embedded.h"
#include "launcher_core.h"
#include "run_store.hpp"
#include "ui_canvas.h"
#include "ui_launcher.h"
#include "ui_pad.h"
#include "ui_platform.h"
#include "ui_quad.h"
#include "ui_widgets.h"
#ifndef ZA_PS5
#include "png_write.h"
#endif

extern "C" {
// runtime/nvn/vulkan/device.c
void ui_window_init(void);
SDL_Window* ui_window(void);
bool vk_frame_begin(const float clear[4]);
void vk_frame_end(const char* shot_path);
void* vk_frame_cmd(void);
// port/observer-r17 (r28: linked through hebrew_trial's --wrap=za_observer_menu)
bool za_observer_menu(const char* active_run);
// overlay_ps5.cpp
void za_cheats_init(void);
void za_ui_overlay_handoff(UiQuadLayer* layer, const float dst[4]);
}

namespace {

#ifdef ZA_PS5
// The initial PS5 pipeline cache (as native_menu_music.cpp did; the device is created right after this, so it must
// run before ui_window_init). access() is refused for native titles, even for existing files.
void seedPipelineCache() {
    const std::string target = "/download0/zarecomp/cache/vk_pipelines.bin";
    struct stat existing {};
    if (!stat(target.c_str(), &existing) || errno != ENOENT) return;
    za::Bytes bytes;
    if (!za::native::readFile("/app0/cache/vk_pipelines.bin", bytes, 256u << 20) || bytes.size() < 32) return;
    if (!za::native::makeDirs("/download0/zarecomp/cache")) return;
    const auto temp = target + ".initial";
    int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_EXCL, 0644);
    if (fd < 0) return;
    size_t at = 0;
    bool ok = true;
    while (at < bytes.size()) {
        ssize_t n = write(fd, bytes.data() + at, bytes.size() - at);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) { ok = false; break; }
        at += size_t(n);
    }
    if (ok && fsync(fd)) ok = false;
    if (close(fd)) ok = false;
    za::Bytes check;
    if (ok && za::native::readFile(temp, check, 256u << 20) && check == bytes && !rename(temp.c_str(), target.c_str()))
        ui::platform::log("[za-randomizer] initial PS5 pipeline cache copied; runtime will validate its device UUID\n");
}
#endif

void setEnv(const char* name, const char* value) {
#ifdef ZA_PS5
    setenv(name, value, 1);
#else
    SDL_setenv_unsafe(name, value, 1);
#endif
}
void unsetEnv(const char* name) {
#ifdef ZA_PS5
    unsetenv(name);
#else
    SDL_unsetenv_unsafe(name);
#endif
}

// The 16:9 canvas fitted into the window (letterboxed when the window is not 16:9).
void fitCanvas(int w, int h, float dst[4]) {
    float sx = float(w) / 1920.0f, sy = float(h) / 1080.0f, s = sx < sy ? sx : sy;
    dst[2] = 1920.0f * s;
    dst[3] = 1080.0f * s;
    dst[0] = (float(w) - dst[2]) * 0.5f;
    dst[1] = (float(h) - dst[3]) * 0.5f;
}

ui::Fonts g_fonts;
bool g_fontsLoaded = false;
UiQuadLayer* g_layer = nullptr;  // lives for the process (also across an in-place reboot back to the launcher)

}  // namespace

extern "C" void launcher_run(const char* root) {
    using namespace ui;
    platform::logf("[ui-v2] launcher starting inside the game window (root %s)\n", root ? root : "");
#ifdef ZA_PS5
    seedPipelineCache();
#endif
    ui_window_init();  // window + instance + surface + device + swapchain, once; the game uses the same
    SDL_Window* win = ui_window();
    if (!g_fontsLoaded) g_fontsLoaded = fonts::load(g_fonts);
    if (!g_fontsLoaded) platform::log("[ui-v2] embedded fonts failed to load\n");
    static Canvas canvas(1920, 1080);
    if (!g_layer) g_layer = ui_quad_create(1920, 1080);
    if (!g_layer) platform::log("[ui-v2] launcher layer could not be created; the launcher runs blind\n");

    launcher::Paths paths;
    paths.runRoot = platform::runRoot();
    paths.assets = platform::assetsDir();
    paths.gameImage = platform::gameImage(root);
    paths.repairStage = platform::repairStage();
    paths.buildLabel = ZA_UI_BUILD_LABEL;
    launcher::Platform plat;
    plat.log = platform::log;
    plat.freshSeed = platform::freshSeed;
    plat.observerContinue = za_observer_menu;
    plat.unixTime = platform::unixTime;
    plat.random32 = platform::random32;
    launcher::Controller ctl(paths, plat);
    if (!ctl.init()) platform::log("[ui-v2] launcher init failed; showing the error screen\n");

    pad::State pad;
    pad::Script script;
    const char* scriptEnv = std::getenv("ZA_UI_SCRIPT");  // PC proof: "frame:BUTTON,..." (launcher frames)
    if (scriptEnv && !script.parse(scriptEnv)) platform::log("[ui-v2] ZA_UI_SCRIPT is malformed; ignored\n");
    const char* shotDir = std::getenv("ZA_UI_SHOT_DIR");
    const char* shotFrames = std::getenv("ZA_UI_SHOT_FRAMES");  // "12,40,..." (launcher frames): window PNG + canvas PNG
    static const float black[4] = {0.043f, 0.082f, 0.141f, 1};  // Bg0, so a frame without the quad still matches
    uint64_t frame = 0, nextFrameNs = 0;
    const uint64_t periodNs = 16666667;
    bool uploaded = false;
    float dst[4] = {0, 0, 1920, 1080};
    int lastW = 0, lastH = 0;
    while (!ctl.done()) {
        uint64_t nowMs = platform::nowMs();
        SDL_Event e;
        pad::Button pressed;
        while (SDL_PollEvent(&e)) {
            if (e.type == SDL_EVENT_QUIT) { platform::log("window closed\n"); exit(0); }
            if (e.type == SDL_EVENT_GAMEPAD_REMOVED) pad::clear(pad);
            if (e.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN || e.type == SDL_EVENT_GAMEPAD_BUTTON_UP) {
                pad::Button b;
                if (pad::fromSdlButton(e.gbutton.button, b) && pad::buttonEvent(pad, b, e.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN, nowMs, pressed))
                    ctl.press(pressed);
            } else if (e.type == SDL_EVENT_GAMEPAD_AXIS_MOTION) {
                if (pad::triggerEvent(pad, e.gaxis.axis, e.gaxis.value, nowMs, pressed)) ctl.press(pressed);
            }
#ifndef ZA_PS5
            else if (e.type == SDL_EVENT_KEY_DOWN && !e.key.repeat) {  // keyboard on the PC: arrows, Enter, Backspace...
                pad::Button b;
                bool ok = true;
                switch (e.key.key) {
                    case SDLK_UP: b = pad::Button::Up; break;
                    case SDLK_DOWN: b = pad::Button::Down; break;
                    case SDLK_LEFT: b = pad::Button::Left; break;
                    case SDLK_RIGHT: b = pad::Button::Right; break;
                    case SDLK_RETURN: b = pad::Button::Cross; break;
                    case SDLK_BACKSPACE: b = pad::Button::Square; break;
                    case SDLK_ESCAPE: b = pad::Button::Circle; break;
                    case SDLK_TAB: b = pad::Button::Triangle; break;
                    case SDLK_PAGEUP: b = pad::Button::L1; break;
                    case SDLK_PAGEDOWN: b = pad::Button::R1; break;
                    default: ok = false;
                }
                if (ok) ctl.press(b);
            }
#endif
        }
        if (pad::repeat(pad, nowMs, pressed)) ctl.press(pressed);
        std::vector<pad::Button> due;
        script.due(frame, due);
        for (pad::Button b : due) ctl.press(b);
        ctl.tick(nowMs);
        if (ctl.done()) break;
        if (ctl.dirty() && g_fontsLoaded) {
            launcher::draw(canvas, g_fonts, ctl.state());
            ctl.clearDirty();
            uploaded = false;
        }
        // one frame per display refresh (the swapchain may be mailbox: the loop alone would spin)
        uint64_t nowNs = SDL_GetTicksNS();
        if (nextFrameNs > nowNs && nextFrameNs - nowNs <= periodNs) SDL_DelayNS(nextFrameNs - nowNs);
        nowNs = SDL_GetTicksNS();
        nextFrameNs = (nextFrameNs > nowNs - periodNs && nextFrameNs <= nowNs + periodNs ? nextFrameNs : nowNs) + periodNs;
        if (!uploaded && g_layer) {
            ui_quad_upload(g_layer, vk_frame_cmd(), canvas.data(), uint32_t(canvas.width()) * 4, 0, 0, canvas.width(), canvas.height(), false);
            uploaded = true;
        }
        if (!vk_frame_begin(black)) { SDL_Delay(16); continue; }
        int w = 0, h = 0;
        SDL_GetWindowSizeInPixels(win, &w, &h);
        if (w != lastW || h != lastH) {
            fitCanvas(w, h, dst);
            lastW = w;
            lastH = h;
            platform::logf("[ui-v2] launcher canvas 1920x1080 -> window %dx%d at %.0f,%.0f %.0fx%.0f\n", w, h, dst[0], dst[1], dst[2], dst[3]);
        }
        static const float uv[4] = {0, 0, 1, 1};
        if (g_layer) ui_quad_draw(g_layer, vk_frame_cmd(), dst, uv, 1.0f);
        const char* shot = nullptr;
        char shotPath[512];
        if (shotDir && shotFrames) {
            for (const char* p = shotFrames; *p;) {
                char* end;
                long at = std::strtol(p, &end, 10);
                if (end == p) break;
                if (at == long(frame)) {
                    std::snprintf(shotPath, sizeof shotPath, "%s/launcher-window-%05ld.png", shotDir, at);
                    shot = shotPath;
#ifndef ZA_PS5
                    char canvasPath[512];
                    std::snprintf(canvasPath, sizeof canvasPath, "%s/launcher-canvas-%05ld.png", shotDir, at);
                    auto rgba = canvas.toStraightRGBA();
                    writePng(canvasPath, rgba.data(), canvas.width(), canvas.height());
#endif
                }
                p = *end == ',' ? end + 1 : end;
            }
        }
        vk_frame_end(shot);
        frame++;
    }
    const std::string selected = ctl.selectedRun();
    setEnv("LARECOMP_RANDO_SEED", selected.c_str());
    unsetEnv("LARECOMP_SAVE_DIR");  // the run's own save folder (runtime/rando.c)
    platform::logf("[ui-v2] launcher done after %llu frames: run %s%s; summary: %s\n", (unsigned long long)frame, selected.c_str(),
                   ctl.createdRun().empty() ? " (continued)" : " (created)", ctl.selectedSummary().c_str());
    // the last frame stays on screen (nothing presents until the game's first frame) and then crossfades into it
    if (g_layer) za_ui_overlay_handoff(g_layer, dst);
    za_cheats_init();  // reads the run's cheats.txt (LARECOMP_RANDO_SEED is set now)
    platform::logf("[ui-v2] handing the window to the game at t=%.3f s\n", double(SDL_GetTicksNS()) / 1e9);
    const char* exitAfter = std::getenv("ZA_UI_EXIT_AFTER_LAUNCHER");  // PC proof of the launcher alone
    if (exitAfter && *exitAfter == '1') { std::fflush(stderr); exit(0); }
}
