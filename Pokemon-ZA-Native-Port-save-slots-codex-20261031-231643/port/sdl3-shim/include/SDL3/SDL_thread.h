/* SDL3 shim (PS5): SDL_thread.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_thread_h_
#define SDL_thread_h_

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SDL_Thread SDL_Thread;
typedef int(SDLCALL *SDL_ThreadFunction)(void *data);

/* Not Windows: no _beginthreadex / _endthreadex, as in the SDL header. */
#ifndef SDL_BeginThreadFunction
#define SDL_BeginThreadFunction NULL
#endif
#ifndef SDL_EndThreadFunction
#define SDL_EndThreadFunction NULL
#endif

/* The symbol SDL exports; SDL_CreateThread is the macro over it, exactly as in SDL. */
extern SDL_DECLSPEC SDL_Thread *SDLCALL SDL_CreateThreadRuntime(SDL_ThreadFunction fn, const char *name, void *data,
                                                                SDL_FunctionPointer pfnBeginThread,
                                                                SDL_FunctionPointer pfnEndThread);
#define SDL_CreateThread(fn, name, data) \
    SDL_CreateThreadRuntime((fn), (name), (data), (SDL_FunctionPointer)(SDL_BeginThreadFunction), \
                            (SDL_FunctionPointer)(SDL_EndThreadFunction))

extern SDL_DECLSPEC void SDLCALL SDL_WaitThread(SDL_Thread *thread, int *status);
extern SDL_DECLSPEC void SDLCALL SDL_DetachThread(SDL_Thread *thread);

#ifdef __cplusplus
}
#endif

#endif /* SDL_thread_h_ */
