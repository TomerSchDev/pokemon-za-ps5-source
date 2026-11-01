#include "compiler.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    int stage = !strcmp(argv[1], "vert") ? 0 : !strcmp(argv[1], "frag") ? 1 : !strcmp(argv[1], "comp") ? 2 : -1;
    FILE *f = fopen(argv[2], "rb");
    if (!f) return 3;
    if (fseek(f, 0, SEEK_END)) { fclose(f); return 3; }
    long n = ftell(f);
    if (n < 0 || n > (8 << 20)) { fclose(f); return 3; }
    rewind(f);
    char *source = malloc((size_t)n + 1);
    if (!source) { fclose(f); return 3; }
    if (fread(source, 1, (size_t)n, f) != (size_t)n) { fclose(f); free(source); return 3; }
    fclose(f); source[n] = 0;
    uint32_t *words = NULL; size_t count = 0; char error[4096];
    if (!za_glsl_init()) { free(source); return 4; }
    struct timespec start, end;
    clock_gettime(CLOCK_MONOTONIC, &start);
    int ok = za_glsl_compile(source, stage, &words, &count, error, sizeof error);
    clock_gettime(CLOCK_MONOTONIC, &end);
    if (!ok) fprintf(stderr, "%s\n", error);
    if (ok) {
        f = fopen(argv[3], "wb");
        if (!f) ok = 0;
        else { size_t wrote = fwrite(words, sizeof(uint32_t), count, f); int closed = fclose(f); ok = wrote == count && closed == 0; }
    }
    printf("{\"ok\":%s,\"words\":%zu,\"compile_ms\":%.3f}\n", ok ? "true" : "false", count,
        (end.tv_sec-start.tv_sec)*1000.0+(end.tv_nsec-start.tv_nsec)/1000000.0);
    free(words); free(source); za_glsl_finish(); return ok ? 0 : 1;
}
