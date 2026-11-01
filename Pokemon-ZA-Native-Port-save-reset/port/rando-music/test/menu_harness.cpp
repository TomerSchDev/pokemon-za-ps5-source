// Host harness for the REAL r29-music menu source (native_menu_music.cpp, with only its three console paths
// rewritten to a temporary folder by run-menu-test.sh). A stub Display records every drawn string and feeds a
// scripted controller sequence: SEED -> 1, MUSIC -> SHUFFLE BY CATEGORY, START NEW RUN, confirm. The published run
// is then checked by the script against the core's own output for seed 1.
#include "menu_display.hpp"
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>

namespace za::native {
static std::vector<uint32_t> script;
static size_t at = 0;
static FILE* textLog = nullptr;
bool Display::open() { return true; }
bool Display::close() { return true; }
void Display::clear() { fprintf(textLog, "--- frame\n"); }
void Display::rect(int, int, int, int, uint32_t) {}
void Display::text(int x, int y, const std::string& value, uint32_t, int) { fprintf(textLog, "%d,%d %s\n", x, y, value.c_str()); }
bool Display::present() { return true; }
uint32_t Display::buttons() {
    static int idle = 0;
    if (++idle % 3) return 0;  // a press, then idle polls
    return at < script.size() ? script[at++] : 0;
}
uint64_t Display::milliseconds() { return 0; }
}  // namespace za::native

extern "C" int sceKernelDebugOutText(int, const char* text) {
    fputs(text, stderr);
    return 0;
}
extern "C" bool za_observer_menu(const char*) { return false; }
extern "C" int za_randomizer_boot();

int main(int argc, char** argv) {
    using namespace za::native;
    if (argc != 2) return 2;
    textLog = fopen(argv[1], "w");
    if (!textLog) return 2;
    // main menu starts on START NEW RUN (row 1) when no run exists
    script = {Up, Cross,                       // row 0 "CONTINUE - NO RUN YET": Cross must do nothing
              Down, Down, Cross,               // row 2 SEED -> keypad
              Cross, Up, Right, Right, Cross,  // '1', CLEAR -> '0' -> DONE: seed "1"
              Down, Down, Down, Down, Down, Down, Down, Down,  // row 2 -> row 10 MUSIC
              Right,                           // OFF -> SHUFFLE BY CATEGORY
              Up, Up, Up, Up, Up, Up, Up, Up, Up,  // back to row 1
              Cross, Cross};                   // START NEW RUN -> confirm -> create
    const int rc = za_randomizer_boot();
    fclose(textLog);
    printf("menu returned %d after %zu scripted presses\n", rc, at);
    return rc;
}
