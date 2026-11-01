/* Persistent host compiler. Tab-delimited local paths, no shell execution. */
#include "compiler.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

int main(void) {
    if (!za_glsl_init()) return 2;
    char line[8192];
    while (fgets(line, sizeof line, stdin)) {
        char *stage_s = strtok(line, "\t"), *input = strtok(NULL, "\t"), *output = strtok(NULL, "\r\n");
        int ok = 0, stage = stage_s ? atoi(stage_s) : -1;
        char *source = NULL, error[4096] = "Invalid request";
        uint32_t *words = NULL; size_t count = 0;
        struct timespec start, end; clock_gettime(CLOCK_MONOTONIC, &start);
        FILE *f = input ? fopen(input, "rb") : NULL;
        if (f && output) {
            if (!fseek(f, 0, SEEK_END)) {
                long n = ftell(f); rewind(f);
                if (n >= 0 && n <= (8 << 20)) {
                    source = malloc((size_t)n + 1);
                    if (source && fread(source, 1, (size_t)n, f) == (size_t)n) {
                        source[n] = 0;
                        ok = za_glsl_compile(source, stage, &words, &count, error, sizeof error);
                    }
                }
            }
        }
        if (f) fclose(f);
        if (ok) {
            f = fopen(output, "wb");
            if (!f) ok = 0;
            else { size_t written = fwrite(words, sizeof(uint32_t), count, f); int closed = fclose(f); ok = written == count && closed == 0; }
        }
        if (!ok && output) {
            char log[4096];
            if (snprintf(log, sizeof log, "%s.error", output) < (int)sizeof log) {
                f = fopen(log, "w"); if (f) { fputs(error, f); fclose(f); }
            }
        }
        clock_gettime(CLOCK_MONOTONIC, &end);
        printf("{\"ok\":%s,\"bytes\":%zu,\"compile_ms\":%.3f}\n", ok ? "true" : "false", count*4,
            (end.tv_sec-start.tv_sec)*1000.0+(end.tv_nsec-start.tv_nsec)/1000000.0);
        fflush(stdout); free(source); free(words);
    }
    za_glsl_finish(); return 0;
}
