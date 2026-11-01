#!/usr/bin/env bash
# rando-dexcount for r28a: prepare the PS5 objects to layer on the r28-play work tree. Builds NO package.
#
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/rando-dexcount/ps5/apply-r28a.sh [WORK_TREE] [OUT_DIR]
#   WORK_TREE  only READ: default /home/tomer/ps5-za-native/r28-play-20261030; a copy such as r28a-play-20261030
#              works the same (its source/ gives -Iruntime; r28a/ or r28/liblasgame-r28.a is the base archive)
#   OUT_DIR    must be NEW: default /home/tomer/ps5-za-native/rando-dexcount-r28a-<date>
#   BASE_ARCHIVE=/path/x.a BASE_ARCHIVE_SHA256=<sha>  another game archive to layer on (pinned by SHA-256)
#   DEXCOUNT_PANEL=0  only the condition evaluator (main_310); the mission panel number (main_261) stays original
#
# Changes, nothing else:
#   game unit main_310.c (f_7000a1158c, evaluator of have_pokemon_encyclopedia_total_condition) -> main_310.o
#   game unit main_261.c (f_700082b5c4, mission panel value, item type 2 only)                   -> main_261.o
#     both replaced in a COPY of the game archive: OUT/liblasgame-r28-dexcount.a (every other member identical)
#   new object OUT/za_dexcount.o (port/rando-dexcount/za_dexcount.c, trace on: "[dexcount] ..." to klog + stderr)
#     -> append to ZA_PS5_EXTRA_INPUTS of the title link
#   runtime, title, menu, randomizer core/progression/run_store, Hebrew/items/money objects: unchanged
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
own=$(cd "$here/.." && pwd)
work=${1:-/home/tomer/ps5-za-native/r28-play-20261030}
out=${2:-/home/tomer/ps5-za-native/rando-dexcount-r28a-$(date +%Y%m%d)}
game=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025
default_base=$work/r28/liblasgame-r28.a; [[ -f $work/r28a/liblasgame-r28.a ]] && default_base=$work/r28a/liblasgame-r28.a
base=${BASE_ARCHIVE:-$default_base}
base_sha=${BASE_ARCHIVE_SHA256:-a86c3134e7de8d14ce7a960b1000024d35dcc2eabac8b3529036936da494bb30}
panel=${DEXCOUNT_PANEL:-1}
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
ar=/usr/lib/llvm-21/bin/llvm-ar
nm=/usr/lib/llvm-21/bin/llvm-nm
units=(main_310); [[ $panel == 0 ]] || units+=(main_261)

[[ -d $work/source/runtime && -f $base ]] || { echo "work tree / base archive missing"; exit 2; }
[[ $(sha256sum "$base" | cut -d' ' -f1) == "$base_sha" ]] || { echo "base archive is not the pinned one: $base"; exit 2; }
[[ ! -e $out ]] || { echo "output must be new: $out"; exit 2; }
for u in "${units[@]}"; do
  if grep -qw "main/$u" "$work/source/build/ps5/gen/giants.mk" 2>/dev/null; then echo "$u is a giant unit"; exit 2; fi
done
mkdir -p "$out/control" "$out/src" "$out/evidence"
cp "$own/za_dexcount.c" "$own/za_dexcount.h" "$own/prepare-dexcount-hooks.py" "$here/apply-r28a.sh" "$here/compare_ar.py" "$out/src/"
exec > >(tee "$out/evidence/apply.log") 2>&1
echo "== 1. patch main_310.c + main_261.c (build ID + source SHA-256 checked by the patcher)"
python3 "$own/prepare-dexcount-hooks.py" "$game/aot/main" "$game/game/exefs/main" "$out/gen"
cc_unit(){  # exactly the game-unit recipe of port/perf-r28/build-r28-play.sh
 /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
  -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
  -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
  -O1 -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
  -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 -c "$1" -o "$2"
}
cd "$work/source"
for u in "${units[@]}"; do
  echo "== 2. $u: control (the ORIGINAL unit must rebuild the archive member byte for byte), then patched"
  cc_unit "$game/aot/main/$u.c" "$out/control/$u.o"
  "$ar" p "$base" "$u.o" > "$out/control/$u.member.o"
  cmp -s "$out/control/$u.o" "$out/control/$u.member.o" || { echo "Control mismatch: $u"; exit 2; }
  cc_unit "$out/gen/$u.c" "$out/$u.o"
  "$nm" --defined-only "$out/control/$u.o" | awk '{print $NF}' | sort > "$out/evidence/$u.control.defined"
  "$nm" --defined-only "$out/$u.o" | awk '{print $NF}' | sort > "$out/evidence/$u.patched.defined"
  cmp -s "$out/evidence/$u.control.defined" "$out/evidence/$u.patched.defined" || { echo "$u: defined symbols changed"; exit 2; }
  added=$(comm -13 <("$nm" -u "$out/control/$u.o" | awk '{print $NF}' | sort) <("$nm" -u "$out/$u.o" | awk '{print $NF}' | sort) | tr '\n' ' ')
  case "$u:$added" in
    "main_310:za_dexcount_combine za_dexcount_extra_enabled "|"main_261:za_dexcount_display za_dexcount_extra_enabled ") ;;
    *) echo "$u: unexpected new imports: $added"; exit 2 ;;
  esac
  echo "$u ok: control $(sha256sum "$out/control/$u.o" | cut -d' ' -f1) patched $(sha256sum "$out/$u.o" | cut -d' ' -f1); new imports: $added"
done
echo "== 3. za_dexcount.o (title C flags of r28; trace on: one klog + stderr line per changed value)"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
  -DZA_DEXCOUNT_TRACE=1 -DZA_DEXCOUNT_KLOG=1 -c "$own/za_dexcount.c" -o "$out/za_dexcount.o"
"$nm" --defined-only "$out/za_dexcount.o" | grep -cE ' T za_dexcount_(combine|display|extra_enabled)$' | grep -qx 3
"$nm" -u "$out/za_dexcount.o" | awk '{print $NF}' | sort > "$out/evidence/za_dexcount.imports"
imports=$(tr '\n' ' ' < "$out/evidence/za_dexcount.imports")
echo "za_dexcount.o imports (libc stdio + klog, all already imported by the r28 title): $imports"
[[ $imports == "__stderrp fflush fputs sceKernelDebugOutText snprintf " ]] || { echo 'za_dexcount.o: unexpected imports'; exit 2; }
echo "== 4. archive copy with the patched members replaced"
cp --reflink=auto "$base" "$out/liblasgame-r28-dexcount.a"
tmpd=$(mktemp -d); for u in "${units[@]}"; do cp "$out/$u.o" "$tmpd/$u.o"; done
(cd "$tmpd" && "$ar" rcs "$out/liblasgame-r28-dexcount.a" "${units[@]/%/.o}"); rm -rf "$tmpd"
python3 "$here/compare_ar.py" "$base" "$out/liblasgame-r28-dexcount.a" "${units[@]/%/.o}" > "$out/evidence/archive-compare.json"
for u in "${units[@]}"; do "$ar" p "$out/liblasgame-r28-dexcount.a" "$u.o" | cmp -s - "$out/$u.o"; done
echo "archive: only ${units[*]} differ; member order and count unchanged"
echo "== 5. manifest"
python3 - "$out" "$base" "$game/aot/main" "${units[@]}" <<'EOF'
import hashlib, json, os, sys
out, base, aot, units = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
h = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
fn = {'main_310': 'f_7000a1158c', 'main_261': 'f_700082b5c4'}
m = dict(purpose='rando-dexcount r28a: have_pokemon_encyclopedia_total counts Lumiose + Hyperspace (DLC) dex',
         console_tested=False, package_built=False,
         game_units={u: dict(function=fn[u], source_original_sha256=h(os.path.join(aot, u + '.c')),
                             source_patched_sha256=h(os.path.join(out, 'gen', u + '.c')),
                             object_original_sha256=h(os.path.join(out, 'control', u + '.o')),
                             object_patched_sha256=h(os.path.join(out, u + '.o'))) for u in units},
         new_object=dict(path=os.path.join(out, 'za_dexcount.o'), sha256=h(os.path.join(out, 'za_dexcount.o')),
                         source_sha256=h(os.path.join(out, 'src/za_dexcount.c')),
                         header_sha256=h(os.path.join(out, 'src/za_dexcount.h')), defines=['ZA_DEXCOUNT_TRACE=1', 'ZA_DEXCOUNT_KLOG=1']),
         archive=dict(base=base, base_sha256=h(base), new=os.path.join(out, 'liblasgame-r28-dexcount.a'),
                      new_sha256=h(os.path.join(out, 'liblasgame-r28-dexcount.a')), changed_members=[u + '.o' for u in units]),
         link=dict(game_archive=os.path.join(out, 'liblasgame-r28-dexcount.a'),
                   ZA_PS5_EXTRA_INPUTS_append=os.path.join(out, 'za_dexcount.o')))
open(os.path.join(out, 'dexcount-r28a-manifest.json'), 'w').write(json.dumps(m, indent=2) + '\n')
print(json.dumps(m, indent=2))
EOF
(cd "$out" && sha256sum gen/*.c ./*.o liblasgame-r28-dexcount.a control/*.o src/* > evidence/SHA256SUMS.txt)
echo "rando-dexcount r28a objects ready in $out (no package built, no console access)"
