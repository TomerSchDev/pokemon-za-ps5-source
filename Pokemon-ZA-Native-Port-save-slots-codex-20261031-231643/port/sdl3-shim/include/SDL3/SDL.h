/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: SDL.h
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The umbrella header, as in SDL: everything but SDL_vulkan.h (which the runtime
 * includes by name) and SDL_main.h (the runtime has a plain main). Only the
 * subset the runtime uses exists; see README.md for the function list and status.
 */
#ifndef SDL_h_
#define SDL_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_audio.h>
#include <SDL3/SDL_cpuinfo.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_events.h>
#include <SDL3/SDL_filesystem.h>
#include <SDL3/SDL_gamepad.h>
#include <SDL3/SDL_hints.h>
#include <SDL3/SDL_init.h>
#include <SDL3/SDL_joystick.h>
#include <SDL3/SDL_keyboard.h>
#include <SDL3/SDL_keycode.h>
#include <SDL3/SDL_log.h>
#include <SDL3/SDL_messagebox.h>
#include <SDL3/SDL_mouse.h>
#include <SDL3/SDL_pixels.h>
#include <SDL3/SDL_scancode.h>
#include <SDL3/SDL_surface.h>
#include <SDL3/SDL_thread.h>
#include <SDL3/SDL_timer.h>
#include <SDL3/SDL_version.h>
#include <SDL3/SDL_video.h>

#endif /* SDL_h_ */
