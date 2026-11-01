/* SMO title-local SDL_SavePNG replacement. No shared SDL shim changes.
 * PNG RGBA8 with a zlib stream of stored DEFLATE blocks; no extra dependency.
 * Surface rows are already oriented by Vulkan's screenshot/present pass.
 * A signed pitch is honored: pixels points to logical row zero in either case.
 */
#include <SDL3/SDL.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
    FILE *file;
    uint8_t *block;
    uint32_t crc_table[256];
    uint32_t used, adler_a, adler_b;
    uint64_t remaining;
} SmoPng;

static void smo_png_be32(uint8_t out[4], uint32_t value) {
    out[0] = (uint8_t)(value >> 24); out[1] = (uint8_t)(value >> 16);
    out[2] = (uint8_t)(value >> 8); out[3] = (uint8_t)value;
}

static uint32_t smo_png_crc(SmoPng *png, uint32_t crc, const uint8_t *bytes, size_t count) {
    for (size_t i = 0; i < count; ++i) crc = png->crc_table[(crc ^ bytes[i]) & 255] ^ (crc >> 8);
    return crc;
}

static bool smo_png_write(SmoPng *png, const void *bytes, size_t count) {
    return !count || fwrite(bytes, 1, count, png->file) == count;
}

static bool smo_png_chunk(SmoPng *png, const char type[4], const uint8_t *data, uint32_t count) {
    uint8_t length[4], check[4];
    smo_png_be32(length, count);
    uint32_t crc = smo_png_crc(png, UINT32_MAX, (const uint8_t *)type, 4);
    crc = smo_png_crc(png, crc, data, count) ^ UINT32_MAX;
    smo_png_be32(check, crc);
    return smo_png_write(png, length, 4) && smo_png_write(png, type, 4) &&
           smo_png_write(png, data, count) && smo_png_write(png, check, 4);
}

static bool smo_png_byte(SmoPng *png, uint8_t value) {
    png->block[5 + png->used++] = value;
    png->adler_a += value;
    if (png->adler_a >= 65521) png->adler_a -= 65521;
    png->adler_b += png->adler_a;
    if (png->adler_b >= 65521) png->adler_b -= 65521;
    --png->remaining;
    if (png->used == 65535 || !png->remaining) {
        const uint16_t count = (uint16_t)png->used, complement = (uint16_t)~count;
        png->block[0] = png->remaining ? 0 : 1; /* BFINAL, BTYPE=stored, byte aligned. */
        png->block[1] = (uint8_t)count; png->block[2] = (uint8_t)(count >> 8);
        png->block[3] = (uint8_t)complement; png->block[4] = (uint8_t)(complement >> 8);
        if (!smo_png_chunk(png, "IDAT", png->block, png->used + 5)) return false;
        png->used = 0;
    }
    return true;
}

bool __wrap_SDL_SavePNG(SDL_Surface *surface, const char *path) {
    if (!surface || !path || !*path || !surface->pixels || surface->w <= 0 || surface->h <= 0)
        return SDL_SetError("SMO PNG: invalid surface/path");
    if (surface->format != SDL_PIXELFORMAT_ABGR8888 && surface->format != SDL_PIXELFORMAT_RGBA8888)
        return SDL_SetError("SMO PNG: unsupported pixel format 0x%x", (unsigned)surface->format);
    const uint64_t row_bytes = (uint64_t)(unsigned)surface->w * 4;
    const uint64_t pitch = surface->pitch < 0 ? (uint64_t)-(int64_t)surface->pitch : (uint64_t)surface->pitch;
    if (pitch < row_bytes || row_bytes > SIZE_MAX - 1 ||
        (uint64_t)(unsigned)surface->h > SIZE_MAX / (row_bytes + 1))
        return SDL_SetError("SMO PNG: invalid pitch or image size");
    const uint64_t span = pitch * ((uint64_t)(unsigned)surface->h - 1);
    const uintptr_t pixels = (uintptr_t)surface->pixels;
    if (span > SIZE_MAX || (surface->pitch >= 0 && pixels > UINTPTR_MAX - span) ||
        (surface->pitch < 0 && pixels < span) ||
        (surface->pitch >= 0 && pixels + span > UINTPTR_MAX - row_bytes) ||
        (surface->pitch < 0 && pixels > UINTPTR_MAX - row_bytes))
        return SDL_SetError("SMO PNG: image address range overflow");
    SmoPng png = {0};
    png.block = malloc(65535 + 5);
    if (!png.block) return SDL_SetError("SMO PNG: block allocation failed");
    png.file = fopen(path, "wb");
    if (!png.file) { free(png.block); return SDL_SetError("SMO PNG: open '%s' failed (%d)", path, errno); }
    for (uint32_t i = 0; i < 256; ++i) {
        uint32_t crc = i;
        for (unsigned bit = 0; bit < 8; ++bit) crc = (crc >> 1) ^ ((crc & 1) ? 0xEDB88320u : 0);
        png.crc_table[i] = crc;
    }
    png.adler_a = 1;
    png.remaining = (row_bytes + 1) * (uint64_t)(unsigned)surface->h;
    const uint8_t signature[8] = {137,80,78,71,13,10,26,10};
    uint8_t ihdr[13] = {0};
    smo_png_be32(ihdr, (uint32_t)surface->w); smo_png_be32(ihdr + 4, (uint32_t)surface->h);
    ihdr[8] = 8; ihdr[9] = 6; /* 8-bit RGBA, standard compression/filter, no interlace. */
    const uint8_t zlib_header[2] = {0x78,0x01};
    bool ok = smo_png_write(&png, signature, sizeof signature) &&
              smo_png_chunk(&png, "IHDR", ihdr, sizeof ihdr) &&
              smo_png_chunk(&png, "IDAT", zlib_header, sizeof zlib_header);
    for (unsigned y = 0; ok && y < (unsigned)surface->h; ++y) {
        const uintptr_t address = surface->pitch >= 0 ? pixels + pitch * y : pixels - pitch * y;
        const uint8_t *row = (const uint8_t *)address;
        ok = smo_png_byte(&png, 0); /* PNG row filter None. */
        for (unsigned x = 0; ok && x < (unsigned)surface->w; ++x) {
            uint32_t word;
            memcpy(&word, row + (size_t)x * 4, sizeof word);
            uint8_t r, g, b, a;
            if (surface->format == SDL_PIXELFORMAT_ABGR8888) {
                r = (uint8_t)word; g = (uint8_t)(word >> 8);
                b = (uint8_t)(word >> 16); a = (uint8_t)(word >> 24);
            } else {
                r = (uint8_t)(word >> 24); g = (uint8_t)(word >> 16);
                b = (uint8_t)(word >> 8); a = (uint8_t)word;
            }
            ok = smo_png_byte(&png, r) && smo_png_byte(&png, g) &&
                 smo_png_byte(&png, b) && smo_png_byte(&png, a);
        }
    }
    uint8_t adler[4];
    smo_png_be32(adler, (png.adler_b << 16) | png.adler_a);
    if (ok) ok = !png.remaining && !png.used && smo_png_chunk(&png, "IDAT", adler, sizeof adler) &&
                 smo_png_chunk(&png, "IEND", NULL, 0);
    int saved_errno = errno;
    if (fclose(png.file) != 0) { if (ok) saved_errno = errno; ok = false; }
    free(png.block);
    if (!ok) {
        /* Never leave a partial capture masquerading as a complete PNG. */
        remove(path);
        return SDL_SetError("SMO PNG: write/close '%s' failed (%d)", path, saved_errno);
    }
    return true;
}
