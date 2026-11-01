// Host test of port/perf-r26/cheats-r26.cpp: the settings file (v1 / v2), the FPS readout math, the text width, and
// the menu rows (FPS COUNTER toggle, MONEY disabled, RESET as before). Built by test.sh with -DZA_CHEATS_HOST_TEST
// against the SDL3 shim headers and Mesa's vulkan.h; the Vulkan / SDL / console calls are stubbed here.
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
static int performanceMode, performanceRequests, lastPerformanceRequest=-1;
extern "C" {
int sceKernelDebugOutText(int, const char *t) { fputs(t, stdout); return 0; }
uint64_t renderer_present_count(void) { return 0; }
int za_performance_status(void) { return performanceMode; }
void za_performance_request(int trial) { ++performanceRequests;lastPerformanceRequest=trial;performanceMode=trial?1:0; }
Uint64 SDL_GetTicksNS(void) { return 0; }
void vkCmdClearAttachments(VkCommandBuffer, uint32_t, const VkClearAttachment *, uint32_t, const VkClearRect *) {}
void za_cheats_test_load(const char *, unsigned *, unsigned *, unsigned *, unsigned *, bool *);
unsigned za_cheats_test_fps_x10(unsigned, uint64_t);
unsigned za_cheats_test_ms_x10(unsigned, uint64_t);
int za_cheats_test_text_width(const char *, int);
bool menu_handle_event(const SDL_Event *);
bool menu_is_open(void);
void menu_test_open(void);
void menu_render(void *, uint32_t, uint32_t);
void za_cheats_init(void);
}
static int fails;
#define CHECK(x) do { if (!(x)) { printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #x); fails++; } } while (0)
static void load(const char *text, unsigned es, unsigned ec, unsigned efps, unsigned eadds, bool ehave) {
    unsigned s = 9, c = 9, fps = 7, adds = 0; bool have = true;
    za_cheats_test_load(text, &s, &c, &fps, &adds, &have);
    CHECK(s == es); CHECK(c == ec); CHECK(fps == efps); CHECK(adds == eadds); CHECK(have == ehave);
}
static SDL_Event button(int b, bool down) {
    SDL_Event e; memset(&e, 0, sizeof e);
    e.type = down ? SDL_EVENT_GAMEPAD_BUTTON_DOWN : SDL_EVENT_GAMEPAD_BUTTON_UP; e.gbutton.button = (Uint8)b; return e;
}
static void press(int b) { SDL_Event d = button(b, true), u = button(b, false); menu_handle_event(&d); menu_handle_event(&u); }
int main() {
    // settings file: v1 keeps two fields and leaves the FPS default; v2 reads three or four; bad values change nothing
    load("za-cheats-v1\n3 2\n", 3, 2, 7, 0, false);
    load("za-cheats-v1\n9 2\n", 9, 9, 7, 0, false);
    load("za-cheats-v2\n1 4 1 12\n", 1, 4, 1, 12, true);
    load("za-cheats-v2\n1 4 0\n", 1, 4, 0, 0, true);
    load("za-cheats-v2\n1 4\n", 1, 4, 7, 0, false);
    load("za-cheats-v2\n1 4 5 2\n", 1, 4, 7, 2, false);   // fps out of range: ignored, the other fields kept
    load("garbage\n", 9, 9, 7, 0, false);
    load("", 9, 9, 7, 0, false);
    // readout math: 15 frames in 250 ms -> 60.0 FPS, 16.7 ms; 15 frames in 312.5 ms -> 48.0 FPS, 20.8 ms
    CHECK(za_cheats_test_fps_x10(15, 250000000ull) == 600);
    CHECK(za_cheats_test_ms_x10(15, 250000000ull) == 167);
    CHECK(za_cheats_test_fps_x10(15, 312500000ull) == 480);
    CHECK(za_cheats_test_ms_x10(15, 312500000ull) == 208);
    CHECK(za_cheats_test_fps_x10(15, 125000000ull) == 1200);  // 120 FPS
    CHECK(za_cheats_test_ms_x10(15, 125000000ull) == 83);
    // text width: 6 cells a glyph minus the trailing gap; '.' is 3 cells
    CHECK(za_cheats_test_text_width("60 FPS", 3) == 6 * 6 * 3 - 3);
    CHECK(za_cheats_test_text_width("16.7 MS", 2) == (6 * 6 + 3) * 2 - 2);
    CHECK(za_cheats_test_text_width("", 2) == 0);
    // The real menu must reach the existing trial API; FPS COUNTER and MONEY cannot arm it.
    CHECK(!menu_is_open());
    { SDL_Event l = button(SDL_GAMEPAD_BUTTON_LEFT_STICK, true), r = button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, true);
      menu_handle_event(&l); menu_handle_event(&r);
      SDL_Event lu = button(SDL_GAMEPAD_BUTTON_LEFT_STICK, false), ru = button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, false);
      menu_handle_event(&lu); menu_handle_event(&ru); }
    CHECK(menu_is_open());
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);           // SHINY -> 4X ROLLS
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // CAPTURE
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);           // CAPTURE -> 2X SCORE
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // MONEY (not available): no effect
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // FPS COUNTER
    press(SDL_GAMEPAD_BUTTON_SOUTH);                // -> ON
    menu_render(nullptr, 3840, 2160);               // draws the readout and the menu with the stubbed clear
    press(SDL_GAMEPAD_BUTTON_SOUTH);                // -> OFF
    CHECK(performanceRequests==0);
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // FPS TRIAL
    press(SDL_GAMEPAD_BUTTON_DPAD_LEFT);press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    CHECK(performanceRequests==0);                  // only X arms the trial
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(performanceRequests==1&&lastPerformanceRequest==1&&performanceMode==1);
    menu_render(nullptr,3840,2160);
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(performanceRequests==2&&lastPerformanceRequest==0&&performanceMode==0);
    performanceMode=2;                              // r16 automatically fell back: X must allow a fresh trial
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(performanceRequests==3&&lastPerformanceRequest==1&&performanceMode==1);
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(performanceRequests==4&&lastPerformanceRequest==0&&performanceMode==0);
    unsetenv("LARECOMP_RANDO_SEED");                // settings writes are never needed for a session-only trial
    setenv("ZA_DT_POLICY","safe",1);za_cheats_init();
    press(SDL_GAMEPAD_BUTTON_SOUTH);CHECK(performanceRequests==4);
    unsetenv("ZA_DT_POLICY");setenv("ZA_PERF_FORCE60","1",1);za_cheats_init();
    press(SDL_GAMEPAD_BUTTON_SOUTH);CHECK(performanceRequests==4);
    unsetenv("ZA_PERF_FORCE60");za_cheats_init();
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // RESET BOTH TO NORMAL
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);            // wraps to SHINY
    press(SDL_GAMEPAD_BUTTON_DPAD_UP);              // back to RESET (6 rows)
    press(SDL_GAMEPAD_BUTTON_EAST);                 // close
    CHECK(!menu_is_open());
    menu_render(nullptr, 1920, 1080);               // closed: nothing drawn (readout off)
    printf("%s\n", fails ? "FAILED" : "PASS test_cheats_r26: settings v1/v2, readout math, six rows, trial/start/stop/retry, config overrides");
    return fails ? 1 : 0;
}
