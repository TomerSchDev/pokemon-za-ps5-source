/* SDL3 shim (PS5): SDL_error.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_error_h_
#define SDL_error_h_

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Sets the calling thread's error string; always returns false (so `return SDL_SetError(...)` reports a failure). */
extern SDL_DECLSPEC bool SDLCALL SDL_SetError(SDL_PRINTF_FORMAT_STRING const char *fmt, ...) SDL_PRINTF_VARARG_FUNC(1);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetError(void);
extern SDL_DECLSPEC bool SDLCALL SDL_ClearError(void);

#ifdef __cplusplus
}
#endif

#endif /* SDL_error_h_ */
