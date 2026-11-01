#!/usr/bin/env bash
# ui-v2 host build (WSL, clang-21): the rasterizer, model, screens, picker, pad, the launcher controller over the REAL
# randomizer core, and the REAL overlay glue - with the title's language constraints (C++17/20, no exceptions, no RTTI,
# -Werror) and, for the tests, ASan + UBSan. Then: the unit tests, the launcher-flow test (creates a run in a scratch
# root with the local copy of the title's assets), the overlay-glue test, the mockups and the golden check.
#   bash tools/build-host.sh [out dir]        (default: /home/tomer/ui-v2-build/host, outside git)
# Environment: ZA_UI_ASSETS (the complete v3 asset folder including assets_hashes_v3.h; default
# rando-v3-lab/assets), ZA_MUSIC_PLAN (r29's plan JSON; default /home/tomer/ps5-za-native/r29-music-plan-v2.json),
# PIN_GOLDENS=1 (accept the fresh mockups as the goldens), PS5_CHECK=1 (also compile every title-side object with the
# PS5 toolchain into a prepared merge tree's include set: tools/compile-title-objects.sh; needs ZA_WORK_TREE).
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
port=$(cd "$root/.." && pwd)
project=$(cd "$port/.." && pwd)
out=${1:-/home/tomer/ui-v2-build/host}
assets=${ZA_UI_ASSETS:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/rando-v3-lab/assets}
plan=${ZA_MUSIC_PLAN:-/home/tomer/ps5-za-native/r29-music-plan-v2.json}
deps=${ZA_DEPS:-/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib}
mkdir -p "$out/gen" "$out/mockups" "$root/mockups"
CXX=${CXX:-clang++-21}
CC=${CC:-clang-21}
jobs=${ZA_UI_JOBS:-4}
[[ $jobs =~ ^[1-9][0-9]*$ && $jobs -le 16 ]] || { echo "ZA_UI_JOBS must be 1..16" >&2; exit 2; }
pending=()
trap 'for pid in "${pending[@]}"; do kill "$pid" 2>/dev/null || true; done' EXIT
spawn() {
    "$@" & pending+=("$!")
    if [[ ${#pending[@]} -ge $jobs ]]; then wait "${pending[0]}"; pending=("${pending[@]:1}"); fi
}
join() { for pid in "${pending[@]}"; do wait "$pid"; done; pending=(); }
[[ -f $assets/v3.json && -f $assets/assets_hashes_v3.h ]] || { echo "no prepared rando-v3 assets at $assets" >&2; exit 2; }
[[ -f $plan ]] || { echo "no music plan at $plan" >&2; exit 2; }
if [[ ${ZA_REQUIRE_HANDOFF:-1} == 1 ]]; then
    python3 "$root/tools/verify-generator-handoff.py" "$port/rando-v3/HANDOFF.json" "$assets" --out "$out/gen/generator-receipt.json"
fi
echo "== generated inputs"
python3 "$root/tools/embed-font.py" "$root/fonts" "$root/src/fonts_embedded.inc"
python3 "$root/tools/gen-capabilities.py" "$port/rando-v3/capabilities.json" "$root/src/capabilities_generated.inc"
python3 "$port/rando-music/tools/embed_plan.py" "$plan" "$out/gen/za_music_plan.cpp"
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
warn=(-Wall -Wextra -Werror -Wno-missing-field-initializers -fno-exceptions -fno-rtti)
ui_inc=(-isystem "$root/third_party/stb" -I"$root/src" -I"$port/rando-v3/src" -I"$port/rando-v3" -I"$port/randomizer" -I"$port/rando-v2" -I"$port/cheats-r28")
core_inc=(-I"$port/rando-v3/core" -I"$port/rando-music" -I"$port/cheats-r27" -I"$port/perf-r28/src" -I"$assets"
          -I"$deps/json/include" -I"$deps/mbedtls/include" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -DJSON_NOEXCEPTION=1)
sdl_inc=(-I"$port/sdl3-shim/include")
echo "== ui objects (C++17, as the title compiles them; -O2 for the mockups and the render timing)"
objs=()
for s in ui_canvas ui_widgets ui_model settings_codes items_picker ui_launcher ui_overlay ui_pad fonts_embedded legacy_look png_write; do
    spawn "$CXX" -std=c++17 -O2 -g "${warn[@]}" "${ui_inc[@]}" -c "$root/src/$s.cpp" -o "$out/$s.o"
    objs+=("$out/$s.o")
done
join
"$CXX" -std=c++17 -O2 -g "${warn[@]}" "${ui_inc[@]}" "$root/src/mockups_main.cpp" "${objs[@]}" -lz -o "$out/mockups-render"
echo "== the same ui objects with ASan/UBSan for the tests"
sobjs=()
for s in ui_canvas ui_widgets ui_model settings_codes items_picker ui_launcher ui_overlay ui_pad fonts_embedded legacy_look png_write; do
    spawn "$CXX" -std=c++17 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" -c "$root/src/$s.cpp" -o "$out/san-$s.o"
    sobjs+=("$out/san-$s.o")
done
join
"$CXX" -std=c++17 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "$root/test/test_ui.cpp" "${sobjs[@]}" -lz -o "$out/test_ui"
"$CXX" -std=c++17 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "$root/test/test_settings_codes.cpp" \
    "$out/san-ui_model.o" "$out/san-settings_codes.o" -o "$out/test_settings_codes"
echo "== the launcher controller over the real core (C++20 as the title; ASan/UBSan)"
for c in sha256 platform_util; do "$CC" -std=c11 -O1 -g "${san[@]}" "${core_inc[@]}" -c "$deps/mbedtls/library/$c.c" -o "$out/mbed-$c.o"; done
core_srcs=("$port/rando-v3/core/randomizer.cpp" "$port/rando-v3/src/legacy_progression.cpp" "$port/rando-v3/src/legacy_research_rewards.cpp"
           "$port/rando-v3/src/rando_v3.cpp" "$port/randomizer/import_repair.cpp" "$port/rando-v3/src/run_store_v3.cpp" "$port/rando-music/za_music.cpp"
           "$out/gen/za_music_plan.cpp" "$port/rando-v2/run_name.cpp" "$port/rando-v2/za_player_name.cpp" "$port/rando-v2/name_keyboard.cpp")
core_objs=()
for s in "${core_srcs[@]}"; do
    o=$out/core-$(basename "${s%.*}").o
    spawn "$CXX" -std=c++20 -O1 -g "${san[@]}" -fno-exceptions -fno-rtti -Wno-unused-parameter "${ui_inc[@]}" "${core_inc[@]}" -c "$s" -o "$o"
    core_objs+=("$o")
done
join
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" -c "$root/src/launcher_core.cpp" -o "$out/san-launcher_core.o"
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" "$root/test/test_launcher_flow.cpp" "$out/san-launcher_core.o" \
    "${sobjs[@]}" "${core_objs[@]}" "$out/mbed-sha256.o" "$out/mbed-platform_util.o" -lz -lpthread -o "$out/test_launcher_flow"
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" "$root/test/test_saves.cpp" "$out/san-launcher_core.o" \
    "${sobjs[@]}" "${core_objs[@]}" "$out/mbed-sha256.o" "$out/mbed-platform_util.o" -lz -lpthread -o "$out/test_saves"
echo "== the overlay glue with the console helpers stubbed (ASan/UBSan)"
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" "${sdl_inc[@]}" -DZA_UI_HOST_TEST=1 -DZA_MONEY_HOOK=1 \
    -c "$root/src/overlay_ps5.cpp" -o "$out/san-overlay_ps5.o"
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" "${sdl_inc[@]}" -DZA_UI_HOST_TEST=1 -c "$root/src/ui_platform.cpp" -o "$out/san-ui_platform.o"
"$CXX" -std=c++20 -O1 -g "${san[@]}" -fno-exceptions -fno-rtti -DZA_MONEY_TRACE=1 -I"$port/cheats-r27" -c "$port/cheats-r27/za_money.cpp" -o "$out/san-za_money.o"
"$CXX" -std=c++20 -O1 -g "${san[@]}" "${warn[@]}" "${ui_inc[@]}" "${core_inc[@]}" "${sdl_inc[@]}" "$root/test/test_overlay_glue.cpp" \
    "$out/san-overlay_ps5.o" "$out/san-ui_platform.o" "$out/san-za_money.o" "${sobjs[@]}" -lz -lpthread -o "$out/test_overlay_glue"
echo "== tests"
"$out/test_ui" "$root/fonts" | tee "$out/test_ui.log"
"$out/test_settings_codes" | tee "$out/test_settings_codes.log"
rm -rf "$out/flow-root" "$out/flow-root-keep" "$out/glue-root" "$out/saves-root"
"$out/test_launcher_flow" "$assets/" "$out/flow-root" 2> "$out/test_launcher_flow.stderr" | tee "$out/test_launcher_flow.log" || { tail -40 "$out/test_launcher_flow.stderr"; exit 1; }
# saves: the compatibility rule (+ the flow test's real v3 report and, when given, an old v2 report read in place),
# the slot container, the save-progress reader on the flow test's real generated save, deletion on a scratch root
flow_run=$(ls -d "$out/flow-root-keep"/r* 2>/dev/null | head -1)
"$out/test_saves" "$out/saves-root" "${flow_run:+$flow_run/report.json}" "${ZA_V2_REPORT:-}" "${flow_run:+$flow_run/save/save_0/main}" "${ZA_SLOT_NAMES:-}" \
    2> "$out/test_saves.stderr" | tee "$out/test_saves.log" || { tail -40 "$out/test_saves.stderr"; exit 1; }
"$out/test_overlay_glue" "$out/glue-root" 2> "$out/test_overlay_glue.stderr" | tee "$out/test_overlay_glue.log" || { tail -40 "$out/test_overlay_glue.stderr"; exit 1; }
echo "== mockups and goldens"
"$out/mockups-render" "$root/fonts" "$out/mockups" > "$out/mockups.log"
if [[ ${PIN_GOLDENS:-0} == 1 ]]; then
    cp "$out/mockups"/*.png "$root/mockups/"
    python3 "$root/tools/check-goldens.py" "$root/mockups/SHA256SUMS.txt" "$out/mockups" --pin | tee "$out/goldens.log"
else
    python3 "$root/tools/check-goldens.py" "$root/mockups/SHA256SUMS.txt" "$out/mockups" | tee "$out/goldens.log"
fi
# determinism: a second render must be byte-identical to the first
mkdir -p "$out/mockups2"
"$out/mockups-render" "$root/fonts" "$out/mockups2" > /dev/null
for p in "$out/mockups"/*.png; do cmp -s "$p" "$out/mockups2/$(basename "$p")" || { echo "non-deterministic render: $p" >&2; exit 1; }; done
echo "mockups render deterministically ($(ls "$out/mockups"/*.png | wc -l) images)"
if [[ ${PS5_CHECK:-0} == 1 ]]; then
    bash "$root/tools/compile-title-objects.sh" "${ZA_WORK_TREE:?ZA_WORK_TREE: a prepared merge tree}" "$out/ps5" "$assets" "${ZA_UI_LABEL:-r29-ui}" | tee "$out/ps5-check.log"
fi
echo "ui-v2 host build complete: $out"
