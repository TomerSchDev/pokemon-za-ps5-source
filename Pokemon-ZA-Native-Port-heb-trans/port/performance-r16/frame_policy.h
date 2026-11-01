#ifndef ZA_R16_FRAME_POLICY_H
#define ZA_R16_FRAME_POLICY_H
#include <stdint.h>
#include <stdbool.h>
enum { ZA_FPS_ORIGINAL, ZA_FPS_TRIAL, ZA_FPS_FALLBACK };
typedef struct {
    int mode;
    bool started;
    unsigned warm, slow, excluded;
    uint64_t now0, present0, last_now, builds0;
    double last_fps;
} ZaFramePolicy;
static inline void za_frame_arm(ZaFramePolicy *s, bool trial) {
    *s = (ZaFramePolicy){.mode = trial ? ZA_FPS_TRIAL : ZA_FPS_ORIGINAL};
}
/* Explicit arm from the in-game menu prevents startup from consuming warmup.
 * Low 32 bits: outstanding shader work (queued + running); upper bits: epoch.
 * A job completing between samples changes the epoch, even if pending is zero.
 * Gaps suspend eligibility; sustained normal-duration slow frames still count. */
static inline int32_t za_frame_step(ZaFramePolicy *s, int32_t original,
                                    uint64_t now, uint64_t presents, uint64_t builds) {
    if (s->mode != ZA_FPS_TRIAL) return original;
    bool reset = !s->started || now <= s->last_now || presents < s->present0 ||
                 now - s->last_now > UINT64_C(250000000) ||
                 (uint32_t)builds != 0 || builds != s->builds0;
    s->last_now = now;
    if (reset) {
        if (s->started) ++s->excluded;
        s->started = true; s->now0 = now; s->present0 = presents; s->builds0 = builds;
        s->warm = s->slow = 0;
        return 0;
    }
    if (now - s->now0 < UINT64_C(1000000000)) return 0;
    s->last_fps = (double)(presents - s->present0) * 1e9 / (double)(now - s->now0);
    s->now0 = now; s->present0 = presents;
    if (s->warm < 5) { ++s->warm; return 0; }
    s->slow = s->last_fps < 58.5 ? s->slow + 1 : 0;
    if (s->slow < 5) return 0;
    s->mode = ZA_FPS_FALLBACK;
    return original;
}
#endif
