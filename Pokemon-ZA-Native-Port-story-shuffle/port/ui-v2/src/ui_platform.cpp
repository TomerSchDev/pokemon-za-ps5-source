#include "ui_platform.h"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <ctime>

#include <SDL3/SDL.h>

#ifdef ZA_PS5
extern "C" int sceKernelDebugOutText(int, const char*);
#endif

namespace ui::platform {

void log(const char* line) {
#ifdef ZA_PS5
    sceKernelDebugOutText(0, line);
#else
    std::fputs(line, stderr);
    std::fflush(stderr);
#endif
}

void logf(const char* fmt, ...) {
    char line[768];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(line, sizeof line, fmt, args);
    va_end(args);
    log(line);
}

#ifdef ZA_PS5
std::string runRoot() { return "/download0/zarecomp/rando"; }
std::string assetsDir() { return "/app0/randomizer-assets/"; }
std::string gameImage(const char*) { return "/app0/game/romfs.bin"; }
std::string repairStage() { return "/app0/run-repair"; }
std::string itemsUiPath() { return "/download0/zarecomp/rando/items-ui.txt"; }
std::string freshSeed() {
    const uint64_t value = (uint64_t(arc4random()) << 32) | arc4random();
    return std::to_string(value % 10000000000ULL);
}
uint32_t random32() { return arc4random(); }
#else
// The PC proof: the data root is the working directory (runtime/paths.c chdir's there); the runs live in rando/
// as the runtime expects (rando_boot: "rando/<seed>"). The randomizer assets come from ZA_UI_ASSETS (a folder
// prepared by port/randomizer/prepare-assets.py), the game image from the game root the runtime was started with.
// Paths are given to the C library as "/Users/..." on the current drive when the data root has no drive letter
// (run_store's makeDirs wants a leading slash).
static std::string dataRoot() {
    const char* r = std::getenv("ZA_UI_DATA_ROOT");
    if (r && *r) return r;
    const char* d = std::getenv("LARECOMP_DATA_ROOT");
    std::string root = d && *d ? d : ".";
    if (root.size() > 2 && root[1] == ':') root = root.substr(2);  // C:\x -> \x (the current drive)
    for (char& c : root) if (c == '\\') c = '/';
    return root;
}
std::string runRoot() { return dataRoot() + "/rando"; }
std::string assetsDir() {
    const char* a = std::getenv("ZA_UI_ASSETS");
    std::string s = a && *a ? a : dataRoot() + "/randomizer-assets";
    for (char& c : s) if (c == '\\') c = '/';
    if (s.empty() || s.back() != '/') s += '/';
    return s;
}
std::string gameImage(const char* gameRoot) {
    const char* g = std::getenv("ZA_UI_GAME_IMAGE");
    if (g && *g) return g;
    std::string s = gameRoot ? gameRoot : "extracted";
    for (char& c : s) if (c == '\\') c = '/';
    return s + "/romfs.bin";
}
std::string repairStage() { return ""; }
std::string itemsUiPath() { return runRoot() + "/items-ui.txt"; }
static uint32_t entropy32() {
#ifdef ZA_UI_HOST_TEST
    // The Linux host harness uses the PS5 SDL shim headers and stubs only the clock; no desktop SDL is linked.
    return arc4random();
#else
    return SDL_rand_bits();
#endif
}
std::string freshSeed() {
    uint64_t value = (uint64_t(entropy32()) << 32) | entropy32();
    return std::to_string(value % 10000000000ULL);
}
uint32_t random32() { return entropy32(); }
#endif

uint64_t unixTime() { return uint64_t(std::time(nullptr)); }
uint64_t nowMs() { return SDL_GetTicksNS() / 1000000ull; }

}  // namespace ui::platform
