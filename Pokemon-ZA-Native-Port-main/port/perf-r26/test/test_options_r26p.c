/* Host test of za_r26p_options.h: the fps= key, and that r26's keys still parse through za_r26p_parse. */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../za_r26p_options.h"

static char env_names[64][64], env_values[64][128];
static int env_n;
static int t_setenv(const char *n, const char *v, int o) {
    (void)o;
    for (int i = 0; i < env_n; i++) if (!strcmp(env_names[i], n)) { snprintf(env_values[i], 128, "%s", v); return 0; }
    snprintf(env_names[env_n], 64, "%s", n); snprintf(env_values[env_n], 128, "%s", v); env_n++; return 0;
}
static int t_unsetenv(const char *n) {
    for (int i = 0; i < env_n; i++) if (!strcmp(env_names[i], n)) { env_names[i][0] = 0; return 0; }
    return 0;
}
static char *t_get(const char *n) {  /* (ZaGetenvFn's exact type: char *(*)(const char *), as getenv) */
    for (int i = 0; i < env_n; i++) if (!strcmp(env_names[i], n)) return env_values[i];
    return NULL;
}
static int logs; static char last_log[256];
static void t_log(const char *fmt, const char *a, const char *b) { snprintf(last_log, sizeof last_log, fmt, a, b); logs++; }

int main(void) {
    char text[] = "fps=1\nscale=1\nvkprof=0\nsubmit=thread\ndyn=off\n";
    za_r26p_parse(text, t_setenv, t_unsetenv, t_log);
    assert(t_get("ZA_PERF_FPS_COUNTER") && !strcmp(t_get("ZA_PERF_FPS_COUNTER"), "1"));
    assert(t_get("LARECOMP_SCALE") && !strcmp(t_get("LARECOMP_SCALE"), "1"));
    assert(t_get("ZA_PERF_VKPROF_OFF"));
    assert(t_get("ZA_PERF_SUBMIT") && !strcmp(t_get("ZA_PERF_SUBMIT"), "thread"));
    assert(!t_get("ZA_DT_POLICY"));
    char text2[] = "fps=0\n";
    za_r26p_parse(text2, t_setenv, t_unsetenv, t_log);
    assert(!t_get("ZA_PERF_FPS_COUNTER"));
    char text3[] = "fps=yes\n";
    logs = 0; za_r26p_parse(text3, t_setenv, t_unsetenv, t_log);
    assert(logs == 1 && strstr(last_log, "bad value for 'fps'"));
    assert(!t_get("ZA_PERF_FPS_COUNTER"));
    char text4[] = "# fps=1\n";
    logs = 0; za_r26p_parse(text4, t_setenv, t_unsetenv, t_log);
    assert(logs == 0 && !t_get("ZA_PERF_FPS_COUNTER"));
    /* the precedence rules are r26's, unchanged: no dyn, no force60 -> "off" */
    assert(!strcmp(za_r26_resolve(t_get, t_setenv, t_unsetenv, t_log), "off"));
    puts("PASS test_options_r26p: fps=1/0/bad/commented, r26 and r25 keys still parsed");
    return 0;
}
