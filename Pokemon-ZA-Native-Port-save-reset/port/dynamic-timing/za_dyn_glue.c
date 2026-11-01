/* Port glue for the dynamic frame timing - a proposal for the next title build (see za_dyn_glue.h for the hook
 * sites). Not linked into any build yet; the host tests link it against stubs (test/test_glue.c).
 *
 * Environment (the title entry would map /app0/perf-r24-options.txt keys onto these, like r24-prof does):
 *   ZA_DT_POLICY=off|safe|rc3   off (default): H1 returns za_title_frame_cfg(original) - r16's trial and the
 *                               r24-prof force60 wrap keep working unchanged; H2/H3-H5 pass through.
 *                               safe: the recommended controller. rc3: RC3.0's decisions on these hooks.
 *   ZA_DT_LOG=<seconds>         one [za-dyn] status line per period (default 2; 0: switches only)
 *   ZA_DT_SUB60=1               experiment: steps below 16.67 ms when frames are faster (needs 120 Hz pacing)
 *   ZA_DT_REGISTRY=0|1          override honor_registry (read the byte at main+0x610b980)
 *   ZA_DT_ANIM=table|step       H6/H7 (optional hooks): the animation-rate denominator stays the table value
 *                               (default), or gets the dynamic step as RC3's rewritten table gives it (A/B only)
 *   ZA_DT_STRESS_FPS=<20..60>   console test: hold the game at this frame rate (a limiter in H1; also with off)
 *   ZA_DT_STRESS_SPIKE_MS=<n> / ZA_DT_STRESS_SPIKE_EVERY=<frames>   console test: one long frame every N frames
 * With a policy other than off, dynamic owns the frame mode: za_title_frame_cfg (r16 trial, force60) is not
 * called. Time source: plat_now_ns() (CLOCK_MONOTONIC, or the TSC with LARECOMP_PS5_TSC=1) - the same clock the
 * runtime's present pacing and rt_ticks() (the game's nn::os::GetSystemTick) use. */
#include "za_dyn_glue.h"

#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "za_dyn_timing.h"

uint64_t plat_now_ns(void);
void plat_sleep_until_ns(uint64_t t);
int32_t za_title_frame_cfg(int32_t original);  /* r16 (port/performance-r16/performance.c), maybe --wrap'ed */
int sceKernelDebugOutText(int channel, const char *text);

/* The RC3 "flag": guest memory is mapped at its guest address in this port (runtime/cpu.h LD8 dereferences the
 * address), so the byte is read directly. Replaceable for the host tests. */
#ifndef ZA_DT_REGISTRY_ADDR
#define ZA_DT_REGISTRY_ADDR UINT64_C(0x700610b980)
#endif
static uint8_t za_dt_registry_guest(void) { return *(const volatile uint8_t *)(uintptr_t)ZA_DT_REGISTRY_ADDR; }
uint8_t (*za_dt_registry_reader)(void) = za_dt_registry_guest;

static ZaDtConfig g_cfg;
static ZaDtState g_st;
static _Atomic uint64_t g_pub;       /* za_dt_pack(decision) of the last H1; 0: inactive */
static _Atomic int g_policy = -1;    /* -1: not initialised */
static _Atomic uint64_t g_step_sub, g_step_pass;  /* H3-H5 calls that got the dynamic step / the table value */
static _Atomic uint64_t g_anim_calls, g_anim_same;  /* H6/H7 calls / of them with the frame's mode */
static bool g_anim_step;                           /* ZA_DT_ANIM=step */
static bool g_ready;
static uint32_t g_stress_fps, g_spike_ms, g_spike_every;
static uint64_t g_log_every_ns, g_log_at, g_release_ns, g_stress_frames;
static int32_t g_last_mode = -1;

static void za_dt_log(const char *fmt, ...) {
    char line[384];
    va_list ap;
    va_start(ap, fmt);
    vsnprintf(line, sizeof line, fmt, ap);
    va_end(ap);
    sceKernelDebugOutText(0, line);
}

static long za_dt_env_long(const char *name, long def, long lo, long hi) {
    const char *e = getenv(name);
    if (!e || !*e) return def;
    char *end = NULL;
    long v = strtol(e, &end, 10);
    if (!end || *end || v < lo || v > hi) return def;
    return v;
}

static const char *za_dt_policy_name(ZaDtPolicy p) {
    return p == ZA_DT_POLICY_SAFE ? "safe" : p == ZA_DT_POLICY_RC3_COMPAT ? "rc3" : "off";
}

void za_dt_init_from_env(void) {
    const char *e = getenv("ZA_DT_POLICY");
    ZaDtPolicy p = ZA_DT_POLICY_OFF;
    if (e && !strcmp(e, "safe")) p = ZA_DT_POLICY_SAFE;
    else if (e && !strcmp(e, "rc3")) p = ZA_DT_POLICY_RC3_COMPAT;
    else if (e && *e && strcmp(e, "off")) za_dt_log("[za-dyn] unknown ZA_DT_POLICY '%s': off\n", e);
    za_dt_config_default(&g_cfg, p);
    if (za_dt_env_long("ZA_DT_SUB60", 0, 0, 1)) g_cfg.allow_sub60_step = true;
    long reg = za_dt_env_long("ZA_DT_REGISTRY", -1, 0, 1);
    if (reg >= 0) g_cfg.honor_registry = reg != 0;
    const char *anim = getenv("ZA_DT_ANIM");
    g_anim_step = anim && !strcmp(anim, "step");
    g_log_every_ns = (uint64_t)za_dt_env_long("ZA_DT_LOG", 2, 0, 3600) * UINT64_C(1000000000);
    g_stress_fps = (uint32_t)za_dt_env_long("ZA_DT_STRESS_FPS", 0, 20, 60);
    g_spike_ms = (uint32_t)za_dt_env_long("ZA_DT_STRESS_SPIKE_MS", 0, 1, 5000);
    g_spike_every = (uint32_t)za_dt_env_long("ZA_DT_STRESS_SPIKE_EVERY", 0, 1, 100000);
    za_dt_reset(&g_st);
    atomic_store(&g_pub, 0);
    atomic_store(&g_step_sub, 0);
    atomic_store(&g_step_pass, 0);
    atomic_store(&g_anim_calls, 0);
    atomic_store(&g_anim_same, 0);
    g_log_at = g_release_ns = g_stress_frames = 0;
    g_last_mode = -1;
    g_ready = true;
    atomic_store(&g_policy, (int)p);
    if (p != ZA_DT_POLICY_OFF)
        za_dt_log("[za-dyn] policy=%s: dynamic owns the frame mode (r16 trial / force60 bypassed); present interval %s; "
                  "steps %s; registry byte %s; anim denominator %s; stress fps=%u spike=%ums/%u\n",
                  za_dt_policy_name(p), g_cfg.force_present_60 ? "1" : "mode+1",
                  g_cfg.allow_sub60_step ? "8.33..33.33 ms (sub60 experiment)" : "16.67..33.33 ms",
                  g_cfg.honor_registry ? "honoured" : "ignored",
                  g_anim_step ? "STEP (RC3-like experiment)" : "table", g_stress_fps, g_spike_ms, g_spike_every);
}

static void za_dt_status_line(uint64_t now, const ZaDtDecision *d, int32_t original, uint32_t variable_flag) {
    const ZaDtState *s = &g_st;
    za_dt_log("[za-dyn] mode=%d present=%d step_us=%.1f fps=%.2f ema_ms=%.3f lag_ms=%.2f sw=%llu/%llu gaps=%llu "
              "cap=%llu rb=%llu dup=%llu foreign=%llu adopt=%llu stand=%llu fast=%llu reg=%llu sim/wall=%.4f "
              "orig=%d var=%u steps=%llu/%llu anim=%llu/%llu t=%llu\n",
              d->active ? d->mode : -1, d->active ? d->present_mode : -1, (double)d->step_ns / 1000.0, s->fps,
              s->ema_ns / 1e6, s->lag_ns / 1e6, (unsigned long long)s->switches_down,
              (unsigned long long)s->switches_up, (unsigned long long)s->gaps, (unsigned long long)s->capped,
              (unsigned long long)s->rollbacks, (unsigned long long)s->duplicates, (unsigned long long)s->foreign,
              (unsigned long long)s->adoptions, (unsigned long long)s->standdowns,
              (unsigned long long)s->fast_frames, (unsigned long long)s->registry_frames,
              s->wall_ns > 0 ? s->sim_ns / s->wall_ns : 0.0, (int)original, (unsigned)variable_flag,
              (unsigned long long)atomic_exchange(&g_step_sub, 0), (unsigned long long)atomic_exchange(&g_step_pass, 0),
              (unsigned long long)atomic_exchange(&g_anim_calls, 0), (unsigned long long)atomic_exchange(&g_anim_same, 0),
              (unsigned long long)now);
}

static void za_dt_stress(uint64_t now) {
    g_stress_frames++;
    uint64_t until = now;
    if (g_stress_fps) until = za_dt_limiter_deadline(g_release_ns, now, g_stress_fps);
    if (g_spike_ms && g_spike_every && g_stress_frames % g_spike_every == 0)
        until = (until > now ? until : now) + (uint64_t)g_spike_ms * UINT64_C(1000000);
    if (until > now) plat_sleep_until_ns(until);
    if (g_stress_fps || g_spike_ms) g_release_ns = until > now ? until : now;
}

int32_t za_dt_frame_cfg(int32_t original, uint32_t variable_flag, uint64_t clock_obj) {
    if (!g_ready) za_dt_init_from_env();
    if (g_cfg.policy == ZA_DT_POLICY_OFF) {
        int32_t r = za_title_frame_cfg(original);
        /* (the stress knobs work here too: static 60 under a forced drop shows the slow motion to compare with) */
        if (g_stress_fps || g_spike_ms) za_dt_stress(plat_now_ns());
        return r;
    }
    uint64_t now = plat_now_ns();
    ZaDtInput in = {now, original, (uint8_t)variable_flag,
                    g_cfg.honor_registry ? za_dt_registry_reader() : (uint8_t)0, clock_obj};
    ZaDtDecision d = za_dt_frame(&g_st, &g_cfg, &in);
    atomic_store_explicit(&g_pub, za_dt_pack(&d), memory_order_release);
    int32_t shown = d.active ? d.mode : -1;
    if (shown != g_last_mode) {
        za_dt_log("[za-dyn] %s mode %d -> %d (fps %.2f, step %.3f ms, orig %d, var %u)\n",
                  d.active ? "dynamic" : "pass-through", (int)g_last_mode, (int)shown, g_st.fps,
                  (double)d.step_ns / 1e6, (int)original, (unsigned)variable_flag);
        g_last_mode = shown;
    }
    if (g_log_every_ns && now >= g_log_at) {
        za_dt_status_line(now, &d, original, variable_flag);
        g_log_at = now + g_log_every_ns;
    }
    if (g_stress_fps || g_spike_ms) za_dt_stress(now);
    return d.mode;
}

uint32_t za_dt_present_mode(uint32_t mode) {
    uint64_t w = atomic_load_explicit(&g_pub, memory_order_acquire);
    if (!(w >> 63)) return mode;
    ZaDtDecision d = za_dt_unpack(w);
    return (uint32_t)d.present_mode;
}

uint64_t za_dt_step_ns(int32_t mode, uint64_t original_ns) {
    uint64_t w = atomic_load_explicit(&g_pub, memory_order_acquire);
    if (!(w >> 63)) return original_ns;  /* (dynamic off or standing down: no counting, no cost) */
    ZaDtDecision d = za_dt_unpack(w);
    uint64_t step = za_dt_step_for(&d, mode, original_ns);
    bool sub = mode == d.mode && mode >= 0 && mode <= 1 && original_ns == za_dt_table_202[mode];
    atomic_fetch_add_explicit(sub ? &g_step_sub : &g_step_pass, 1, memory_order_relaxed);
    return step;
}

uint64_t za_dt_anim_table_ns(int32_t mode, uint64_t original_ns) {
    uint64_t w = atomic_load_explicit(&g_pub, memory_order_acquire);
    if (!(w >> 63)) return original_ns;
    ZaDtDecision d = za_dt_unpack(w);
    atomic_fetch_add_explicit(&g_anim_calls, 1, memory_order_relaxed);
    if (mode == d.mode) atomic_fetch_add_explicit(&g_anim_same, 1, memory_order_relaxed);
    /* default: the original table - rate = step / nominal, animations at wall-clock speed. The experiment hands the
     * dynamic step instead, as RC3's rewritten table does: rate ~ 1, animations at FPS/60 or FPS/30. */
    return g_anim_step ? za_dt_step_for(&d, mode, original_ns) : original_ns;
}

int za_dt_status(void) {
    if (atomic_load(&g_policy) <= 0) return -1;
    uint64_t w = atomic_load_explicit(&g_pub, memory_order_acquire);
    return (w >> 63) ? (int)((w >> 56) & 0x7f) : -1;
}
