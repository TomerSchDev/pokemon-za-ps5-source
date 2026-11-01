/* SDL3 shim (PS5): SDL_surface.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_surface_h_
#define SDL_surface_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_pixels.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_SurfaceFlags;
#define SDL_SURFACE_PREALLOCATED 0x00000001u
#define SDL_SURFACE_LOCK_NEEDED  0x00000002u
#define SDL_SURFACE_LOCKED       0x00000004u
#define SDL_SURFACE_SIMD_ALIGNED 0x00000008u

/* The public part of the SDL 3.4.18 surface, field for field. */
typedef struct SDL_Surface SDL_Surface;
struct SDL_Surface {
    SDL_SurfaceFlags flags;
    SDL_PixelFormat format;
    int w;
    int h;
    int pitch;
    void *pixels;
    int refcount;
    void *reserved;
};

extern SDL_DECLSPEC SDL_Surface *SDLCALL SDL_CreateSurface(int width, int height, SDL_PixelFormat format);
extern SDL_DECLSPEC SDL_Surface *SDLCALL SDL_CreateSurfaceFrom(int width, int height, SDL_PixelFormat format, void *pixels, int pitch);
extern SDL_DECLSPEC void SDLCALL SDL_DestroySurface(SDL_Surface *surface);
/* Only a copy in the same format is supported by the shim (ABGR8888 -> ABGR8888); other conversions fail. */
extern SDL_DECLSPEC SDL_Surface *SDLCALL SDL_ConvertSurface(SDL_Surface *surface, SDL_PixelFormat format);
/* Not provided on the PS5 (no PNG codec in the shim): both fail with an SDL error. Build the runtime PNG paths out. */
extern SDL_DECLSPEC SDL_Surface *SDLCALL SDL_LoadPNG(const char *file);
extern SDL_DECLSPEC bool SDLCALL SDL_SavePNG(SDL_Surface *surface, const char *file);

#ifdef __cplusplus
}
#endif

#endif /* SDL_surface_h_ */
