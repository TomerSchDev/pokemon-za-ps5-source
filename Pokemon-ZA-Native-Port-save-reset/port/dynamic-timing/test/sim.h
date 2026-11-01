/* Test helpers: a virtual clock, the port's present pacing, and checks. Host only. */
#ifndef ZA_DT_TEST_SIM_H
#define ZA_DT_TEST_SIM_H
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

static int g_failures, g_checks;
#define CHECK(cond, ...)                                                       \
    do {                                                                       \
        g_checks++;                                                            \
        if (!(cond)) {                                                         \
            g_failures++;                                                      \
            fprintf(stderr, "FAIL %s:%d: %s: ", __FILE__, __LINE__, #cond);    \
            fprintf(stderr, __VA_ARGS__);                                      \
            fputc('\n', stderr);                                               \
        }                                                                      \
    } while (0)
#define NEAR(a, b, tol) (fabs((double)(a) - (double)(b)) <= (double)(tol))

#define MS(x) ((uint64_t)((x) * 1e6 + 0.5))
#define SEC UINT64_C(1000000000)

/* The port's present pacing (runtime/nvn/objects.c present_pace): sleep until `next` unless more than a period
 * late, then next += interval * 16,666,667. interval 0: no pacing. */
typedef struct {
    uint64_t now, next;
} VClock;

static inline uint64_t vclock_frame(VClock *k, uint64_t cost_ns, int interval) {
    uint64_t start = k->now, t = start + cost_ns;
    if (interval > 0) {
        uint64_t period = UINT64_C(16666667) * (uint64_t)(interval > 4 ? 1 : interval);
        if (k->next > t && k->next - t <= period) t = k->next;
        else k->next = t;
        k->next += period;
    }
    k->now = t;
    return t - start;
}

/* Deterministic pseudo-random numbers for jitter. */
static uint32_t g_lcg = 12345u;
static inline double lcg_unit(void) {
    g_lcg = g_lcg * 1664525u + 1013904223u;
    return (double)(g_lcg >> 8) / (double)(1u << 24);
}

#endif
