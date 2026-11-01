/* r24-prof: the keys of /app0/perf-r24-options.txt -> environment variables the runtime reads.
 * r24-perf's keys unchanged, plus r24-prof's. Factored out of the title entry so the host test
 * (test/test_options.c) drives the same code. A missing file or key keeps the r23c/r24 behaviour.
 *
 *   dcache=cpu|tls        ZA_PERF_DCACHE         (r24) dispatch cache per Cpu, or thread-local
 *   gaps=0|1              ZA_PERF_GAPS           (r24) GPU timeline per frame (0: unset)
 *   prof=0|1                                     (r24) per-pass GPU profile ...
 *   prof_every=<n>        ZA_PERF_GPUPROF_EVERY  (r24) ... every n frames (120 when prof=1 and this is absent)
 *   mode=<w>x<h>          SDL3_PS5_MODE          (r24) display mode, else the first one
 *   scale=<f>             LARECOMP_SCALE         render height = 1080 x f whatever the display (0.25 .. 4)
 *   force60=0|1           ZA_PERF_FORCE60        the game's frame mode forced to 60 at every read (measurement)
 *   sample=0|1            ZA_PROF_SAMPLE         sampling CPU profiler
 *   sample_us=<n>         ZA_PROF_US             period between samples of the render thread (200 .. 100000)
 *   sample_threads=render|all ZA_PROF_THREADS    render thread only, or also every guest thread (round robin)
 *   sample_seconds=<n>    ZA_PROF_SECONDS        one sample file and one klog summary per window (5 .. 120)
 *   sample_keep=<n>       ZA_PROF_KEEP           files kept per boot, the oldest overwritten (1 .. 200) */
#pragma once
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>

typedef int (*ZaSetenvFn)(const char *name, const char *value, int overwrite);
typedef int (*ZaUnsetenvFn)(const char *name);
typedef void (*ZaOptLogFn)(const char *fmt, const char *a, const char *b);

enum { ZA_OPT_SET = 0, ZA_OPT_UNSET = 1, ZA_OPT_FLAG = 2, ZA_OPT_UNKNOWN = -1, ZA_OPT_BAD_VALUE = -2 };

typedef struct { bool prof, every; } ZaOptState;

static bool za_opt_int(const char *val, long lo, long hi) {
    char *end = NULL;
    if (!val || !*val) return false;
    long v = strtol(val, &end, 10);
    return end && !*end && v >= lo && v <= hi;
}

static bool za_opt_bool(const char *val, bool *out) {
    if (!strcmp(val, "0")) { *out = false; return true; }
    if (!strcmp(val, "1")) { *out = true; return true; }
    return false;
}

/* One key=value. Returns ZA_OPT_*; writes nothing for an unknown key or a bad value. */
static int za_r24prof_option(const char *key, const char *val, ZaOptState *st, ZaSetenvFn set, ZaUnsetenvFn unset) {
    bool b;
    if (!strcmp(key, "prof")) { st->prof = atoi(val) != 0; return ZA_OPT_FLAG; }  /* (LARECOMP_VK_PROF is r16's) */
    if (!strcmp(key, "dcache")) return set("ZA_PERF_DCACHE", val, 1), ZA_OPT_SET;
    if (!strcmp(key, "gaps")) {
        if (atoi(val) == 0) return unset("ZA_PERF_GAPS"), ZA_OPT_UNSET;
        return set("ZA_PERF_GAPS", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "prof_every")) { st->every = true; return set("ZA_PERF_GPUPROF_EVERY", val, 1), ZA_OPT_SET; }
    if (!strcmp(key, "mode")) return set("SDL3_PS5_MODE", val, 1), ZA_OPT_SET;
    if (!strcmp(key, "scale")) {
        char *end = NULL;
        double f = val && *val ? strtod(val, &end) : 0;
        if (!end || *end || !(f >= 0.25 && f <= 4.0)) return ZA_OPT_BAD_VALUE;
        return set("LARECOMP_SCALE", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "force60") || !strcmp(key, "sample")) {
        const char *var = key[0] == 'f' ? "ZA_PERF_FORCE60" : "ZA_PROF_SAMPLE";
        if (!za_opt_bool(val, &b)) return ZA_OPT_BAD_VALUE;
        if (!b) return unset(var), ZA_OPT_UNSET;
        return set(var, "1", 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "sample_us")) {
        if (!za_opt_int(val, 200, 100000)) return ZA_OPT_BAD_VALUE;
        return set("ZA_PROF_US", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "sample_threads")) {
        if (strcmp(val, "render") && strcmp(val, "all")) return ZA_OPT_BAD_VALUE;
        return set("ZA_PROF_THREADS", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "sample_seconds")) {
        if (!za_opt_int(val, 5, 120)) return ZA_OPT_BAD_VALUE;
        return set("ZA_PROF_SECONDS", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "sample_keep")) {
        if (!za_opt_int(val, 1, 200)) return ZA_OPT_BAD_VALUE;
        return set("ZA_PROF_KEEP", val, 1), ZA_OPT_SET;
    }
    return ZA_OPT_UNKNOWN;
}

/* The whole file: one key=value a line, '#' starts a comment, blanks trimmed. Modifies text. */
static void za_r24prof_parse(char *text, ZaSetenvFn set, ZaUnsetenvFn unset, ZaOptLogFn log) {
    ZaOptState st = {false, false};
    for (char *line = text, *next; line && *line; line = next) {
        next = strchr(line, '\n');
        if (next) *next++ = 0;
        char *hash = strchr(line, '#');
        if (hash) *hash = 0;
        size_t len = strlen(line);
        while (len && (line[len - 1] == '\r' || line[len - 1] == ' ' || line[len - 1] == '\t')) line[--len] = 0;
        while (*line == ' ' || *line == '\t') line++;
        if (!*line) continue;
        char *eq = strchr(line, '=');
        if (!eq) { log("[za-r24-options] ignored '%s'%s\n", line, ""); continue; }
        *eq = 0;
        const char *key = line, *val = eq + 1;
        int r = za_r24prof_option(key, val, &st, set, unset);
        if (r == ZA_OPT_UNKNOWN) log("[za-r24-options] unknown key '%s'%s\n", key, "");
        else if (r == ZA_OPT_BAD_VALUE) log("[za-r24-options] bad value for '%s': '%s' (ignored)\n", key, val);
        else if (r == ZA_OPT_FLAG) log("[za-r24-options] prof=%s%s\n", val, st.prof ? " (per-pass GPU profile)" : "");
        else log("[za-r24-options] %s=%s\n", key, val);
    }
    if (st.prof && !st.every) set("ZA_PERF_GPUPROF_EVERY", "120", 1);
}
