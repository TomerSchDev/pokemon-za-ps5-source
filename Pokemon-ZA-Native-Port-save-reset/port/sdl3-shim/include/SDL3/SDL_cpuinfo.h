/* SDL3 shim (PS5): SDL_cpuinfo.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_cpuinfo_h_
#define SDL_cpuinfo_h_

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

/* The CPUs a title's threads may run on (13 on this console: affinity mask 0x1fff). */
extern SDL_DECLSPEC int SDLCALL SDL_GetNumLogicalCPUCores(void);
/* Direct memory in MiB (sceKernelGetDirectMemorySize): what the title can use, not the console's total RAM. */
extern SDL_DECLSPEC int SDLCALL SDL_GetSystemRAM(void);

#ifdef __cplusplus
}
#endif

#endif /* SDL_cpuinfo_h_ */
