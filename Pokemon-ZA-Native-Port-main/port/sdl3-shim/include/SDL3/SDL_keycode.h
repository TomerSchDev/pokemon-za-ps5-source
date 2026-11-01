/* SDL3 shim (PS5): SDL_keycode.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_keycode_h_
#define SDL_keycode_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_scancode.h>

typedef Uint32 SDL_Keycode;

#define SDLK_EXTENDED_MASK (1u << 29)
#define SDLK_SCANCODE_MASK (1u << 30)
#define SDL_SCANCODE_TO_KEYCODE(X) (X | SDLK_SCANCODE_MASK)

#define SDLK_UNKNOWN   0x00000000u
#define SDLK_RETURN    0x0000000du
#define SDLK_ESCAPE    0x0000001bu
#define SDLK_BACKSPACE 0x00000008u
#define SDLK_TAB       0x00000009u
#define SDLK_SPACE     0x00000020u
#define SDLK_DELETE    0x0000007fu
#define SDLK_A         0x00000061u /* letters are their lowercase ASCII */
#define SDLK_F1        0x4000003au
#define SDLK_F9        0x40000042u
#define SDLK_F11       0x40000044u
#define SDLK_RIGHT     0x4000004fu
#define SDLK_LEFT      0x40000050u
#define SDLK_DOWN      0x40000051u
#define SDLK_UP        0x40000052u
#define SDLK_KP_4      0x4000005cu
#define SDLK_KP_5      0x4000005du
#define SDLK_KP_6      0x4000005eu
#define SDLK_KP_8      0x40000060u
#define SDLK_KP_0      0x40000062u

typedef Uint16 SDL_Keymod;

#define SDL_KMOD_NONE   0x0000u
#define SDL_KMOD_LSHIFT 0x0001u
#define SDL_KMOD_RSHIFT 0x0002u
#define SDL_KMOD_LEVEL5 0x0004u
#define SDL_KMOD_LCTRL  0x0040u
#define SDL_KMOD_RCTRL  0x0080u
#define SDL_KMOD_LALT   0x0100u
#define SDL_KMOD_RALT   0x0200u
#define SDL_KMOD_LGUI   0x0400u
#define SDL_KMOD_RGUI   0x0800u
#define SDL_KMOD_NUM    0x1000u
#define SDL_KMOD_CAPS   0x2000u
#define SDL_KMOD_MODE   0x4000u
#define SDL_KMOD_SCROLL 0x8000u
#define SDL_KMOD_CTRL   (SDL_KMOD_LCTRL | SDL_KMOD_RCTRL)
#define SDL_KMOD_SHIFT  (SDL_KMOD_LSHIFT | SDL_KMOD_RSHIFT)
#define SDL_KMOD_ALT    (SDL_KMOD_LALT | SDL_KMOD_RALT)
#define SDL_KMOD_GUI    (SDL_KMOD_LGUI | SDL_KMOD_RGUI)

#endif /* SDL_keycode_h_ */
