/* SDL3 shim (PS5): SDL_init.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_init_h_
#define SDL_init_h_

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef Uint32 SDL_InitFlags;

#define SDL_INIT_AUDIO    0x00000010u /**< implies SDL_INIT_EVENTS */
#define SDL_INIT_VIDEO    0x00000020u /**< implies SDL_INIT_EVENTS */
#define SDL_INIT_JOYSTICK 0x00000200u /**< implies SDL_INIT_EVENTS */
#define SDL_INIT_HAPTIC   0x00001000u
#define SDL_INIT_GAMEPAD  0x00002000u /**< implies SDL_INIT_JOYSTICK */
#define SDL_INIT_EVENTS   0x00004000u
#define SDL_INIT_SENSOR   0x00008000u
#define SDL_INIT_CAMERA   0x00010000u

extern SDL_DECLSPEC bool SDLCALL SDL_Init(SDL_InitFlags flags);
extern SDL_DECLSPEC bool SDLCALL SDL_InitSubSystem(SDL_InitFlags flags);
extern SDL_DECLSPEC void SDLCALL SDL_QuitSubSystem(SDL_InitFlags flags);
extern SDL_DECLSPEC SDL_InitFlags SDLCALL SDL_WasInit(SDL_InitFlags flags);
extern SDL_DECLSPEC void SDLCALL SDL_Quit(void);

#ifdef __cplusplus
}
#endif

#endif /* SDL_init_h_ */
