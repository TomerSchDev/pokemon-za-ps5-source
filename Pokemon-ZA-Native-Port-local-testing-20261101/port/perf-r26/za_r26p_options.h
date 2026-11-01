/* r26p: the keys of /app0/perf-r24-options.txt -> environment variables. Every r24 ... r26 key is parsed exactly as
 * before (port/perf-r26/za_r26_options.h, included unchanged); r26p adds:
 *
 *   fps=0|1              ZA_PERF_FPS_COUNTER   1: the L3+R3 overlay's live FPS readout starts ON (its "FPS COUNTER"
 *                                              row toggles it; the choice is persisted per run in cheats.txt and then
 *                                              wins over this default); 0 (or absent): starts OFF
 * Factored out of the title entry so the host test (test/test_options_r26p.c) drives the same code. */
#pragma once
#include "za_r26_options.h"
/* (r26's whole-file parser is replaced by za_r26p_parse below; referenced so -Wunused-function stays quiet) */
static void (*const za_r26p_r26_parse)(char *, ZaSetenvFn, ZaUnsetenvFn, ZaOptLogFn) __attribute__((unused)) =
    za_r26_parse;

static int za_r26p_option(const char *key, const char *val, ZaOptState *st, ZaSetenvFn set, ZaUnsetenvFn unset) {
    if (!strcmp(key, "fps")) {
        if (!strcmp(val, "0")) return unset("ZA_PERF_FPS_COUNTER"), ZA_OPT_UNSET;
        if (!strcmp(val, "1")) return set("ZA_PERF_FPS_COUNTER", "1", 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    return za_r26_option(key, val, st, set, unset);
}

/* The whole file, as za_r26_parse but with r26p's key. Modifies text. */
static void za_r26p_parse(char *text, ZaSetenvFn set, ZaUnsetenvFn unset, ZaOptLogFn log) {
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
        int r = za_r26p_option(key, val, &st, set, unset);
        if (r == ZA_OPT_UNKNOWN) log("[za-r24-options] unknown key '%s'%s\n", key, "");
        else if (r == ZA_OPT_BAD_VALUE) log("[za-r24-options] bad value for '%s': '%s' (ignored)\n", key, val);
        else if (r == ZA_OPT_FLAG) log("[za-r24-options] prof=%s%s\n", val, st.prof ? " (per-pass GPU profile)" : "");
        else log("[za-r24-options] %s=%s\n", key, val);
    }
    if (st.prof && !st.every) set("ZA_PERF_GPUPROF_EVERY", "120", 1);
}
