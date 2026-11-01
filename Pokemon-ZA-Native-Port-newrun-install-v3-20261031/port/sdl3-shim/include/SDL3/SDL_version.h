/* SDL3 shim (PS5): SDL_version.h - the version whose ABI the shim follows. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_version_h_
#define SDL_version_h_

#include <SDL3/SDL_stdinc.h>

#define SDL_MAJOR_VERSION 3
#define SDL_MINOR_VERSION 4
#define SDL_MICRO_VERSION 18

#define SDL_VERSIONNUM(major, minor, patch) ((major) * 1000000 + (minor) * 1000 + (patch))
#define SDL_VERSION SDL_VERSIONNUM(SDL_MAJOR_VERSION, SDL_MINOR_VERSION, SDL_MICRO_VERSION)

#ifdef __cplusplus
extern "C" {
#endif

extern SDL_DECLSPEC int SDLCALL SDL_GetVersion(void);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetRevision(void);

#ifdef __cplusplus
}
#endif

#endif /* SDL_version_h_ */
