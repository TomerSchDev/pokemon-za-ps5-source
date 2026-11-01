/* Host tests for za_tsc_check.h: the round arithmetic and the decision on synthetic readings, the threaded runner on
 * the host's real TSC (pinned to two CPUs) and with fake skewed clocks for one side, and the TSC-derived clock
 * (base, readings before the base, the cross-thread monotonic clamp). */
#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
#include <x86intrin.h>

#include "../za_tsc_check.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static uint64_t rd(void) { _mm_lfence(); uint64_t t = __rdtsc(); _mm_lfence(); return t; }
static uint64_t rd_behind(void) { return rd() - 400000; }   /* B 400k ticks behind A */
static uint64_t rd_ahead(void) { return rd() + 400000; }    /* B 400k ticks ahead of A */
static int pin(int cpu) {
    cpu_set_t s;
    CPU_ZERO(&s);
    CPU_SET(cpu, &s);
    return pthread_setaffinity_np(pthread_self(), sizeof s, &s);
}
static int no_pin(int cpu) { (void)cpu; return -1; }

static void test_arithmetic(void) {
    ZaTscReport r;
    memset(&r, 0, sizeof r);
    r.pairs = 1;
    ZaTscPair *p = &r.pair[0];
    za_tsc_pair_begin(p, 0, 1);
    /* synchronized clocks, ~100-tick one-way latency */
    for (uint64_t i = 0; i < 100; i++) za_tsc_pair_feed(p, 1000 * i, 1000 * i + 100, 1000 * i + 110, 1000 * i + 210);
    p->pinned = 1;
    CHECK(p->rounds == 100 && p->back_ab == 0 && p->back_ba == 0 && p->max_back == 0);
    CHECK(p->delta_hi == 100 && p->delta_lo == -100 && p->min_rtt == 210);
    za_tsc_decide(&r, 1600, 3200);
    CHECK(r.accept && r.max_skew == 100);
    /* B 5000 ticks behind: its reading after A's is smaller - backwards beyond a 1600-tick bound */
    za_tsc_pair_begin(p, 0, 1);
    p->pinned = 1;
    for (uint64_t i = 0; i < 10; i++) za_tsc_pair_feed(p, 100000 + 1000 * i, 100000 + 1000 * i + 100 - 5000, 100000 + 1000 * i + 110 - 5000, 100000 + 1000 * i + 210);
    CHECK(p->back_ab == 10 && p->max_back == 4900);
    za_tsc_decide(&r, 1600, 100000);
    CHECK(!r.accept && strstr(r.reason, "backwards"));
    za_tsc_decide(&r, 5000, 100000);  /* (within a looser bound: accepted on that criterion, skew 5100 < 100000) */
    CHECK(r.accept && r.max_skew == 5100);
    za_tsc_decide(&r, 5000, 3200);    /* the skew bound then refuses */
    CHECK(!r.accept && strstr(r.reason, "skew"));
    /* unpinned, timed out, nothing measured */
    p->pinned = 0;
    za_tsc_decide(&r, 1 << 30, 1 << 30);
    CHECK(!r.accept && strstr(r.reason, "pinned"));
    p->pinned = 1, p->timed_out = 1;
    za_tsc_decide(&r, 1 << 30, 1 << 30);
    CHECK(!r.accept && strstr(r.reason, "timed out"));
    r.pairs = 0;
    za_tsc_decide(&r, 1 << 30, 1 << 30);
    CHECK(!r.accept);
    /* inconsistent bounds: a clock that moved during the check */
    r.pairs = 1;
    za_tsc_pair_begin(p, 0, 1);
    p->pinned = 1;
    za_tsc_pair_feed(p, 1000, 1100, 1110, 1210);          /* d in (-100, 100) */
    za_tsc_pair_feed(p, 5000, 5000 + 100 + 300, 5000 + 110 + 300, 5000 + 210 + 100);  /* d in (200, 400) */
    za_tsc_decide(&r, 1 << 30, 1 << 30);
    CHECK(!r.accept && r.inconsistent);
    printf("PASS round arithmetic and decision (synchronized, behind, loose/strict bounds, unpinned, timeout, inconsistent)\n");
}

static void test_runner(void) {
    if (sysconf(_SC_NPROCESSORS_ONLN) < 2) { printf("SKIP runner: one CPU\n"); return; }
    const uint64_t hz_guess = 2000000000ull;  /* (only bounds the per-round timeout here) */
    ZaTscReport r;
    memset(&r, 0, sizeof r);
    r.pairs = 1;
    CHECK(za_tsc_run_pair(&r.pair[0], 0, 1, 2000, rd, rd, pin, hz_guess / 10) == 0);
    CHECK(r.pair[0].rounds == 2000 && !r.pair[0].timed_out);
    za_tsc_decide(&r, 2000 /* ~1 us */, 200000 /* ~100 us: a VM's cross-core latency */);
    printf("     host TSC cpu0<->cpu1: pinned=%d backwards=%llu/%llu offset in (%lld, %lld) ticks, min rtt %llu: %s\n",
           r.pair[0].pinned, (unsigned long long)r.pair[0].back_ab, (unsigned long long)r.pair[0].back_ba,
           (long long)r.pair[0].delta_lo, (long long)r.pair[0].delta_hi, (unsigned long long)r.pair[0].min_rtt, r.reason);
    CHECK(r.pair[0].back_ab == 0 && r.pair[0].back_ba == 0);  /* the host's TSC is one clock */
    CHECK(r.pair[0].delta_lo < r.pair[0].delta_hi);
    /* B's clock behind: backwards detected, refused */
    CHECK(za_tsc_run_pair(&r.pair[0], 0, 1, 500, rd, rd_behind, pin, hz_guess / 10) == 0);
    za_tsc_decide(&r, 2000, 1u << 31);
    CHECK(r.pair[0].back_ab == 500 && !r.accept);
    /* B's clock ahead: nothing goes backwards A->B, but B->A does (t4 < t3) - refused; the skew bound alone too */
    CHECK(za_tsc_run_pair(&r.pair[0], 0, 1, 500, rd, rd_ahead, pin, hz_guess / 10) == 0);
    za_tsc_decide(&r, 2000, 200000);
    CHECK(r.pair[0].back_ba == 500 && !r.accept);
    /* threads that cannot be pinned: refused whatever the readings */
    CHECK(za_tsc_run_pair(&r.pair[0], 0, 1, 200, rd, rd, no_pin, hz_guess / 10) == 0);
    za_tsc_decide(&r, 2000, 200000);
    CHECK(!r.pair[0].pinned && !r.accept);
    printf("PASS threaded runner: host TSC, a side behind / ahead (refused), unpinned (refused)\n");
}

typedef struct { uint64_t *last; uint64_t base; int bad; } Mono;
static void *mono_thread(void *arg) {
    Mono *m = arg;
    uint64_t prev = 0;
    for (uint64_t i = 0; i < 200000; i++) {
        /* inputs jitter backwards by up to 50 around a rising value */
        const uint64_t in = m->base + i * 10 - (i * 7919 % 50);
        const uint64_t out = za_tsc_monotonic(m->last, in);
        if (out < prev || out < in) m->bad++;
        prev = out;
    }
    return NULL;
}

static void test_clock(void) {
    const uint64_t hz = 1596300204ull;
    CHECK(za_tsc_ticks_ns(hz, hz) == 1000000000ull);
    CHECK(za_tsc_ticks_ns(1596300, hz) == 999999);  /* (rounds down) */
    CHECK(za_tsc_ticks_ns(0, 0) == 0);
    const uint64_t base_tsc = 50ull * hz, base_ns = 7000000000ull;
    CHECK(za_tsc_clock_ns(base_tsc, base_tsc, base_ns, hz) == base_ns);
    CHECK(za_tsc_clock_ns(base_tsc + hz, base_tsc, base_ns, hz) == base_ns + 1000000000ull);
    CHECK(za_tsc_clock_ns(base_tsc - hz / 1000, base_tsc, base_ns, hz) == base_ns - 999999ull);  /* before the base (hz/1000 ticks: 999,999.9 ns, rounded down) */
    CHECK(za_tsc_clock_ns(0, base_tsc, 5, hz) == 0);  /* (never below zero) */
    /* very large spans: 128-bit arithmetic */
    CHECK(za_tsc_clock_ns(base_tsc + 3600ull * 24 * 365 * hz, base_tsc, base_ns, hz) == base_ns + 3600ull * 24 * 365 * 1000000000ull);
    uint64_t last = 0;
    CHECK(za_tsc_monotonic(&last, 100) == 100 && za_tsc_monotonic(&last, 90) == 100 && za_tsc_monotonic(&last, 120) == 120);
    last = 0;
    Mono m[4];
    pthread_t t[4];
    for (int i = 0; i < 4; i++) { m[i] = (Mono){&last, 1000000, 0}; CHECK(pthread_create(&t[i], NULL, mono_thread, &m[i]) == 0); }
    for (int i = 0; i < 4; i++) { pthread_join(t[i], NULL); CHECK(m[i].bad == 0); }
    printf("PASS TSC-derived clock: scaling, readings before the base, 128-bit spans, monotonic clamp across 4 threads\n");
}

int main(void) {
    test_arithmetic();
    test_runner();
    test_clock();
    printf("PASS za_tsc_check.h\n");
    return 0;
}
