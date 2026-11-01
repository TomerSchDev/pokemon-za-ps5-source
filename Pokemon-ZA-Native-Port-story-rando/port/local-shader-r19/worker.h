#pragma once
#include <stddef.h>
#include <stdint.h>

#define ZA_LOCAL_MAX_SOURCE (2u << 20)
#define ZA_LOCAL_QUEUE_CAPACITY 8
/* One worker owns every glslang call. Calls block their existing shader-build
 * worker, never spawn a compiler per pipeline. The queue and input size are
 * bounded. Results are caller-owned; errors always leave words/count empty. */
struct za_local_metrics { double queue_ms, compile_ms; };
struct za_local_stats {
    uint64_t submitted, completed, failed, timed_out, rejected;
    unsigned slots_used, high_water;
    int ready, disabled;
};
int za_local_compiler_start(void);
int za_local_compile(const char *source, size_t length, int stage, uint32_t api,
                     uint32_t **words, size_t *count, char *error, size_t error_size,
                     struct za_local_metrics *metrics);
void za_local_compiler_stats(struct za_local_stats *out);
/* Tests/tools only: call after every caller has returned. One-shot lifetime. */
void za_local_compiler_shutdown(void);

int za_glsl_compile_for_api(const char *, int, uint32_t, uint32_t **, size_t *, char *, size_t);
