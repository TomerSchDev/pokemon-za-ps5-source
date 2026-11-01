/* SDL3 shim (PS5): SDL_hints.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_hints_h_
#define SDL_hints_h_

#include <SDL3/SDL_stdinc.h>

/* The two hints the runtime sets (runtime/nvn/vulkan/device.c). Accepted and ignored on the PS5. */
#define SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS "SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS"
#define SDL_HINT_WINDOW_ACTIVATE_WHEN_SHOWN "SDL_WINDOW_ACTIVATE_WHEN_SHOWN"

#ifdef __cplusplus
extern "C" {
#endif

extern SDL_DECLSPEC bool SDLCALL SDL_SetHint(const char *name, const char *value);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetHint(const char *name);

#ifdef __cplusplus
}
#endif

#endif /* SDL_hints_h_ */
