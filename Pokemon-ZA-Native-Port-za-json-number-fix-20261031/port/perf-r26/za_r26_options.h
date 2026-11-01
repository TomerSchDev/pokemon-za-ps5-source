/* r26: the keys of /app0/perf-r24-options.txt -> environment variables. Every r24 / r24-prof / r24-clock / r25 key is
 * parsed exactly as before (port/perf-r25/za_r25_options.h, included unchanged); r26 adds the dynamic frame timing
 * (port/perf-r26/za_dyn_glue_r26.c, the hooks H1-H7 in the game archive):
 *
 *   dyn=off|safe|rc3          ZA_DT_POLICY (+ ZA_R26_DYN_REQUESTED)  safe: the recommended controller - the game stays
 *                             in its 60 mode (0) while the smoothed rate is 46 FPS or more and its step follows the real
 *                             frame time between 16.67 and 33.33 ms; below 46 the 30 mode index (1) with the same real-time
 *                             step, back to 0 after 30 frames at 48 or more; present interval 1 throughout. rc3: RC3.0's
 *                             decisions (integer FPS, its 46 threshold and snaps) on the same hooks, for comparison.
 *                             off (or absent): r25 exactly - r16's za_title_frame_cfg (and force60) decide the mode.
 *   dyn_log=<0..3600>         ZA_DT_LOG              seconds between [za-dyn] status lines (default 2; 0: switches only)
 *   dyn_anim=table|step       ZA_DT_ANIM             H6/H7: step = RC3-like animation denominator (A/B experiment only)
 *   dyn_stress_fps=<0|20..60> ZA_DT_STRESS_FPS       console test: hold the game at this rate (a limiter in H1; works with
 *                                                   dyn=off too, to show static 60's slow motion); 0 = off
 *   dyn_spike_ms=<0|1..5000>  ZA_DT_STRESS_SPIKE_MS  console test: one long frame of this length ...
 *   dyn_spike_every=<0|1..100000> ZA_DT_STRESS_SPIKE_EVERY  ... every this many frames
 *   fnprof=<from>:<to>        LARECOMP_FNPROF (+ LARECOMP_FNPROF_OUT=/download0/zarecomp/fnprof-r26.txt)  count guest
 *                             function entries between those presented frames (runtime/fnprof.c); slows the window down
 *
 * Precedence (za_r26_resolve, after the whole file): force60=1 is a measurement override - with it, dyn is not
 * applied (ZA_DT_POLICY removed, logged): the frame mode is static 60 through r16's hook and r24-prof's wrap, as in
 * r25. With dyn=safe|rc3 in effect, LARECOMP_PRESENT_INTERVAL is removed (it would override H2's interval 1).
 * Factored out of the title entry so the host test (test/test_options.c) drives the same code. */
#pragma once
#include <stdio.h>

#include "../perf-r25/za_r25_options.h"
/* (r25's whole-file parser is replaced by za_r26_parse below; referenced so -Wunused-function stays quiet) */
static void (*const za_r26_r25_parse)(char *, ZaSetenvFn, ZaUnsetenvFn, ZaOptLogFn) __attribute__((unused)) =
    za_r25_parse;

static int za_r26_int_key(const char *val, long lo, long hi, const char *var, ZaSetenvFn set, ZaUnsetenvFn unset) {
    if (!strcmp(val, "0")) return unset(var), ZA_OPT_UNSET;
    if (!za_opt_int(val, lo, hi)) return ZA_OPT_BAD_VALUE;
    return set(var, val, 1), ZA_OPT_SET;
}

static bool za_r26_fnprof_value(const char *val) {
    char *end = NULL;
    long from = strtol(val, &end, 10);
    if (!end || end == val || *end != ':' || from < 0) return false;
    const char *b = end + 1;
    long to = strtol(b, &end, 10);
    return end && end != b && !*end && to > from && to <= 100000000L;
}

static int za_r26_option(const char *key, const char *val, ZaOptState *st, ZaSetenvFn set, ZaUnsetenvFn unset) {
    if (!strcmp(key, "dyn")) {
        if (!strcmp(val, "off")) return unset("ZA_DT_POLICY"), unset("ZA_R26_DYN_REQUESTED"), ZA_OPT_UNSET;
        if (!strcmp(val, "safe") || !strcmp(val, "rc3"))
            return set("ZA_DT_POLICY", val, 1), set("ZA_R26_DYN_REQUESTED", val, 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    if (!strcmp(key, "dyn_log")) {
        if (!za_opt_int(val, 0, 3600)) return ZA_OPT_BAD_VALUE;
        return set("ZA_DT_LOG", val, 1), ZA_OPT_SET;
    }
    if (!strcmp(key, "dyn_anim")) {
        if (!strcmp(val, "table")) return unset("ZA_DT_ANIM"), ZA_OPT_UNSET;
        if (!strcmp(val, "step")) return set("ZA_DT_ANIM", "step", 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    if (!strcmp(key, "dyn_stress_fps")) return za_r26_int_key(val, 20, 60, "ZA_DT_STRESS_FPS", set, unset);
    if (!strcmp(key, "dyn_spike_ms")) return za_r26_int_key(val, 1, 5000, "ZA_DT_STRESS_SPIKE_MS", set, unset);
    if (!strcmp(key, "dyn_spike_every")) return za_r26_int_key(val, 1, 100000, "ZA_DT_STRESS_SPIKE_EVERY", set, unset);
    if (!strcmp(key, "fnprof")) {
        if (!za_r26_fnprof_value(val)) return ZA_OPT_BAD_VALUE;
        set("LARECOMP_FNPROF", val, 1);
        set("LARECOMP_FNPROF_OUT", "/download0/zarecomp/fnprof-r26.txt", 1);
        return ZA_OPT_SET;
    }
    return za_r25_option(key, val, st, set, unset);
}

/* The whole file, as za_r25_parse but with r26's keys. Modifies text. */
static void za_r26_parse(char *text, ZaSetenvFn set, ZaUnsetenvFn unset, ZaOptLogFn log) {
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
        int r = za_r26_option(key, val, &st, set, unset);
        if (r == ZA_OPT_UNKNOWN) log("[za-r24-options] unknown key '%s'%s\n", key, "");
        else if (r == ZA_OPT_BAD_VALUE) log("[za-r24-options] bad value for '%s': '%s' (ignored)\n", key, val);
        else if (r == ZA_OPT_FLAG) log("[za-r24-options] prof=%s%s\n", val, st.prof ? " (per-pass GPU profile)" : "");
        else log("[za-r24-options] %s=%s\n", key, val);
    }
    if (st.prof && !st.every) set("ZA_PERF_GPUPROF_EVERY", "120", 1);
}

typedef char *(*ZaGetenvFn)(const char *name);

/* After the whole file: the precedence rules. Returns the policy in effect: "off", "safe" or "rc3". */
static const char *za_r26_resolve(ZaGetenvFn get, ZaSetenvFn set, ZaUnsetenvFn unset, ZaOptLogFn log) {
    (void)set;
    const char *p = get("ZA_DT_POLICY");
    const char *f = get("ZA_PERF_FORCE60");
    bool force60 = f && !strcmp(f, "1");
    if (p && (!strcmp(p, "safe") || !strcmp(p, "rc3")) && force60) {
        log("[za-r26] dyn=%s not applied: force60=1 is a measurement override (static 60 through r16's hook and "
            "r24-prof's wrap, as r25)%s\n", p, "");
        unset("ZA_DT_POLICY");
        return "off";
    }
    if (p && (!strcmp(p, "safe") || !strcmp(p, "rc3"))) {
        if (get("LARECOMP_PRESENT_INTERVAL")) {
            unset("LARECOMP_PRESENT_INTERVAL");
            log("[za-r26] LARECOMP_PRESENT_INTERVAL removed: dyn=%s sets the present interval (H2)%s\n", p, "");
        }
        log("[za-r26] dyn=%s: dynamic timing owns the game's frame mode; r16's za_title_frame_cfg is not called, so its "
            "FPS TRIAL row and its fallback to 30 cannot act%s\n", p, "");
        return !strcmp(p, "safe") ? "safe" : "rc3";
    }
    log("[za-r26] dyn=off: the frame mode is r16's (za_title_frame_cfg%s%s), as r25\n",
        force60 ? ", force60 wrap: static 60" : "", "");
    return "off";
}
