/* SDL3 shim (PS5): SDL_pixels.h - subset of SDL 3.4.18 (little-endian target). SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_pixels_h_
#define SDL_pixels_h_

#include <SDL3/SDL_stdinc.h>

typedef enum SDL_PixelFormat {
    SDL_PIXELFORMAT_UNKNOWN = 0,
    SDL_PIXELFORMAT_RGBA8888 = 0x16462004u,
    SDL_PIXELFORMAT_ABGR8888 = 0x16762004u, /**< R, G, B, A bytes in memory: what the runtime hands to the PNG code */
    /* byte-order aliases, as SDL defines them on a little-endian machine */
    SDL_PIXELFORMAT_RGBA32 = SDL_PIXELFORMAT_ABGR8888,
    SDL_PIXELFORMAT_ABGR32 = SDL_PIXELFORMAT_RGBA8888
} SDL_PixelFormat;

#endif /* SDL_pixels_h_ */
