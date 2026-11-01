/* Host test of za_clock_r25.c's radv_threaded path (the file included, the PS5 imports stubbed): with radv_threaded on,
 * the clock reads of RADV's recording worker (radv_threaded_replaying) are counted in cg_radv alone, take the real call
 * under clock=real and the TSC without the cross-thread clamp under clock=tsc; everyone else's reads, the render
 * thread's even while it replays (the layer's fallback), and every read with radv_threaded off, are counted and
 * clamped as before. Then a worker thread and the render thread together (run under TSan too). */
#define _GNU_SOURCE
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static uint64_t fake_tsc = 1000000;  /* sceKernelReadTsc: +10 a read (1 GHz: 10 ns) */
static uint64_t real_calls;          /* the real clock's calls */
static __thread int replaying;       /* radv_threaded_replaying() of this thread */
#define REAL_NS 5000000000ull        /* what the real clock answers */

uint64_t sceKernelReadTsc(void) { return __atomic_add_fetch(&fake_tsc, 10, __ATOMIC_RELAXED); }
uint64_t sceKernelGetTscFrequency(void) { return 1000000000ull; }
int sceKernelDebugOutText(int channel, const char *text) { (void)channel; (void)text; return 0; }
int __real_clock_gettime(clockid_t id, struct timespec *ts) {
    (void)id;
    __atomic_add_fetch(&real_calls, 1, __ATOMIC_RELAXED);
    ts->tv_sec = (time_t)(REAL_NS / 1000000000ull);
    ts->tv_nsec = (long)(REAL_NS % 1000000000ull);
    return 0;
}
void __real_za_prof_note_render(void) {}
void __real_za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio) { (void)gid; (void)entry; (void)prio; }
void __real_za_prof_thread_end(void) {}
_Bool radv_threaded_replaying(void) { return replaying; }

#include "../za_clock_r25.c"

static uint64_t ns_of(const struct timespec *ts) { return (uint64_t)ts->tv_sec * 1000000000ull + (uint64_t)ts->tv_nsec; }
static uint64_t calls(int c) { return __atomic_load_n(&za_cg_calls[c], __ATOMIC_RELAXED); }
static uint64_t radv(void) { return __atomic_load_n(&za_cg_radv.calls, __ATOMIC_RELAXED); }
static uint64_t key(const char *report, const char *name) {  /* " name=<value>" in the report */
    char pat[64];
    snprintf(pat, sizeof pat, " %s=", name);
    const char *p = strstr(report, pat);
    CHECK(p);
    return strtoull(p + strlen(pat), NULL, 10);
}

#define WORKER_CALLS 200000u
static void *worker(void *arg) {  /* RADV's recording worker spinning on the clock */
    (void)arg;
    replaying = 1;
    struct timespec ts;
    for (unsigned i = 0; i < WORKER_CALLS; i++) CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    return NULL;
}

int main(void) {
    struct timespec ts;
    /* radv_threaded off: even a replaying thread is r25's ordinary path (counted, the real call under clock=real) */
    replaying = 1;
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0 && ns_of(&ts) == REAL_NS);
    CHECK(calls(ZA_CG_OTHER) == 1 && radv() == 0 && real_calls == 1);

    /* on, clock=real: the worker's read is the real call, counted in cg_radv only */
    za_clock_r25_radv_threaded();
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0 && ns_of(&ts) == REAL_NS);
    CHECK(calls(ZA_CG_OTHER) == 1 && radv() == 1 && real_calls == 2);
    replaying = 0;  /* another (non-render, non-guest) thread: as before */
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    CHECK(calls(ZA_CG_OTHER) == 2 && radv() == 1 && real_calls == 3);

    /* clock=tsc (set as za_clock_r25_enable would after an accepted check), another thread already at 9 s */
    za_ck_hz = 1000000000ull;
    za_ck_base_tsc = __atomic_load_n(&fake_tsc, __ATOMIC_RELAXED);
    za_ck_base_ns = 7000000000ull;
    __atomic_store_n(&za_ck_last, 9000000000ull, __ATOMIC_RELAXED);
    __atomic_store_n(&za_ck_on, 1, __ATOMIC_RELEASE);
    replaying = 1;
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
    CHECK(ns_of(&ts) > 7000000000ull && ns_of(&ts) < 7000001000ull);       /* the TSC, unclamped */
    CHECK(__atomic_load_n(&za_ck_last, __ATOMIC_RELAXED) == 9000000000ull);  /* the clamp untouched */
    CHECK(real_calls == 3 && za_cg_tsc == 0 && radv() == 2 && calls(ZA_CG_OTHER) == 2);
    CHECK(__wrap_clock_gettime(CLOCK_REALTIME, &ts) == 0 && real_calls == 4 && radv() == 3);  /* other ids: real */
    replaying = 0;
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0 && ns_of(&ts) >= 9000000000ull);  /* clamped, as before */
    CHECK(za_cg_tsc == 1 && calls(ZA_CG_OTHER) == 3 && radv() == 3);

    /* the render thread is never the worker, even replaying (the layer records itself when it cannot allocate) */
    __wrap_za_prof_note_render();
    replaying = 1;
    CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0 && ns_of(&ts) >= 9000000000ull);
    CHECK(calls(ZA_CG_RENDER) == 1 && radv() == 3 && za_cg_tsc == 2);

    /* the report: cg_radv last, then reset */
    char out[1024];
    za_clock_report(out, sizeof out);
    CHECK(key(out, "cg_radv") == 3 && key(out, "cg_render") == 1 && key(out, "cg_other") == 3 && key(out, "cg_tsc") == 2);
    CHECK(strstr(out, " ck=tsc ") != NULL);
    za_clock_report(out, sizeof out);
    CHECK(key(out, "cg_radv") == 0 && key(out, "cg_other") == 0);

    /* a worker thread spinning while the render thread reads: every worker read in cg_radv, none elsewhere */
    replaying = 0;
    pthread_t t;
    CHECK(pthread_create(&t, NULL, worker, NULL) == 0);
    for (unsigned i = 0; i < 1000; i++) CHECK(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0 && ns_of(&ts) >= 9000000000ull);
    CHECK(pthread_join(t, NULL) == 0);
    za_clock_report(out, sizeof out);
    CHECK(key(out, "cg_radv") == WORKER_CALLS && key(out, "cg_render") == 1000 && key(out, "cg_other") == 0);
    printf("PASS za_clock_r25.c radv_threaded: RADV's worker in cg_radv only, unclamped TSC / real call, others unchanged\n");
    return 0;
}
