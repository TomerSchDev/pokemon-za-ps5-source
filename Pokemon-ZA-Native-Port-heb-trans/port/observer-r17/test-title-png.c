#include <SDL3/SDL.h>
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
bool __wrap_SDL_SavePNG(SDL_Surface *, const char *);
static char error_text[512];
static unsigned writes, closes, fail_write_at;
static int fail_close;
bool SDL_SetError(const char *format, ...) {
    va_list args; va_start(args, format); vsnprintf(error_text, sizeof error_text, format, args); va_end(args);
    return false;
}
const char *SDL_GetError(void) { return error_text; }
size_t __real_fwrite(const void *, size_t, size_t, FILE *);
int __real_fclose(FILE *);
size_t __wrap_fwrite(const void *p, size_t size, size_t count, FILE *file) {
    if (++writes == fail_write_at) { errno = EIO; return 0; }
    return __real_fwrite(p, size, count, file);
}
int __wrap_fclose(FILE *file) {
    closes++;
    int result = __real_fclose(file);
    if (fail_close) { errno = EIO; return EOF; }
    return result;
}
static void fixture(const char *folder, unsigned format_index, int negative, unsigned case_index,
                    unsigned width, unsigned height) {
    const size_t row = width * 4, pitch = row + 13, bytes = pitch * height;
    uint8_t *guarded = malloc(bytes + 64);
    memset(guarded, 0xCC, bytes + 64);
    uint8_t *first = guarded + 32 + (negative ? pitch * (height - 1) : 0);
    const int stride = negative ? -(int)pitch : (int)pitch;
    for (unsigned y = 0; y < height; ++y) {
        uint8_t *line = first + (ptrdiff_t)stride * y;
        for (unsigned x = 0; x < width; ++x) {
            const uint8_t r = (uint8_t)(x * 31 + y * 7), g = (uint8_t)(x * 3 + y * 41);
            const uint8_t b = (uint8_t)(x * 19 + y * 11), a = (uint8_t)(x * 17 + y * 23);
            uint32_t pixel = format_index ? ((uint32_t)r << 24) | ((uint32_t)g << 16) | ((uint32_t)b << 8) | a
                                          : ((uint32_t)a << 24) | ((uint32_t)b << 16) | ((uint32_t)g << 8) | r;
            memcpy(line + x * 4, &pixel, 4);
        }
    }
    uint8_t *before = malloc(bytes + 64); memcpy(before, guarded, bytes + 64);
    SDL_Surface surface = {.format = format_index ? SDL_PIXELFORMAT_RGBA8888 : SDL_PIXELFORMAT_ABGR8888,
                           .w = (int)width, .h = (int)height, .pitch = stride, .pixels = first};
    char path[1024]; snprintf(path, sizeof path, "%s/fmt%u_neg%d_case%u.png", folder, format_index, negative, case_index);
    assert(__wrap_SDL_SavePNG(&surface, path));
    assert(memcmp(guarded, before, bytes + 64) == 0);
    free(before); free(guarded);
}
int main(int argc, char **argv) {
    assert(argc == 2);
    const unsigned sizes[][2] = {{1,1}, {5,7}, {16383,1}, {16384,1}, {257,257}};
    for (unsigned format = 0; format < 2; ++format)
        for (int negative = 0; negative < 2; ++negative)
            for (unsigned i = 0; i < 5; ++i) fixture(argv[1], format, negative, i, sizes[i][0], sizes[i][1]);
    uint8_t pixels[40] = {0};
    SDL_Surface surface = {.format = SDL_PIXELFORMAT_ABGR8888, .w = 2, .h = 2, .pitch = 12, .pixels = pixels};
    char path[1024]; snprintf(path, sizeof path, "%s/error.png", argv[1]);
    for (unsigned error = 0; error < 9; ++error) {
        SDL_Surface invalid = surface;
        switch(error) {
            case 0: invalid.pixels = NULL; break;
            case 1: invalid.format = 0xDEADBEEF; break;
            case 2: invalid.w = 0; break;
            case 3: invalid.h = -1; break;
            case 4: invalid.pitch = 7; break;
            case 5: invalid.w = INT_MAX; break;
            case 6: invalid.pixels = (void *)(UINTPTR_MAX - 1); break;
            case 7: invalid.pitch = -12; invalid.pixels = (void *)1; break;
            case 8: invalid.pitch = INT_MIN; invalid.w = INT_MAX; break;
        }
        unsigned opened_closes = closes;
        assert(!__wrap_SDL_SavePNG(&invalid, path));
        assert(closes == opened_closes && access(path, F_OK) != 0);
    }
    assert(!__wrap_SDL_SavePNG(NULL, path));
    assert(!__wrap_SDL_SavePNG(&surface, NULL));
    assert(!__wrap_SDL_SavePNG(&surface, ""));
    char missing[1024]; snprintf(missing, sizeof missing, "%s/missing/fail.png", argv[1]);
    assert(!__wrap_SDL_SavePNG(&surface, missing));
    /* Fail early/late writes and close. Every opened file closes; partial PNG
     * disappears and the caller gets failure, even on buffered close failure. */
    const unsigned failures[] = {1, 6, 14};
    for (unsigned i = 0; i < 3; ++i) {
        writes = closes = 0; fail_write_at = failures[i];
        assert(!__wrap_SDL_SavePNG(&surface, path));
        assert(closes == 1 && access(path, F_OK) != 0);
    }
    fail_write_at = 0; fail_close = 1; closes = 0;
    assert(!__wrap_SDL_SavePNG(&surface, path));
    assert(closes == 1 && access(path, F_OK) != 0);
    fail_close = 0;
    puts("{\"passed\":true,\"round_trip_images\":20,\"source_buffer_canaries\":true,"
         "\"positive_negative_pitch\":true,\"rgba_abgr_formats\":true,\"invalid_surfaces\":12,"
         "\"write_failures\":3,\"close_failure\":true,\"partial_files_removed\":true}");
}
