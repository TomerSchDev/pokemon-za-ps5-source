#!/usr/bin/env bash
# PC runtime (lasrecomp.exe) with the texfix - for a scripted PC session only, never shipped. MSYS2 UCRT64 shell.
#
# The PC runtime in use (hebrew-lab/runtime/lasrecomp.exe, c74c9435...) is ZA Recomp v0.1.4 (commit 4d82d89) built
# with MSYS2 clang 21 against SDL3 3.4.18 (research/pokeza-pc/update-2.0.2-20261025/runtime-build.log; its two local
# changes only recognise the extracted 2.0.2 build in the launcher - not used with --play). Its source tree and the
# SDL 3.4.18 SDK are gone; MSYS2 has SDL3 3.2.28, which lacks SDL_LoadPNG / SDL_SavePNG (SDL 3.4). Here: v0.1.4 from
# the repository (git archive, LF), port/runtime-texfix applied, those two declared in a forced include and imported
# from SDL3.dll through an import stub (the run uses the PC runtime's own SDL3.dll 3.4.18, copied). GAMELIB_ID as the
# installed game library (game/lasgame.dll.id). Usage: build-pc-texfix.sh <work dir>   (src/ already exported there)
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=${1:?work dir}
src=$work/src
compat=$work/sdl34
export PATH=/ucrt64/bin:/usr/bin:$PATH
mkdir -p "$compat"
cat > "$compat/sdl34_compat.h" <<'EOF'
/* SDL 3.4 functions the runtime calls (MSYS2's SDL3 3.2 headers lack them); SDL3.dll 3.4.18 exports them */
#pragma once
#include <SDL3/SDL_surface.h>
#ifdef __cplusplus
extern "C" {
#endif
extern SDL_DECLSPEC SDL_Surface *SDLCALL SDL_LoadPNG(const char *file);
extern SDL_DECLSPEC bool SDLCALL SDL_SavePNG(SDL_Surface *surface, const char *file);
#ifdef __cplusplus
}
#endif
EOF
printf 'LIBRARY SDL3.dll\nEXPORTS\nSDL_LoadPNG\nSDL_SavePNG\n' > "$compat/sdl34.def"
dlltool -d "$compat/sdl34.def" -l "$compat/libSDL3_34.dll.a"
cd "$src"
ldflags="-fuse-ld=lld -Wl,--stack,16777216 -lSDL3 -lavformat -lavcodec -lavutil -lswscale -lvulkan-1 -lwinmm -lole32"
ldflags+=" -lshell32 -lcomdlg32 -luuid -lshaderc_shared $compat/libSDL3_34.dll.a -Wl,--export-all-symbols"
ldflags+=" -Wl,--out-implib,build/lasrecomp.dll.a"
make -j8 GAMELIB_ID=7b03da558e0b6144 CC="clang -include $compat/sdl34_compat.h" \
    CXX="clang++ -include $compat/sdl34_compat.h" LDFLAGS="$ldflags" build/lasrecomp.exe 2>&1 | tee "$work/build-pc.log"
ls -la build/lasrecomp.exe
sha256sum build/lasrecomp.exe | tee "$work/lasrecomp-texfix.sha256"
