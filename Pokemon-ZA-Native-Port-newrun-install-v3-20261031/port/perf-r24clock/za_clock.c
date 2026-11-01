/* r24-clock: every clock_gettime the title makes, counted and timed per thread class, for the [za-r24-perf] line.
 *
 * Linked with --wrap=clock_gettime: each clock_gettime referenced by the title's own objects (runtime, SDL3 shim,
 * observer, ...) and by the RADV archive (Mesa's os_time_get_nano and friends) arrives here; calls made inside
 * system modules (libkernel / libc internals) do not. The time inside the real call is measured with the TSC
 * (sceKernelReadTsc, ~12 ns a read), so the cost of one clock_gettime on the console is measured directly.
 *
 * Classes: "render" is the thread that last called nvnQueueSubmitCommands (--wrap=za_prof_note_render; on this game
 * it is a guest thread), "guest" any other guest thread (--wrap=za_prof_thread_begin / za_prof_thread_end, kernel.c
 * thread_main), "other" everything else (RADV's kick thread, the vsync timer, audio, shader workers, ...).
 *
 * exec.c za_r24_stats appends za_clock_report's text to its [za-r24-perf] line once per ~2 s window:
 *   cg_render=<calls> cg_render_ns=<ns inside clock_gettime> cg_render_max_ns=<longest call>  (same for guest, other)
 * Window totals reset at each report, like the line's other keys. */
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <time.h>

uint64_t sceKernelReadTsc(void);
uint64_t sceKernelGetTscFrequency(void);
int sceKernelDebugOutText(int channel, const char *text);

int __real_clock_gettime(clockid_t id, struct timespec *ts);
void __real_za_prof_note_render(void);
void __real_za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio);
void __real_za_prof_thread_end(void);

enum { ZA_CG_RENDER, ZA_CG_GUEST, ZA_CG_OTHER, ZA_CG_N };
static const char *const za_cg_names[ZA_CG_N] = {"render", "guest", "other"};
static uint64_t za_cg_calls[ZA_CG_N], za_cg_ticks[ZA_CG_N], za_cg_max[ZA_CG_N];
static uintptr_t za_cg_render;              /* pthread_self() of the last nvnQueueSubmitCommands caller, 0: none yet */
static __thread int za_cg_guest;            /* (emulated TLS; never read from a signal handler) */

static int za_cg_class(void) {
    uintptr_t render = __atomic_load_n(&za_cg_render, __ATOMIC_RELAXED);
    if (render && (uintptr_t)pthread_self() == render) return ZA_CG_RENDER;
    return za_cg_guest ? ZA_CG_GUEST : ZA_CG_OTHER;
}

int __wrap_clock_gettime(clockid_t id, struct timespec *ts) {
    uint64_t t0 = sceKernelReadTsc();
    int r = __real_clock_gettime(id, ts);
    uint64_t dt = sceKernelReadTsc() - t0;
    int c = za_cg_class();
    __atomic_add_fetch(&za_cg_calls[c], 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&za_cg_ticks[c], dt, __ATOMIC_RELAXED);
    uint64_t m = __atomic_load_n(&za_cg_max[c], __ATOMIC_RELAXED);
    while (dt > m && !__atomic_compare_exchange_n(&za_cg_max[c], &m, dt, 1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
    return r;
}

void __wrap_za_prof_note_render(void) {
    uintptr_t self = (uintptr_t)pthread_self();
    if (__atomic_load_n(&za_cg_render, __ATOMIC_RELAXED) != self) __atomic_store_n(&za_cg_render, self, __ATOMIC_RELAXED);
    __real_za_prof_note_render();
}

void __wrap_za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio) {
    za_cg_guest = 1;
    __real_za_prof_thread_begin(gid, entry, prio);
}

void __wrap_za_prof_thread_end(void) {
    __real_za_prof_thread_end();
    za_cg_guest = 0;
}

static uint64_t za_cg_ticks_to_ns(uint64_t ticks, uint64_t hz) {
    return hz ? (uint64_t)(((unsigned __int128)ticks * 1000000000ull) / hz) : 0;
}

/* The window's counts (then reset), appended to the [za-r24-perf] line. Returns the characters written. */
size_t za_clock_report(char *out, size_t cap) {
    static uint64_t hz;
    if (!hz) {
        hz = sceKernelGetTscFrequency();
        char line[160];
        snprintf(line, sizeof line, "[za-r24clock] clock_gettime counted per thread class (TSC %llu Hz for the timing)\n",
                 (unsigned long long)hz);
        sceKernelDebugOutText(0, line);
    }
    size_t n = 0;
    for (int c = 0; c < ZA_CG_N && n < cap; c++) {
        uint64_t calls = __atomic_exchange_n(&za_cg_calls[c], 0, __ATOMIC_RELAXED);
        uint64_t ticks = __atomic_exchange_n(&za_cg_ticks[c], 0, __ATOMIC_RELAXED);
        uint64_t max = __atomic_exchange_n(&za_cg_max[c], 0, __ATOMIC_RELAXED);
        int w = snprintf(out + n, cap - n, " cg_%s=%llu cg_%s_ns=%llu cg_%s_max_ns=%llu", za_cg_names[c],
                         (unsigned long long)calls, za_cg_names[c], (unsigned long long)za_cg_ticks_to_ns(ticks, hz),
                         za_cg_names[c], (unsigned long long)za_cg_ticks_to_ns(max, hz));
        if (w < 0) break;
        n += (size_t)w < cap - n ? (size_t)w : cap - n - 1;
    }
    return n;
}
