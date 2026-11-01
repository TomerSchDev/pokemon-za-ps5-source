#!/usr/bin/env bash
# Canonical PC queue lease required. Only new scratch output; no console access.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
project=$(cd "$root/../.." && pwd)
out=${1:?NEW output directory}
old=/home/tomer/ui-v2-build/save-reset-20261031-07
assets=/home/tomer/ps5-za-native/rando-v3-codex-m1-assets
runtime=$(cd "$project/../pokeza-recomp-ps5-save-slot-writer" && pwd)
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
[[ -n ${PC_TEST_AGENT:-} && -n ${PC_TEST_TICKET:-} && -n ${PC_TEST_TOKEN:-} ]] || { echo 'PC lease environment required' >&2; exit 2; }
[[ $out == /home/tomer/ps5-za-native/save-slots-* && ! -e $out ]] || { echo 'Output must be a NEW save-slots-* directory' >&2; exit 2; }
mkdir -p "$out"
# Verify all original source inputs except the two intentionally changed units.
python3 - "$project" <<'PY'
import hashlib, json, pathlib, sys
root = pathlib.Path(sys.argv[1])
pins = json.loads(pathlib.Path('/home/tomer/ps5-za-native/save-slots-pkg-20261031-03/evidence/source-hashes.json').read_text())
changed = {'port/ui-v2/src/launcher_core.cpp', 'port/ui-v2/src/launcher_core.h', 'port/ui-v2/src/za_slot.h', 'port/ui-v2/test/test_saves.cpp'}
for name, pin in pins.items():
    if name in changed: continue
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == pin, name
print('PASS: unchanged Claude source pins', len(pins)-len(changed))
PY
cxx=${CXX:-clang++-21}
cc=${CC:-clang-21}
san=(-fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer)
incs=(-isystem "$root/third_party/stb" -I"$root/src" -I"$project/port/rando-v3/src" -I"$project/port/rando-v3"
 -I"$project/port/randomizer" -I"$project/port/rando-v2" -I"$project/port/cheats-r28" -I"$project/port/rando-v3/core"
 -I"$project/port/rando-music" -I"$project/port/cheats-r27" -I"$project/port/perf-r28/src" -I"$assets"
 -I"$deps/json/include" -I"$deps/mbedtls/include" '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"' -DJSON_NOEXCEPTION=1)
flags=(-std=c++20 -O1 -g -Wall -Wextra -Werror -Wno-missing-field-initializers -fno-exceptions -fno-rtti "${san[@]}")
"$cxx" "${flags[@]}" -I"$root/src" "$root/test/test_saves_fs.cpp" -Wl,--wrap=lstat -Wl,--wrap=open -o "$out/test_saves_fs"
"$out/test_saves_fs" "$out/fs-root" | tee "$out/test_saves_fs.log"
"$cxx" "${flags[@]}" -I"$root/src" "$root/test/test_slot_atomic.cpp" -Wl,--wrap=open -Wl,--wrap=unlink -Wl,--wrap=fsync -o "$out/test_slot_atomic"
"$out/test_slot_atomic" "$out/atomic-root" | tee "$out/test_slot_atomic.log"
"$cxx" "${flags[@]}" "${incs[@]}" -c "$root/src/launcher_core.cpp" -o "$out/launcher_core.o"
objs=()
for s in ui_canvas ui_widgets ui_model settings_codes items_picker ui_launcher ui_overlay ui_pad fonts_embedded legacy_look png_write; do objs+=("$old/san-$s.o"); done
for s in randomizer legacy_progression legacy_research_rewards rando_v3 import_repair run_store_v3 za_music za_music_plan run_name za_player_name name_keyboard; do objs+=("$old/core-$s.o"); done
objs+=("$old/mbed-sha256.o" "$old/mbed-platform_util.o")
for test in test_saves test_launcher_flow; do
 "$cxx" "${flags[@]}" "${incs[@]}" "$root/test/$test.cpp" "$out/launcher_core.o" "${objs[@]}" -lz -lpthread -o "$out/$test"
done
"$out/test_saves" "$out/saves-root" > "$out/test_saves.log" 2> "$out/test_saves.stderr"
"$out/test_launcher_flow" "$assets/" "$out/flow-root" > "$out/test_launcher_flow.log" 2> "$out/test_launcher_flow.stderr"
# Test the ACTUAL background writer with an unknown nested metadata field.
# Its production source is copied byte-for-byte; only test data is extended.
proof=$out/runtime-proof
mkdir -p "$proof/runtime/services" "$proof/runtime/platform" "$proof/tools/save_slot"
cp "$runtime/runtime/platform.h" "$proof/runtime/"
cp "$runtime/runtime/platform/linux_compat.h" "$proof/runtime/platform/"
for f in save_slot.c save_slot.h za_slot.h; do cp "$runtime/runtime/services/$f" "$proof/runtime/services/"; done
cp "$root/src/za_slot.h" "$proof/runtime/services/za_slot.h"  # candidate uses the identical hardened header
for f in test.sh test_log.h test_save_slot.c; do cp "$runtime/tools/save_slot/$f" "$proof/tools/save_slot/"; done
python3 - "$proof/tools/save_slot/test_save_slot.c" <<'PY'
import pathlib, sys
p=pathlib.Path(sys.argv[1]); text=p.read_text()
old='static const char RandJson[] = "{\\"schema\\":\\"za-slot-rand-1\\",\\"run_id\\":\\"rTEST\\"}";'
new='static const char RandJson[] = "{\\"schema\\":\\"za-slot-rand-1\\",\\"run_id\\":\\"rTEST\\",\\"source_report\\":{\\"future_extra\\":{\\"nested\\":[\\"unknown\\",42,true]}}}";'
assert text.count(old)==1
p.write_text(text.replace(old,new))
PY
bash "$proof/tools/save_slot/test.sh" "$out/runtime-test" > "$out/test_writer.log" 2> "$out/test_writer.stderr"
# API/flag availability at the actual PS5 target (compile-only, not hardware).
vulkan=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$vulkan/.deps/native/ps5-payload-sdk PS5_CLANG=/usr/bin/clang-21
printf '#include "saves_fs.h"\nextern "C" bool saves_probe(const char *p) { return ui::launcher::saves::fs_detail::isDirectoryNoFollow(p); }\n' > "$out/ps5-api-probe.cpp"
sh "$vulkan/tooling/prospero-clang18" -std=c++20 -O2 -Wall -Wextra -Werror -fno-exceptions -fno-rtti -I"$root/src" -c "$out/ps5-api-probe.cpp" -o "$out/ps5-api-probe.o"
printf '#define ZA_SLOT_IMPLEMENTATION\n#include "za_slot.h"\n' > "$out/ps5-slot-probe.c"
sh "$vulkan/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -I"$root/src" -c "$out/ps5-slot-probe.c" -o "$out/ps5-slot-probe.o"
sha256sum "$root/src/launcher_core.cpp" "$root/src/saves_fs.h" "$root/test/test_saves.cpp" "$root/test/test_saves_fs.cpp" "$runtime/runtime/services/save_slot.c" > "$out/source-sha256.txt"
cat "$out/test_saves.log" "$out/test_launcher_flow.log" "$out/test_writer.log"
echo 'PASS: continuation host tests and PS5 API compile-only check (no hardware claim)'
