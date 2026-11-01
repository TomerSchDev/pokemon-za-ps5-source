/* r26 host test of za_r26_options.h: the new keys, bad values, r25 keys still parsed, and the precedence rules. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../za_r26_options.h"

static int g_failures, g_checks;
#define CHECK(c, ...) do { g_checks++; if (!(c)) { g_failures++; fprintf(stderr, "FAIL %s:%d: ", __FILE__, __LINE__); \
    fprintf(stderr, __VA_ARGS__); fputc('\n', stderr); } } while (0)

/* a fake environment */
static struct { char name[64], value[128]; int used; } g_env[64];
static int fake_set(const char *n, const char *v, int ow) {
    for (int i = 0; i < 64; i++)
        if (g_env[i].used && !strcmp(g_env[i].name, n)) {
            if (ow) snprintf(g_env[i].value, sizeof g_env[i].value, "%s", v);
            return 0;
        }
    for (int i = 0; i < 64; i++)
        if (!g_env[i].used) {
            g_env[i].used = 1;
            snprintf(g_env[i].name, sizeof g_env[i].name, "%s", n);
            snprintf(g_env[i].value, sizeof g_env[i].value, "%s", v);
            return 0;
        }
    return -1;
}
static int fake_unset(const char *n) {
    for (int i = 0; i < 64; i++)
        if (g_env[i].used && !strcmp(g_env[i].name, n)) g_env[i].used = 0;
    return 0;
}
static char *fake_get(const char *n) {
    for (int i = 0; i < 64; i++)
        if (g_env[i].used && !strcmp(g_env[i].name, n)) return g_env[i].value;
    return NULL;
}
static char g_log[4096];
static void fake_log(const char *fmt, const char *a, const char *b) {
    size_t n = strlen(g_log);
    snprintf(g_log + n, sizeof g_log - n, fmt, a, b);
}
static void reset(void) { memset(g_env, 0, sizeof g_env), g_log[0] = 0; }
static void parse(const char *text) {
    char buf[2048];
    snprintf(buf, sizeof buf, "%s", text);
    za_r26_parse(buf, fake_set, fake_unset, fake_log);
}
static int is(const char *n, const char *v) { const char *g = fake_get(n); return v ? g && !strcmp(g, v) : !g; }

int main(void) {
    reset();
    parse("# r26 test\nscale=1\nticks=tsc\nvkprof=0\ngaps=1\nsubmit=thread\ndyn=safe\ndyn_log=5\ndyn_anim=step\n"
          "dyn_stress_fps=45\ndyn_spike_ms=120\ndyn_spike_every=300\nfnprof=600:900\n");
    CHECK(is("ZA_DT_POLICY", "safe") && is("ZA_R26_DYN_REQUESTED", "safe"), "dyn=safe");
    CHECK(is("ZA_DT_LOG", "5") && is("ZA_DT_ANIM", "step") && is("ZA_DT_STRESS_FPS", "45"), "dyn_log/anim/stress");
    CHECK(is("ZA_DT_STRESS_SPIKE_MS", "120") && is("ZA_DT_STRESS_SPIKE_EVERY", "300"), "spikes");
    CHECK(is("LARECOMP_FNPROF", "600:900") && is("LARECOMP_FNPROF_OUT", "/download0/zarecomp/fnprof-r26.txt"), "fnprof");
    CHECK(is("ZA_PERF_SUBMIT", "thread") && is("LARECOMP_SCALE", "1") && is("SDL3_PS5_TICKS", "tsc") &&
          is("ZA_PERF_VKPROF_OFF", "1") && is("ZA_PERF_GAPS", "1"), "r25 / r24-clock / r24 keys still parsed");
    CHECK(!strstr(g_log, "unknown") && !strstr(g_log, "bad value"), "no complaints: %s", g_log);
    CHECK(!strcmp(za_r26_resolve(fake_get, fake_set, fake_unset, fake_log), "safe") && is("ZA_DT_POLICY", "safe") &&
          strstr(g_log, "r16's za_title_frame_cfg is not called"), "resolve: dyn=safe in effect");

    reset();
    parse("dyn=fast\ndyn_stress_fps=10\ndyn_spike_ms=9999\nfnprof=900:600\nfnprof=x\ndyn_anim=nope\ndyn_log=-1\n");
    CHECK(is("ZA_DT_POLICY", NULL) && is("ZA_DT_STRESS_FPS", NULL) && is("ZA_DT_STRESS_SPIKE_MS", NULL) &&
          is("LARECOMP_FNPROF", NULL) && is("ZA_DT_ANIM", NULL) && is("ZA_DT_LOG", NULL), "bad values set nothing");
    int bad = 0;
    for (const char *p = g_log; (p = strstr(p, "bad value")); p++) bad++;
    CHECK(bad == 7, "seven bad values logged (%d): %s", bad, g_log);

    reset();
    parse("dyn=safe\ndyn_stress_fps=45\ndyn_stress_fps=0\ndyn=off\n");
    CHECK(is("ZA_DT_POLICY", NULL) && is("ZA_R26_DYN_REQUESTED", NULL) && is("ZA_DT_STRESS_FPS", NULL),
          "later lines win: dyn=off and stress 0 unset");

    reset();
    parse("force60=1\ndyn=safe\n");
    CHECK(!strcmp(za_r26_resolve(fake_get, fake_set, fake_unset, fake_log), "off") && is("ZA_DT_POLICY", NULL) &&
          is("ZA_R26_DYN_REQUESTED", "safe") && is("ZA_PERF_FORCE60", "1") && strstr(g_log, "measurement override"),
          "force60 overrides dyn: %s", g_log);

    reset();
    parse("dyn=rc3\n");
    fake_set("LARECOMP_PRESENT_INTERVAL", "2", 1);
    CHECK(!strcmp(za_r26_resolve(fake_get, fake_set, fake_unset, fake_log), "rc3") &&
          is("LARECOMP_PRESENT_INTERVAL", NULL) && strstr(g_log, "LARECOMP_PRESENT_INTERVAL removed"),
          "dyn removes LARECOMP_PRESENT_INTERVAL");

    reset();
    parse("force60=1\n");
    CHECK(!strcmp(za_r26_resolve(fake_get, fake_set, fake_unset, fake_log), "off") && strstr(g_log, "static 60"),
          "dyn absent: off, force60 noted: %s", g_log);

    printf("%s: %d checks, %d failures\n", g_failures ? "FAILED" : "ALL PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
