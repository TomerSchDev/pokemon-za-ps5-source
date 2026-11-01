/* rando-dexopen runtime side. See za_dexopen.h. C11, no allocation, no locks, no game-memory access: the patched
 * translated functions pass the two words they already hold and take the result back into the same register. */
#include "za_dexopen.h"

#include <stdatomic.h>
#ifdef ZA_DEXOPEN_TRACE
#include <stdio.h>
#ifdef ZA_DEXOPEN_KLOG /* PS5: nothing reads stderr on the console (runtime/platform/ps5.c); klog does */
int sceKernelDebugOutText(int channel, const char *text);
#endif
#endif

static atomic_int g_enabled = 1;
static atomic_ullong g_calls[ZA_DEXOPEN_SITES], g_forced[ZA_DEXOPEN_SITES], g_lines[ZA_DEXOPEN_SITES];
static atomic_uint g_seen[ZA_DEXOPEN_SITES]; /* last observed flag + 1; 0 = nothing observed yet */

#ifdef ZA_DEXOPEN_TRACE
static const char *const k_site_name[ZA_DEXOPEN_SITES] = {"DLC::IsHyperspaceDexEnabled (f_70008d4178)",
                                                           "Pokedex::GetMegaDexCount (f_700033f8d8)"};
#endif

int za_dexopen_enabled(void) { return atomic_load_explicit(&g_enabled, memory_order_relaxed) != 0; }

void za_dexopen_set_enabled(int on) { atomic_store_explicit(&g_enabled, on ? 1 : 0, memory_order_relaxed); }

/* observed: the flag the game's own getter returned, or ZA_DEXOPEN_FLAG_UNKNOWN when the getter was not reached. */
static void za_dexopen_note(int site, uint32_t observed, uint32_t original, uint32_t result) {
    unsigned long long n = atomic_fetch_add_explicit(&g_calls[site], 1, memory_order_relaxed) + 1;
    if (result != original) atomic_fetch_add_explicit(&g_forced[site], 1, memory_order_relaxed);
    unsigned prev = atomic_exchange_explicit(&g_seen[site], observed + 1u, memory_order_relaxed);
    if (prev == observed + 1u) return; /* first use of the site, then only when the game's own flag value changes */
    atomic_fetch_add_explicit(&g_lines[site], 1, memory_order_relaxed);
#ifdef ZA_DEXOPEN_TRACE
    char line[200];
    if (observed == ZA_DEXOPEN_FLAG_UNKNOWN)
        snprintf(line, sizeof line, "[dexopen] %s: flag manager not ready, FLAG_DLC_DEX_ENABLE not read -> %u (call %llu)\n",
                 k_site_name[site], result, n);
    else
        snprintf(line, sizeof line, "[dexopen] %s: FLAG_DLC_DEX_ENABLE=%u -> %u%s (call %llu)\n", k_site_name[site],
                 observed, result, result != original ? " (forced: Hyperspace Pokedex list open)" : "", n);
#ifdef ZA_DEXOPEN_KLOG
    sceKernelDebugOutText(0, line);
#endif
    fputs(line, stderr);
    fflush(stderr);
#else
    (void)n;
#endif
}

uint32_t za_dexopen_hyperspace_dex_enabled(uint32_t ready, uint32_t flag) {
    uint32_t original = ready & flag; /* the game's `w0 = w8 & w19` (w8 is 0 or 1) */
    uint32_t result = za_dexopen_enabled() ? ready : original;
    za_dexopen_note(ZA_DEXOPEN_SITE_GETTER, ready ? flag : ZA_DEXOPEN_FLAG_UNKNOWN, original, result);
    return result;
}

uint32_t za_dexopen_mega_dex_flag(uint32_t flag) {
    uint32_t result = za_dexopen_enabled() ? 1u : flag; /* reached only after the game's own readiness check */
    za_dexopen_note(ZA_DEXOPEN_SITE_MEGADEX, flag, flag, result);
    return result;
}

uint64_t za_dexopen_calls(int site) { return atomic_load_explicit(&g_calls[site], memory_order_relaxed); }
uint64_t za_dexopen_forced(int site) { return atomic_load_explicit(&g_forced[site], memory_order_relaxed); }
uint32_t za_dexopen_last_flag(int site) { return atomic_load_explicit(&g_seen[site], memory_order_relaxed) - 1u; }
uint64_t za_dexopen_trace_lines(int site) { return atomic_load_explicit(&g_lines[site], memory_order_relaxed); }
