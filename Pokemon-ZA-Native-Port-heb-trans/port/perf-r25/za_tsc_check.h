/* r25 clock=tsc: is the TSC one clock across the console's cores, and the TSC-derived CLOCK_MONOTONIC.
 *
 * The cross-core check. Two threads, pinned to two different CPUs, exchange TSC readings in rounds (a ping-pong over
 * shared memory, release/acquire ordered, each read fenced with lfence on both sides):
 *   A reads t1 and publishes it;  B, after seeing it, reads t2, then t3, and publishes both;  A, after seeing them,
 *   reads t4.
 * With one clock across the two cores every reading taken after another one on the other core is at least as large:
 * t2 >= t1 and t4 >= t3. A reading below the one it causally follows went backwards across cores. And B's offset from A
 * (d = B's clock - A's clock) lies strictly between t3 - t4 and t2 - t1 in every round, so over all rounds
 * delta_lo = max(t3 - t4) < d < delta_hi = min(t2 - t1); |d| <= max(|delta_lo|, |delta_hi|) bounds the skew (the bound
 * includes one cross-core latency; with synchronized TSCs it is about that latency).
 * The decision (za_tsc_decide) accepts only if every pair ran pinned, no round timed out, no reading went backwards by
 * more than max_back ticks, the bounds are consistent and the skew bound is at most max_skew ticks.
 *
 * The clock. While accepted, CLOCK_MONOTONIC = base_ns + (tsc - base_tsc) in ns (base taken from the real clock
 * once), and readings are clamped to the largest one returned so far across all threads (za_tsc_monotonic), so a
 * residual sub-microsecond skew can never make a caller's later reading smaller than an earlier one.
 *
 * Pure parts (za_tsc_pair_feed, za_tsc_decide, za_tsc_ticks_ns, za_tsc_clock_ns, za_tsc_monotonic) and the threaded
 * runner (za_tsc_run_pair) are all here, so test/test_tsc_check.c runs the same code on the host with fake skewed
 * clocks. */
#pragma once
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define ZA_TSC_MAX_PAIRS 16

typedef struct {
    int cpu_a, cpu_b, pinned;      /* pinned: both threads were pinned to their CPU */
    unsigned rounds;               /* completed rounds */
    uint64_t back_ab, back_ba;     /* rounds with t2 < t1 / with t4 < t3 */
    uint64_t max_back;             /* largest backwards step (ticks) */
    int64_t delta_lo, delta_hi;    /* bounds of B - A (ticks) */
    uint64_t min_rtt;              /* smallest t4 - t1 (ticks) */
    int timed_out;
} ZaTscPair;

typedef struct {
    unsigned pairs;
    ZaTscPair pair[ZA_TSC_MAX_PAIRS];
    uint64_t max_back, max_skew, min_rtt;
    int all_pinned, timed_out, inconsistent, accept;
    const char *reason;
} ZaTscReport;

static void za_tsc_pair_begin(ZaTscPair *p, int cpu_a, int cpu_b) {
    memset(p, 0, sizeof *p);
    p->cpu_a = cpu_a, p->cpu_b = cpu_b;
    p->delta_lo = INT64_MIN, p->delta_hi = INT64_MAX;
    p->min_rtt = UINT64_MAX;
}

static void za_tsc_pair_feed(ZaTscPair *p, uint64_t t1, uint64_t t2, uint64_t t3, uint64_t t4) {
    if (t2 < t1) { p->back_ab++; if (t1 - t2 > p->max_back) p->max_back = t1 - t2; }
    if (t4 < t3) { p->back_ba++; if (t3 - t4 > p->max_back) p->max_back = t3 - t4; }
    const int64_t hi = (int64_t)(t2 - t1), lo = (int64_t)(t3 - t4);
    if (hi < p->delta_hi) p->delta_hi = hi;
    if (lo > p->delta_lo) p->delta_lo = lo;
    if (t4 >= t1 && t4 - t1 < p->min_rtt) p->min_rtt = t4 - t1;
    p->rounds++;
}

static uint64_t za_tsc_abs64(int64_t v) { return v < 0 ? (uint64_t)0 - (uint64_t)v : (uint64_t)v; }

static void za_tsc_decide(ZaTscReport *r, uint64_t max_back, uint64_t max_skew) {
    r->max_back = r->max_skew = 0;
    r->min_rtt = UINT64_MAX;
    r->all_pinned = r->pairs > 0;
    r->timed_out = r->inconsistent = 0;
    for (unsigned i = 0; i < r->pairs; i++) {
        const ZaTscPair *p = &r->pair[i];
        if (!p->pinned) r->all_pinned = 0;
        if (p->timed_out || !p->rounds) r->timed_out = 1;
        if (p->max_back > r->max_back) r->max_back = p->max_back;
        if (p->min_rtt < r->min_rtt) r->min_rtt = p->min_rtt;
        if (p->rounds && p->delta_lo >= p->delta_hi) r->inconsistent = 1;
        if (p->rounds) {
            const uint64_t a = za_tsc_abs64(p->delta_lo), b = za_tsc_abs64(p->delta_hi), s = a > b ? a : b;
            if (s > r->max_skew) r->max_skew = s;
        }
    }
    r->accept = 0;
    if (!r->pairs) r->reason = "no CPU pair measured";
    else if (!r->all_pinned) r->reason = "threads could not be pinned to their CPUs";
    else if (r->timed_out) r->reason = "a round timed out";
    else if (r->max_back > max_back) r->reason = "a TSC reading went backwards across cores beyond the bound";
    else if (r->inconsistent) r->reason = "inconsistent offset bounds (the TSCs moved apart during the check)";
    else if (r->max_skew > max_skew) r->reason = "the skew bound exceeds the limit";
    else r->accept = 1, r->reason = "accepted";
}

/* ---- the threaded runner */
typedef uint64_t (*ZaTscRead)(void);   /* a fenced TSC read */
typedef int (*ZaTscPin)(int cpu);       /* pin the calling thread to cpu; 0 on success */

typedef struct {
    ZaTscPair *p;
    ZaTscRead read_a, read_b;
    ZaTscPin pin;
    unsigned rounds;
    uint64_t timeout;                    /* ticks (of read_a) a round may take */
    int pinned_a, pinned_b;
    int ready, phase, abort;             /* (__atomic builtins) phase: 0 A's turn, 1 B's turn, 2 A reads the reply */
    uint64_t t1, t2, t3;
} ZaTscRun;

static void *za_tsc_thread_b(void *arg) {
    ZaTscRun *r = arg;
    r->pinned_b = r->pin ? r->pin(r->p->cpu_b) == 0 : 0;
    __atomic_fetch_add(&r->ready, 1, __ATOMIC_ACQ_REL);
    for (unsigned i = 0; i < r->rounds; i++) {
        while (__atomic_load_n(&r->phase, __ATOMIC_ACQUIRE) != 1)
            if (__atomic_load_n(&r->abort, __ATOMIC_ACQUIRE)) return NULL;
        const uint64_t t2 = r->read_b();
        const uint64_t t3 = r->read_b();
        __atomic_store_n(&r->t2, t2, __ATOMIC_RELAXED);
        __atomic_store_n(&r->t3, t3, __ATOMIC_RELAXED);
        __atomic_store_n(&r->phase, 2, __ATOMIC_RELEASE);
    }
    return NULL;
}

static void *za_tsc_thread_a(void *arg) {
    ZaTscRun *r = arg;
    r->pinned_a = r->pin ? r->pin(r->p->cpu_a) == 0 : 0;
    __atomic_fetch_add(&r->ready, 1, __ATOMIC_ACQ_REL);
    while (__atomic_load_n(&r->ready, __ATOMIC_ACQUIRE) < 2) {}
    for (unsigned i = 0; i < r->rounds; i++) {
        const uint64_t t1 = r->read_a();
        __atomic_store_n(&r->t1, t1, __ATOMIC_RELAXED);
        __atomic_store_n(&r->phase, 1, __ATOMIC_RELEASE);
        while (__atomic_load_n(&r->phase, __ATOMIC_ACQUIRE) != 2) {
            if (r->read_a() - t1 > r->timeout) {
                r->p->timed_out = 1;
                __atomic_store_n(&r->abort, 1, __ATOMIC_RELEASE);
                return NULL;
            }
        }
        const uint64_t t4 = r->read_a();
        za_tsc_pair_feed(r->p, t1, __atomic_load_n(&r->t2, __ATOMIC_RELAXED), __atomic_load_n(&r->t3, __ATOMIC_RELAXED), t4);
        __atomic_store_n(&r->phase, 0, __ATOMIC_RELEASE);
    }
    return NULL;
}

/* One pair: two new threads (the caller is never pinned). 0, or the pthread_create error. */
static int za_tsc_run_pair(ZaTscPair *p, int cpu_a, int cpu_b, unsigned rounds, ZaTscRead read_a, ZaTscRead read_b,
                           ZaTscPin pin, uint64_t timeout) {
    za_tsc_pair_begin(p, cpu_a, cpu_b);
    ZaTscRun r;
    memset(&r, 0, sizeof r);
    r.p = p, r.read_a = read_a, r.read_b = read_b, r.pin = pin, r.rounds = rounds, r.timeout = timeout;
    pthread_t a, b;
    int e = pthread_create(&b, NULL, za_tsc_thread_b, &r);
    if (e) { p->timed_out = 1; return e; }
    e = pthread_create(&a, NULL, za_tsc_thread_a, &r);
    if (e) {
        __atomic_store_n(&r.abort, 1, __ATOMIC_RELEASE);
        pthread_join(b, NULL);
        p->timed_out = 1;
        return e;
    }
    pthread_join(a, NULL);
    __atomic_store_n(&r.abort, 1, __ATOMIC_RELEASE);  /* (B is done, or stuck after A timed out) */
    pthread_join(b, NULL);
    p->pinned = r.pinned_a && r.pinned_b;
    return 0;
}

/* ---- the clock */
static uint64_t za_tsc_ticks_ns(uint64_t ticks, uint64_t hz) {
    return hz ? (uint64_t)(((unsigned __int128)ticks * 1000000000ull) / hz) : 0;
}

/* base_ns + (tsc - base_tsc) in ns; a reading slightly before the base (another core) counts back from base_ns. */
static uint64_t za_tsc_clock_ns(uint64_t tsc, uint64_t base_tsc, uint64_t base_ns, uint64_t hz) {
    if (tsc >= base_tsc) return base_ns + za_tsc_ticks_ns(tsc - base_tsc, hz);
    const uint64_t back = za_tsc_ticks_ns(base_tsc - tsc, hz);
    return back < base_ns ? base_ns - back : 0;
}

/* Never below the largest value returned so far (across threads). */
static uint64_t za_tsc_monotonic(uint64_t *last, uint64_t ns) {  /* (*last: __atomic builtins only) */
    uint64_t seen = __atomic_load_n(last, __ATOMIC_RELAXED);
    while (ns > seen) {
        if (__atomic_compare_exchange_n(last, &seen, ns, 1, __ATOMIC_RELAXED, __ATOMIC_RELAXED)) return ns;
    }
    return ns > seen ? ns : seen;
}
