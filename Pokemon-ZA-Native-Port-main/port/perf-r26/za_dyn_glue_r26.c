/* r26: the dynamic frame timing glue, linked into the title. A copy of port/dynamic-timing/za_dyn_glue.c (the hook
 * functions H1-H7, the policies, the [za-dyn] lines and the stress knobs are unchanged) with two additions:
 *   - window accounting in H1 for every policy, off included: frames, wall time between H1 calls (gaps over 250 ms
 *     left out), the simulation time handed out (the step of the returned mode - the dynamic step when dynamic owns
 *     the frame, the duration table's value otherwise), a smoothed frame time, mode switches and visible step changes;
 *   - za_dt_report(): those, as key=value pairs for exec.c's [za-r24-perf] line (render thread, reads atomics only).
 * The step / anim counters are cumulative here (the original exchanged them to 0 at each [za-dyn] line); the [za-dyn]
 * line prints differences against its own snapshot, so the two readers don't take counts from each other.
 *
 * Environment (the title entry maps /app0/perf-r24-options.txt keys onto these; port/perf-r26/za_r26_options.h):
 *   ZA_DT_POLICY=off|safe|rc3   off (default): H1 returns za_title_frame_cfg(original) - r16's trial and the
 *                               r24-prof force60 wrap keep working unchanged; H2/H3-H5 pass through.
 *                               safe: the recommended controller. rc3: RC3.0's decisions on these hooks.
 *   ZA_DT_LOG=<seconds>         one [za-dyn] status line per period (default 2; 0: switches only)
 *   ZA_DT_SUB60=1               experiment: steps below 16.67 ms when frames are faster (needs 120 Hz pacing)
 *   ZA_DT_REGISTRY=0|1          override honor_registry (read the byte at main+0x610b980)
 *   ZA_DT_ANIM=table|step       H6/H7: the animation-rate denominator stays the table value (default), or gets the
 *                               dynamic step as RC3's rewritten table gives it (A/B only)
 *   ZA_DT_STRESS_FPS=<20..60>   console test: hold the game at this frame rate (a limiter in H1; also with off)
 *   ZA_DT_STRESS_SPIKE_MS=<n> / ZA_DT_STRESS_SPIKE_EVERY=<frames>   console test: one long frame every N frames
 *   ZA_R26_DYN_REQUESTED        (set by the title entry) the dyn= value asked for, shown when force60 overrode it
 * With a policy other than off, dynamic owns the frame mode: za_title_frame_cfg (r16 trial, force60) is not
 * called. Time source: plat_now_ns() - the clock the runtime's present pacing and rt_ticks() use. */
#include "za_dyn_glue_r26.h"

#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../dynamic-timing/za_dyn_timing.h"

uint64_t plat_now_ns(void);
void plat_sleep_until_ns(uint64_t t);
int32_t za_title_frame_cfg(int32_t original);  /* r16 (port/performance-r16/performance.c), --wrap'ed by r24-prof */
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
static _Atomic uint64_t g_step_sub, g_step_pass;  /* cumulative: H3-H5 calls that got the dynamic step / the table */
static _Atomic uint64_t g_anim_calls, g_anim_same;  /* cumulative: H6/H7 calls / of them with the frame's mode */
static uint64_t g_ls_sub, g_ls_pass, g_ls_calls, g_ls_same;  /* the [za-dyn] line's snapshot (H1 thread) */
static bool g_anim_step;                           /* ZA_DT_ANIM=step */
static bool g_ready;
static uint32_t g_stress_fps, g_spike_ms, g_spike_every;
static uint64_t g_log_every_ns, g_log_at, g_release_ns, g_stress_frames;
static int32_t g_last_mode = -1;

/* r26 window accounting (written by H1 only; published through atomics for za_dt_report) */
#define ZA_R26_GAP_NS UINT64_C(250000000)      /* the model's gap: loads, pauses, clock jumps are not frames */
#define ZA_R26_STEPCHG_NS UINT64_C(500000)     /* a step change of at least 0.5 ms counts as a visible change */
static uint64_t g_acc_last_ns, g_acc_prev_step;
static double g_acc_ema_ns;
static int32_t g_acc_last_mode = INT32_MIN;
static _Atomic uint64_t g_r26_frames, g_r26_wall_ns, g_r26_sim_ns, g_r26_gaps, g_r26_sw, g_r26_stepchg;
static _Atomic uint64_t g_r26_ema_ns, g_r26_step_ns;
static _Atomic int g_r26_mode = -1;

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
    /* (the counters stay cumulative - za_dt_report keeps its own snapshot on another thread; the [za-dyn] line
     * starts from the current values) */
    g_ls_sub = atomic_load(&g_step_sub), g_ls_pass = atomic_load(&g_step_pass);
    g_ls_calls = atomic_load(&g_anim_calls), g_ls_same = atomic_load(&g_anim_same);
    g_log_at = g_release_ns = g_stress_frames = 0;
    g_last_mode = -1;
    g_acc_last_ns = g_acc_prev_step = 0;
    g_acc_ema_ns = 0;
    g_acc_last_mode = INT32_MIN;
    g_ready = true;
    atomic_store(&g_policy, (int)p);
    if (p != ZA_DT_POLICY_OFF)
        za_dt_log("[za-dyn] policy=%s: dynamic owns the frame mode (r16 trial / force60 bypassed); present interval %s; "
                  "steps %s; registry byte %s; anim denominator %s; stress fps=%u spike=%ums/%u\n",
                  za_dt_policy_name(p), g_cfg.force_present_60 ? "1" : "mode+1",
                  g_cfg.allow_sub60_step ? "8.33..33.33 ms (sub60 experiment)" : "16.67..33.33 ms",
                  g_cfg.honor_registry ? "honoured" : "ignored",
                  g_anim_step ? "STEP (RC3-like experiment)" : "table", g_stress_fps, g_spike_ms, g_spike_every);
    /* (policy off logs nothing here, as the original glue: the title entry's [za-r26] line says what was decided) */
}

static void za_dt_status_line(uint64_t now, const ZaDtDecision *d, int32_t original, uint32_t variable_flag) {
    const ZaDtState *s = &g_st;
    uint64_t sub = atomic_load(&g_step_sub), pass = atomic_load(&g_step_pass);
    uint64_t calls = atomic_load(&g_anim_calls), same = atomic_load(&g_anim_same);
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
              (unsigned long long)(sub - g_ls_sub), (unsigned long long)(pass - g_ls_pass),
              (unsigned long long)(calls - g_ls_calls), (unsigned long long)(same - g_ls_same),
              (unsigned long long)now);
    g_ls_sub = sub, g_ls_pass = pass, g_ls_calls = calls, g_ls_same = same;
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

/* r26: one frame of the window accounting (H1 thread). `step` is the duration the game's update groups get for
 * `mode` this frame (0: unknown mode). */
static void za_r26_account(uint64_t now, int32_t mode, uint64_t step) {
    if (g_acc_last_ns && now > g_acc_last_ns) {
        uint64_t dt = now - g_acc_last_ns;
        if (dt <= ZA_R26_GAP_NS) {
            atomic_fetch_add_explicit(&g_r26_frames, 1, memory_order_relaxed);
            atomic_fetch_add_explicit(&g_r26_wall_ns, dt, memory_order_relaxed);
            atomic_fetch_add_explicit(&g_r26_sim_ns, step, memory_order_relaxed);
            g_acc_ema_ns = g_acc_ema_ns > 0 ? g_acc_ema_ns + 0.05 * ((double)dt - g_acc_ema_ns) : (double)dt;
            atomic_store_explicit(&g_r26_ema_ns, (uint64_t)g_acc_ema_ns, memory_order_relaxed);
        } else {
            atomic_fetch_add_explicit(&g_r26_gaps, 1, memory_order_relaxed);
        }
    }
    g_acc_last_ns = now;
    if (mode != g_acc_last_mode) {
        if (g_acc_last_mode != INT32_MIN) atomic_fetch_add_explicit(&g_r26_sw, 1, memory_order_relaxed);
        g_acc_last_mode = mode;
    }
    if (g_acc_prev_step &&
        (step > g_acc_prev_step ? step - g_acc_prev_step : g_acc_prev_step - step) >= ZA_R26_STEPCHG_NS)
        atomic_fetch_add_explicit(&g_r26_stepchg, 1, memory_order_relaxed);
    g_acc_prev_step = step;
    atomic_store_explicit(&g_r26_mode, (int)mode, memory_order_relaxed);
    atomic_store_explicit(&g_r26_step_ns, step, memory_order_relaxed);
}

long long za_dt_llround(double x) {
    return x < 0 ? -(long long)(-x + 0.5) : (long long)(x + 0.5);
}

static uint64_t za_r26_table_step(int32_t mode) {
    return mode >= 0 && mode < ZA_DT_TABLE_N ? za_dt_table_202[mode] : 0;
}

int32_t za_dt_frame_cfg(int32_t original, uint32_t variable_flag, uint64_t clock_obj) {
    if (!g_ready) za_dt_init_from_env();
    if (g_cfg.policy == ZA_DT_POLICY_OFF) {
        int32_t r = za_title_frame_cfg(original);
        uint64_t now = plat_now_ns();
        za_r26_account(now, r, za_r26_table_step(r));
        /* (the stress knobs work here too: static 60 under a forced drop shows the slow motion to compare with) */
        if (g_stress_fps || g_spike_ms) za_dt_stress(now);
        return r;
    }
    uint64_t now = plat_now_ns();
    ZaDtInput in = {now, original, (uint8_t)variable_flag,
                    g_cfg.honor_registry ? za_dt_registry_reader() : (uint8_t)0, clock_obj};
    ZaDtDecision d = za_dt_frame(&g_st, &g_cfg, &in);
    atomic_store_explicit(&g_pub, za_dt_pack(&d), memory_order_release);
    za_r26_account(now, d.mode, d.active ? d.step_ns : za_r26_table_step(d.mode));
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

/* r26: the window since the previous call, for exec.c's [za-r24-perf] line (render thread; the only caller).
 *   dyn           the policy in effect: off / safe / rc3, init before the first frame-mode read
 *   dyn_req       the dyn= key as asked for (differs from dyn when force60 overrode it), - when absent
 *   dyn_mode      the frame mode H1 returned last (0: the 60 mode, 1: the 30 mode); -1 before the first frame
 *   dyn_step_ns   the step the update groups got with it (the dynamic step, or the duration table's value)
 *   dyn_ema_ns    the smoothed frame time (EMA 0.05 of the time between frame-mode reads)
 *   dyn_frames / dyn_wall_ns / dyn_sim_ns   frames in the window, their wall time, the simulation time handed out
 *   dyn_drift_ns  wall - sim over the window: > 0 the game fell behind the clock (slow motion), < 0 ran ahead
 *   dyn_simwall   sim / wall over the window (1.0000: real time)
 *   dyn_sw        frame-mode switches; dyn_stepchg  frames whose step changed by 0.5 ms or more
 *   dyn_gaps      frame-mode reads more than 250 ms apart (loads, pauses), left out of the window
 *   dyn_steps     H3-H5 calls that got the dynamic step / the table value (0/0 while dynamic is off)
 *   dyn_anim      H6/H7 calls / of them with the frame's mode (0/0 while dynamic is off) */
size_t za_dt_report(char *out, size_t cap) {
    static uint64_t l_frames, l_wall, l_sim, l_gaps, l_sw, l_chg, l_sub, l_pass, l_calls, l_same;
#define ZA_R26_DELTA(cur, last) ((cur) >= (last) ? (cur) - (last) : (cur))
    uint64_t frames = atomic_load_explicit(&g_r26_frames, memory_order_relaxed);
    uint64_t wall = atomic_load_explicit(&g_r26_wall_ns, memory_order_relaxed);
    uint64_t sim = atomic_load_explicit(&g_r26_sim_ns, memory_order_relaxed);
    uint64_t gaps = atomic_load_explicit(&g_r26_gaps, memory_order_relaxed);
    uint64_t sw = atomic_load_explicit(&g_r26_sw, memory_order_relaxed);
    uint64_t chg = atomic_load_explicit(&g_r26_stepchg, memory_order_relaxed);
    uint64_t sub = atomic_load_explicit(&g_step_sub, memory_order_relaxed);
    uint64_t pass = atomic_load_explicit(&g_step_pass, memory_order_relaxed);
    uint64_t calls = atomic_load_explicit(&g_anim_calls, memory_order_relaxed);
    uint64_t same = atomic_load_explicit(&g_anim_same, memory_order_relaxed);
    uint64_t dframes = ZA_R26_DELTA(frames, l_frames), dwall = ZA_R26_DELTA(wall, l_wall),
             dsim = ZA_R26_DELTA(sim, l_sim);
    int pol = atomic_load(&g_policy);
    const char *req = getenv("ZA_R26_DYN_REQUESTED");
    int n = snprintf(out, cap,
                     " dyn=%s dyn_req=%s dyn_mode=%d dyn_step_ns=%llu dyn_ema_ns=%llu dyn_frames=%llu dyn_wall_ns=%llu"
                     " dyn_sim_ns=%llu dyn_drift_ns=%lld dyn_simwall=%.4f dyn_sw=%llu dyn_stepchg=%llu dyn_gaps=%llu"
                     " dyn_steps=%llu/%llu dyn_anim=%llu/%llu",
                     pol < 0 ? "init" : za_dt_policy_name((ZaDtPolicy)pol), req && *req ? req : "-",
                     atomic_load_explicit(&g_r26_mode, memory_order_relaxed),
                     (unsigned long long)atomic_load_explicit(&g_r26_step_ns, memory_order_relaxed),
                     (unsigned long long)atomic_load_explicit(&g_r26_ema_ns, memory_order_relaxed),
                     (unsigned long long)dframes, (unsigned long long)dwall, (unsigned long long)dsim,
                     (long long)dwall - (long long)dsim, dwall ? (double)dsim / (double)dwall : 0.0,
                     (unsigned long long)ZA_R26_DELTA(sw, l_sw), (unsigned long long)ZA_R26_DELTA(chg, l_chg),
                     (unsigned long long)ZA_R26_DELTA(gaps, l_gaps), (unsigned long long)ZA_R26_DELTA(sub, l_sub),
                     (unsigned long long)ZA_R26_DELTA(pass, l_pass), (unsigned long long)ZA_R26_DELTA(calls, l_calls),
                     (unsigned long long)ZA_R26_DELTA(same, l_same));
#undef ZA_R26_DELTA
    l_frames = frames, l_wall = wall, l_sim = sim, l_gaps = gaps, l_sw = sw, l_chg = chg;
    l_sub = sub, l_pass = pass, l_calls = calls, l_same = same;
    return n < 0 ? 0 : (size_t)n;
}
