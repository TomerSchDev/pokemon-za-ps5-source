#!/usr/bin/env bash
# Host test of the real r29-music menu source (ASan/UBSan): only its three console paths are rewritten to a new
# temporary folder; the assets are the title's own (prepared-streamed + reward-assets), BGM.bnk is read read-only
# from the game's RomFS image. Checks the published run against the core's output for seed 1.
#   bash run-menu-test.sh PLAN.json ROMFS_BIN OUT_DIR(new) EXPECTED_CATEGORY_SEED1_SHA256
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
music=$(cd "$here/.." && pwd)
project=$(cd "$music/../.." && pwd)
plan=$1 romfs=$2 out=$3 expect=$4
[[ ! -e $out ]] || { echo "OUT_DIR must be new" >&2; exit 2; }
mkdir -p "$out/bin" "$out/assets" "$out/game" "$out/src"
deps=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/za-switch-mods/lib
prepared=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/ingame-randomizer/prepared-streamed
for f in "$prepared"/*.json "$prepared"/*.bin "$project/port/randomizer/reward-assets"/*; do ln -s "$f" "$out/assets/$(basename "$f")"; done
ln -s "$romfs" "$out/game/romfs.bin"
sed -e "s#\"/download0/zarecomp/rando\"#\"$out/rando\"#" -e "s#\"/app0/randomizer-assets/\"#\"$out/assets/\"#" \
    -e "s#\"/app0/game/romfs.bin\"#\"$out/game/romfs.bin\"#" "$music/native_menu_music.cpp" > "$out/src/native_menu_harness.cpp"
diff "$music/native_menu_music.cpp" "$out/src/native_menu_harness.cpp" > "$out/path-rewrite.diff" || true
[[ $(grep -c '^<' "$out/path-rewrite.diff") == 3 ]] || { echo 'expected exactly three rewritten lines' >&2; exit 2; }
python3 "$music/tools/embed_plan.py" "$plan" "$out/src/za_music_plan.cpp"
mbed=$deps/mbedtls
core=$project/port/randomizer/core
san=(-fsanitize=address,undefined -fno-sanitize-recover=all)
cfg=(-I"$mbed/include" -I"$core" -I"$project/port/randomizer" -I"$project/port/rando-v2" -I"$deps/json/include" -I"$music"
     -I/home/tomer/ps5-za-native/r28-play-20261030/r28/objects '-DMBEDTLS_CONFIG_FILE="za_mbedtls_config.h"')
for c in sha256 platform_util; do clang-21 -std=c11 -O1 -g "${san[@]}" "${cfg[@]}" -c "$mbed/library/$c.c" -o "$out/bin/$c.o"; done
clang++-21 -std=c++20 -O1 -g "${san[@]}" -Wall -Wextra -Werror -Wno-unused-parameter -fno-exceptions -fno-rtti -DJSON_NOEXCEPTION=1 \
    -Wno-unused-private-field "${cfg[@]}" \
    "$out/src/native_menu_harness.cpp" "$here/menu_harness.cpp" "$out/src/za_music_plan.cpp" "$music/za_music.cpp" \
    "$music/run_store_music.cpp" "$core/randomizer.cpp" "$project/port/randomizer/progression.cpp" \
    "$project/port/randomizer/research_rewards.cpp" "$project/port/randomizer/import_repair.cpp" \
    "$project/port/rando-v2/run_name.cpp" "$project/port/rando-v2/za_player_name.cpp" "$project/port/rando-v2/name_keyboard.cpp" \
    "$out/bin/sha256.o" "$out/bin/platform_util.o" -o "$out/bin/menu_harness"
"$out/bin/menu_harness" "$out/drawn-text.log" 2> "$out/console.log"
cat "$out/console.log"
python3 - "$out" "$expect" <<'PY'
import hashlib, json, os, sys
out, expect = sys.argv[1], sys.argv[2]
root = os.path.join(out, 'rando')
active = json.load(open(os.path.join(root, 'active.json')))['id']
rep = json.load(open(os.path.join(root, active, 'report.json')))
bank = open(os.path.join(root, active, 'romfs/audio/wwise/bin/Switch/BGM.bnk'), 'rb').read()
text = open(os.path.join(out, 'drawn-text.log')).read()
assert rep['seed'] == '1' and rep['music']['mode'] == 'category' and rep['options']['music'] == 'category', rep['music']
assert hashlib.sha256(bank).hexdigest() == rep['native_music']['sha256'] == expect, 'bank differs from the core output'
assert len(rep['native_tables']) == 4
assert '64,546 MUSIC  SHUFFLE BY CATEGORY' in text and '64,583 SAVED RUNS  0' in text, 'menu rows'
assert 'MUSIC  SHUFFLE BY CATEGORY - TOWN / ZONE / BATTLE / BOSS' in text, 'confirm page'
assert '64,546 MUSIC  OFF' in text, 'default OFF'
print('PASS: real menu source on host: seed 1 typed, MUSIC row cycled to SHUFFLE BY CATEGORY (row 10, default OFF),'
      ' confirm page shows the mode, run %s published with native_music %s = core output' % (active, expect[:16]))
PY
