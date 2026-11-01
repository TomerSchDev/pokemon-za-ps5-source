#!/usr/bin/env bash
# rando-dexopen for r28b: prepare the PS5 objects to layer on the r28a-play FINAL tree. Builds NO package.
#
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/rando-dexopen/ps5/apply-r28b.sh [WORK_TREE] [OUT_DIR]
#   WORK_TREE  only READ: default /home/tomer/ps5-za-native/r28a-play-final-20261030 (its source/ gives -Iruntime; its
#              rando-dexcount/liblasgame-r28-dexcount.a is the base archive = r28a's game archive, dexcount included)
#   OUT_DIR    must be NEW: default /home/tomer/ps5-za-native/rando-dexopen-r28b-<date>
#   BASE_ARCHIVE=/path/x.a BASE_ARCHIVE_SHA256=<sha>  another game archive to layer on (pinned by SHA-256)
#
# Changes, nothing else:
#   game unit main_287.c (f_70008d4178, DLC::IsHyperspaceDexEnabled: returns readiness, flag not required) -> main_287.o
#   game unit main_115.c (f_700033f8d8, Pokedex::GetMegaDexCount: the Hyperspace-rows filter forced on)   -> main_115.o
#     both replaced in a COPY of the game archive: OUT/liblasgame-r28-dexopen.a (every other member identical)
#   new object OUT/za_dexopen.o (port/rando-dexopen/za_dexopen.c, trace on: "[dexopen] ..." to klog + stderr)
#     -> append to ZA_PS5_EXTRA_INPUTS of the title link
#   runtime, title, menu, randomizer core/progression/run_store, Hebrew/items/money/dexcount objects: unchanged
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
own=$(cd "$here/.." && pwd)
work=${1:-/home/tomer/ps5-za-native/r28a-play-final-20261030}
out=${2:-/home/tomer/ps5-za-native/rando-dexopen-r28b-$(date +%Y%m%d)}
game=/mnt/c/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025
base=${BASE_ARCHIVE:-$work/rando-dexcount/liblasgame-r28-dexcount.a}
base_sha=${BASE_ARCHIVE_SHA256:-1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc}
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
ar=/usr/lib/llvm-21/bin/llvm-ar
nm=/usr/lib/llvm-21/bin/llvm-nm
units=(main_287 main_115)
declare -A want_import=([main_287]='za_dexopen_hyperspace_dex_enabled ' [main_115]='za_dexopen_mega_dex_flag ')

[[ -d $work/source/runtime && -f $base ]] || { echo "work tree / base archive missing"; exit 2; }
[[ $(sha256sum "$base" | cut -d' ' -f1) == "$base_sha" ]] || { echo "base archive is not the pinned one: $base"; exit 2; }
[[ ! -e $out ]] || { echo "output must be new: $out"; exit 2; }
for u in "${units[@]}"; do
  if grep -qw "main/$u" "$work/source/build/ps5/gen/giants.mk" 2>/dev/null; then echo "$u is a giant unit"; exit 2; fi
done
mkdir -p "$out/control" "$out/src" "$out/evidence"
cp "$own/za_dexopen.c" "$own/za_dexopen.h" "$own/prepare-dexopen-hooks.py" "$here/apply-r28b.sh" "$here/compare_ar.py" "$out/src/"
exec > >(tee "$out/evidence/apply.log") 2>&1
echo "== 1. patch main_287.c + main_115.c (build ID + source SHA-256 checked by the patcher)"
python3 "$own/prepare-dexopen-hooks.py" "$game/aot/main" "$game/game/exefs/main" "$out/gen"
cc_unit(){  # exactly the game-unit recipe of port/perf-r28/build-r28-play.sh (as port/rando-dexcount/ps5/apply-r28a.sh)
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
  [[ $added == "${want_import[$u]}" ]] || { echo "$u: unexpected new imports: $added"; exit 2; }
  echo "$u ok: control $(sha256sum "$out/control/$u.o" | cut -d' ' -f1) patched $(sha256sum "$out/$u.o" | cut -d' ' -f1); new imports: $added"
done
echo "== 3. za_dexopen.o (title C flags of r28; trace on: one klog + stderr line per site on first use / flag change)"
sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -Wall -Wextra -Werror -ffunction-sections -fdata-sections \
  -DZA_DEXOPEN_TRACE=1 -DZA_DEXOPEN_KLOG=1 -c "$own/za_dexopen.c" -o "$out/za_dexopen.o"
"$nm" --defined-only "$out/za_dexopen.o" | grep -cE ' T za_dexopen_(hyperspace_dex_enabled|mega_dex_flag|enabled|set_enabled)$' | grep -qx 4
"$nm" -u "$out/za_dexopen.o" | awk '{print $NF}' | sort > "$out/evidence/za_dexopen.imports"
imports=$(tr '\n' ' ' < "$out/evidence/za_dexopen.imports")
echo "za_dexopen.o imports (libc stdio + klog, all already imported by the r28/r28a title): $imports"
[[ $imports == "__stderrp fflush fputs sceKernelDebugOutText snprintf " ]] || { echo 'za_dexopen.o: unexpected imports'; exit 2; }
echo "== 4. archive copy with the patched members replaced"
cp --reflink=auto "$base" "$out/liblasgame-r28-dexopen.a"
tmpd=$(mktemp -d); for u in "${units[@]}"; do cp "$out/$u.o" "$tmpd/$u.o"; done
(cd "$tmpd" && "$ar" rcs "$out/liblasgame-r28-dexopen.a" "${units[@]/%/.o}"); rm -rf "$tmpd"
python3 "$here/compare_ar.py" "$base" "$out/liblasgame-r28-dexopen.a" "${units[@]/%/.o}" > "$out/evidence/archive-compare.json"
for u in "${units[@]}"; do "$ar" p "$out/liblasgame-r28-dexopen.a" "$u.o" | cmp -s - "$out/$u.o"; done
echo "archive: only ${units[*]} differ; member order and count unchanged"
echo "== 5. manifest"
python3 - "$out" "$base" "$game/aot/main" "${units[@]}" <<'EOF'
import hashlib, json, os, sys
out, base, aot, units = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:]
h = lambda p: hashlib.sha256(open(p, 'rb').read()).hexdigest()
fn = {'main_287': 'f_70008d4178 DLC::IsHyperspaceDexEnabled', 'main_115': 'f_700033f8d8 Pokedex::GetMegaDexCount'}
imp = {'main_287': 'za_dexopen_hyperspace_dex_enabled', 'main_115': 'za_dexopen_mega_dex_flag'}
m = dict(purpose='rando-dexopen r28b: the Hyperspace (Mega Dimension) Pokedex list is enumerated from the start; '
                 'FLAG_DLC_DEX_ENABLE is treated as set by its two readers, never written',
         console_tested=False, package_built=False,
         game_units={u: dict(function=fn[u], new_import=imp[u], source_original_sha256=h(os.path.join(aot, u + '.c')),
                             source_patched_sha256=h(os.path.join(out, 'gen', u + '.c')),
                             object_original_sha256=h(os.path.join(out, 'control', u + '.o')),
                             object_patched_sha256=h(os.path.join(out, u + '.o'))) for u in units},
         new_object=dict(path=os.path.join(out, 'za_dexopen.o'), sha256=h(os.path.join(out, 'za_dexopen.o')),
                         source_sha256=h(os.path.join(out, 'src/za_dexopen.c')),
                         header_sha256=h(os.path.join(out, 'src/za_dexopen.h')), defines=['ZA_DEXOPEN_TRACE=1', 'ZA_DEXOPEN_KLOG=1'],
                         imports=open(os.path.join(out, 'evidence/za_dexopen.imports')).read().split()),
         archive=dict(base=base, base_sha256=h(base), new=os.path.join(out, 'liblasgame-r28-dexopen.a'),
                      new_sha256=h(os.path.join(out, 'liblasgame-r28-dexopen.a')), changed_members=[u + '.o' for u in units]),
         link=dict(game_archive=os.path.join(out, 'liblasgame-r28-dexopen.a'),
                   ZA_PS5_EXTRA_INPUTS_append=os.path.join(out, 'za_dexopen.o')),
         expected_linked_calls=['f_70008d4178 -> za_dexopen_hyperspace_dex_enabled', 'f_700033f8d8 -> za_dexopen_mega_dex_flag'])
open(os.path.join(out, 'dexopen-r28b-manifest.json'), 'w').write(json.dumps(m, indent=2) + '\n')
print(json.dumps(m, indent=2))
EOF
(cd "$out" && sha256sum gen/*.c ./*.o liblasgame-r28-dexopen.a control/*.o src/* > evidence/SHA256SUMS.txt)
echo "rando-dexopen r28b objects ready in $out (no package built, no console access)"
