// Loads the recompiled game code library (runtime/gamelib.h).
#include "gamelib.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef _WIN32
#include <windows.h>
#else
#include <dlfcn.h>
#endif
#if defined(__x86_64__)
#include <cpuid.h>
#endif

#include "gamebuild.h"
#include "paths.h"
#include "rt.h"

static const GameLibTables *g_tables;
static char g_error[256];

// Read from cpuid here rather than through __builtin_cpu_supports: that one answers from compiler-rt's / libgcc's
// __cpu_model, which a constructor (__cpu_indicator_init) fills before main - on the PS5 the title's init_array runs
// through the SDK's crt, unverified on the console, and a model left empty answers "no" to everything, which sends
// gamelib_id to the -v2 variant and leaves the built-in game code "built for another version". The answer is the
// builtin's: AVX2 and FMA count only when the OS keeps the YMM state (OSXSAVE set and XCR0 bits 1-2, as compiler-rt's
// getAvailableFeatures demands before either), BMI2 from leaf 7 alone.
unsigned gamelib_cpu_features(void) {
#if defined(__x86_64__)
    unsigned a, b, c, d, f = 0;
    if (!__get_cpuid(1, &a, &b, &c, &d)) return 0;
    bool ymm = (c & bit_OSXSAVE) && (c & bit_AVX);
    if (ymm) {
        unsigned lo, hi;
        __asm__ volatile("xgetbv" : "=a"(lo), "=d"(hi) : "c"(0));
        ymm = (lo & 6) == 6;
    }
    if (ymm && (c & bit_FMA)) f |= GAMELIB_CPU_FMA;
    if (__get_cpuid_count(7, 0, &a, &b, &c, &d)) {
        if (ymm && (b & bit_AVX2)) f |= GAMELIB_CPU_AVX2;
        if (b & bit_BMI2) f |= GAMELIB_CPU_BMI2;
    }
    return f;
#else
    return 0;
#endif
}

bool gamelib_old_cpu(void) {
#if defined(__x86_64__)
    const char *e = getenv("LARECOMP_OLD_CPU");  // (testing it on a newer CPU)
    if (e && *e == '1') return true;
    return gamelib_cpu_features() != (GAMELIB_CPU_AVX2 | GAMELIB_CPU_FMA | GAMELIB_CPU_BMI2);
#else
    return false;
#endif
}

const char *gamelib_id(void) { return gamelib_old_cpu() ? GAMELIB_ID "-v2" : GAMELIB_ID; }

// The library's id file (<library>.id, written next to it by the build): its GAMELIB_ID, read without loading it.
static bool id_matches(const char *lib) {
    char path[1100], id[128] = {0};
    snprintf(path, sizeof path, "%s.id", lib);
    FILE *f = fopen(path, "rb");
    if (!f) return false;
    size_t n = fread(id, 1, sizeof id - 1, f);
    fclose(f);
    while (n && (id[n - 1] == '\n' || id[n - 1] == '\r')) id[--n] = 0;
    return !strcmp(id, gamelib_id());
}

static bool exists(const char *p) {
    FILE *f = fopen(p, "rb");
    if (f) fclose(f);
    return f != NULL;
}

// The places to look, in order (gamelib.h). Returns how many were filled.
static int candidates(const char *game_dir, char out[3][1100]) {
    int n = 0;
    const char *env = getenv("LARECOMP_GAME_LIB");
    if (env && *env) snprintf(out[n++], 1100, "%s", env);
    char exe_side[1024];
    if (rt_resource(GAMELIB_NAME, NULL, exe_side, sizeof exe_side) && exists(exe_side))
        snprintf(out[n++], 1100, "%s", exe_side);
    if (game_dir) snprintf(out[n++], 1100, "%s/%s", game_dir, GAMELIB_NAME);
    return n;
}

#ifndef LARECOMP_STATIC_GAMELIB
bool gamelib_present(const char *game_dir) {
    if (g_tables) return true;
    char c[3][1100];
    int n = candidates(game_dir, c);
    for (int i = 0; i < n; i++)
        if (exists(c[i]) && id_matches(c[i])) return true;
    return false;
}
#endif

#ifdef LARECOMP_STATIC_GAMELIB
// PS5: the game code is linked into the title (liblasgame.a; Makefile PLATFORM=ps5) - a title can't load a library at
// run time (dlopen / sceKernelLoadStartModule refuse a title's own modules). The abi / id check stays: an archive built
// with another GAMELIB_ID is the wrong one for this runtime, however it got linked.
const GameLibTables *lasgame_tables(void);  // tools/gamelib_entry.c

bool gamelib_present(const char *game_dir) { (void)game_dir; return true; }

bool gamelib_load(const char *game_dir, char *why, size_t why_size) {
    (void)game_dir;
    if (!g_tables) {
        const GameLibTables *t = lasgame_tables();
        if (t && t->abi == GAMELIB_ABI && t->id && !strcmp(t->id, gamelib_id())) {
            g_tables = t;
            LOG("[gamelib] built in (%llu + %llu functions)\n", (unsigned long long)*t->main_count,
                (unsigned long long)*t->sdk_count);
        } else {
            snprintf(g_error, sizeof g_error, "the built-in game code was built for another version (%s; this runtime: %s)",
                     t && t->id ? t->id : "?", gamelib_id());
        }
    }
    if (!g_tables && why) snprintf(why, why_size, "%s", g_error);
    return g_tables != NULL;
}
#else
static const GameLibTables *open_lib(const char *path) {
#ifdef _WIN32
    HMODULE h = LoadLibraryA(path);
    if (!h) { snprintf(g_error, sizeof g_error, "can't load %s (error %lu)", path, GetLastError()); return NULL; }
    GameLibEntry entry = (GameLibEntry)(void *)GetProcAddress(h, GAMELIB_ENTRY);
#else
    void *h = dlopen(path, RTLD_NOW | RTLD_LOCAL);
    if (!h) { snprintf(g_error, sizeof g_error, "%s", dlerror()); return NULL; }
    GameLibEntry entry = (GameLibEntry)dlsym(h, GAMELIB_ENTRY);
#endif
    if (!entry) { snprintf(g_error, sizeof g_error, "%s: not game code", path); return NULL; }
    const GameLibTables *t = entry();
    if (!t || t->abi != GAMELIB_ABI || !t->id || strcmp(t->id, gamelib_id())) {
        snprintf(g_error, sizeof g_error, "%s was built for another version", path);
        return NULL;  // (left loaded: nothing of it runs)
    }
    return t;
}

bool gamelib_load(const char *game_dir, char *why, size_t why_size) {
    static bool tried;
    if (!tried) {
        tried = true;
        snprintf(g_error, sizeof g_error, "the game code hasn't been built: set up the game files on the start screen");
        char c[3][1100];
        int n = candidates(game_dir, c);
        const char *env = getenv("LARECOMP_GAME_LIB");
        for (int i = 0; i < n && !g_tables; i++) {
            if (!exists(c[i])) continue;
            bool given = i == 0 && env && *env;  // LARECOMP_GAME_LIB: loaded as given, the library's own id decides
            if (!given && !id_matches(c[i])) {
                snprintf(g_error, sizeof g_error, "%s was built for another version", c[i]);
                continue;
            }
            g_tables = open_lib(c[i]);
            if (g_tables) LOG("[gamelib] %s (%llu + %llu functions)\n", c[i], (unsigned long long)*g_tables->main_count,
                              (unsigned long long)*g_tables->sdk_count);
        }
    }
    if (!g_tables && why) snprintf(why, why_size, "%s", g_error);
    return g_tables != NULL;
}
#endif  // LARECOMP_STATIC_GAMELIB

const GameLibTables *gamelib_tables(void) { return g_tables; }
