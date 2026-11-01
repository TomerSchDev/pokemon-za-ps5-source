// Real overlay + real MONEY mailbox. Only SDL/Vulkan/performance/console calls
// are stubbed. No run id is set, so settings writes never target real storage.
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include "menu_font.h"
#include "za_money.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

static int performanceMode, performanceRequests, lastPerformanceRequest = -1;
static std::vector<VkClearRect> draws;
extern "C" {
int sceKernelDebugOutText(int, const char*) { return 0; }
uint64_t renderer_present_count(void) { return 0; }
int za_performance_status(void) { return performanceMode; }
void za_performance_request(int trial) { ++performanceRequests; lastPerformanceRequest = trial; performanceMode = trial ? 1 : 0; }
Uint64 SDL_GetTicksNS(void) { return 0; }
void vkCmdClearAttachments(VkCommandBuffer, uint32_t, const VkClearAttachment*, uint32_t count, const VkClearRect* rects) {
    draws.insert(draws.end(), rects, rects + count);
}
bool menu_handle_event(const SDL_Event*);
bool menu_is_open(void);
bool menu_input_captured(void);
void menu_render(void*, uint32_t, uint32_t);
void za_cheats_init(void);
void za_cheats_test_load(const char*, unsigned*, unsigned*, unsigned*, unsigned*, bool*);
unsigned za_cheats_test_fps_x10(unsigned, uint64_t);
unsigned za_cheats_test_ms_x10(unsigned, uint64_t);
}
static int failures, selectedRow;
#define CHECK(x) do { if (!(x)) { std::printf("FAIL %s:%d %s\n", __FILE__, __LINE__, #x); ++failures; } } while (0)
static SDL_Event button(int b, bool down) {
    SDL_Event e{};
    e.type = down ? SDL_EVENT_GAMEPAD_BUTTON_DOWN : SDL_EVENT_GAMEPAD_BUTTON_UP;
    e.gbutton.button = Uint8(b);
    return e;
}
static void press(int b) {
    const auto down = button(b, true), up = button(b, false);
    CHECK(menu_handle_event(&down));
    CHECK(menu_handle_event(&up));
}
static void chooseRow(int target) {
    while (selectedRow != target) { press(SDL_GAMEPAD_BUTTON_DPAD_DOWN); selectedRow = (selectedRow + 1) % 6; }
}
// Decode actual Vulkan glyph rectangles. This checks the user-visible status
// rather than private overlay state or a second implementation of the mailbox.
static std::string renderedRow(int row) {
    draws.clear(); menu_render(nullptr, 1280, 720);
    constexpr int x0 = 144, scale = 3, advance = 18;
    const int y0 = 205 + row * 42;
    std::array<std::array<unsigned char, 7>, 64> cells{};
    int end = -1;
    for (const auto& draw : draws) {
        const auto& r = draw.rect;
        if (r.extent.width != scale || r.extent.height != scale || r.offset.x < x0 ||
            r.offset.y < y0 || r.offset.y >= y0 + 7 * scale) continue;
        const int dx = r.offset.x - x0, dy = r.offset.y - y0;
        const int ch = dx / advance, xx = (dx % advance) / scale, yy = dy / scale;
        if (ch >= int(cells.size()) || xx >= 5 || dx % scale || dy % scale) continue;
        cells[size_t(ch)][size_t(yy)] |= static_cast<unsigned char>(1u << (4 - xx));
        if (ch > end) end = ch;
    }
    std::string text;
    for (int i = 0; i <= end; ++i) {
        char decoded = '?';
        for (const auto& glyph : glyphs) {
            if (!std::memcmp(cells[size_t(i)].data(), glyph.rows, 7)) { decoded = glyph.character; break; }
        }
        text += decoded;
    }
    return text;
}
static bool contains(const std::string& text, const char* part) { return text.find(part) != std::string::npos; }

int main() {
    unsetenv("LARECOMP_RANDO_SEED"); unsetenv("ZA_DT_POLICY");
    unsetenv("ZA_PERF_FORCE60"); unsetenv("ZA_PERF_FPS_COUNTER");
    za_cheats_init();
    CHECK(!menu_is_open() && !za_money_ready() && !za_money_pending());
    const auto l = button(SDL_GAMEPAD_BUTTON_LEFT_STICK, true), r = button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, true);
    menu_handle_event(&l); menu_handle_event(&r);
    const auto lu = button(SDL_GAMEPAD_BUTTON_LEFT_STICK, false), ru = button(SDL_GAMEPAD_BUTTON_RIGHT_STICK, false);
    menu_handle_event(&lu); menu_handle_event(&ru);
    CHECK(menu_is_open() && menu_input_captured());

    // Retain v1/v2 settings compatibility without replaying historical money adds.
    unsigned s = 0, c = 0, fps = 0, adds = 0; bool haveFps = false;
    za_cheats_test_load("za-cheats-v1\n3 2\n", &s, &c, &fps, &adds, &haveFps);
    CHECK(s == 3 && c == 2 && !haveFps);
    za_cheats_test_load("za-cheats-v2\n1 4 1 12\n", &s, &c, &fps, &adds, &haveFps);
    CHECK(s == 1 && c == 4 && fps == 1 && adds == 12 && haveFps);
    CHECK(!za_money_pending() && za_money_applied() == 0);
    CHECK(za_cheats_test_fps_x10(15, 250000000) == 600 && za_cheats_test_ms_x10(15, 250000000) == 167);
    CHECK(za_cheats_test_fps_x10(15, 312500000) == 480 && za_cheats_test_ms_x10(15, 312500000) == 208);

    chooseRow(3); CHECK(renderedRow(3) == "FPS COUNTER  OFF");
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(renderedRow(3) == "FPS COUNTER  ON");
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 0);
    chooseRow(4); CHECK(contains(renderedRow(4), "FPS TRIAL  30"));
    press(SDL_GAMEPAD_BUTTON_DPAD_LEFT); press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    CHECK(performanceRequests == 0);
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 1 && lastPerformanceRequest == 1 && performanceMode == 1);
    CHECK(contains(renderedRow(4), "60 AUTO"));
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 2 && lastPerformanceRequest == 0);
    performanceMode = 2; CHECK(contains(renderedRow(4), "30 FALLBACK"));
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 3 && lastPerformanceRequest == 1);
    setenv("ZA_DT_POLICY", "safe", 1); za_cheats_init();
    CHECK(contains(renderedRow(4), "CONTROLLED BY CONFIG"));
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 3);
    unsetenv("ZA_DT_POLICY"); setenv("ZA_PERF_FORCE60", "1", 1); za_cheats_init();
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(performanceRequests == 3);
    unsetenv("ZA_PERF_FORCE60"); za_cheats_init();

    chooseRow(0); press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    chooseRow(1); press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
    CHECK(renderedRow(0) == "SHINY  4X ROLLS" && renderedRow(1) == "CAPTURE  2X SCORE");
    chooseRow(5); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(renderedRow(0) == "SHINY  NORMAL" && renderedRow(1) == "CAPTURE  NORMAL");
    chooseRow(2);

#ifdef ZA_MONEY_HOOK
    alignas(16) std::array<unsigned char, 128> object{};
    object.fill(0xa5);
    auto set = [&](uint32_t v) { std::memcpy(object.data() + 0x40, &v, 4); };
    auto get = [&]() { uint32_t v; std::memcpy(&v, object.data() + 0x40, 4); return v; };
    set(2345);
    const auto original = object;
    const uint64_t ptr = uint64_t(uintptr_t(object.data()));
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT); // Choose 10,000; selection never queues.
    CHECK(contains(renderedRow(2), "LOAD SAVE FIRST"));
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(!za_money_ready() && !za_money_pending() && za_money_applied() == 0 && object == original);
    za_cheat_money_component(ptr); // Simulate the validated game lookup on a test-owned object.
    CHECK(za_money_ready() && !za_money_pending() && object == original);
    press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(za_money_pending() == 10000 && za_money_applied() == 0 && object == original);
    CHECK(contains(renderedRow(2), "QUEUED") && !contains(renderedRow(2), "ADDED"));
    press(SDL_GAMEPAD_BUTTON_SOUTH); // The pending request must survive repeated X.
    CHECK(za_money_pending() == 10000 && za_money_applied() == 0 && object == original);
    za_cheat_money_component(ptr);
    CHECK(get() == 12345 && !za_money_pending() && za_money_applied() == 1);
    const auto ack = renderedRow(2);
    if (!contains(ack, "ADDED") || contains(ack, "RETRY")) std::printf("observed after queued request was applied: [%s]\n", ack.c_str());
    CHECK(contains(ack, "ADDED") && !contains(ack, "RETRY"));
    za_cheat_money_component(ptr); CHECK(get() == 12345 && za_money_applied() == 1);

    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(za_money_pending() == 10000);
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT); // Selection to 100,000 cancels, does not enqueue.
    CHECK(!za_money_pending() && !za_money_enabled());
    za_cheat_money_component(ptr); CHECK(get() == 12345 && za_money_applied() == 1);
    press(SDL_GAMEPAD_BUTTON_DPAD_LEFT); // Return to 10,000.
    press(SDL_GAMEPAD_BUTTON_SOUTH); CHECK(za_money_pending() == 10000);
    press(SDL_GAMEPAD_BUTTON_DPAD_LEFT); // NORMAL cancels.
    CHECK(!za_money_pending() && !za_money_enabled());
    press(SDL_GAMEPAD_BUTTON_SOUTH); za_cheat_money_component(ptr);
    CHECK(get() == 12345 && za_money_applied() == 1 && !za_money_pending());

    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(za_money_pending() == 10000);
    za_money_lifecycle_reset();
    CHECK(!za_money_ready() && !za_money_enabled() && !za_money_pending());
    CHECK(contains(renderedRow(2), "LOAD SAVE FIRST"));
    za_cheat_money_component(ptr); CHECK(get() == 12345 && za_money_applied() == 1);

    set(9999998); za_cheat_money_component(ptr); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(get() == 9999998 && za_money_pending() == 10000 && za_money_applied() == 1);
    za_cheat_money_component(ptr);
    CHECK(get() == 9999999 && za_money_last_value() == 9999999 && za_money_applied() == 2);
    press(SDL_GAMEPAD_BUTTON_SOUTH); za_cheat_money_component(ptr);
    CHECK(get() == 9999999 && !za_money_pending() && za_money_applied() == 2); // no fake success at cap
    set(10000000); press(SDL_GAMEPAD_BUTTON_SOUTH); za_cheat_money_component(ptr);
    CHECK(get() == 10000000 && !za_money_ready() && !za_money_pending() && za_money_applied() == 2);
    CHECK(contains(renderedRow(2), "LOAD SAVE FIRST"));
    for (size_t i = 0; i < object.size(); ++i) if (i < 0x40 || i >= 0x44) CHECK(object[i] == original[i]);
    set(100); za_cheat_money_component(ptr); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(za_money_pending() == 10000);
    za_cheats_init(); // Session initialization must cancel; no persisted request replay.
    CHECK(!za_money_ready() && !za_money_pending() && !za_money_enabled());
    za_cheat_money_component(ptr); CHECK(get() == 100 && za_money_applied() == 2);
#else
    CHECK(renderedRow(2) == "MONEY  NOT AVAILABLE");
    press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT); press(SDL_GAMEPAD_BUTTON_SOUTH);
    CHECK(!za_money_pending() && !za_money_enabled() && za_money_applied() == 0);
#endif
    CHECK(performanceRequests == 3); // Money and reset must never start/stop FPS trial.
    press(SDL_GAMEPAD_BUTTON_EAST);
    CHECK(!menu_is_open() && !menu_input_captured());
    std::printf("%s: r27 overlay + real money hook, FPS trial/counter, settings, queued/applied/cancel/cap/reset (%d failures)\n",
                failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
