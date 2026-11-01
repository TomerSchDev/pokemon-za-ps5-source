/* Host tests of the proposed port glue (za_dyn_glue.c) against stubs of the runtime: a virtual plat_now_ns /
 * plat_sleep_until_ns, r16's za_title_frame_cfg (with the r24-prof force60 behaviour), sceKernelDebugOutText,
 * and the registry byte. Also a concurrency smoke test of the published word. */
#define _POSIX_C_SOURCE 200809L /* setenv / unsetenv under -std=c11 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../za_dyn_glue.h"
#include "../za_dyn_timing.h"
#include "sim.h"

/* ---------------------------------------------------------------- runtime stubs */
static _Atomic uint64_t g_now = SEC;
uint64_t plat_now_ns(void) { return atomic_load(&g_now); }
void plat_sleep_until_ns(uint64_t t) {
    if (t > atomic_load(&g_now)) atomic_store(&g_now, t);
}
static int g_r16_calls, g_force60;
int32_t za_title_frame_cfg(int32_t original) {
    g_r16_calls++;
    return g_force60 ? 0 : original;
}
static int g_log_lines;
static char g_last_log[512];
int sceKernelDebugOutText(int channel, const char *text) {
    (void)channel;
    g_log_lines++;
    snprintf(g_last_log, sizeof g_last_log, "%s", text);
    return 0;
}
static uint8_t g_registry;
static uint8_t registry_stub(void) { return g_registry; }

static void env(const char *policy, const char *stress_fps, const char *spike_ms, const char *spike_every) {
    unsetenv("ZA_DT_POLICY"), unsetenv("ZA_DT_STRESS_FPS"), unsetenv("ZA_DT_STRESS_SPIKE_MS");
    unsetenv("ZA_DT_STRESS_SPIKE_EVERY"), unsetenv("ZA_DT_SUB60"), unsetenv("ZA_DT_REGISTRY"), unsetenv("ZA_DT_ANIM");
    if (policy) setenv("ZA_DT_POLICY", policy, 1);
    if (stress_fps) setenv("ZA_DT_STRESS_FPS", stress_fps, 1);
    if (spike_ms) setenv("ZA_DT_STRESS_SPIKE_MS", spike_ms, 1);
    if (spike_every) setenv("ZA_DT_STRESS_SPIKE_EVERY", spike_every, 1);
    setenv("ZA_DT_LOG", "2", 1);
    za_dt_registry_reader = registry_stub;
    za_dt_init_from_env();
}

/* One game frame through H1 -> H2 -> H3, then `work` ns of frame time. Returns the step SetFrameMode got. */
static uint64_t frame(uint64_t work, int32_t original, uint32_t *present_out) {
    int32_t mode = za_dt_frame_cfg(original, 0, 0x7001234560ull);
    uint32_t present = za_dt_present_mode((uint32_t)mode);
    if (present_out) *present_out = present;
    uint64_t step = za_dt_step_ns(mode, mode >= 0 && mode < ZA_DT_TABLE_N ? za_dt_table_202[mode] : 0);
    atomic_fetch_add(&g_now, work);
    return step;
}

static void test_off(void) {
    env(NULL, NULL, NULL, NULL);
    g_r16_calls = 0;
    g_force60 = 0;
    uint32_t present = 99;
    int32_t m = za_dt_frame_cfg(1, 0, 1);
    CHECK(m == 1 && g_r16_calls == 1, "off: r16 policy decides (%d, calls %d)", m, g_r16_calls);
    g_force60 = 1;
    m = za_dt_frame_cfg(1, 0, 1);
    CHECK(m == 0 && g_r16_calls == 2, "off: the force60 wrap still works");
    present = za_dt_present_mode(0);
    CHECK(present == 0 && za_dt_present_mode(1) == 1, "off: present passes through");
    CHECK(za_dt_step_ns(0, 16666667) == 16666667 && za_dt_step_ns(1, 33333334) == 33333334, "off: table");
    CHECK(za_dt_status() == -1, "off: status");
    env("bogus", NULL, NULL, NULL);
    CHECK(za_dt_status() == -1 && strstr(g_last_log, "unknown ZA_DT_POLICY"), "unknown policy -> off");
    /* the stress limiter also works with dynamic off: static 60 under a forced 40 FPS (the slow-motion case) */
    env(NULL, "40", NULL, NULL);
    g_r16_calls = 0;
    m = za_dt_frame_cfg(1, 0, 1);  /* (the limiter's first frame has nothing to wait for) */
    atomic_fetch_add(&g_now, MS(2));
    uint64_t t0 = plat_now_ns();
    for (int i = 0; i < 100; i++) {
        m = za_dt_frame_cfg(1, 0, 1);
        atomic_fetch_add(&g_now, MS(2));
    }
    CHECK(m == 0 && g_r16_calls == 101 && NEAR((double)(plat_now_ns() - t0) / 100.0, 25e6, 0.1e6),
          "off + stress 40: force60 kept, %.3f ms/frame", (double)(plat_now_ns() - t0) / 100e6);
    g_force60 = 0;
    puts("PASS glue off: r16 / force60 untouched, H2-H5 pass through, stress limiter usable for static 60");
}

static void test_safe(void) {
    env("safe", NULL, NULL, NULL);
    CHECK(strstr(g_last_log, "policy=safe") != NULL, "init line: %s", g_last_log);
    g_r16_calls = 0;
    g_force60 = 1;  /* dynamic owns the mode even with force60 set */
    uint32_t present = 99;
    uint64_t step = 0;
    for (int i = 0; i < 600; i++) step = frame(MS(20), 1, &present);
    CHECK(g_r16_calls == 0, "safe: r16 not consulted (%d)", g_r16_calls);
    CHECK(present == 0 && za_dt_status() == 0, "safe 50 FPS: mode 0, present interval 1");
    CHECK(NEAR(step, 20e6, 0.2e6), "safe 50 FPS: step %.3f ms", (double)step / 1e6);
    CHECK(za_dt_step_ns(1, 33333334) == 33333334, "a group in another mode keeps its table value");
    for (int i = 0; i < 600; i++) step = frame(MS(25), 1, &present);
    CHECK(za_dt_status() == 1 && NEAR(step, 25e6, 0.3e6) && present == 0, "safe 40 FPS: mode 1, %.3f ms",
          (double)step / 1e6);
    int lines = g_log_lines;
    for (int i = 0; i < 200; i++) {
        frame(MS(25), 1, NULL);
        (void)za_dt_step_ns(0, za_dt_table_202[0]);  /* a group the game keeps in another mode */
    }
    CHECK(g_log_lines > lines && strstr(g_last_log, "[za-dyn] mode=1") != NULL, "status line: %s", g_last_log);
    unsigned long long sub = 0, pass = 0;
    const char *st = strstr(g_last_log, "steps=");
    CHECK(st && sscanf(st, "steps=%llu/%llu", &sub, &pass) == 2 && sub > 0 && pass > 0,
          "the status line counts substituted/passed step calls: %s", st ? st : "(none)");
    /* the game's variable-step flag: pass-through for the frame, H3 back to the table */
    int32_t m = za_dt_frame_cfg(1, 1, 0x7001234560ull);
    CHECK(m == 1 && za_dt_present_mode(1) == 1 && za_dt_step_ns(1, 33333334) == 33333334, "variable flag");
    g_force60 = 0;
    puts("PASS glue safe: owns the mode, present interval 1, steps follow the frame time, logs, stands down");
}

static void test_stress_knobs(void) {
    env("safe", "40", NULL, NULL);  /* the limiter in H1 holds 40 FPS with no other work */
    uint64_t step = 0;
    uint64_t t0 = plat_now_ns();
    for (int i = 0; i < 400; i++) step = frame(MS(2), 1, NULL);
    double per = (double)(plat_now_ns() - t0) / 400.0;
    CHECK(NEAR(per, 25e6, 0.2e6) && za_dt_status() == 1 && NEAR(step, 25e6, 0.3e6),
          "stress 40 FPS: %.3f ms/frame, step %.3f", per / 1e6, (double)step / 1e6);
    env("safe", NULL, "120", "100");  /* a 120 ms hitch every 100 frames at 60 */
    uint64_t max = 0;
    for (int i = 0; i < 1000; i++) {
        step = frame(MS(16.667), 1, NULL);
        if (i > 200 && step > max) max = step;
    }
    CHECK(za_dt_status() == 0 && max < 21739131, "hitches stay in mode 0 (max step %.3f)", (double)max / 1e6);
    puts("PASS glue stress knobs: frame limiter and periodic hitches for console tests");
}

static void test_registry(void) {
    env("rc3", NULL, NULL, NULL);
    g_registry = 0;
    uint64_t step = 0;
    for (int i = 0; i < 400; i++) step = frame(MS(20), 1, NULL);
    CHECK(step == 20000000, "rc3 50 FPS: %llu", (unsigned long long)step);
    g_registry = 1;
    step = frame(MS(20), 1, NULL);
    CHECK(step == ZA_DT_NS_60, "rc3: registry byte -> original step");
    g_registry = 0;
    puts("PASS glue rc3: integer-FPS steps, registry byte honoured");
}

static void test_anim_hooks(void) {
    env("safe", NULL, NULL, NULL);  /* H6/H7 default: the denominator keeps the table value */
    uint64_t step = 0;
    for (int i = 0; i < 400; i++) step = frame(MS(20), 1, NULL);
    uint64_t den = za_dt_anim_table_ns(0, za_dt_table_202[0]);
    CHECK(den == za_dt_table_202[0], "default: table value");
    CHECK(NEAR(za_dt_anim_rate(step, den), 1.2, 0.02), "50 FPS: rate = step / nominal = %.3f",
          (double)za_dt_anim_rate(step, den));
    for (int i = 0; i < 200; i++) frame(MS(20), 1, NULL), (void)za_dt_anim_table_ns(0, za_dt_table_202[0]);
    unsigned long long calls = 0, same = 0;
    const char *a = strstr(g_last_log, "anim=");
    CHECK(a && sscanf(a, "anim=%llu/%llu", &calls, &same) == 2 && calls > 0 && same == calls,
          "status line counts the animation-rate calls: %s", a ? a : "(none)");
    setenv("ZA_DT_ANIM", "step", 1);  /* the RC3-like experiment */
    za_dt_init_from_env();
    for (int i = 0; i < 400; i++) step = frame(MS(20), 1, NULL);
    den = za_dt_anim_table_ns(0, za_dt_table_202[0]);
    CHECK(den == step && NEAR(za_dt_anim_rate(step, den), 1.0, 0.001), "experiment: rate %.4f (RC3-like)",
          (double)za_dt_anim_rate(step, den));
    CHECK(za_dt_anim_table_ns(1, za_dt_table_202[1]) == za_dt_table_202[1], "experiment: other modes untouched");
    unsetenv("ZA_DT_ANIM");
    puts("PASS glue H6/H7: table denominator by default (rate = step/nominal), RC3-like step on request, counted");
}

/* ---------------------------------------------------------------- concurrency smoke test */
static _Atomic int g_stop;
static _Atomic uint64_t g_bad, g_reads;
static void *reader(void *arg) {
    (void)arg;
    while (!atomic_load(&g_stop)) {
        for (int m = 0; m < 2; m++) {
            uint64_t v = za_dt_step_ns(m, za_dt_table_202[m]);
            if (!(v == za_dt_table_202[m] || (v >= ZA_DT_NS_60 && v <= ZA_DT_NS_30))) atomic_fetch_add(&g_bad, 1);
            uint32_t p = za_dt_present_mode((uint32_t)m);
            if (p != 0 && p != (uint32_t)m) atomic_fetch_add(&g_bad, 1);
            if (za_dt_anim_table_ns(m, za_dt_table_202[m]) != za_dt_table_202[m]) atomic_fetch_add(&g_bad, 1);
            atomic_fetch_add(&g_reads, 1);
        }
    }
    return NULL;
}

static void test_threads(void) {
    env("safe", NULL, NULL, NULL);
    pthread_t t[4];
    atomic_store(&g_stop, 0);
    for (int i = 0; i < 4; i++) pthread_create(&t[i], NULL, reader, NULL);
    for (int i = 0; i < 200000; i++) frame(MS(14) + (uint64_t)(lcg_unit() * 20e6), 1, NULL);
    atomic_store(&g_stop, 1);
    for (int i = 0; i < 4; i++) pthread_join(t[i], NULL);
    CHECK(atomic_load(&g_bad) == 0 && atomic_load(&g_reads) > 0, "readers saw %llu bad of %llu",
          (unsigned long long)atomic_load(&g_bad), (unsigned long long)atomic_load(&g_reads));
    printf("     4 reader threads, %llu reads during 200,000 frames: %llu inconsistent\n",
           (unsigned long long)atomic_load(&g_reads), (unsigned long long)atomic_load(&g_bad));
    puts("PASS glue threads: the step hooks only ever see the table value or a step in band");
}

int main(void) {
    test_off();
    test_safe();
    test_stress_knobs();
    test_registry();
    test_anim_hooks();
    test_threads();
    printf("%s: %d checks, %d failures\n", g_failures ? "FAILED" : "ALL PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
