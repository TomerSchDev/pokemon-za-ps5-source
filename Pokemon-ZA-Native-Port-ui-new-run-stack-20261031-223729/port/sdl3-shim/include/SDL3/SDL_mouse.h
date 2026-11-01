/* SDL3 shim (PS5): SDL_mouse.h - subset of SDL 3.4.18 (no mouse: nothing is ever pressed). SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_mouse_h_
#define SDL_mouse_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_video.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_MouseID;

typedef enum SDL_MouseWheelDirection {
    SDL_MOUSEWHEEL_NORMAL,
    SDL_MOUSEWHEEL_FLIPPED
} SDL_MouseWheelDirection;

typedef Uint32 SDL_MouseButtonFlags;

#define SDL_BUTTON_LEFT   1
#define SDL_BUTTON_MIDDLE 2
#define SDL_BUTTON_RIGHT  3
#define SDL_BUTTON_X1     4
#define SDL_BUTTON_X2     5

#define SDL_BUTTON_MASK(X) (1u << ((X) - 1))
#define SDL_BUTTON_LMASK   SDL_BUTTON_MASK(SDL_BUTTON_LEFT)
#define SDL_BUTTON_MMASK   SDL_BUTTON_MASK(SDL_BUTTON_MIDDLE)
#define SDL_BUTTON_RMASK   SDL_BUTTON_MASK(SDL_BUTTON_RIGHT)
#define SDL_BUTTON_X1MASK  SDL_BUTTON_MASK(SDL_BUTTON_X1)
#define SDL_BUTTON_X2MASK  SDL_BUTTON_MASK(SDL_BUTTON_X2)

extern SDL_DECLSPEC bool SDLCALL SDL_SetWindowRelativeMouseMode(SDL_Window *window, bool enabled);

#ifdef __cplusplus
}
#endif

#endif /* SDL_mouse_h_ */
