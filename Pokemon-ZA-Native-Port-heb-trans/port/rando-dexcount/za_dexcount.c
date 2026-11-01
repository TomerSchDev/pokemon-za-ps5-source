/* rando-dexcount runtime side. See za_dexcount.h. C11, no allocation, no locks, no game-memory access:
 * the patched translated functions do every game call themselves and only pass the two counts here. */
#include "za_dexcount.h"

#include <stdatomic.h>
#ifdef ZA_DEXCOUNT_TRACE
#include <stdio.h>
#ifdef ZA_DEXCOUNT_KLOG /* PS5: nothing reads stderr on the console (runtime/platform/ps5.c); klog does */
int sceKernelDebugOutText(int channel, const char *text);
#endif
#endif

static atomic_int g_enabled = 1;
static atomic_uint g_last_lumiose, g_last_hyperspace, g_last_combined;
static atomic_ullong g_evaluations, g_displays;
#ifdef ZA_DEXCOUNT_TRACE
static atomic_ullong g_traced_eval = ~0ull, g_traced_display = ~0ull;
#endif

int za_dexcount_extra_enabled(void) { return atomic_load_explicit(&g_enabled, memory_order_relaxed) != 0; }

void za_dexcount_set_enabled(int on) { atomic_store_explicit(&g_enabled, on ? 1 : 0, memory_order_relaxed); }

static uint32_t sum(uint32_t lumiose, uint32_t hyperspace) {
    uint32_t combined = lumiose + hyperspace;
    return combined < lumiose ? UINT32_MAX : combined; /* (cannot happen with 232 + 132 species; never wrap) */
}

#ifdef ZA_DEXCOUNT_TRACE
static void trace(atomic_ullong *last, const char *what, uint32_t l, uint32_t h, uint32_t s, unsigned long long n) {
    unsigned long long pair = ((unsigned long long)l << 32) | h;
    if (atomic_exchange_explicit(last, pair, memory_order_relaxed) == pair) return; /* only when a value changes */
    char line[160];
    snprintf(line, sizeof line, "[dexcount] %s: lumiose=%u hyperspace=%u combined=%u (call %llu)\n", what, l, h, s, n);
#ifdef ZA_DEXCOUNT_KLOG
    sceKernelDebugOutText(0, line);
#endif
    fputs(line, stderr);
    fflush(stderr);
}
#endif

uint32_t za_dexcount_combine(uint32_t lumiose, uint32_t hyperspace) {
    uint32_t combined = sum(lumiose, hyperspace);
    atomic_store_explicit(&g_last_lumiose, lumiose, memory_order_relaxed);
    atomic_store_explicit(&g_last_hyperspace, hyperspace, memory_order_relaxed);
    atomic_store_explicit(&g_last_combined, combined, memory_order_relaxed);
    unsigned long long n = atomic_fetch_add_explicit(&g_evaluations, 1, memory_order_relaxed) + 1;
#ifdef ZA_DEXCOUNT_TRACE
    trace(&g_traced_eval, "have_pokemon_encyclopedia_total condition", lumiose, hyperspace, combined, n);
#else
    (void)n;
#endif
    return combined;
}

uint32_t za_dexcount_display(uint32_t lumiose, uint32_t hyperspace) {
    uint32_t combined = sum(lumiose, hyperspace);
    unsigned long long n = atomic_fetch_add_explicit(&g_displays, 1, memory_order_relaxed) + 1;
#ifdef ZA_DEXCOUNT_TRACE
    trace(&g_traced_display, "mission panel Number Registered", lumiose, hyperspace, combined, n);
#else
    (void)n;
#endif
    return combined;
}

uint32_t za_dexcount_last_lumiose(void) { return atomic_load_explicit(&g_last_lumiose, memory_order_relaxed); }
uint32_t za_dexcount_last_hyperspace(void) { return atomic_load_explicit(&g_last_hyperspace, memory_order_relaxed); }
uint32_t za_dexcount_last_combined(void) { return atomic_load_explicit(&g_last_combined, memory_order_relaxed); }
uint64_t za_dexcount_evaluations(void) { return atomic_load_explicit(&g_evaluations, memory_order_relaxed); }
uint64_t za_dexcount_displays(void) { return atomic_load_explicit(&g_displays, memory_order_relaxed); }
