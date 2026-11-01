#ifndef ZA_TITLE_PERFORMANCE_H
#define ZA_TITLE_PERFORMANCE_H
#include <stdint.h>
#include <stdbool.h>

/* An opt-in static-60 trial, with a one-way return to the original frame mode.
 * Missing/invalid profile preserves the original game instruction exactly.
 * No GPU counter/DRS settings or persistent user settings are changed. */
typedef struct {
    bool enabled, started, fell_back;
    unsigned warm, slow;
    uint64_t t0, p0;
    double last_fps;
} ZaPerformance;

static inline int32_t za_performance_step(ZaPerformance *s, int32_t original,
                                         uint64_t now, uint64_t presents) {
    if (!s->enabled || s->fell_back) return original;
    if (!s->started) {
        s->started = true; s->t0 = now; s->p0 = presents;
        return 0;
    }
    if (now < s->t0 || presents < s->p0) {
        s->fell_back = true; return original;
    }
    if (now - s->t0 < UINT64_C(1000000000)) return 0;
    s->last_fps = (double)(presents - s->p0) * 1e9 / (double)(now - s->t0);
    s->t0 = now; s->p0 = presents;
    if (s->warm < 5) { s->warm++; return 0; }
    s->slow = s->last_fps < 58.5 ? s->slow + 1 : 0;
    if (s->slow < 5) return 0;
    s->fell_back = true;
    return original;
}
#endif
