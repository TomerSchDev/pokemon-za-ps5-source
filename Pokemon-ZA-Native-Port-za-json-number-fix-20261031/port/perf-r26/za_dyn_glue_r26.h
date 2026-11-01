/* r26: port/dynamic-timing/za_dyn_glue.h (the hook functions, unchanged) plus the [za-r24-perf] report. */
#ifndef ZA_DYN_GLUE_R26_H
#define ZA_DYN_GLUE_R26_H
#include <stddef.h>

#include "../dynamic-timing/za_dyn_glue.h"

/* Appends " dyn=... dyn_mode=... ..." for the window since the previous call (one caller: exec.c's stats line on the
 * render thread). Reads only atomics the frame hook (H1) publishes. Returns the characters written. */
size_t za_dt_report(char *out, size_t cap);

/* The model (port/dynamic-timing/za_dyn_timing.c) is compiled with -Dllround=za_dt_llround (build-perf-r26.sh,
 * test/test.sh): its one libm call is served here, so the title gains no dynamic import over r25 (llround would be new;
 * its sibling lround is the one r24-clock ran on the console). Rounds half away from zero, as llround. */
long long za_dt_llround(double x);

#endif
