/* SDL3 shim (PS5): SDL_messagebox.h - subset of SDL 3.4.18; the box is a log line. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_messagebox_h_
#define SDL_messagebox_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_video.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_MessageBoxFlags;
#define SDL_MESSAGEBOX_ERROR       0x00000010u
#define SDL_MESSAGEBOX_WARNING     0x00000020u
#define SDL_MESSAGEBOX_INFORMATION 0x00000040u

extern SDL_DECLSPEC bool SDLCALL SDL_ShowSimpleMessageBox(SDL_MessageBoxFlags flags, const char *title, const char *message, SDL_Window *window);

#ifdef __cplusplus
}
#endif

#endif /* SDL_messagebox_h_ */
