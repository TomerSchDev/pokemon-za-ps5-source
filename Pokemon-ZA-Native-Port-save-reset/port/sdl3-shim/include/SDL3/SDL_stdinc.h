/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: SDL_stdinc.h
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The subset of SDL 3.4.18 SDL_stdinc.h that the recomp runtime uses. Names,
 * types and values are SDL (zlib licence, (C) Sam Lantinga); everything the
 * runtime does not touch is left out. ABI source: the SDL3-3.4.18 devel headers
 * (research/pokeza-pc/runtime-opt-r1/SDL3-3.4.18), the ones the PC build of the
 * runtime was compiled against.
 */
#ifndef SDL_stdinc_h_
#define SDL_stdinc_h_

#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

/* SDL_begin_code.h on a non-Windows target: no decoration, no calling convention. */
#define SDL_DECLSPEC
#define SDLCALL

#define SDL_SINT64_C(c) INT64_C(c)
#define SDL_UINT64_C(c) UINT64_C(c)

typedef int8_t Sint8;
typedef uint8_t Uint8;
typedef int16_t Sint16;
typedef uint16_t Uint16;
typedef int32_t Sint32;
typedef uint32_t Uint32;
typedef int64_t Sint64;
typedef uint64_t Uint64;

/* A generic function pointer (SDL_Vulkan_GetVkGetInstanceProcAddr, SDL_CreateThreadRuntime). */
typedef void *SDL_FunctionPointer;

#define SDL_PRINTF_FORMAT_STRING
#define SDL_PRINTF_VARARG_FUNC(fmtargnumber) __attribute__((format(__printf__, fmtargnumber, fmtargnumber + 1)))
#define SDL_PRINTF_VARARG_FUNCV(fmtargnumber) __attribute__((format(__printf__, fmtargnumber, 0)))
#define SDL_MALLOC __attribute__((malloc))

/* SDL compile-time assertion, usable in C and C++. */
#define SDL_COMPILE_TIME_ASSERT(name, x) typedef int SDL_compile_time_assert_##name[(x) * 2 - 1]

#ifdef __cplusplus
extern "C" {
#endif

/* The allocator behind what SDL hands out (SDL_GetGamepads, SDL_GetPrefPath): plain malloc/free here. */
extern SDL_DECLSPEC SDL_MALLOC void *SDLCALL SDL_malloc(size_t size);
extern SDL_DECLSPEC SDL_MALLOC void *SDLCALL SDL_calloc(size_t nmemb, size_t size);
extern SDL_DECLSPEC void *SDLCALL SDL_realloc(void *mem, size_t size);
extern SDL_DECLSPEC void SDLCALL SDL_free(void *mem);
extern SDL_DECLSPEC SDL_MALLOC char *SDLCALL SDL_strdup(const char *str);

#ifdef __cplusplus
}
#endif

#endif /* SDL_stdinc_h_ */
