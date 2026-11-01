/* r26 host tests of the glue's additions (za_dyn_glue_r26.c): the window accounting H1 does for every policy and
 * za_dt_report() (the [za-r24-perf] keys), against the same runtime stubs as port/dynamic-timing/test/test_glue.c.
 * The original glue tests run unchanged against the r26 glue as well (test.sh). */
#define _POSIX_C_SOURCE 200809L /* setenv / unsetenv under -std=c11 */
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../dynamic-timing/test/sim.h"
#include "../../dynamic-timing/za_dyn_timing.h"
#include "../za_dyn_glue_r26.h"

/* ---------------------------------------------------------------- runtime stubs */
static _Atomic uint64_t g_now = SEC;
uint64_t plat_now_ns(void) { return atomic_load(&g_now); }
void plat_sleep_until_ns(uint64_t t) {
    if (t > atomic_load(&g_now)) atomic_store(&g_now, t);
}
static _Atomic int g_r16_calls, g_force60;
int32_t za_title_frame_cfg(int32_t original) {  /* r16 + r24-prof's force60 wrap, as the title links them */
    atomic_fetch_add(&g_r16_calls, 1);
    return atomic_load(&g_force60) ? 0 : original;
}
int sceKernelDebugOutText(int channel, const char *text) {
    (void)channel, (void)text;
    return 0;
}

static void env(const char *policy, const char *stress_fps) {
    unsetenv("ZA_DT_POLICY"), unsetenv("ZA_DT_STRESS_FPS"), unsetenv("ZA_DT_STRESS_SPIKE_MS");
    unsetenv("ZA_DT_STRESS_SPIKE_EVERY"), unsetenv("ZA_DT_SUB60"), unsetenv("ZA_DT_REGISTRY"), unsetenv("ZA_DT_ANIM");
    unsetenv("ZA_R26_DYN_REQUESTED");
    if (policy) setenv("ZA_DT_POLICY", policy, 1);
    if (stress_fps) setenv("ZA_DT_STRESS_FPS", stress_fps, 1);
    setenv("ZA_DT_LOG", "2", 1);
    za_dt_init_from_env();
}

/* One game frame: H1, then H3 for a group in the returned mode, then `work` ns. */
static void frame(uint64_t work, int32_t original) {
    int32_t mode = za_dt_frame_cfg(original, 0, 0x7001234560ull);
    (void)za_dt_step_ns(mode, mode >= 0 && mode < ZA_DT_TABLE_N ? za_dt_table_202[mode] : 0);
    atomic_fetch_add(&g_now, work);
}

static char g_line[1024];
static const char *report(void) {
    size_t n = za_dt_report(g_line, sizeof g_line);
    CHECK(n > 0 && n < sizeof g_line && g_line[n] == 0, "report length %zu", n);
    return g_line;
}
/* the value after " key=" in the last report (NAN when absent) */
static double val(const char *key) {
    char k[64];
    snprintf(k, sizeof k, " %s=", key);
    const char *p = strstr(g_line, k);
    return p ? strtod(p + strlen(k), NULL) : NAN;
}
static int has(const char *text) { return strstr(g_line, text) != NULL; }

static void test_before_init(void) {
    report();  /* (a fresh process: no frame-mode read yet) */
    CHECK(has(" dyn=init ") && val("dyn_mode") == -1 && val("dyn_frames") == 0, "before init: %s", g_line);
    puts("PASS report before the first frame-mode read: dyn=init, mode -1, empty window");
}

static void test_off_static60_slow_motion(void) {
    env(NULL, "45");  /* dyn=off, force60 (static 60) under a forced 45 FPS: the case dynamic timing fixes */
    atomic_store(&g_force60, 1);
    for (int i = 0; i < 50; i++) frame(MS(2), 1);  /* (settle) */
    report();
    for (int i = 0; i < 900; i++) frame(MS(2), 1);
    report();
    CHECK(has(" dyn=off ") && has(" dyn_req=- ") && val("dyn_mode") == 0 && val("dyn_step_ns") == 16666667,
          "off/force60: %s", g_line);
    CHECK(NEAR(val("dyn_frames"), 900, 1) && NEAR(val("dyn_simwall"), 0.75, 0.002),
          "static 60 at 45 FPS runs at 75%%: simwall %.4f", val("dyn_simwall"));
    CHECK(val("dyn_drift_ns") > 0 && NEAR(val("dyn_drift_ns"), val("dyn_wall_ns") * 0.25, 1e6),
          "drift = wall - sim = %.0f", val("dyn_drift_ns"));
    CHECK(NEAR(val("dyn_ema_ns"), 22222222, 0.05e6), "smoothed frame time %.0f", val("dyn_ema_ns"));
    CHECK(has(" dyn_steps=0/0 ") && has(" dyn_anim=0/0") && val("dyn_sw") == 0, "off: no substitution: %s", g_line);
    /* r16's original 30 mode at 30 FPS: real time */
    atomic_store(&g_force60, 0);
    env(NULL, "30");
    for (int i = 0; i < 50; i++) frame(MS(2), 1);
    report();
    for (int i = 0; i < 600; i++) frame(MS(2), 1);
    report();
    CHECK(val("dyn_mode") == 1 && val("dyn_step_ns") == 33333334 && NEAR(val("dyn_simwall"), 1.0, 0.002),
          "r16 30 mode at 30 FPS: %s", g_line);
    puts("PASS off: accounting of the static modes - static 60 under 45 FPS shows 0.75 of real time");
}

static void test_safe_real_time(void) {
    env("safe", "45");
    setenv("ZA_R26_DYN_REQUESTED", "safe", 1);
    for (int i = 0; i < 400; i++) frame(MS(2), 1);
    report();
    for (int i = 0; i < 900; i++) frame(MS(2), 1);
    report();
    CHECK(has(" dyn=safe ") && has(" dyn_req=safe ") && val("dyn_mode") == 1, "safe at 45 FPS: %s", g_line);
    CHECK(NEAR(val("dyn_simwall"), 1.0, 0.01) && NEAR(val("dyn_step_ns"), 22222222, 0.3e6),
          "safe at 45 FPS runs in real time: simwall %.4f step %.0f", val("dyn_simwall"), val("dyn_step_ns"));
    unsigned long long sub = 0, pass = 0;
    const char *st = strstr(g_line, " dyn_steps=");
    CHECK(st && sscanf(st, " dyn_steps=%llu/%llu", &sub, &pass) == 2 && sub >= 899 && pass == 0,
          "the window's substituted steps: %s", st ? st : "(none)");
    /* back to 60: one switch up, real time */
    env("safe", NULL);
    for (int i = 0; i < 400; i++) frame(MS(16.667), 1);
    report();
    for (int i = 0; i < 600; i++) frame(MS(16.667), 1);
    report();
    CHECK(val("dyn_mode") == 0 && NEAR(val("dyn_step_ns"), 16666667, 0.05e6) && NEAR(val("dyn_simwall"), 1.0, 0.003),
          "safe at 60: %s", g_line);
    /* a 1 s stall is a gap, not a frame */
    report();
    frame(MS(16.667), 1);
    atomic_fetch_add(&g_now, SEC);
    for (int i = 0; i < 100; i++) frame(MS(16.667), 1);
    report();
    CHECK(val("dyn_gaps") == 1 && val("dyn_wall_ns") < 100 * 17e6, "stall: %s", g_line);
    puts("PASS safe: 45 FPS in real time (step follows the frame), 60 at 16.67 ms, a stall left out of the window");
}

static void test_switch_counts(void) {
    env("safe", NULL);
    for (int i = 0; i < 300; i++) frame(MS(16.667), 1);
    report();
    for (int i = 0; i < 300; i++) frame(MS(25), 1);   /* 40 FPS: down to the 30 index */
    for (int i = 0; i < 400; i++) frame(MS(16.667), 1);  /* 60: back up after the dwell */
    report();
    CHECK(val("dyn_sw") == 2, "two mode switches: %s", g_line);
    CHECK(val("dyn_stepchg") >= 2, "visible step changes counted: %.0f", val("dyn_stepchg"));
    puts("PASS switches and step changes counted per window");
}

/* The report runs on the render thread while H1 runs on the frame thread: no lost or torn window under TSan. */
static _Atomic int g_stop;
static uint64_t g_frames_reported;
static void *reporter(void *arg) {
    (void)arg;
    char line[1024];
    while (!atomic_load(&g_stop)) {
        za_dt_report(line, sizeof line);
        const char *p = strstr(line, " dyn_frames=");
        if (p) g_frames_reported += strtoull(p + 12, NULL, 10);
    }
    za_dt_report(line, sizeof line);
    const char *p = strstr(line, " dyn_frames=");
    if (p) g_frames_reported += strtoull(p + 12, NULL, 10);
    return NULL;
}

static void test_concurrent_report(void) {
    env("safe", NULL);
    for (int i = 0; i < 10; i++) frame(MS(16.667), 1);
    report();  /* (the window starts here) */
    pthread_t t;
    g_frames_reported = 0;
    atomic_store(&g_stop, 0);
    pthread_create(&t, NULL, reporter, NULL);
    for (int i = 0; i < 100000; i++) frame(MS(14) + (uint64_t)(lcg_unit() * 20e6), 1);
    atomic_store(&g_stop, 1);
    pthread_join(t, NULL);
    CHECK(g_frames_reported == 100000, "frames reported by the concurrent reader: %llu",
          (unsigned long long)g_frames_reported);
    puts("PASS concurrent report: every frame counted exactly once across the windows");
}

int main(void) {
    test_before_init();
    test_off_static60_slow_motion();
    test_safe_real_time();
    test_switch_counts();
    test_concurrent_report();
    printf("%s: %d checks, %d failures\n", g_failures ? "FAILED" : "ALL PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
