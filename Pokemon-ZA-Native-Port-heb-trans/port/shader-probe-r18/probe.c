#define _POSIX_C_SOURCE 200809L
#include "../shader-prewarm/compiler.h"
#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>
#include <ps5platform/heap.h>

extern int sceKernelDebugOutText(int, const char *);
#define INPUT "/app0/shader-probe-r18b"
#define OUTPUT "/download0/za-shader-probe-r18b"
static char output[192];
static atomic_int done;
static int result = 1;

static double now_ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec * 1000.0 + t.tv_nsec / 1000000.0;
}
static void log_text(const char *text) {
    sceKernelDebugOutText(0, text);
}
static char *read_source(const char *name) {
    char path[256];
    snprintf(path, sizeof path, INPUT "/%s", name);
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END)) { fclose(f); return NULL; }
    long n = ftell(f);
    if (n <= 0 || n > (8 << 20)) { fclose(f); return NULL; }
    rewind(f);
    char *p = malloc((size_t)n + 1);
    if (!p) { fclose(f); return NULL; }
    size_t got = fread(p, 1, (size_t)n, f);
    fclose(f);
    if (got != (size_t)n) { free(p); return NULL; }
    p[n] = 0;
    return p;
}
static void heap_row(FILE *f, const char *phase) {
    struct ps5_heap_stats s = {0};
    ps5_heap_stats(&s);
    fprintf(f, "{\"type\":\"heap\",\"phase\":\"%s\",\"mapped_bytes\":%zu,"
            "\"peak_mapped_bytes\":%zu,\"segments\":%u,\"arenas\":%u,\"libc_fallbacks\":%llu}\n",
            phase, s.mapped_bytes, s.peak_bytes, s.segments, s.arenas, s.libc_fallbacks);
    fflush(f);
}
static int compile_one(FILE *f, const char *name, const char *source,
                       int stage, int expected, int iteration) {
    uint32_t *words = NULL;
    size_t count = 0;
    char error[4096] = {0};
    double start = now_ms();
    int ok = za_glsl_compile(source, stage, &words, &count, error, sizeof error);
    double elapsed = now_ms() - start;
    int passed = !!ok == !!expected;
    if (ok) {
        char path[320];
        snprintf(path, sizeof path, "%s/%02d-%s.spv", output, iteration, name);
        FILE *spv = fopen(path, "wb");
        if (!spv) passed = 0;
        else {
            size_t wrote = fwrite(words, sizeof *words, count, spv);
            int closed = fclose(spv);
            if (wrote != count || closed) passed = 0;
        }
    } else if (words || count || !error[0]) passed = 0;
    fprintf(f, "{\"type\":\"compile\",\"name\":\"%s\",\"iteration\":%d,"
            "\"stage\":%d,\"expected\":%d,\"ok\":%d,\"passed\":%d,\"bytes\":%zu,\"compile_ms\":%.3f}\n",
            name, iteration, stage, expected, ok, passed, count * sizeof *words, elapsed);
    free(words);
    heap_row(f, name);
    return passed;
}
static void *worker(void *unused) {
    (void)unused;
    char path[256];
    snprintf(path, sizeof path, "%s/results.jsonl", output);
    FILE *f = fopen(path, "wb");
    if (!f) { log_text("[za-shader-probe-r18b] cannot open results\n"); goto finished; }
    fprintf(f, "{\"type\":\"start\",\"build\":\"r18b\",\"pid\":%d,\"repeats\":3,\"worker_stack_bytes\":8388608}\n", getpid());
    heap_row(f, "before_init");
    double started = now_ms();
    int initialized = za_glsl_init();
    fprintf(f, "{\"type\":\"init\",\"ok\":%d,\"ms\":%.3f}\n", initialized, now_ms() - started);
    heap_row(f, "after_init");
    int passed = 0, total = 0;
    if (initialized) {
        const char *names[] = {
            "f120ba848ee181dc.vert", "3198145b25b05558.frag", "a1ef9d4227fc9202.vert",
            "a2c55b2c0d2b389c.vert", "1ec6b1959cac7285.frag", "e0988fdfe87fc048.vert",
            "adce547ac7e3f484.frag", "5deb7d0d2467a9be.vert", "67281a0d557ad6e9.vert",
            "7362f8f494e987bf.vert", "90d68f4f7edf55bc.frag", "1fad545410e2cf35.vert"
        };
        for (int iteration = 0; iteration < 3; ++iteration) {
            for (size_t i = 0; i < sizeof names / sizeof *names; ++i) {
                char *source = read_source(names[i]);
                ++total;
                if (source) {
                    int stage = strstr(names[i], ".vert") ? 0 : 1;
                    passed += compile_one(f, names[i], source, stage, 1, iteration);
                    free(source);
                } else {
                    fprintf(f, "{\"type\":\"missing_input\",\"name\":\"%s\"}\n", names[i]);
                    fflush(f);
                }
            }
            heap_row(f, "iteration_complete");
        }
        const char *compute = "#version 450\nlayout(local_size_x=1) in; void main() {}\n";
        const char *include = "#version 450\n#extension GL_GOOGLE_include_directive : require\n#include \"denied.glsl\"\nvoid main(){}\n";
        total += 5;
        passed += compile_one(f, "smoke.comp", compute, 2, 1, 0);
        passed += compile_one(f, "invalid.frag", "#version 450\nthis is not GLSL\n", 1, 0, 0);
        passed += compile_one(f, "include.vert", include, 0, 0, 0);
        passed += compile_one(f, "invalid.stage", compute, 5, 0, 0);
        passed += compile_one(f, "recovery.comp", compute, 2, 1, 0);
        za_glsl_finish();
        heap_row(f, "after_finish");
    }
    result = initialized && passed == 41 && total == 41 ? 0 : 1;
    fprintf(f, "{\"type\":\"complete\",\"passed\":%d,\"total\":%d,\"exit_code\":%d}\n", passed, total, result);
    fflush(f);
    fsync(fileno(f));
    fclose(f);
    log_text(result ? "[za-shader-probe-r18b] FAILED\n" : "[za-shader-probe-r18b] COMPLETE 41/41; awaiting host collection\n");
finished:
    atomic_store_explicit(&done, 1, memory_order_release);
    return NULL;
}
int main(void) {
    log_text("[za-shader-probe-r18b] starting bounded local compiler test\n");
    char *run = read_source("run-id.txt");
    if (!run) return 2;
    size_t n = strlen(run);
    if (!n || n > 48) { free(run); return 2; }
    for (size_t i = 0; i < n; ++i)
        if (!((run[i] >= 'a' && run[i] <= 'z') || (run[i] >= '0' && run[i] <= '9') || run[i] == '-')) {
            free(run); return 2;
        }
    snprintf(output, sizeof output, OUTPUT "/%s", run);
    free(run);
    if (mkdir(OUTPUT, 0777) && errno != EEXIST) return 3;
    if (mkdir(output, 0777)) return 3; /* Never replace an earlier run's evidence. */
    pthread_attr_t attr;
    if (pthread_attr_init(&attr)) return 4;
    if (pthread_attr_setstacksize(&attr, 8u << 20)) { pthread_attr_destroy(&attr); return 4; }
    pthread_t thread;
    int error = pthread_create(&thread, &attr, worker, NULL);
    pthread_attr_destroy(&attr);
    if (error) return 4;
    double deadline = now_ms() + 90000.0;
    while (!atomic_load_explicit(&done, memory_order_acquire)) {
        if (now_ms() >= deadline) {
            log_text("[za-shader-probe-r18b] watchdog 90s, terminating own probe\n");
            _exit(124);
        }
        struct timespec delay = {0, 100000000};
        nanosleep(&delay, NULL);
    }
    pthread_join(thread, NULL);
    /* Keep download0 mounted while the host copies and verifies every SPIR-V.
     * The host closes only the PID in this run's start record. SDK exit() was
     * observed to raise SIGSYS on this firmware. The 60s fallback retains that
     * known limitation; this is not a claim of a fixed normal title shutdown. */
    deadline = now_ms() + 60000.0;
    while (now_ms() < deadline) {
        struct timespec delay = {0, 100000000};
        nanosleep(&delay, NULL);
    }
    log_text("[za-shader-probe-r18b] collection timeout, using fallback exit\n");
    _exit(result);
}
