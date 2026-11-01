#!/usr/bin/env bash
# Build the real UI-v2 controller/launcher/overlay/quad into the Windows runtime in a NEW isolated workspace.
# This is the PC Vulkan proof; the console-only performance/Hebrew/observer hooks use pc_entry.c stand-ins.
# Usage from MSYS2 bash: build-pc-ui.sh NEW_WORK_DIR [ASSETS_DIR]
# Existing ui-v2-work/pc runtime objects/dependencies are read/copied, never changed. No console access.
set -euo pipefail
export PATH="/c/msys64/ucrt64/bin:/c/msys64/usr/bin:$PATH"
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ui=$(cd "$here/.." && pwd)
project=$(cd "$ui/../.." && pwd)
base=$(dirname "$project")
work=${1:?new PC work directory required}
assets=${2:-$base/rando-v3-lab/assets}
reference=${ZA_PC_REFERENCE:-$base/ui-v2-work/pc}
python=${ZA_PYTHON:-/c/Users/Tomer/AppData/Local/Programs/Python/Python312/python.exe}
[[ ! -e $work ]] || { echo "PC work directory already exists: $work" >&2; exit 2; }
[[ -d $reference/src && -d $reference/deps && -f $reference/out/lasgame-uiv2.dll ]] || { echo "PC reference is incomplete" >&2; exit 2; }
"$python" "$ui/tools/verify-generator-handoff.py" "$project/port/rando-v3/HANDOFF.json" "$assets"
mkdir -p "$work"
work=$(cd "$work" && pwd)
for folder in src deps; do cp -a "$reference/$folder" "$work/"; done
export ZA_WORK=$work OUT=$work/out ZA_UI_PC_LAUNCHER=1
mkdir -p "$work/ui-objects" "$work/gen"
"$python" "$ui/tools/embed-font.py" "$ui/fonts" "$ui/src/fonts_embedded.inc"
"$python" "$ui/tools/gen-capabilities.py" "$project/port/rando-v3/capabilities.json" "$ui/src/capabilities_generated.inc"
plan=${ZA_MUSIC_PLAN:-/home/tomer/ps5-za-native/r29-music-plan-v2.json}
if [[ ! -f $plan ]]; then
    # WSL's verified plan is game-derived and copied locally, never added to git.
    plan=$work/gen/music-plan.json
    cp //wsl.localhost/Ubuntu/home/tomer/ps5-za-native/r29-music-plan-v2.json "$plan"
fi
"$python" "$project/port/rando-music/tools/embed_plan.py" "$plan" "$work/gen/za_music_plan.cpp"
bash "$here/build-pc-runtime.sh" objects
deps=${ZA_DEPS:-/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib}
incs=(-I"$ui/src" -isystem "$ui/third_party/stb" -I"$project/port/rando-v3/src" -I"$project/port/rando-v3"
      -I"$project/port/rando-v3/core" -I"$project/port/randomizer" -I"$project/port/rando-v2" -I"$project/port/rando-music"
      -I"$project/port/cheats-r28" -I"$project/port/cheats-r27" -I"$project/port/perf-r28/src" -I"$assets"
      -I"$deps/json/include" -I"$deps/mbedtls/include" -I"$work/deps/sdl3/include" -I"$work/src/runtime" -I"$work/src/runtime/nvn")
cxx=(-std=c++20 -O2 -g -Wall -Wextra -Werror -Wno-missing-field-initializers -Wno-unused-parameter -fno-exceptions -fno-rtti
     -DJSON_NOEXCEPTION=1 '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -DZA_MONEY_HOOK=1 '-DZA_UI_BUILD_LABEL="r29-ui PC proof"'
     -include "$here/pc_compat.h")
objects=()
for stem in ui_canvas ui_widgets ui_model settings_codes items_picker ui_launcher ui_overlay ui_pad fonts_embedded ui_platform launcher_core launcher_ps5 overlay_ps5 png_write; do
    clang++ "${cxx[@]}" "${incs[@]}" -c "$ui/src/$stem.cpp" -o "$work/ui-objects/$stem.o"
    objects+=("$work/ui-objects/$stem.o")
done
for source in "$project/port/rando-v3/core/randomizer.cpp" "$project/port/rando-v3/src/legacy_progression.cpp" \
              "$project/port/rando-v3/src/legacy_research_rewards.cpp" "$project/port/rando-v3/src/rando_v3.cpp" \
              "$project/port/rando-v3/src/run_store_v3.cpp" "$project/port/randomizer/import_repair.cpp" \
              "$project/port/rando-v2/run_name.cpp" "$project/port/rando-v2/za_player_name.cpp" "$project/port/rando-v2/name_keyboard.cpp" \
              "$project/port/rando-music/za_music.cpp" "$work/gen/za_music_plan.cpp"; do
    stem=$(basename "${source%.*}")
    clang++ "${cxx[@]}" "${incs[@]}" -c "$source" -o "$work/ui-objects/$stem.o"
    objects+=("$work/ui-objects/$stem.o")
done
for stem in sha256 platform_util; do
    clang -O2 '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' "${incs[@]}" -c "$deps/mbedtls/library/$stem.c" -o "$work/ui-objects/mbed-$stem.o"
    objects+=("$work/ui-objects/mbed-$stem.o")
done
clang -std=c11 -O2 -Wall -Wextra -Werror -Wno-missing-field-initializers "${incs[@]}" -c "$ui/src/ui_quad.c" -o "$work/ui-objects/ui_quad.o"
objects+=("$work/ui-objects/ui_quad.o")
for stem in pc_entry pc_compat; do
    clang -std=c11 -O2 -Wall -Wextra -Werror -c "$here/$stem.c" -o "$work/ui-objects/$stem.o"
    objects+=("$work/ui-objects/$stem.o")
done
bash "$here/build-pc-runtime.sh" link "${objects[@]}" -- -lz
cp "$reference/out/lasgame-uiv2.dll" "$reference/out/lasgame-uiv2.dll.id" "$OUT/"
(cd "$OUT" && sha256sum lasrecomp-uiv2.exe lasgame-uiv2.dll > SHA256SUMS.txt)
echo "PC UI candidate compiled: $OUT/lasrecomp-uiv2.exe (no game launched)"
