/* SDL3 shim (PS5): SDL_keyboard.h - subset of SDL 3.4.18 (names and the US layout only; no keyboard). SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_keyboard_h_
#define SDL_keyboard_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_keycode.h>
#include <SDL3/SDL_scancode.h>
#include <SDL3/SDL_video.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_KeyboardID;

extern SDL_DECLSPEC SDL_Keycode SDLCALL SDL_GetKeyFromScancode(SDL_Scancode scancode, SDL_Keymod modstate, bool key_event);
extern SDL_DECLSPEC SDL_Scancode SDLCALL SDL_GetScancodeFromKey(SDL_Keycode key, SDL_Keymod *modstate);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetScancodeName(SDL_Scancode scancode);
extern SDL_DECLSPEC SDL_Scancode SDLCALL SDL_GetScancodeFromName(const char *name);

#ifdef __cplusplus
}
#endif

#endif /* SDL_keyboard_h_ */
