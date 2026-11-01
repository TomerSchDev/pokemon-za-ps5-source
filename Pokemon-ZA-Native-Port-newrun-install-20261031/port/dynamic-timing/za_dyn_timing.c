/* Dynamic frame timing model (see za_dyn_timing.h). Pure C11. */
#include "za_dyn_timing.h"

#include <math.h>
#include <string.h>

const uint64_t za_dt_table_202[ZA_DT_TABLE_N] = {UINT64_C(16666667), UINT64_C(33333334), UINT64_C(50000000),
                                                 UINT64_C(66666667), UINT64_C(83333334)};

void za_dt_config_default(ZaDtConfig *c, ZaDtPolicy policy) {
    memset(c, 0, sizeof *c);
    c->policy = policy;
    c->alpha = 0.05;               /* RC3's 5 % new / 95 % old */
    c->enter30_below = 46;         /* RC3: fcmp (float)(int)fps, 46.0; csel lt */
    c->leave30_from = 46;
    c->nominal30_below = 31;       /* RC3: fmov s1, #31.0 */
    c->nominal60_from = 58;        /* RC3: fmov s1, #29.0; fadd s1, s1, s1 */
    c->key_timeout_ns = UINT64_C(500000000);
    c->force_present_60 = true;    /* RC3's SDK patch (swap interval 1) - without it mode 1 is held at 30 */
    c->min_step_ns = UINT64_C(8333333);
    c->prime_from_first = true;    /* (both presets: the mod's start from tick 0 is a defect, not a policy) */
    c->gap_ns = UINT64_C(250000000);
    if (policy == ZA_DT_POLICY_RC3_COMPAT) {
        /* The mod's decisions (thresholds, integer-FPS steps, no hysteresis, the registry byte), on this port's
         * consumer-correct hooks. Its start-up, stall and one-frame-delay defects are not reproduced. */
        c->quantize_fps = true;
        c->honor_registry = true;
    } else if (policy == ZA_DT_POLICY_SAFE) {
        c->leave30_from = 48;      /* hysteresis: enter mode 1 at 45 FPS and below, leave at 48 and above ... */
        c->min_dwell = 30;         /* ... held for 30 frames */
        c->nominal30_below = 0;    /* no snapping: 30..31 FPS would get 33.33 ms (up to 3.3 % fast) ... */
        c->nominal60_from = 0;     /* ... and 58..60 FPS 16.67 ms (up to 3.3 % slow) */
        c->sample_cap_ns = UINT64_C(50000000);
        c->drift_gain = 0.02;
        c->drift_max_frac = 0.05;
        c->drift_cap_ns = UINT64_C(100000000);
        c->burst_margin = 0.15;
    }
}

void za_dt_reset(ZaDtState *s) { memset(s, 0, sizeof *s); }

ZaDtDecision za_dt_passthrough(int32_t original_mode) {
    ZaDtDecision d = {false, original_mode, original_mode,
                      original_mode >= 0 && original_mode < ZA_DT_TABLE_N ? za_dt_table_202[original_mode] : 0};
    return d;
}

static double za_clampd(double v, double lo, double hi) { return v < lo ? lo : v > hi ? hi : v; }
static uint64_t za_nominal(int32_t mode) { return mode == 1 ? ZA_DT_NS_30 : ZA_DT_NS_60; }

static ZaDtDecision za_current(const ZaDtState *s, const ZaDtConfig *c) {
    ZaDtDecision d = {true, s->mode, c->force_present_60 ? 0 : s->mode, s->step_ns};
    return d;
}

static void za_unprime(ZaDtState *s) {
    s->primed = s->have_sample = s->active = s->skip_next = false;
    s->lag_ns = 0;
    s->dwell = s->up_streak = 0;
}

/* RC3's step from the integer FPS: (int)((1.0f / (float)fps) * 1e9f), in single precision as the mod computes it.
 * fps_i >= 1, so the value is at most 1e9: no overflow. */
static double za_quantized(int fps_i) {
    float s = 1.0f / (float)fps_i;
    s *= 1e9f;
    return (double)(int32_t)s;
}

ZaDtDecision za_dt_frame(ZaDtState *s, const ZaDtConfig *c, const ZaDtInput *in) {
    if (c->policy == ZA_DT_POLICY_OFF) {
        s->active = false;
        return za_dt_passthrough(in->original_mode);
    }
    /* The game asked for something else than 60/30 (a 20/15 FPS config), or its own variable-step path is on:
     * stand down - the original instruction's value and the original table. */
    if ((in->original_mode != 0 && in->original_mode != 1) || in->variable_flag) {
        if (s->primed) s->standdowns++, za_unprime(s);
        return za_dt_passthrough(in->original_mode);
    }
    s->frames++;
    if (!s->primed) {
        s->primed = s->active = true;
        s->key = in->key;
        s->last_ns = s->key_seen_ns = in->now_ns;
        s->mode = 0;
        s->step_ns = ZA_DT_NS_60;
        s->dwell = s->up_streak = 0;
        if (!(s->ema_ns > 0)) s->ema_ns = (double)ZA_DT_NS_60;
        s->fps = 1e9 / s->ema_ns;
        return za_current(s, c);
    }
    if (in->key != s->key) {
        /* Another frame-clock object. While the primary keeps ticking its calls are not samples (two calls a
         * frame would halve every period); once the primary is silent, the new one takes over. */
        if (in->now_ns > s->key_seen_ns && in->now_ns - s->key_seen_ns > c->key_timeout_ns) {
            s->adoptions++;
            s->key = in->key;
            s->key_seen_ns = s->last_ns = in->now_ns;
        } else {
            s->foreign++;
        }
        return za_current(s, c);
    }
    s->key_seen_ns = in->now_ns;
    if (in->now_ns <= s->last_ns) {  /* clock went back (TSC across cores) or no time passed: no sample */
        if (in->now_ns < s->last_ns) s->rollbacks++, s->skip_next = true;  /* the next delta spans the jump too */
        else s->duplicates++;
        s->last_ns = in->now_ns;
        return za_current(s, c);
    }
    uint64_t dt = in->now_ns - s->last_ns;
    s->last_ns = in->now_ns;
    if (s->skip_next) {
        s->skip_next = false;
        return za_current(s, c);
    }
    if (c->gap_ns && dt > c->gap_ns) {  /* load, suspend, pause of the process, clock jump: not a frame */
        s->gaps++;
        s->lag_ns = 0;
        return za_current(s, c);
    }
    double sample = (double)dt;
    if (c->sample_cap_ns && dt > c->sample_cap_ns) sample = (double)c->sample_cap_ns, s->capped++;
    if (!s->have_sample && c->prime_from_first) s->ema_ns = sample;
    else s->ema_ns = c->alpha * sample + (1.0 - c->alpha) * s->ema_ns;
    s->have_sample = true;
    s->samples++;
    s->fps = 1e9 / s->ema_ns;
    int fps_i = s->fps >= 1e6 ? 1000000 : (int)s->fps;  /* truncation, as the mod's fcvtzs */

    /* Mode: drops at once, returns only after min_dwell frames at leave30_from or above. */
    s->dwell++;
    if (s->mode == 0) {
        if (fps_i < c->enter30_below) s->mode = 1, s->switches_down++, s->dwell = 0, s->up_streak = 0;
    } else if (fps_i >= c->leave30_from) {
        if (++s->up_streak >= (c->min_dwell ? c->min_dwell : 1))
            s->mode = 0, s->switches_up++, s->dwell = 0, s->up_streak = 0;
    } else {
        s->up_streak = 0;
    }

    double base;
    if (s->mode == 1 && fps_i < c->nominal30_below)
        base = (double)ZA_DT_NS_30;
    else if (s->mode == 0 && c->nominal60_from > 0 && fps_i >= c->nominal60_from)
        base = (double)ZA_DT_NS_60;
    else
        base = c->quantize_fps && fps_i > 0 ? za_quantized(fps_i) : s->ema_ns;
    if (s->ema_ns < (double)ZA_DT_NS_60 * 0.97) {  /* faster than ~62 FPS: only possible without 60 Hz pacing */
        s->fast_frames++;
        if (c->allow_sub60_step && s->mode == 0) base = s->ema_ns;
    }
    bool registry = c->honor_registry && in->registry_byte;
    if (registry) base = (double)za_nominal(s->mode), s->registry_frames++;

    double lo = c->allow_sub60_step ? (double)c->min_step_ns : (double)ZA_DT_NS_60, hi = (double)ZA_DT_NS_30;
    double step = za_clampd(base, lo, hi);
    if (c->drift_gain > 0 && !registry) {
        double lim = c->drift_max_frac * step;
        step = za_clampd(step + za_clampd(c->drift_gain * s->lag_ns, -lim, lim), lo, hi);
    }
    if (c->burst_margin > 0) {  /* frames got faster than the EMA: do not fast-forward past the real frame */
        double most = (double)dt * (1.0 + c->burst_margin);
        if (step > most) step = most > lo ? most : lo;
    }
    s->step_ns = (uint64_t)llround(step);
    if (c->drift_gain > 0) {
        /* Owed: the frame up to the 30 step - time beyond it is forgiven, as the original 30 mode forgives it,
         * instead of being repaid later as fast motion. Being ahead of the wall clock (frames faster than the
         * floor) is carried for at most one 60 step. */
        double owed = sample < hi ? sample : hi;
        s->lag_ns = za_clampd(s->lag_ns + owed - (double)s->step_ns, -(double)ZA_DT_NS_60, (double)c->drift_cap_ns);
    }
    s->wall_ns += sample;
    s->sim_ns += (double)s->step_ns;
    s->active = true;
    return za_current(s, c);
}

uint64_t za_dt_step_for(const ZaDtDecision *d, int32_t mode, uint64_t original_ns) {
    if (!d->active || mode != d->mode || mode < 0 || mode > 1) return original_ns;
    if (original_ns != za_dt_table_202[mode]) return original_ns;  /* not the 2.0.2 table: leave it alone */
    return d->step_ns;
}

uint64_t za_dt_pack(const ZaDtDecision *d) {
    if (!d->active) return 0;
    return (UINT64_C(1) << 63) | ((uint64_t)((uint32_t)d->mode & 0x7f) << 56) |
           ((uint64_t)((uint32_t)d->present_mode & 0xff) << 48) | (d->step_ns & UINT64_C(0xffffffffffff));
}

ZaDtDecision za_dt_unpack(uint64_t w) {
    ZaDtDecision d = {(w >> 63) != 0, (int32_t)((w >> 56) & 0x7f), (int32_t)((w >> 48) & 0xff),
                      w & UINT64_C(0xffffffffffff)};
    return d;
}

float za_dt_anim_rate(uint64_t step_ns, uint64_t table_ns) {
    /* main_467.c f_7001015260: FP_SETD(0, fromint_d(step)), x8 = table[mode] - 1, FP_SETD(1, fromint_d(x8)),
     * d0 = d0 / d1, s8 = (float)d0 (signed 64-bit conversions). */
    return (float)((double)(int64_t)step_ns / (double)(int64_t)(table_ns - 1));
}

uint64_t za_dt_limiter_deadline(uint64_t last_release_ns, uint64_t now_ns, uint32_t fps) {
    if (!fps || !last_release_ns) return now_ns;
    uint64_t period = UINT64_C(1000000000) / fps, target = last_release_ns + period;
    if (target <= now_ns || target - now_ns > period) return now_ns;  /* late already, or the clock went back */
    return target;
}
