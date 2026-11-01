/* Host test of za_clock.c: the clock_gettime wrap counts and times calls per thread class (render / guest / other)
 * and za_clock_report prints and resets the window. The PS5 functions are stubbed: a fake TSC at 1 GHz that the
 * stubbed real clock_gettime advances by a known amount, so the reported time inside the call is exact.
 * Build: clang -fsanitize=address,undefined -pthread (test.sh). */
#include <assert.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

static _Atomic uint64_t fake_tsc = 1000;
uint64_t sceKernelReadTsc(void) { return fake_tsc += 1; }  /* (each read advances 1 ns) */
uint64_t sceKernelGetTscFrequency(void) { return 1000000000ull; }
int sceKernelDebugOutText(int channel, const char *text) { (void)channel, (void)text; return 0; }
int __real_clock_gettime(clockid_t id, struct timespec *ts) {
    fake_tsc += 20000;  /* a 20 us syscall */
    return clock_gettime(id, ts);
}
static _Atomic int render_noted, begun, ended;
void __real_za_prof_note_render(void) { render_noted++; }
void __real_za_prof_thread_begin(uint64_t gid, uint64_t entry, int prio) { (void)gid, (void)entry, (void)prio; begun++; }
void __real_za_prof_thread_end(void) { ended++; }

#include "../za_clock.c"

static void calls(int n) {
    struct timespec ts;
    for (int i = 0; i < n; i++) assert(__wrap_clock_gettime(CLOCK_MONOTONIC, &ts) == 0);
}
/* The render thread stays alive until the others are done, as on the console: a finished thread's pthread_t may be
 * reused by the next one created (it would then count as the render thread). */
static pthread_mutex_t m = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cv = PTHREAD_COND_INITIALIZER;
static int render_ready, others_done;
static void *render_thread(void *a) {
    (void)a;
    __wrap_za_prof_note_render();
    calls(300);
    pthread_mutex_lock(&m);
    render_ready = 1;
    pthread_cond_broadcast(&cv);
    while (!others_done) pthread_cond_wait(&cv, &m);
    pthread_mutex_unlock(&m);
    return NULL;
}
static void *guest_thread(void *a) {
    (void)a;
    __wrap_za_prof_thread_begin(1, 2, 3);
    calls(100);
    __wrap_za_prof_thread_end();
    calls(10);  /* (after its end: no longer a guest) */
    return NULL;
}
static void *other_thread(void *a) { (void)a; calls(50); return NULL; }

static unsigned long long field(const char *text, const char *key) {
    char pat[64];
    snprintf(pat, sizeof pat, " %s=", key);
    const char *p = strstr(text, pat);
    assert(p);
    return strtoull(p + strlen(pat), NULL, 10);
}

int main(void) {
    pthread_t r, g[4], o;
    assert(!pthread_create(&r, NULL, render_thread, NULL));
    pthread_mutex_lock(&m);  /* (the render thread is known and done counting before the others start) */
    while (!render_ready) pthread_cond_wait(&cv, &m);
    pthread_mutex_unlock(&m);
    for (int i = 0; i < 4; i++) assert(!pthread_create(&g[i], NULL, guest_thread, NULL));
    assert(!pthread_create(&o, NULL, other_thread, NULL));
    for (int i = 0; i < 4; i++) assert(!pthread_join(g[i], NULL));
    assert(!pthread_join(o, NULL));
    calls(7);  /* main: other */
    char line[512];
    size_t n = za_clock_report(line, sizeof line);
    assert(n == strlen(line));
    printf("window 1:%s\n", line);
    pthread_mutex_lock(&m);
    others_done = 1;
    pthread_cond_broadcast(&cv);
    pthread_mutex_unlock(&m);
    assert(!pthread_join(r, NULL));
    assert(field(line, "cg_render") == 300 && field(line, "cg_guest") == 400 && field(line, "cg_other") == 50 + 40 + 7);
    /* each call: 20,000 ns inside plus the 1 ns of the second TSC read */
    assert(field(line, "cg_render_ns") == 300ull * 20001 && field(line, "cg_guest_ns") == 400ull * 20001);
    assert(field(line, "cg_other_ns") == 97ull * 20001 && field(line, "cg_render_max_ns") == 20001);
    assert(render_noted == 1 && begun == 4 && ended == 4);
    /* the window resets */
    n = za_clock_report(line, sizeof line);
    assert(field(line, "cg_render") == 0 && field(line, "cg_guest") == 0 && field(line, "cg_other") == 0);
    assert(field(line, "cg_render_max_ns") == 0);
    /* a short buffer: truncated, NUL-terminated, never past cap */
    calls(3);
    char small[24];
    memset(small, 'x', sizeof small);
    n = za_clock_report(small, sizeof small);
    assert(n < sizeof small && small[n] == 0 && strlen(small) == n);
    printf("PASS test_clock: per-class counts (render 300 / guest 400 / other 97), time inside the call, max, window "
           "reset, truncation\n");
    return 0;
}
