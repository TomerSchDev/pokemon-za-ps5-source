/* r25: the keys of /app0/perf-r24-options.txt -> environment variables. Every r24 / r24-prof / r24-clock key is
 * parsed exactly as before (port/perf-r24clock/za_r24clock_options.h, included unchanged); r25 adds:
 *
 *   submit=inline|thread  ZA_PERF_SUBMIT         thread: a submitter thread makes the vkQueueSubmit2 / vkQueuePresentKHR
 *                                                calls, in order, off the game's render thread (exec.c,
 *                                                za_submitter_vk.inc); inline (or absent): as r24-clock
 *   clock=real|tsc        ZA_PERF_CLOCK          tsc: after a cross-core TSC check, CLOCK_MONOTONIC from the TSC for every
 *                                                caller but the game's timing (za_clock_r25.c); real (or absent): as before
 *   radv_threaded=0|1     RADV_THREADED_RECORDING  1: RADV's threaded recording (PS5_Mesa d0d7325e, in the linked
 *                                                archive: layers/radv_threaded_layer.c reads it with os_get_option at
 *                                                vkCreateDevice) - vkCmd* calls are queued and a worker of the device
 *                                                records them, vkEndCommandBuffer waits for it; 0 (or absent): off
 * Factored out of the title entry so the host test (test/test_options.c) drives the same code. */
#pragma once
#include "../perf-r24clock/za_r24clock_options.h"
/* (r24-clock's whole-file parser is replaced by za_r25_parse below; referenced so -Wunused-function stays quiet) */
static void (*const za_r25_r24clock_parse)(char *, ZaSetenvFn, ZaUnsetenvFn, ZaOptLogFn) __attribute__((unused)) =
    za_r24clock_parse;

static int za_r25_option(const char *key, const char *val, ZaOptState *st, ZaSetenvFn set, ZaUnsetenvFn unset) {
    if (!strcmp(key, "submit")) {
        if (!strcmp(val, "inline")) return unset("ZA_PERF_SUBMIT"), ZA_OPT_UNSET;
        if (!strcmp(val, "thread")) return set("ZA_PERF_SUBMIT", "thread", 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    if (!strcmp(key, "clock")) {
        if (!strcmp(val, "real")) return unset("ZA_PERF_CLOCK"), ZA_OPT_UNSET;
        if (!strcmp(val, "tsc")) return set("ZA_PERF_CLOCK", "tsc", 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    if (!strcmp(key, "radv_threaded")) {
        if (!strcmp(val, "0")) return unset("RADV_THREADED_RECORDING"), ZA_OPT_UNSET;
        if (!strcmp(val, "1")) return set("RADV_THREADED_RECORDING", "1", 1), ZA_OPT_SET;
        return ZA_OPT_BAD_VALUE;
    }
    return za_r24clock_option(key, val, st, set, unset);
}

/* The whole file, as za_r24clock_parse but with r25's keys. Modifies text. */
static void za_r25_parse(char *text, ZaSetenvFn set, ZaUnsetenvFn unset, ZaOptLogFn log) {
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
        int r = za_r25_option(key, val, &st, set, unset);
        if (r == ZA_OPT_UNKNOWN) log("[za-r24-options] unknown key '%s'%s\n", key, "");
        else if (r == ZA_OPT_BAD_VALUE) log("[za-r24-options] bad value for '%s': '%s' (ignored)\n", key, val);
        else if (r == ZA_OPT_FLAG) log("[za-r24-options] prof=%s%s\n", val, st.prof ? " (per-pass GPU profile)" : "");
        else log("[za-r24-options] %s=%s\n", key, val);
    }
    if (st.prof && !st.every) set("ZA_PERF_GPUPROF_EVERY", "120", 1);
}
