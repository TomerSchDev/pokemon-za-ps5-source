/* SDL3 shim (PS5): SDL_joystick.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_joystick_h_
#define SDL_joystick_h_

#include <SDL3/SDL_stdinc.h>

/* Instance id of a joystick; 0 is invalid. The DualSense on port 0 is id 1 here. */
typedef Uint32 SDL_JoystickID;

#define SDL_JOYSTICK_AXIS_MAX 32767
#define SDL_JOYSTICK_AXIS_MIN -32768

#endif /* SDL_joystick_h_ */
