/* Only FLAG_DLC_DEX_ENABLE. Runs synchronously on the calling guest thread.
 * Native getter/setter operate on the existing flag record; no save-file IO,
 * allocation, retained guest pointers, phase changes or fabricated return value.
 */
#include "cpu.h"
#include <stdatomic.h>
#ifdef ZA_DLC_DEX_TRACE
#include <stdio.h>
#ifdef ZA_DLC_DEX_KLOG
int sceKernelDebugOutText(int channel, const char *text);
#endif
#endif

void f_70000393b8(Cpu *c); /* bool GetFlag(manager, key descriptor) */
void f_70009d0114(Cpu *c); /* bool SetExistingFlag(manager, key descriptor, bool) */

#define DEX_DESCRIPTOR 0x7003e26880ull
#define DEX_HASH 0x58e63b00d271631full
#define FLAGS_READY 0x700610e100ull
#define FLAGS_SLOT 0x7003ec3328ull

enum { WAITING, BAD_DESCRIPTOR, MISSING_MANAGER, ALREADY_ON, ENABLED, SET_FAILED };
static atomic_flag consumer = ATOMIC_FLAG_INIT;
#ifdef ZA_DLC_DEX_TRACE
static atomic_uint last_trace = ATOMIC_VAR_INIT(~0u);
static atomic_uint trace_count;
static void trace(unsigned state, unsigned before, unsigned set_ok, unsigned after) {
    if (atomic_exchange_explicit(&last_trace, state, memory_order_relaxed) == state) return;
    if (atomic_fetch_add_explicit(&trace_count, 1, memory_order_relaxed) >= 16) return;
    char line[192];
    snprintf(line, sizeof line,
        "[dlc-dex-unlock-r1] state=%u flag=FLAG_DLC_DEX_ENABLE before=%u set_ok=%u after=%u\n",
        state, before, set_ok, after);
#ifdef ZA_DLC_DEX_KLOG
    sceKernelDebugOutText(0, line);
#endif
    fputs(line, stderr);
    fflush(stderr);
}
#else
#define trace(state, before, set_ok, after) do { (void)(state); (void)(before); (void)(set_ok); (void)(after); } while (0)
#endif

static unsigned get_flag(Cpu *c, uint64_t manager) {
    c->x[0] = manager;
    c->x[1] = DEX_DESCRIPTOR;
    f_70000393b8(c);
    return (unsigned)c->x[0] & 1u;
}

unsigned za_dlc_dex_unlock_pump(Cpu *c) {
    unsigned result = 0;
    if (atomic_flag_test_and_set_explicit(&consumer, memory_order_acquire)) return 0;
    /* Same readiness location and ordering as f_70008d4178. */
    unsigned ready = LD32(FLAGS_READY);
    __atomic_thread_fence(__ATOMIC_SEQ_CST);
    if (!ready) { trace(WAITING, 0, 0, 0); goto done; }
    if (LD64(DEX_DESCRIPTOR) != DEX_HASH) { trace(BAD_DESCRIPTOR, 0, 0, 0); goto done; }
    uint64_t manager = LD64(FLAGS_SLOT);
    if (manager < 0x10000ull || (manager & 7ull)) { trace(MISSING_MANAGER, 0, 0, 0); goto done; }

    Cpu saved;
    memcpy(&saved, c, sizeof saved);
    unsigned before = get_flag(c, manager);
    if (before) {
        result = before;
        memcpy(c, &saved, sizeof saved);
        trace(ALREADY_ON, 1, 0, 1);
        goto done;
    }
    c->x[0] = manager;
    c->x[1] = DEX_DESCRIPTOR;
    c->x[2] = 1;
    f_70009d0114(c);
    unsigned set_ok = (unsigned)c->x[0] & 1u;
    unsigned after = get_flag(c, manager);
    result = after;
    memcpy(c, &saved, sizeof saved);
    trace(set_ok && after ? ENABLED : SET_FAILED, before, set_ok, after);
done:
    atomic_flag_clear_explicit(&consumer, memory_order_release);
    return result;
}
