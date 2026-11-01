/* SDL3 shim (PS5): SDL_filesystem.h - subset of SDL 3.4.18. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_filesystem_h_
#define SDL_filesystem_h_

#include <SDL3/SDL_stdinc.h>

#ifdef __cplusplus
extern "C" {
#endif

/* "/app0/" (the read-only application image). Owned by the shim; do not free. */
extern SDL_DECLSPEC const char *SDLCALL SDL_GetBasePath(void);
/* "/download0/<org>/<app>/", created on demand; free with SDL_free(). */
extern SDL_DECLSPEC char *SDLCALL SDL_GetPrefPath(const char *org, const char *app);
/* mkdir -p; true when the directory exists afterwards. */
extern SDL_DECLSPEC bool SDLCALL SDL_CreateDirectory(const char *path);

#ifdef __cplusplus
}
#endif

#endif /* SDL_filesystem_h_ */
