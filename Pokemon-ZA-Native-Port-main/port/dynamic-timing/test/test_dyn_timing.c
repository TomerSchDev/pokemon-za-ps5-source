/* Host tests of the dynamic-timing model (za_dyn_timing.c) against the port's present pacing, and of the
 * instruction-faithful RC3.0 model (za_rc3_reference.c) on the same scenarios, so the differences are measured.
 * No game, no console: a virtual clock. Build/run: test/run-tests.sh. */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../za_dyn_timing.h"
#include "../za_rc3_reference.h"
#include "sim.h"

typedef uint64_t (*CostFn)(uint64_t i, const void *ctx);

typedef struct {
    CostFn cost;
    const void *ctx;
    uint64_t frames, warmup;
    int pace;                                            /* 1: present interval = present_mode + 1; 0: none */
    int32_t original;                                    /* the config byte (1 on the Switch 1 build) */
    uint8_t variable_flag;
    uint8_t (*registry)(uint64_t i);
    uint64_t (*observe)(uint64_t i, uint64_t true_now);  /* the clock the hook sees */
    int two_keys;                                        /* a second frame clock calls every frame */
    uint64_t key_switch_at;                              /* from this frame on only key B calls (0: never) */
} Scenario;

typedef struct {
    double sim_ns, wall_ns, anim_min, anim_max;
    uint64_t frames, mode1_frames, min_step, max_step, max_jump, burst_frames, last_step;
    int last_mode, last_present;
} Run;

static uint64_t g_all_min = UINT64_MAX, g_all_max;  /* every step handed out by a non-sub60 model run */

static void run_init(Run *r) {
    memset(r, 0, sizeof *r);
    r->min_step = UINT64_MAX;
    r->anim_min = 1e9;
    r->anim_max = -1e9;
}

/* step_i is the time the game simulates for the frame that just ended (wall_{i-1}). */
static void run_account(Run *r, uint64_t i, const Scenario *sc, uint64_t step, uint64_t prev_step,
                        uint64_t prev_wall, double anim_advance_ns) {
    if (i == 0 || i < sc->warmup) return;
    r->frames++;
    if (prev_wall < SEC / 4) {  /* sim/wall over real frames; loads, suspends and clock jumps are not frames */
        r->sim_ns += (double)step;
        r->wall_ns += (double)prev_wall;
    }
    if (step < r->min_step) r->min_step = step;
    if (step > r->max_step) r->max_step = step;
    uint64_t jump = step > prev_step ? step - prev_step : prev_step - step;
    if (prev_step && jump > r->max_jump) r->max_jump = jump;
    if (prev_wall < SEC / 4) {
        if ((double)step > 1.25 * (double)prev_wall) r->burst_frames++;  /* fast motion: sim > 1.25 x wall */
        double a = anim_advance_ns / (double)prev_wall;
        if (a < r->anim_min) r->anim_min = a;
        if (a > r->anim_max) r->anim_max = a;
    }
}

static Run run_model(ZaDtState *s, const ZaDtConfig *c, const Scenario *sc) {
    Run r;
    run_init(&r);
    VClock k = {SEC, 0};
    uint64_t prev_wall = 0, prev_step = 0;
    for (uint64_t i = 0; i < sc->frames; i++) {
        uint64_t seen = sc->observe ? sc->observe(i, k.now) : k.now;
        uint64_t key = sc->key_switch_at && i >= sc->key_switch_at ? 0xB : 0xA;
        ZaDtInput in = {seen, sc->original, sc->variable_flag, sc->registry ? sc->registry(i) : 0, key};
        ZaDtDecision d = za_dt_frame(s, c, &in);
        if (sc->two_keys) {
            ZaDtInput in2 = in;
            in2.key = 0xB;
            in2.now_ns = seen + MS(0.3);  /* the second clock ticks a little later in the same frame */
            (void)za_dt_frame(s, c, &in2);
        }
        int32_t m = d.mode;
        uint64_t table = m >= 0 && m < ZA_DT_TABLE_N ? za_dt_table_202[m] : 0;
        uint64_t step = za_dt_step_for(&d, m, table);  /* what SetFrameMode hands every group */
        /* animation consumer (f_7001015260): the ORIGINAL table stays the denominator in this design */
        double anim = table ? (double)za_dt_anim_rate(step, table) * (double)table : 0;
        run_account(&r, i, sc, step, prev_step, prev_wall, anim);
        if (!c->allow_sub60_step && d.active) {
            if (step < g_all_min) g_all_min = step;
            if (step > g_all_max) g_all_max = step;
        }
        if (m == 1 && i >= sc->warmup) r.mode1_frames++;
        r.last_mode = m;
        r.last_present = d.present_mode;
        r.last_step = step;
        prev_step = step;
        int interval = sc->pace ? d.present_mode + 1 : 0;
        prev_wall = vclock_frame(&k, sc->cost(i, sc->ctx), interval);
    }
    return r;
}

static Run run_rc3(ZaRc3 *m, const Scenario *sc, uint64_t uptime_ns) {
    Run r;
    run_init(&r);
    VClock k = {SEC, 0};
    uint64_t prev_wall = 0, prev_step = 0;
    for (uint64_t i = 0; i < sc->frames; i++) {
        uint64_t seen = sc->observe ? sc->observe(i, k.now) : k.now;
        ZaRc3Frame f = za_rc3_frame(m, za_rc3_ticks_from_ns(seen + uptime_ns), sc->registry ? sc->registry(i) : 0);
        /* the animation consumer reads the REWRITTEN entry; one nominal frame is the original entry */
        double anim = (double)za_dt_anim_rate(f.step_ns, m->table[f.mode_used]) * (double)za_dt_table_202[f.mode_used];
        run_account(&r, i, sc, f.step_ns, prev_step, prev_wall, anim);
        if (f.mode_used == 1 && i >= sc->warmup) r.mode1_frames++;
        r.last_mode = f.mode_used;
        r.last_step = f.step_ns;
        prev_step = f.step_ns;
        /* the SDK patch forces swap interval 1: nothing holds mode 1 at 30 */
        prev_wall = vclock_frame(&k, sc->cost(i, sc->ctx), sc->pace ? 1 : 0);
    }
    return r;
}

static double ratio(const Run *r) { return r->wall_ns > 0 ? r->sim_ns / r->wall_ns : 0; }

/* ---------------------------------------------------------------- scenarios */
static uint64_t cost_const(uint64_t i, const void *ctx) {
    (void)i;
    return *(const uint64_t *)ctx;
}
typedef struct { uint64_t a, b, at, until; } Window;  /* b in [at, until), a elsewhere */
static uint64_t cost_window(uint64_t i, const void *ctx) {
    const Window *t = ctx;
    return i >= t->at && i < t->until ? t->b : t->a;
}
typedef struct { uint64_t a, b, len; } Alt;
static uint64_t cost_alt(uint64_t i, const void *ctx) {
    const Alt *t = ctx;
    return (i / t->len) % 2 ? t->b : t->a;
}
typedef struct { uint64_t mid, spread; } Jitter;
static uint64_t cost_jitter(uint64_t i, const void *ctx) {
    (void)i;
    const Jitter *j = ctx;
    return j->mid - j->spread + (uint64_t)(lcg_unit() * 2.0 * (double)j->spread);
}
static uint64_t obs_back(uint64_t i, uint64_t now) { return i == 300 ? now - MS(21.7) : now; }
static uint64_t obs_back10s(uint64_t i, uint64_t now) { return i >= 300 ? now - 10 * SEC : now; }
static uint64_t obs_fwd10s(uint64_t i, uint64_t now) { return i >= 300 ? now + 10 * SEC : now; }
static uint8_t reg_window(uint64_t i) { return i >= 400 && i < 500; }

static Scenario scenario(CostFn f, const void *ctx, uint64_t frames) {
    Scenario sc = {f, ctx, frames, 200, 1, 1, 0, NULL, NULL, 0, 0};
    return sc;
}

static ZaDtConfig cfg(ZaDtPolicy p) {
    ZaDtConfig c;
    za_dt_config_default(&c, p);
    return c;
}

/* ---------------------------------------------------------------- tests */
static void test_basics(void) {
    CHECK(za_dt_table_202[0] == 16666667 && za_dt_table_202[1] == 33333334 && za_dt_table_202[2] == 50000000 &&
              za_dt_table_202[3] == 66666667 && za_dt_table_202[4] == 83333334,
          "table");
    ZaDtDecision d = {true, 1, 0, UINT64_C(22222222)};
    ZaDtDecision u = za_dt_unpack(za_dt_pack(&d));
    CHECK(u.active && u.mode == 1 && u.present_mode == 0 && u.step_ns == 22222222, "pack");
    ZaDtDecision off = {false, 1, 1, 33333334};
    CHECK(za_dt_pack(&off) == 0 && !za_dt_unpack(0).active, "inactive packs to 0");
    CHECK(za_dt_step_for(&d, 1, 33333334) == 22222222, "matching mode gets the dynamic step");
    CHECK(za_dt_step_for(&d, 0, 16666667) == 16666667, "another mode keeps the table");
    CHECK(za_dt_step_for(&d, 1, 33333333) == 33333333, "an unknown table value is left alone");
    CHECK(za_dt_step_for(&d, 3, 66666667) == 66666667, "modes 2..4 untouched");
    CHECK(za_dt_step_for(&off, 1, 33333334) == 33333334, "inactive passes through");
    ZaDtDecision p = za_dt_passthrough(2);
    CHECK(!p.active && p.mode == 2 && p.present_mode == 2 && p.step_ns == 50000000, "passthrough 2");
    CHECK(za_dt_passthrough(-1).step_ns == 0, "passthrough of an unknown mode");
    CHECK(za_dt_limiter_deadline(0, 100, 40) == 100, "limiter: first frame");
    CHECK(za_dt_limiter_deadline(SEC, SEC + MS(5), 40) == SEC + 25000000, "limiter: holds to 25 ms");
    CHECK(za_dt_limiter_deadline(SEC, SEC + MS(30), 40) == SEC + MS(30), "limiter: late, no wait");
    CHECK(za_dt_limiter_deadline(SEC, SEC - MS(30), 40) == SEC - MS(30), "limiter: clock back, no wait");
    CHECK(NEAR(za_dt_anim_rate(33333334, 16666667), 2.0, 1e-6), "anim rate 2x");
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    CHECK(c.alpha == 0.05 && c.enter30_below == 46 && c.leave30_from == 48 && c.min_dwell == 30 &&
              c.nominal30_below == 0 && c.nominal60_from == 0 && c.gap_ns == 250000000 &&
              c.sample_cap_ns == 50000000 && c.force_present_60 && !c.honor_registry && !c.quantize_fps &&
              c.burst_margin == 0.15 && c.drift_gain == 0.02,
          "safe defaults");
    c = cfg(ZA_DT_POLICY_RC3_COMPAT);
    CHECK(c.leave30_from == 46 && c.min_dwell == 0 && c.quantize_fps && c.honor_registry && c.drift_gain == 0 &&
              c.burst_margin == 0 && c.sample_cap_ns == 0 && c.nominal30_below == 31 && c.nominal60_from == 58,
          "rc3-compat defaults");
    puts("PASS basics: table, packing, step_for, passthrough, limiter, anim rate, presets");
}

static void test_rc3_reference_decode(void) {
    ZaRc3 m;
    za_rc3_init(&m);
    volatile float zero = 0.0f;
    CHECK(za_rc3_fcvtzs(1e20f) == INT32_MAX && za_rc3_fcvtzs(-1e20f) == INT32_MIN &&
              za_rc3_fcvtzs(zero / zero) == 0 && za_rc3_fcvtzs(-3.7f) == -3,
          "fcvtzs");
    /* first call: previous tick 0, so dt = uptime: 100 s -> EMA 5 s -> 0 FPS -> mode 1 for the NEXT call */
    ZaRc3Frame f = za_rc3_frame(&m, za_rc3_ticks_from_ns(100 * SEC), 0);
    CHECK(f.mode_used == 0 && f.next_mode == 1 && f.step_ns == 16666667, "first call uses the initial mode 0");
    CHECK(NEAR(m.s30_ema_s, 5.0, 1e-9) && m.s60_fps_i == 0.0f && m.table[1] == 33333334, "uptime sample");
    CHECK(m.s80_ns_lo == (uint32_t)INT32_MAX, "1/0 FPS saturates (inf -> INT32_MAX)");
    /* 50 FPS steady: the 60 entry becomes 1e9/50 and the mode stays 0 */
    za_rc3_init(&m);
    m.s30_ema_s = 0.02;
    uint64_t t = 100 * SEC;
    m.s18_prev_tick = (double)(int64_t)za_rc3_ticks_from_ns(t);
    for (int i = 0; i < 50; i++) t += 20000000, f = za_rc3_frame(&m, za_rc3_ticks_from_ns(t), 0);
    CHECK(f.mode_used == 0 && m.table[0] == 20000000 && m.table[1] == 33333334 && f.step_ns == 20000000,
          "50 FPS: table[0]=%llu", (unsigned long long)m.table[0]);
    /* registry byte set: the active entry goes back to the original */
    f = za_rc3_frame(&m, za_rc3_ticks_from_ns(t += 20000000), 1);
    CHECK(m.table[0] == 16666667 && f.step_ns == 16666667, "flag forces the original 60 entry");
    puts("PASS rc3 reference: helper decode (fcvtzs, tick-0 start, 50 FPS entry, flag)");
}

static void test_steady_rates(void) {
    puts("     fps   frame_ms | SAFE mode sim/wall step_ms | RC3-exact mode sim/wall step_ms | anim speed SAFE / RC3");
    const double fps_list[] = {25, 30, 31, 35, 40, 44, 45, 46, 47, 50, 55, 57, 58, 59, 60};
    for (size_t n = 0; n < sizeof fps_list / sizeof *fps_list; n++) {
        double fps = fps_list[n];
        uint64_t cost = (uint64_t)(1e9 / fps + 0.5);
        if (fps >= 59.999) cost = MS(10);  /* 60: work ends early, the present pacing holds 16.67 ms */
        Scenario sc = scenario(cost_const, &cost, 3000);
        ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
        ZaDtState s;
        za_dt_reset(&s);
        Run a = run_model(&s, &c, &sc);
        ZaRc3 m;
        za_rc3_init(&m);
        Run b = run_rc3(&m, &sc, 100 * SEC);
        double frame_ms = (double)(fps >= 59.999 ? 16666667 : cost) / 1e6;
        printf("     %4.0f  %8.3f | %d  %.4f  %7.3f | %d  %.4f  %7.3f | %.3f / %.3f\n", fps, frame_ms, a.last_mode,
               ratio(&a), (double)a.last_step / 1e6, b.last_mode, ratio(&b), (double)b.last_step / 1e6,
               (a.anim_min + a.anim_max) / 2, (b.anim_min + b.anim_max) / 2);
        if (fps >= 31) {
            CHECK(NEAR(ratio(&a), 1.0, 0.01), "SAFE %.0f FPS: sim/wall %.4f", fps, ratio(&a));
            CHECK(NEAR(a.anim_min, 1.0, 0.012) && NEAR(a.anim_max, 1.0, 0.012), "SAFE %.0f FPS anim %.4f..%.4f",
                  fps, a.anim_min, a.anim_max);
        } else {
            CHECK(a.last_mode == 1 && NEAR(a.last_step, ZA_DT_NS_30, 3), "%.0f FPS: the original 30 step (%llu)",
                  fps, (unsigned long long)a.last_step);
            CHECK(NEAR(ratio(&a), 33333334.0 / (double)cost, 0.002), "%.0f FPS floor %.4f", fps, ratio(&a));
        }
        CHECK(a.last_mode == (fps < 46 ? 1 : 0), "SAFE %.0f FPS mode %d", fps, a.last_mode);
        CHECK(a.last_present == 0, "present interval 1 while dynamic");
        CHECK(s.switches_up == 0 && s.switches_down <= 1, "SAFE %.0f FPS: switches %llu/%llu", fps,
              (unsigned long long)s.switches_down, (unsigned long long)s.switches_up);
        /* RC3's documented error bands (code-derived, not measured on a console) */
        if (fps == 58 || fps == 59) CHECK(ratio(&b) < 0.985, "RC3 %.0f FPS snaps to 16.67 ms: %.4f", fps, ratio(&b));
        if (fps == 50) CHECK(NEAR(b.anim_max, 0.8333, 0.01), "RC3 50 FPS anim %.4f (RC1.1: 16.67%% slower)", b.anim_max);
        if (fps == 55) CHECK(NEAR(b.anim_max, 16666667.0 / 18181818.0, 0.01), "RC3 55 FPS anim %.4f", b.anim_max);
        if (fps == 45) CHECK(b.anim_max > 1.4, "RC3 45 FPS anim %.4f (mode 1: faster)", b.anim_max);
        if (fps == 40) CHECK(NEAR(b.anim_max, 1.3333, 0.02), "RC3 40 FPS anim %.4f", b.anim_max);
        if (fps == 31) CHECK(NEAR(b.anim_max, 33333334.0 / 32258065.0, 0.01), "RC3 31 FPS anim %.4f", b.anim_max);
    }
    /* RC1.1's published 33 FPS figure (+10%) */
    uint64_t c33 = (uint64_t)(1e9 / 33 + 0.5);
    Scenario sc = scenario(cost_const, &c33, 2000);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b = run_rc3(&m, &sc, 100 * SEC);
    CHECK(NEAR(b.anim_max, 1.10, 0.01), "RC3 33 FPS anim %.4f (RC1.1: 10%% faster)", b.anim_max);
    puts("PASS steady 25..60 FPS: SAFE tracks wall clock within 1% (31..60) and keeps animations at 1.0;"
         " RC3 snapping/anim errors reproduced");
}

static void test_transitions(void) {
    Window w = {MS(10), MS(22.222), 600, 1200};  /* 60 -> 45 -> 60 */
    Scenario sc = scenario(cost_window, &w, 1800);
    sc.warmup = 100;
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(s.switches_down == 1 && s.switches_up == 1, "SAFE 60/45/60 switches %llu/%llu",
          (unsigned long long)s.switches_down, (unsigned long long)s.switches_up);
    CHECK(NEAR(ratio(&a), 1.0, 0.005), "SAFE transition sim/wall %.4f", ratio(&a));
    /* (the largest change is the burst bound cutting the step to 1.15 x the first fast frame) */
    CHECK(a.max_jump < MS(4), "step continuity: max jump %.3f ms", (double)a.max_jump / 1e6);
    CHECK(a.burst_frames == 0, "no fast-motion frames (%llu)", (unsigned long long)a.burst_frames);
    /* latency of the drop: frames from the change to mode 1 */
    ZaDtState s2;
    za_dt_reset(&s2);
    Scenario sc2 = sc;
    sc2.frames = 600 + 80;
    Run a2 = run_model(&s2, &c, &sc2);
    CHECK(a2.last_mode == 1 && a2.mode1_frames >= 20, "drop to mode 1 within 60 frames (%llu frames in mode 1)",
          (unsigned long long)a2.mode1_frames);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b = run_rc3(&m, &sc, 100 * SEC);
    printf("     60->45->60: SAFE sim/wall %.4f max jump %.3f ms | RC3 sim/wall %.4f max jump %.3f ms\n", ratio(&a),
           (double)a.max_jump / 1e6, ratio(&b), (double)b.max_jump / 1e6);
    puts("PASS transitions 60->45->60: one switch each way, continuous step, no fast-motion frames");
}

static void test_oscillation(void) {
    Alt alt = {MS(19.5), MS(24.0), 30};  /* EMA swings ~43..49 FPS around the 46 threshold */
    Scenario sc = scenario(cost_alt, &alt, 2400);
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(s.switches_down == 1 && s.switches_up == 0, "SAFE hysteresis: %llu/%llu",
          (unsigned long long)s.switches_down, (unsigned long long)s.switches_up);
    CHECK(NEAR(ratio(&a), 1.0, 0.01), "SAFE oscillation sim/wall %.4f", ratio(&a));
    ZaDtConfig r3 = cfg(ZA_DT_POLICY_RC3_COMPAT);
    ZaDtState s3;
    za_dt_reset(&s3);
    (void)run_model(&s3, &r3, &sc);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b = run_rc3(&m, &sc, 100 * SEC);
    CHECK(s3.switches_down + s3.switches_up >= 40, "RC3 thresholds flip-flop: %llu",
          (unsigned long long)(s3.switches_down + s3.switches_up));
    printf("     46-FPS oscillation: SAFE switches %llu, RC3-compat switches %llu, RC3-exact sim/wall %.4f\n",
           (unsigned long long)(s.switches_down + s.switches_up), (unsigned long long)(s3.switches_down + s3.switches_up),
           ratio(&b));
    puts("PASS oscillation around 46 FPS: SAFE switches once (hysteresis), RC3 thresholds flip every segment");
}

static void test_stalls(void) {
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    /* a 2 s stall (loading, shader build) in steady 60 */
    Window w = {MS(10), 2 * SEC, 300, 301};
    Scenario sc = scenario(cost_window, &w, 900);
    sc.warmup = 250;
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(s.gaps == 1 && s.switches_down == 0 && a.max_step == ZA_DT_NS_60 && a.burst_frames == 0,
          "SAFE stall: gaps %llu sw %llu max %.3f ms burst %llu", (unsigned long long)s.gaps,
          (unsigned long long)s.switches_down, (double)a.max_step / 1e6, (unsigned long long)a.burst_frames);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b = run_rc3(&m, &sc, 100 * SEC);
    CHECK(b.burst_frames >= 30, "RC3 after a 2 s stall: %llu fast-motion frames", (unsigned long long)b.burst_frames);
    printf("     2 s stall at 60: SAFE fast frames %llu | RC3 fast frames %llu (steps up to %.2f ms at 16.67 ms)\n",
           (unsigned long long)a.burst_frames, (unsigned long long)b.burst_frames, (double)b.max_step / 1e6);
    /* a 120 ms hitch: capped sample, mode stays 0 */
    Window h = {MS(10), MS(120), 300, 301};
    Scenario sh = scenario(cost_window, &h, 900);
    sh.warmup = 250;
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sh);
    CHECK(s2.capped == 1 && s2.switches_down == 0 && a2.max_step < 21739131, "SAFE hitch: cap %llu max %.3f ms",
          (unsigned long long)s2.capped, (double)a2.max_step / 1e6);
    /* a 30 s pause of the process (suspend): the hook is not called */
    Window p = {MS(10), 30 * SEC, 300, 301};
    Scenario sp = scenario(cost_window, &p, 900);
    sp.warmup = 250;
    ZaDtState s3;
    za_dt_reset(&s3);
    Run a3 = run_model(&s3, &c, &sp);
    CHECK(s3.gaps == 1 && a3.max_step == ZA_DT_NS_60 && a3.last_mode == 0, "SAFE pause: max %.3f ms",
          (double)a3.max_step / 1e6);
    ZaRc3 m3;
    za_rc3_init(&m3);
    Run b3 = run_rc3(&m3, &sp, 100 * SEC);
    printf("     30 s pause: SAFE fast frames %llu | RC3 fast frames %llu\n", (unsigned long long)a3.burst_frames,
           (unsigned long long)b3.burst_frames);
    /* a stall while in mode 1 */
    Window w1 = {MS(25), 3 * SEC, 400, 401};
    Scenario s1 = scenario(cost_window, &w1, 900);
    ZaDtState s4;
    za_dt_reset(&s4);
    Run a4 = run_model(&s4, &c, &s1);
    CHECK(a4.last_mode == 1 && NEAR(ratio(&a4), 1.0, 0.01) && a4.burst_frames == 0, "SAFE stall in mode 1: %.4f",
          ratio(&a4));
    puts("PASS stalls: 2 s / 30 s gaps are skipped (no fast-forward), a 120 ms hitch is capped; RC3 fast-forwards");
}

static void test_clock(void) {
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    uint64_t cost = MS(10);
    Scenario sc = scenario(cost_const, &cost, 900);
    sc.observe = obs_back;  /* one reading 5 ms in the past (TSC of another core) */
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(s.rollbacks == 1 && a.max_step <= MS(17.6) && a.last_mode == 0, "SAFE small rollback: max %.3f",
          (double)a.max_step / 1e6);
    sc.observe = obs_back10s;
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sc);
    CHECK(s2.rollbacks == 1 && a2.max_step == ZA_DT_NS_60 && a2.burst_frames == 0, "SAFE 10 s back: max %.3f",
          (double)a2.max_step / 1e6);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b2 = run_rc3(&m, &sc, 100 * SEC);
    CHECK(b2.burst_frames > 0 || b2.min_step < ZA_DT_NS_60, "RC3 10 s back disturbs the steps");
    sc.observe = obs_fwd10s;
    ZaDtState s3;
    za_dt_reset(&s3);
    Run a3 = run_model(&s3, &c, &sc);
    CHECK(s3.gaps == 1 && a3.max_step == ZA_DT_NS_60 && a3.burst_frames == 0, "SAFE 10 s forward");
    ZaRc3 m3;
    za_rc3_init(&m3);
    Run b3 = run_rc3(&m3, &sc, 100 * SEC);
    CHECK(b3.burst_frames >= 30, "RC3 10 s forward: %llu fast frames", (unsigned long long)b3.burst_frames);
    printf("     clock -10 s: RC3 fast frames %llu, min step %.3f ms | +10 s: RC3 fast frames %llu\n",
           (unsigned long long)b2.burst_frames, (double)b2.min_step / 1e6, (unsigned long long)b3.burst_frames);
    puts("PASS clock: rollbacks resync without a sample, forward jumps are gaps; RC3 reacts with wrong steps");
}

static void test_startup(void) {
    uint64_t cost = MS(10);
    Scenario sc = scenario(cost_const, &cost, 400);
    sc.warmup = 2;  /* (the virtual clock's very first frame is unpaced) */
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(a.max_step == ZA_DT_NS_60 && a.burst_frames == 0 && s.switches_down == 0, "SAFE start: max %.3f",
          (double)a.max_step / 1e6);
    ZaRc3 m;
    za_rc3_init(&m);
    Run b = run_rc3(&m, &sc, 100 * SEC);  /* the process has been up 100 s when the first frame ticks */
    CHECK(b.burst_frames >= 60, "RC3 start from tick 0: %llu fast frames", (unsigned long long)b.burst_frames);
    printf("     start-up (uptime 100 s): SAFE fast frames %llu | RC3 fast frames %llu\n",
           (unsigned long long)a.burst_frames, (unsigned long long)b.burst_frames);
    /* starting in a heavy scene: the first real sample primes the EMA */
    uint64_t heavy = MS(28);
    Scenario sh = scenario(cost_const, &heavy, 50);
    sh.warmup = 0;
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sh);
    CHECK(a2.last_mode == 1 && s2.switches_down == 1, "heavy start: mode 1 at once");
    puts("PASS start-up: no first-frame burst (RC3 primes from tick 0 and fast-forwards ~2x for >60 frames)");
}

static void test_standdown_keys_registry(void) {
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    uint64_t cost = MS(20);
    Scenario sc = scenario(cost_const, &cost, 600);
    sc.original = 2;  /* a 20 FPS configuration: the game asked for mode 2 */
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(a.last_mode == 2 && a.last_step == 50000000 && a.last_present == 2, "original mode 2 passes through");
    sc.original = 1;
    sc.variable_flag = 1;  /* the game's own variable-step path */
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sc);
    CHECK(a2.last_mode == 1 && a2.last_step == ZA_DT_NS_30 && a2.last_present == 1, "variable flag: passthrough");
    /* standing down after being active, then resuming */
    ZaDtState s3;
    za_dt_reset(&s3);
    VClock k = {SEC, 0};
    ZaDtInput in = {0, 1, 0, 0, 0xA};
    for (int i = 0; i < 300; i++) in.now_ns = k.now, (void)za_dt_frame(&s3, &c, &in), vclock_frame(&k, MS(20), 1);
    in.variable_flag = 1;
    in.now_ns = k.now;
    ZaDtDecision d = za_dt_frame(&s3, &c, &in);
    CHECK(!d.active && s3.standdowns == 1 && !s3.primed, "stand down");
    in.variable_flag = 0;
    for (int i = 0; i < 300; i++) vclock_frame(&k, MS(20), 1), in.now_ns = k.now, d = za_dt_frame(&s3, &c, &in);
    CHECK(d.active && NEAR(d.step_ns, 20e6, 0.3e6), "resumed: step %.3f", (double)d.step_ns / 1e6);
    /* two frame clocks tick every frame: only the primary is sampled */
    Scenario sk = scenario(cost_const, &cost, 1500);
    sk.two_keys = 1;
    ZaDtState s4;
    za_dt_reset(&s4);
    Run a4 = run_model(&s4, &c, &sk);
    CHECK(s4.foreign >= 1400 && NEAR(ratio(&a4), 1.0, 0.01), "two clocks: foreign %llu sim/wall %.4f",
          (unsigned long long)s4.foreign, ratio(&a4));
    /* the primary goes away, the other one is adopted after 0.5 s */
    Scenario sa = scenario(cost_const, &cost, 1500);
    sa.key_switch_at = 600;
    ZaDtState s5;
    za_dt_reset(&s5);
    Run a5 = run_model(&s5, &c, &sa);
    CHECK(s5.adoptions == 1 && NEAR(ratio(&a5), 1.0, 0.02), "adoption %llu sim/wall %.4f",
          (unsigned long long)s5.adoptions, ratio(&a5));
    /* RC3's registry byte: the original step while it is set (honoured by rc3-compat, ignored by safe) */
    Scenario sr = scenario(cost_const, &cost, 700);
    sr.registry = reg_window;
    ZaDtConfig r3 = cfg(ZA_DT_POLICY_RC3_COMPAT);
    ZaDtState s6;
    za_dt_reset(&s6);
    (void)run_model(&s6, &r3, &sr);
    CHECK(s6.registry_frames == 100, "rc3-compat honours the byte for 100 frames (%llu)",
          (unsigned long long)s6.registry_frames);
    ZaDtState s7;
    za_dt_reset(&s7);
    Run a7 = run_model(&s7, &c, &sr);
    CHECK(s7.registry_frames == 0 && NEAR(ratio(&a7), 1.0, 0.01), "safe ignores it");
    puts("PASS stand-down (mode 2, variable flag), second frame clock, adoption, registry byte");
}

static void test_present_interval(void) {
    /* 50-capable scene with a 33 FPS section. With the present interval following the mode (no SDK patch),
     * mode 1 holds frames at 33.3 ms, so the controller never sees the scene recover. */
    Window w = {MS(20), MS(30.3), 300, 600};
    Scenario sc = scenario(cost_window, &w, 1500);
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    c.force_present_60 = false;
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(a.last_mode == 1 && a.last_present == 1 && s.switches_up == 0, "interval 2 traps mode 1 (mode %d)",
          a.last_mode);
    c.force_present_60 = true;
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sc);
    CHECK(a2.last_mode == 0 && a2.last_present == 0 && s2.switches_up == 1, "interval 1 recovers (mode %d)",
          a2.last_mode);
    puts("PASS present interval: following the mode traps mode 1 at 30 FPS; interval 1 (the SDK patch's"
         " equivalent) recovers");
}

static void test_fast_and_sub60(void) {
    uint64_t cost = MS(8.333);
    Scenario sc = scenario(cost_const, &cost, 1200);
    sc.pace = 0;  /* no present pacing: 120 FPS */
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(s.fast_frames > 1000 && a.last_step == ZA_DT_NS_60 && NEAR(ratio(&a), 2.0, 0.02),
          "uncapped 120 FPS without sub60: 2x speed (%.3f) - pacing must hold 60", ratio(&a));
    c.allow_sub60_step = true;
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sc);
    CHECK(NEAR(ratio(&a2), 1.0, 0.01) && a2.min_step >= 8333333 && a2.max_step <= ZA_DT_NS_60,
          "sub60 experiment: %.4f, steps %.3f..%.3f ms", ratio(&a2), (double)a2.min_step / 1e6,
          (double)a2.max_step / 1e6);
    puts("PASS >60 FPS: without 60 Hz pacing the 16.67 ms floor runs 2x fast; the sub60 experiment tracks 120 FPS");
}

static void test_jitter(void) {
    Alt alt = {MS(14.0), MS(19.333), 1};  /* mean 16.67 ms, alternating */
    Scenario sc = scenario(cost_alt, &alt, 3000);
    sc.pace = 0;
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    Run a = run_model(&s, &c, &sc);
    CHECK(a.last_mode == 0 && s.switches_down == 0 && NEAR(ratio(&a), 1.0, 0.005), "alternating 14/19.3: %.4f",
          ratio(&a));
    Jitter j = {MS(22.0), MS(3.0)};
    Scenario sj = scenario(cost_jitter, &j, 4000);
    ZaDtState s2;
    za_dt_reset(&s2);
    Run a2 = run_model(&s2, &c, &sj);
    CHECK(a2.last_mode == 1 && s2.switches_down == 1 && s2.switches_up == 0 && NEAR(ratio(&a2), 1.0, 0.01),
          "random 22+-3 ms: mode %d sw %llu/%llu %.4f", a2.last_mode, (unsigned long long)s2.switches_down,
          (unsigned long long)s2.switches_up, ratio(&a2));
    puts("PASS jitter: frame-to-frame noise does not switch modes; long-run speed within 1%");
}

static void test_long_session(void) {
    /* 20 minutes of mixed play: 60, heavy 48-52, 40-45, hitches, loads */
    ZaDtConfig c = cfg(ZA_DT_POLICY_SAFE);
    ZaDtState s;
    za_dt_reset(&s);
    VClock k = {SEC, 0};
    uint64_t prev_wall = 0;
    double sim = 0, wall = 0;
    for (uint64_t i = 0; i < 60000; i++) {
        ZaDtInput in = {k.now, 1, 0, 0, 0xA};
        ZaDtDecision d = za_dt_frame(&s, &c, &in);
        uint64_t step = za_dt_step_for(&d, d.mode, za_dt_table_202[d.mode]);
        if (i > 0 && prev_wall < MS(50)) sim += (double)step, wall += (double)prev_wall;
        CHECK(step >= ZA_DT_NS_60 && step <= ZA_DT_NS_30, "band");
        uint64_t phase = (i / 3000) % 4, cost;
        if (phase == 0) cost = MS(10);
        else if (phase == 1) cost = MS(19.5) + (uint64_t)(lcg_unit() * 2e6);
        else if (phase == 2) cost = MS(22.5) + (uint64_t)(lcg_unit() * 2.5e6);
        else cost = MS(15) + (uint64_t)(lcg_unit() * 4e6);
        if (i % 7001 == 7000) cost = MS(400);  /* a load every ~2 min */
        if (i % 997 == 996) cost = MS(90);     /* a hitch every ~17 s */
        prev_wall = vclock_frame(&k, cost, d.present_mode + 1);
    }
    CHECK(NEAR(sim / wall, 1.0, 0.005), "20 min session: sim/wall %.5f", sim / wall);
    CHECK(s.switches_down + s.switches_up < 60, "switches %llu", (unsigned long long)(s.switches_down + s.switches_up));
    printf("     20 min mixed session: sim/wall %.5f, switches %llu/%llu, gaps %llu, capped %llu, lag %.2f ms\n",
           sim / wall, (unsigned long long)s.switches_down, (unsigned long long)s.switches_up,
           (unsigned long long)s.gaps, (unsigned long long)s.capped, s.lag_ns / 1e6);
    puts("PASS long mixed session: in-band simulated time within 0.5% of wall clock");
}

int main(void) {
    test_basics();
    test_rc3_reference_decode();
    test_steady_rates();
    test_transitions();
    test_oscillation();
    test_stalls();
    test_clock();
    test_startup();
    test_standdown_keys_registry();
    test_present_interval();
    test_fast_and_sub60();
    test_jitter();
    test_long_session();
    CHECK(g_all_min >= ZA_DT_NS_60 && g_all_max <= ZA_DT_NS_30, "band over every run: %.3f..%.3f ms",
          (double)g_all_min / 1e6, (double)g_all_max / 1e6);
    printf("     every step handed out (sub60 off): %.3f .. %.3f ms\n", (double)g_all_min / 1e6, (double)g_all_max / 1e6);
    printf("%s: %d checks, %d failures\n", g_failures ? "FAILED" : "ALL PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
