// ui-v2 host test of the REAL overlay glue (src/overlay_ps5.cpp, -DZA_UI_HOST_TEST) with the stubs of
// port/perf-r28/test-menu.cpp for the game-side helpers and a recording stub of ui_quad: the L3+R3 chord, tabs, the
// item picker's request through za_items_request (and the one-request-at-a-time rule), cheats.txt v2 persistence and
// the hooks' arithmetic, FPS trial / Hebrew rows, favourites persistence, the render path's upload-when-dirty.
// Usage: test_overlay_glue <new temp data root>
#include <SDL3/SDL.h>

#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>

#include "za_items.h"

static int failures = 0;
#define CHECK(cond)                                                               \
    do {                                                                          \
        if (!(cond)) {                                                            \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                                           \
        }                                                                         \
    } while (0)

// ---- stubs of the console-side helpers (as port/perf-r28/test-menu.cpp)
static unsigned requests, indexValue, amountValue, hebrewRequests, performanceRequests, performanceArg;
static bool pending, ready = true;
static unsigned applied;
static const ZaItem items[] = {
#include "items.inc"
};
static uint64_t ticks = 1000000000ull, presented = 1;
extern "C" {
uint64_t renderer_present_count() { return presented; }
int za_performance_status() { return 0; }
void za_performance_request(int t) { ++performanceRequests; performanceArg = unsigned(t); }
Uint64 SDL_GetTicksNS() { return ticks; }
unsigned za_items_count() { return sizeof(items) / sizeof(items[0]); }
const ZaItem* za_items_at(unsigned i) { return i < za_items_count() ? &items[i] : nullptr; }
int za_items_request(unsigned i, unsigned a) { if (pending || !ready) return 0; ++requests; indexValue = i; amountValue = a; pending = true; return 1; }
void za_items_reset() { pending = false; }
int za_items_ready() { return ready; }
int za_items_pending() { return pending; }
const char* za_items_status() { return pending ? "QUEUED - OPEN BAG" : ready ? "READY" : "OPEN THE BAG FIRST"; }
unsigned za_items_last_count() { return 99; }
unsigned za_items_applied() { return applied; }
int za_hebrew_trial_status() { return 1; }
int za_hebrew_trial_request() { ++hebrewRequests; return 1; }
// ui_quad recording stub
struct UiQuadLayer { uint32_t w, h; };
static unsigned quadCreates, quadUploads, quadDraws;
static float lastAlpha = 1;
static float lastFadeAlpha = 1;
UiQuadLayer* ui_quad_create(uint32_t w, uint32_t h) { quadCreates++; return new UiQuadLayer{w, h}; }
uint32_t ui_quad_width(const UiQuadLayer* l) { return l->w; }
uint32_t ui_quad_height(const UiQuadLayer* l) { return l->h; }
void ui_quad_upload(UiQuadLayer*, void* cmd, const uint8_t* rgba, uint32_t stride, int x, int y, int w, int h, bool inside) {
    CHECK(cmd && rgba && stride >= uint32_t(w) * 4 && x >= 0 && y >= 0 && w > 0 && h > 0 && inside);
    quadUploads++;
}
void ui_quad_draw(UiQuadLayer*, void* cmd, const float dst[4], const float uv[4], float alpha) {
    CHECK(cmd && dst[2] > 0 && dst[3] > 0 && uv[2] > uv[0] && uv[3] > uv[1]);
    lastAlpha = alpha;
    if (alpha < 1.0f) lastFadeAlpha = alpha;
    quadDraws++;
}
uint64_t ui_quad_upload_count() { return quadUploads; }
uint64_t ui_quad_draw_count() { return quadDraws; }
// the module under test
void za_cheats_init();
bool menu_handle_event(const SDL_Event*);
bool menu_is_open();
bool menu_input_captured();
void menu_apply_window_requests(void*);
void menu_render(void*, uint32_t, uint32_t);
void menu_test_open();
void za_ui_overlay_handoff(UiQuadLayer*, const float dst[4]);
uint32_t za_cheat_spec_before(uint64_t);
void za_cheat_spec_after(uint64_t, uint32_t);
uint32_t za_cheat_capture_score(uint32_t, uint64_t);
void za_cheats_test_load(const char*, unsigned*, unsigned*, unsigned*, unsigned*, bool*);
int za_cheats_test_tab();
int za_cheats_test_row();
unsigned za_cheats_test_shiny();
unsigned za_cheats_test_capture();
bool za_cheats_test_fps();
unsigned za_cheats_test_published_gen();
const char* za_cheats_test_picker_current();
unsigned za_cheats_test_picker_amount();
bool za_cheats_test_toast(char*, size_t);
const uint8_t* za_cheats_test_published(size_t*);
}

static void button(int b, bool down) {
    SDL_Event e{};
    e.type = down ? SDL_EVENT_GAMEPAD_BUTTON_DOWN : SDL_EVENT_GAMEPAD_BUTTON_UP;
    e.gbutton.button = Uint8(b);
    menu_handle_event(&e);
    ticks += 20000000;  // 20 ms between events: no repeat kicks in
}
static void press(int b) { button(b, true); button(b, false); }
static std::string toast() { char t[256]; return za_cheats_test_toast(t, sizeof t) ? t : ""; }
static std::string readText(const std::string& p) { std::ifstream in(p, std::ios::binary); std::stringstream ss; ss << in.rdbuf(); return ss.str(); }

int main(int argc, char** argv) {
    if (argc != 2) { std::fprintf(stderr, "usage: test_overlay_glue <new data root>\n"); return 2; }
    std::string root = argv[1];
    mkdir(root.c_str(), 0755);
    mkdir((root + "/rando").c_str(), 0755);
    mkdir((root + "/rando/r0000000000000001-00000001").c_str(), 0755);
    { std::ofstream f(root + "/rando/r0000000000000001-00000001/cheats.txt", std::ios::binary); f << "za-cheats-v2\n2 1 0 0\n"; }
    setenv("ZA_UI_DATA_ROOT", root.c_str(), 1);
    setenv("LARECOMP_RANDO_SEED", "r0000000000000001-00000001", 1);
    setenv("ZA_PERF_FPS_COUNTER", "1", 1);
    unsetenv("ZA_UI_OVERLAY_SCRIPT");

    // settings file parsing (v1 and v2, malformed)
    {
        unsigned s = 9, c = 9, fps = 9, adds = 9; bool haveFps = true;
        za_cheats_test_load("za-cheats-v1\n3 4", &s, &c, &fps, &adds, &haveFps);
        CHECK(s == 3 && c == 4 && !haveFps);
        za_cheats_test_load("za-cheats-v2\n1 2 1 7\n", &s, &c, &fps, &adds, &haveFps);
        CHECK(s == 1 && c == 2 && fps == 1 && adds == 7 && haveFps);
        za_cheats_test_load("garbage", &s, &c, &fps, &adds, &haveFps);
        CHECK(s == 1 && c == 2);
    }
    za_cheats_init();
    CHECK(za_cheats_test_shiny() == 2 && za_cheats_test_capture() == 1 && !za_cheats_test_fps());  // from the run's cheats.txt
    CHECK(!menu_is_open() && !menu_input_captured());
    // the hooks: 4x rolls (mode 2 -> x16 in trials): original 1 -> 16; capture mode 1 doubles the score
    {
        uint8_t spec[0x30] = {0};
        spec[0x28] = 1;
        uint32_t token = za_cheat_spec_before(uint64_t(uintptr_t(spec)));
        CHECK(spec[0x28] == 16 && (token & 0xff) == 1 && (token >> 8) == 16);
        za_cheat_spec_after(uint64_t(uintptr_t(spec)), token);
        CHECK(spec[0x28] == 1);
        float score = 10.0f; uint32_t bits; std::memcpy(&bits, &score, 4);
        uint8_t target[0x30] = {0};
        uint64_t one = 1; std::memcpy(target + 0x10, &one, 8);
        uint32_t out = za_cheat_capture_score(bits, uint64_t(uintptr_t(target)));
        float scored; std::memcpy(&scored, &out, 4);
        CHECK(scored == 20.0f);
    }
    // L3+R3 opens; events while open are captured; the chord again closes
    button(SDL_GAMEPAD_BUTTON_LEFT_STICK, true);
    button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, true);
    CHECK(menu_is_open() && menu_input_captured());
    button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, false);
    button(SDL_GAMEPAD_BUTTON_LEFT_STICK, false);
    CHECK(menu_is_open());
    unsigned gen0 = za_cheats_test_published_gen();
    CHECK(gen0 > 0);
    // render: the panel is uploaded once per published generation, drawn every frame; the readout too
    void* cmd = &failures;  // any non-null command buffer
    menu_render(cmd, 3840, 2160);
    presented++;
    unsigned uploads1 = quadUploads, draws1 = quadDraws;
    CHECK(uploads1 >= 1 && draws1 >= 1);
    menu_render(cmd, 3840, 2160);
    presented++;
    CHECK(quadUploads == uploads1 && quadDraws > draws1);  // nothing changed: no new upload
    // tabs: R1 -> All items; three more -> Other items; Rare Candy is the 6th row; x99; Cross requests it
    press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER);
    CHECK(za_cheats_test_tab() == 1);
    press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER); press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER); press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER);
    CHECK(za_cheats_test_tab() == 4);
    for (int i = 0; i < 5; i++) press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);
    CHECK(std::string(za_cheats_test_picker_current()) == "Rare Candy");
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT); press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    CHECK(za_cheats_test_picker_amount() == 99);
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(requests == 1 && indexValue == 9 && amountValue == 99 && pending);
    CHECK(toast() == "Rare Candy \xC3\x97" "99 queued");
    CHECK(za_cheats_test_published_gen() > gen0);
    // a second Cross while queued: no new request, a "still queued" toast
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(requests == 1 && toast() == "Still queued");
    // the pump lands the item (closed or open): the toast names it
    pending = false; applied = 1;
    menu_render(cmd, 3840, 2160);
    presented++;
    CHECK(toast() == "Rare Candy added");
    // favourites persist to the global items-ui.txt
    press(SDL_GAMEPAD_BUTTON_WEST);
    std::string itemsUi = readText(root + "/rando/items-ui.txt");
    CHECK(itemsUi.rfind("za-items-ui-v1\n", 0) == 0 && itemsUi.find("fav 50") != std::string::npos && itemsUi.find("recent 50") != std::string::npos);
    // the hold-to-repeat tick: holding Down for 500 ms moves at least once more
    press(SDL_GAMEPAD_BUTTON_DPAD_UP);
    std::string before = za_cheats_test_picker_current();
    button(SDL_GAMEPAD_BUTTON_DPAD_DOWN, true);
    ticks += 600000000ull;
    menu_apply_window_requests(nullptr);
    button(SDL_GAMEPAD_BUTTON_DPAD_DOWN, false);
    CHECK(std::string(za_cheats_test_picker_current()) != before);
    // back to Cheats: L1 four times; shiny Right -> 3 (64x) and cheats.txt rewritten; Reset -> both Normal
    for (int i = 0; i < 4; i++) press(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER);
    CHECK(za_cheats_test_tab() == 0 && za_cheats_test_row() == 0);
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    CHECK(za_cheats_test_shiny() == 3);
    CHECK(readText(root + "/rando/r0000000000000001-00000001/cheats.txt") == "za-cheats-v2\n3 1 0 0\n");
    // FPS counter row (3): toggles and persists
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(za_cheats_test_fps() && readText(root + "/rando/r0000000000000001-00000001/cheats.txt") == "za-cheats-v2\n3 1 1 0\n");
    // FPS trial row (4): Cross requests the 60 trial
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(performanceRequests == 1 && performanceArg == 1);
    // Reset row (6): both Normal
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(za_cheats_test_shiny() == 0 && za_cheats_test_capture() == 0);
    CHECK(readText(root + "/rando/r0000000000000001-00000001/cheats.txt") == "za-cheats-v2\n0 0 1 0\n");
    // Hebrew row (5): Cross requests and closes the menu
    press(SDL_GAMEPAD_BUTTON_DPAD_UP); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(hebrewRequests == 1 && !menu_is_open());
    // Circle closes an open menu; the published canvas is 1920x1080 RGBA
    menu_test_open();
    CHECK(menu_is_open());
    press(SDL_GAMEPAD_BUTTON_EAST);
    CHECK(!menu_is_open());
    size_t bytes = 0;
    CHECK(za_cheats_test_published(&bytes) && bytes == size_t(1920) * 1080 * 4);
    // the launcher's handoff frame fades over 400 ms: alpha falls, then the layer is released
    UiQuadLayer handoff{1920, 1080};
    float dst[4] = {0, 0, 3840, 2160};
    za_ui_overlay_handoff(&handoff, dst);
    unsigned drawsBefore = quadDraws;
    menu_render(cmd, 3840, 2160);
    CHECK(quadDraws > drawsBefore && lastAlpha > 0.99f);
    ticks += 200000000ull;
    drawsBefore = quadDraws;
    menu_render(cmd, 3840, 2160);
    CHECK(lastFadeAlpha > 0.4f && lastFadeAlpha < 0.6f);
    ticks += 300000000ull;
    menu_render(cmd, 3840, 2160);
    drawsBefore = quadDraws;
    menu_render(cmd, 3840, 2160);
    CHECK(quadDraws - drawsBefore <= 2);  // only the readout (and no toast) draw now
    // the scripted presses of the PC proof open the menu at a presented frame
    setenv("ZA_UI_OVERLAY_SCRIPT", "1:R1", 1);
    if (failures) { std::fprintf(stderr, "%d check(s) failed\n", failures); return 1; }
    std::puts("PASS: overlay glue (chord, tabs, picker request + one-at-a-time, toasts incl. landed item, favourites file, repeat, cheats.txt v2, hooks, FPS/Hebrew/Reset rows, render upload-when-dirty, handoff fade)");
    return 0;
}
