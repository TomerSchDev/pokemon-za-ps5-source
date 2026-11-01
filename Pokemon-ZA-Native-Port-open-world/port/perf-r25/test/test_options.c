/* Host test of za_r25_options.h: r25's keys (submit, clock, radv_threaded), a sample of the earlier keys through the
 * same parser, bad values and unknown keys (nothing set), and the shipped test configuration. */
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../za_r25_options.h"

#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); exit(1); } } while (0)

static int logged;
static void log_line(const char *fmt, const char *a, const char *b) { (void)fmt; (void)a; (void)b; logged++; }
static const char *const VARS[] = {"ZA_PERF_SUBMIT", "ZA_PERF_CLOCK", "RADV_THREADED_RECORDING", "ZA_PERF_VKPROF_OFF",
                                   "SDL3_PS5_TICKS", "LARECOMP_PS5_TSC", "ZA_PERF_GAPS", "ZA_PERF_FORCE60", "LARECOMP_SCALE",
                                   "ZA_PERF_GPUPROF_EVERY", NULL};
static void clear(void) { for (int i = 0; VARS[i]; i++) unsetenv(VARS[i]); logged = 0; }
static void parse(const char *text) {
    char buf[1024];
    snprintf(buf, sizeof buf, "%s", text);
    za_r25_parse(buf, setenv, unsetenv, log_line);
}
static int is(const char *var, const char *val) { const char *v = getenv(var); return val ? v && !strcmp(v, val) : !v; }

int main(void) {
    clear();
    parse("submit=thread\nclock=tsc\n");
    CHECK(is("ZA_PERF_SUBMIT", "thread") && is("ZA_PERF_CLOCK", "tsc") && logged == 2);
    parse("submit=inline\nclock=real\n");
    CHECK(is("ZA_PERF_SUBMIT", NULL) && is("ZA_PERF_CLOCK", NULL));
    clear();
    parse("submit=threads\nclock=TSC\nsubmit=\nclock\n");  /* bad values, a line without '=' */
    CHECK(is("ZA_PERF_SUBMIT", NULL) && is("ZA_PERF_CLOCK", NULL) && logged == 4);
    clear();
    parse("frobnicate=1\n");
    CHECK(logged == 1);
    /* radv_threaded: exactly 1 sets RADV's own variable to "1" (RADV takes atoi != 0), 0 removes it, the rest is ignored */
    clear();
    parse("radv_threaded=1\n");
    CHECK(is("RADV_THREADED_RECORDING", "1") && logged == 1);
    parse("radv_threaded=0\n");
    CHECK(is("RADV_THREADED_RECORDING", NULL));
    clear();
    parse("radv_threaded=yes\nradv_threaded=\nradv_threaded=2\n");
    CHECK(is("RADV_THREADED_RECORDING", NULL) && logged == 3);
    clear();
    parse("submit=thread\nradv_threaded=1\nclock=tsc\n");  /* the three together */
    CHECK(is("ZA_PERF_SUBMIT", "thread") && is("RADV_THREADED_RECORDING", "1") && is("ZA_PERF_CLOCK", "tsc"));
    /* the earlier keys still parse through r25's parser */
    clear();
    parse("# r25 test configuration\nscale=1\nforce60=1\nticks=tsc\nvkprof=0\ngaps=1\n# submit=thread\n# clock=tsc\n"
          "# radv_threaded=1\n");
    CHECK(is("LARECOMP_SCALE", "1") && is("ZA_PERF_FORCE60", "1") && is("SDL3_PS5_TICKS", "tsc") &&
          is("ZA_PERF_VKPROF_OFF", "1") && is("ZA_PERF_GAPS", "1") && is("ZA_PERF_SUBMIT", NULL) && is("ZA_PERF_CLOCK", NULL) &&
          is("RADV_THREADED_RECORDING", NULL));
    clear();
    parse("  submit=thread  \r\nclock=tsc # with a comment\r\ntsc=1\nprof=1\n");
    CHECK(is("ZA_PERF_SUBMIT", "thread") && is("ZA_PERF_CLOCK", "tsc") && is("LARECOMP_PS5_TSC", "1") &&
          is("ZA_PERF_GPUPROF_EVERY", "120"));
    printf("PASS za_r25_options.h: submit / clock / radv_threaded, bad values and unknown keys ignored, earlier keys unchanged\n");
    return 0;
}
