/* Host test of za_r24prof_options.h: the keys r24 already had keep their behaviour; r24-prof's keys validate their
 * values. Build: clang -fsanitize=address,undefined (test.sh). */
#include <assert.h>
#include <stdio.h>
#include <string.h>

#include "../za_r24prof_options.h"

#define MAXV 32
static struct { char name[48], value[64]; } env[MAXV];
static int nenv, nlog;

static int mock_set(const char *name, const char *value, int overwrite) {
    (void)overwrite;
    for (int i = 0; i < nenv; i++)
        if (!strcmp(env[i].name, name)) { snprintf(env[i].value, sizeof env[i].value, "%s", value); return 0; }
    assert(nenv < MAXV);
    snprintf(env[nenv].name, sizeof env[nenv].name, "%s", name);
    snprintf(env[nenv].value, sizeof env[nenv].value, "%s", value);
    nenv++;
    return 0;
}
static int mock_unset(const char *name) {
    for (int i = 0; i < nenv; i++)
        if (!strcmp(env[i].name, name)) { env[i] = env[--nenv]; return 0; }
    return 0;
}
static const char *get(const char *name) {
    for (int i = 0; i < nenv; i++) if (!strcmp(env[i].name, name)) return env[i].value;
    return NULL;
}
static void mock_log(const char *fmt, const char *a, const char *b) { (void)fmt, (void)a, (void)b; nlog++; }
static void reset(void) { nenv = 0, nlog = 0; }
static void parse(const char *text) {
    char buf[1024];
    snprintf(buf, sizeof buf, "%s", text);
    za_r24prof_parse(buf, mock_set, mock_unset, mock_log);
}
static int one(const char *key, const char *val) {
    ZaOptState st = {0};
    return za_r24prof_option(key, val, &st, mock_set, mock_unset);
}

int main(void) {
    /* the package default: only r24's keys take effect */
    reset();
    parse("# r24-prof options\ngaps=1\ndcache=tls\nprof=0\n# mode=1920x1080\n# scale=1\n# force60=1\n# sample=1\n");
    assert(nenv == 2 && !strcmp(get("ZA_PERF_GAPS"), "1") && !strcmp(get("ZA_PERF_DCACHE"), "tls"));

    /* r24 behaviour: gaps=0 unsets; prof=1 without prof_every -> 120; prof_every wins; mode passes through */
    reset();
    mock_set("ZA_PERF_GAPS", "1", 1);
    parse("gaps=0\nprof=1\nmode=1920x1080\n");
    assert(!get("ZA_PERF_GAPS") && !strcmp(get("ZA_PERF_GPUPROF_EVERY"), "120") && !strcmp(get("SDL3_PS5_MODE"), "1920x1080"));
    reset();
    parse("prof=1\nprof_every=30\n");
    assert(!strcmp(get("ZA_PERF_GPUPROF_EVERY"), "30"));
    reset();
    parse("prof=0\n");
    assert(!get("ZA_PERF_GPUPROF_EVERY"));

    /* scale */
    reset();
    assert(one("scale", "1") == ZA_OPT_SET && !strcmp(get("LARECOMP_SCALE"), "1"));
    assert(one("scale", "1.5") == ZA_OPT_SET && !strcmp(get("LARECOMP_SCALE"), "1.5"));
    assert(one("scale", "0.25") == ZA_OPT_SET && one("scale", "4") == ZA_OPT_SET);
    reset();
    assert(one("scale", "0.2") == ZA_OPT_BAD_VALUE && one("scale", "4.01") == ZA_OPT_BAD_VALUE);
    assert(one("scale", "1.5x") == ZA_OPT_BAD_VALUE && one("scale", "") == ZA_OPT_BAD_VALUE && one("scale", "abc") == ZA_OPT_BAD_VALUE);
    assert(nenv == 0);

    /* force60 / sample: 0 unsets, 1 sets "1", anything else is ignored */
    reset();
    assert(one("force60", "1") == ZA_OPT_SET && !strcmp(get("ZA_PERF_FORCE60"), "1"));
    assert(one("force60", "2") == ZA_OPT_BAD_VALUE && !strcmp(get("ZA_PERF_FORCE60"), "1"));
    assert(one("force60", "0") == ZA_OPT_UNSET && !get("ZA_PERF_FORCE60"));
    assert(one("sample", "1") == ZA_OPT_SET && !strcmp(get("ZA_PROF_SAMPLE"), "1"));
    assert(one("sample", "yes") == ZA_OPT_BAD_VALUE);
    assert(one("sample", "0") == ZA_OPT_UNSET && !get("ZA_PROF_SAMPLE"));

    /* numeric ranges */
    reset();
    assert(one("sample_us", "199") == ZA_OPT_BAD_VALUE && one("sample_us", "100001") == ZA_OPT_BAD_VALUE);
    assert(one("sample_us", "12a") == ZA_OPT_BAD_VALUE && one("sample_us", "") == ZA_OPT_BAD_VALUE);
    assert(one("sample_us", "200") == ZA_OPT_SET && one("sample_us", "100000") == ZA_OPT_SET && !strcmp(get("ZA_PROF_US"), "100000"));
    assert(one("sample_seconds", "4") == ZA_OPT_BAD_VALUE && one("sample_seconds", "121") == ZA_OPT_BAD_VALUE);
    assert(one("sample_seconds", "5") == ZA_OPT_SET && one("sample_seconds", "120") == ZA_OPT_SET);
    assert(one("sample_keep", "0") == ZA_OPT_BAD_VALUE && one("sample_keep", "201") == ZA_OPT_BAD_VALUE);
    assert(one("sample_keep", "1") == ZA_OPT_SET && one("sample_keep", "200") == ZA_OPT_SET && !strcmp(get("ZA_PROF_KEEP"), "200"));
    assert(one("sample_threads", "render") == ZA_OPT_SET && one("sample_threads", "all") == ZA_OPT_SET);
    assert(one("sample_threads", "guest") == ZA_OPT_BAD_VALUE && !strcmp(get("ZA_PROF_THREADS"), "all"));

    /* unknown keys, lines without '=', CRLF, blanks and comments */
    reset();
    parse("  sample = 1 \r\nfoo=bar\njunk line\n\t# nothing\nsample_us=500\r\nscale=1 # inline comment\n");
    /* ("sample " with a trailing blank before '=' is not the key "sample": only trailing blanks of the line are cut) */
    assert(!get("ZA_PROF_SAMPLE"));
    assert(!strcmp(get("ZA_PROF_US"), "500") && !strcmp(get("LARECOMP_SCALE"), "1"));
    assert(nlog >= 5);

    printf("PASS test_options: package default, r24 keys (gaps/prof/prof_every/mode), scale/force60/sample ranges, "
           "bad values ignored, comments/CRLF/unknown keys\n");
    return 0;
}
