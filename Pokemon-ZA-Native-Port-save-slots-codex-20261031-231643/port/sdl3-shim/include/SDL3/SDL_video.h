/* SDL3 shim (PS5): SDL_video.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_video_h_
#define SDL_video_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_surface.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_DisplayID;
typedef Uint32 SDL_WindowID;

/* One logical window: the VK_KHR_display plane at the physical resolution of the display (3840x2160 on this console). */
typedef struct SDL_Window SDL_Window;

typedef Uint64 SDL_WindowFlags;
#define SDL_WINDOW_FULLSCREEN          SDL_UINT64_C(0x0000000000000001)
#define SDL_WINDOW_OPENGL              SDL_UINT64_C(0x0000000000000002)
#define SDL_WINDOW_OCCLUDED            SDL_UINT64_C(0x0000000000000004)
#define SDL_WINDOW_HIDDEN              SDL_UINT64_C(0x0000000000000008)
#define SDL_WINDOW_BORDERLESS          SDL_UINT64_C(0x0000000000000010)
#define SDL_WINDOW_RESIZABLE           SDL_UINT64_C(0x0000000000000020)
#define SDL_WINDOW_MINIMIZED           SDL_UINT64_C(0x0000000000000040)
#define SDL_WINDOW_MAXIMIZED           SDL_UINT64_C(0x0000000000000080)
#define SDL_WINDOW_MOUSE_GRABBED       SDL_UINT64_C(0x0000000000000100)
#define SDL_WINDOW_INPUT_FOCUS         SDL_UINT64_C(0x0000000000000200)
#define SDL_WINDOW_MOUSE_FOCUS         SDL_UINT64_C(0x0000000000000400)
#define SDL_WINDOW_EXTERNAL            SDL_UINT64_C(0x0000000000000800)
#define SDL_WINDOW_MODAL               SDL_UINT64_C(0x0000000000001000)
#define SDL_WINDOW_HIGH_PIXEL_DENSITY  SDL_UINT64_C(0x0000000000002000)
#define SDL_WINDOW_MOUSE_CAPTURE       SDL_UINT64_C(0x0000000000004000)
#define SDL_WINDOW_MOUSE_RELATIVE_MODE SDL_UINT64_C(0x0000000000008000)
#define SDL_WINDOW_ALWAYS_ON_TOP       SDL_UINT64_C(0x0000000000010000)
#define SDL_WINDOW_UTILITY             SDL_UINT64_C(0x0000000000020000)
#define SDL_WINDOW_TOOLTIP             SDL_UINT64_C(0x0000000000040000)
#define SDL_WINDOW_POPUP_MENU          SDL_UINT64_C(0x0000000000080000)
#define SDL_WINDOW_KEYBOARD_GRABBED    SDL_UINT64_C(0x0000000000100000)
#define SDL_WINDOW_VULKAN              SDL_UINT64_C(0x0000000010000000)
#define SDL_WINDOW_METAL               SDL_UINT64_C(0x0000000020000000)
#define SDL_WINDOW_TRANSPARENT         SDL_UINT64_C(0x0000000040000000)
#define SDL_WINDOW_NOT_FOCUSABLE       SDL_UINT64_C(0x0000000080000000)

extern SDL_DECLSPEC SDL_Window *SDLCALL SDL_CreateWindow(const char *title, int w, int h, SDL_WindowFlags flags);
extern SDL_DECLSPEC void SDLCALL SDL_DestroyWindow(SDL_Window *window);
extern SDL_DECLSPEC SDL_WindowFlags SDLCALL SDL_GetWindowFlags(SDL_Window *window);
extern SDL_DECLSPEC bool SDLCALL SDL_GetWindowSize(SDL_Window *window, int *w, int *h);
extern SDL_DECLSPEC bool SDLCALL SDL_GetWindowSizeInPixels(SDL_Window *window, int *w, int *h);
extern SDL_DECLSPEC bool SDLCALL SDL_SetWindowFullscreen(SDL_Window *window, bool fullscreen);
extern SDL_DECLSPEC bool SDLCALL SDL_SetWindowIcon(SDL_Window *window, SDL_Surface *icon);
extern SDL_DECLSPEC bool SDLCALL SDL_ShowWindow(SDL_Window *window);

#ifdef __cplusplus
}
#endif

#endif /* SDL_video_h_ */
