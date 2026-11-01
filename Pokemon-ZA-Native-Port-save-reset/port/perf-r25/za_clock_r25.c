/* r25: r24-clock's clock_gettime counter (port/perf-r24clock/za_clock.c, unchanged in what it counts and reports) plus
 * clock=tsc: CLOCK_MONOTONIC from the TSC for every caller except the game's own timing.
 *
 * Linked with --wrap=clock_gettime (as r24-clock): each clock_gettime referenced by the title's objects and by the
 * RADV archive (Mesa's c23_timespec_get behind os_time_get_nano / os_time_get_absolute_timeout, vk_device.c,
 * u_thread.c) arrives in __wrap_clock_gettime. Calls made inside system modules do not.
 *
 * clock=tsc (ZA_PERF_CLOCK=tsc, set by the title entry from /app0/perf-r24-options.txt; za_clock_r25_enable is called
 * once, before the game starts): a cross-core TSC check first (za_tsc_check.h: pinned thread pairs, CPU 0 of the
 * title's affinity set against each other CPU in it). If it passes, CLOCK_MONOTONIC requests through the wrap are
 * answered from the TSC (sceKernelReadTsc, ~12 ns, against ~0.9 us for the syscall measured by r24-clock), anchored on
 * one real reading and clamped to be monotonic across threads; every other clock id is the real call. If it fails,
 * nothing changes (logged with the reason).
 *
 * The game's timing stays on the real clock: plat_now_ns (runtime/platform/ps5.c; LARECOMP_PS5_TSC=1 / tsc=1 remains
 * its own switch) and the audio renderer's pacing (runtime/services/audio.c) call za_clock_game_gettime instead
 * (apply-runtime-r25.py), which counts like the wrap and always makes the real call. CLOCK_REALTIME users (kernel.c's
 * absolute wait deadlines) are never converted.
 *
 * exec.c za_r24_stats appends za_clock_report's text to its [za-r24-perf] line once per ~2 s window:
 *   cg_render=<calls> cg_render_ns=<ns> cg_render_max_ns=<longest>   (and guest, other: every call through the wrap
 *                                                                     or za_clock_game_gettime, as r24-clock)
 *   cg_tsc=<calls answered from the TSC> cg_game=<calls through za_clock_game_gettime> ck=tsc|real
 *   ck_drift_ns=<TSC-derived minus real CLOCK_MONOTONIC, sampled once at the report; clock=tsc only>
 *   cg_radv=<calls from RADV's recording worker, radv_threaded=1 only: in no other count; > 0 shows the worker runs> */
#include <errno.h>
#include <pthread.h>
#include <pthread_np.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/cpuset.h>
#include <time.h>

#include "za_tsc_check.h"

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
static uint64_t za_cg_tsc, za_cg_game;      /* window: calls answered from the TSC / through za_clock_game_gettime */
static uintptr_t za_cg_render;              /* pthread_self() of the last nvnQueueSubmitCommands caller, 0: none yet */
static __thread int za_cg_guest;            /* (emulated TLS; never read from a signal handler) */

/* clock=tsc state, written once by za_clock_r25_enable before the game's threads exist (published by za_ck_on). */
static int za_ck_on;                        /* (__atomic) */
static uint64_t za_ck_hz, za_ck_base_tsc, za_ck_base_ns;
static uint64_t za_ck_last;                 /* (__atomic) the largest TSC-derived value returned */

static int za_cg_class(void) {
    uintptr_t render = __atomic_load_n(&za_cg_render, __ATOMIC_RELAXED);
    if (render && (uintptr_t)pthread_self() == render) return ZA_CG_RENDER;
    return za_cg_guest ? ZA_CG_GUEST : ZA_CG_OTHER;
}

static void za_cg_count(int c, uint64_t dt) {
    __atomic_add_fetch(&za_cg_calls[c], 1, __ATOMIC_RELAXED);
    __atomic_add_fetch(&za_cg_ticks[c], dt, __ATOMIC_RELAXED);
    uint64_t m = __atomic_load_n(&za_cg_max[c], __ATOMIC_RELAXED);
    while (dt > m && !__atomic_compare_exchange_n(&za_cg_max[c], &m, dt, 1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) {}
}

static uint64_t za_ck_now_ns(void) {
    return za_tsc_monotonic(&za_ck_last, za_tsc_clock_ns(sceKernelReadTsc(), za_ck_base_tsc, za_ck_base_ns, za_ck_hz));
}

/* radv_threaded=1 (RADV_THREADED_RECORDING; PS5_Mesa's layers/radv_threaded_layer.c radv_threaded_worker): each time
 * RADV's recording worker runs out of batches it spins up to 50 us on CLOCK_MONOTONIC before it sleeps, tens of calls
 * through this wrap a batch (thousands a call under clock=tsc). Told apart by radv_threaded_replaying() (true on that
 * worker), they stay off the shared counters and the cross-thread clamp, which the render thread's own calls would
 * otherwise contend for, and are counted in cg_radv alone, on a line of its own: they only time the worker's own spin. */
_Bool radv_threaded_replaying(void);
static int za_cg_radv_on;  /* (__atomic) set once by the title entry, before the device exists */
static struct { uint64_t calls; char pad[56]; } za_cg_radv __attribute__((aligned(64)));  /* (__atomic) window */

void za_clock_r25_radv_threaded(void) { __atomic_store_n(&za_cg_radv_on, 1, __ATOMIC_RELEASE); }

static int za_cg_radv_worker(void) {
    if (!__atomic_load_n(&za_cg_radv_on, __ATOMIC_RELAXED)) return 0;
    const uintptr_t render = __atomic_load_n(&za_cg_render, __ATOMIC_RELAXED);
    if (render && (uintptr_t)pthread_self() == render) return 0;
    return radv_threaded_replaying();
}

int __wrap_clock_gettime(clockid_t id, struct timespec *ts) {
    if (za_cg_radv_worker()) {
        __atomic_add_fetch(&za_cg_radv.calls, 1, __ATOMIC_RELAXED);
        if (id == CLOCK_MONOTONIC && ts && __atomic_load_n(&za_ck_on, __ATOMIC_ACQUIRE)) {  /* (unclamped) */
            const uint64_t ns = za_tsc_clock_ns(sceKernelReadTsc(), za_ck_base_tsc, za_ck_base_ns, za_ck_hz);
            ts->tv_sec = (time_t)(ns / 1000000000ull);
            ts->tv_nsec = (long)(ns % 1000000000ull);
            return 0;
        }
        return __real_clock_gettime(id, ts);
    }
    uint64_t t0 = sceKernelReadTsc();
    int r;
    if (id == CLOCK_MONOTONIC && ts && __atomic_load_n(&za_ck_on, __ATOMIC_ACQUIRE)) {
        const uint64_t ns = za_ck_now_ns();
        ts->tv_sec = (time_t)(ns / 1000000000ull);
        ts->tv_nsec = (long)(ns % 1000000000ull);
        r = 0;
        __atomic_add_fetch(&za_cg_tsc, 1, __ATOMIC_RELAXED);
    } else {
        r = __real_clock_gettime(id, ts);
    }
    za_cg_count(za_cg_class(), sceKernelReadTsc() - t0);
    return r;
}

/* The game's timing (plat_now_ns, the audio renderer): counted like the wrap, always the real clock. */
int za_clock_game_gettime(clockid_t id, struct timespec *ts) {
    uint64_t t0 = sceKernelReadTsc();
    int r = __real_clock_gettime(id, ts);
    __atomic_add_fetch(&za_cg_game, 1, __ATOMIC_RELAXED);
    za_cg_count(za_cg_class(), sceKernelReadTsc() - t0);
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

/* ---- clock=tsc: the cross-core check, then the switch */
static uint64_t za_ck_fenced_tsc(void) {
    __builtin_ia32_lfence();
    const uint64_t t = sceKernelReadTsc();
    __builtin_ia32_lfence();
    return t;
}

static int za_ck_pin(int cpu) {
    cpuset_t set;
    CPU_ZERO(&set);
    CPU_SET(cpu, &set);
    return pthread_setaffinity_np(pthread_self(), sizeof set, &set);
}

static void za_ck_log(const char *line) { sceKernelDebugOutText(0, line); }

#define ZA_CK_ROUNDS 1000u
#define ZA_CK_MAX_BACK_NS 1000ull   /* a reading may not go backwards across cores by more than this */
#define ZA_CK_MAX_SKEW_NS 2000ull   /* bound on the cores' offset (includes one cross-core latency) */

void za_clock_r25_enable(void) {
    char line[320];
    const uint64_t hz = sceKernelGetTscFrequency();
    if (!hz) { za_ck_log("[za-r25-clock] clock=tsc refused: the TSC frequency reads 0; CLOCK_MONOTONIC stays the real call\n"); return; }
    /* the CPUs this title may run on: CPU pairs (the first one, each other one) */
    cpuset_t allowed;
    CPU_ZERO(&allowed);
    int e = pthread_getaffinity_np(pthread_self(), sizeof allowed, &allowed);
    int cpus[CPU_SETSIZE < 64 ? CPU_SETSIZE : 64], ncpu = 0;
    for (int c = 0; !e && c < CPU_SETSIZE && c < 64; c++) if (CPU_ISSET(c, &allowed)) cpus[ncpu++] = c;
    static ZaTscReport rep;
    memset(&rep, 0, sizeof rep);
    for (int i = 1; i < ncpu && rep.pairs < ZA_TSC_MAX_PAIRS; i++) {
        ZaTscPair *p = &rep.pair[rep.pairs++];
        if (za_tsc_run_pair(p, cpus[0], cpus[i], ZA_CK_ROUNDS, za_ck_fenced_tsc, za_ck_fenced_tsc, za_ck_pin,
                            hz / 20 /* 50 ms a round */) != 0) break;
    }
    const uint64_t max_back = ZA_CK_MAX_BACK_NS * hz / 1000000000ull, max_skew = ZA_CK_MAX_SKEW_NS * hz / 1000000000ull;
    za_tsc_decide(&rep, max_back, max_skew);
    for (unsigned i = 0; i < rep.pairs; i++) {
        const ZaTscPair *p = &rep.pair[i];
        snprintf(line, sizeof line,
                 "[za-r25-clock] TSC pair cpu %d -> cpu %d: pinned=%d rounds=%u backwards=%llu/%llu max_back_ns=%llu "
                 "offset_ns in (%lld, %lld) min_rtt_ns=%llu timed_out=%d\n",
                 p->cpu_a, p->cpu_b, p->pinned, p->rounds, (unsigned long long)p->back_ab, (unsigned long long)p->back_ba,
                 (unsigned long long)za_tsc_ticks_ns(p->max_back, hz),
                 p->delta_lo == INT64_MIN ? 0LL : (long long)(p->delta_lo < 0 ? -(int64_t)za_tsc_ticks_ns(za_tsc_abs64(p->delta_lo), hz) : (int64_t)za_tsc_ticks_ns((uint64_t)p->delta_lo, hz)),
                 p->delta_hi == INT64_MAX ? 0LL : (long long)(p->delta_hi < 0 ? -(int64_t)za_tsc_ticks_ns(za_tsc_abs64(p->delta_hi), hz) : (int64_t)za_tsc_ticks_ns((uint64_t)p->delta_hi, hz)),
                 (unsigned long long)(p->min_rtt == UINT64_MAX ? 0 : za_tsc_ticks_ns(p->min_rtt, hz)), p->timed_out);
        za_ck_log(line);
    }
    snprintf(line, sizeof line,
             "[za-r25-clock] cross-core TSC check: %u CPUs (affinity rc %d), %u pairs x %u rounds, all pinned=%d, max "
             "backwards %llu ns (limit %llu), skew bound %llu ns (limit %llu): %s\n",
             ncpu, e, rep.pairs, ZA_CK_ROUNDS, rep.all_pinned, (unsigned long long)za_tsc_ticks_ns(rep.max_back, hz),
             ZA_CK_MAX_BACK_NS, (unsigned long long)za_tsc_ticks_ns(rep.max_skew, hz), ZA_CK_MAX_SKEW_NS, rep.reason);
    za_ck_log(line);
    if (!rep.accept) {
        za_ck_log("[za-r25-clock] clock=tsc refused: CLOCK_MONOTONIC stays the real call\n");
        return;
    }
    /* the anchor: the real reading taken between the two closest TSC reads of a few tries */
    uint64_t best = UINT64_MAX;
    for (int i = 0; i < 16; i++) {
        struct timespec ts;
        const uint64_t a = za_ck_fenced_tsc();
        __real_clock_gettime(CLOCK_MONOTONIC, &ts);
        const uint64_t b = za_ck_fenced_tsc();
        if (b - a < best) {
            best = b - a;
            za_ck_base_tsc = a + (b - a) / 2;
            za_ck_base_ns = (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
        }
    }
    za_ck_hz = hz;
    __atomic_store_n(&za_ck_last, za_ck_base_ns, __ATOMIC_RELAXED);
    __atomic_store_n(&za_ck_on, 1, __ATOMIC_RELEASE);
    snprintf(line, sizeof line,
             "[za-r25-clock] clock=tsc on: CLOCK_MONOTONIC from the TSC (%llu Hz, anchor window %llu ns) for every caller "
             "but the game's timing (plat_now_ns, audio: real clock)\n",
             (unsigned long long)hz, (unsigned long long)za_tsc_ticks_ns(best, hz));
    za_ck_log(line);
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
                         (unsigned long long)calls, za_cg_names[c], (unsigned long long)za_tsc_ticks_ns(ticks, hz),
                         za_cg_names[c], (unsigned long long)za_tsc_ticks_ns(max, hz));
        if (w < 0) return n;
        n += (size_t)w < cap - n ? (size_t)w : cap - n - 1;
    }
    const int on = __atomic_load_n(&za_ck_on, __ATOMIC_ACQUIRE);
    long long drift = 0;
    if (on) {  /* (unclamped: the TSC-derived value against one real reading, both now) */
        struct timespec ts;
        const uint64_t a = za_ck_fenced_tsc();
        __real_clock_gettime(CLOCK_MONOTONIC, &ts);
        const uint64_t b = za_ck_fenced_tsc();
        const uint64_t mine = za_tsc_clock_ns(a + (b - a) / 2, za_ck_base_tsc, za_ck_base_ns, za_ck_hz);
        drift = (long long)mine - (long long)((uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec);
    }
    if (n < cap) {
        int w = snprintf(out + n, cap - n, " cg_tsc=%llu cg_game=%llu ck=%s ck_drift_ns=%lld cg_radv=%llu",
                         (unsigned long long)__atomic_exchange_n(&za_cg_tsc, 0, __ATOMIC_RELAXED),
                         (unsigned long long)__atomic_exchange_n(&za_cg_game, 0, __ATOMIC_RELAXED), on ? "tsc" : "real", drift,
                         (unsigned long long)__atomic_exchange_n(&za_cg_radv.calls, 0, __ATOMIC_RELAXED));
        if (w > 0) n += (size_t)w < cap - n ? (size_t)w : cap - n - 1;
    }
    return n;
}
