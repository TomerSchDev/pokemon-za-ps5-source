#!/usr/bin/env bash
# Hebrew RTL on PS5: the PC's TextBox layout hook (rtl_engine.c + FriBidi) linked into the INSTALLED r28b + MUSIC image.
#
#   MSYS_NO_PATHCONV=1 wsl -d Ubuntu -- bash /mnt/c/.../port/hebrew-rtl/build-r29-hebrew.sh OUT
#   OUT  a folder under /home/tomer/ps5-za-native holding in/main_992.c (the 2.0.2 AOT unit, copied from the NAS AOT tree)
#        and fribidi/fribidi-1.0.16 (extracted from the pinned tarball). OUT/image must not exist yet.
#
# Changes, nothing else:
#   game unit main_992.c: the definition f_700264efe4 (nn::ui2d::TextBox vslot 26; no direct callers) is renamed
#     original_700264efe4 -> main_992.o replaced in a COPY of the base game archive (every other member identical)
#   new objects: rtl_engine.o (defines f_700264efe4, calls original_700264efe4) + FriBidi 1.0.16 (LGPL-2.1) objects
#   everything else is the r28b-music link exactly: runtime, title, menu, music, dexcount, Hebrew trial, cheats.
# Controls: the base link is reproduced byte for byte first; the original unit must rebuild its archive member byte for byte.
set -euo pipefail
trap 'echo "FAILED at line $LINENO: $BASH_COMMAND" >&2' ERR
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$here/../.." && pwd)
out=${1:?OUT required}
work=/home/tomer/ps5-za-native/r28b-dlc-dex-20261030-c01   # verifier scripts; default base
[[ $out == /home/tomer/ps5-za-native/* && -f $out/in/main_992.c && -d $out/fribidi/fribidi-1.0.16 && ! -e $out/image ]] \
  || { echo 'OUT must hold in/main_992.c and fribidi/fribidi-1.0.16, and no image/ yet' >&2; exit 2; }
pin(){ [[ $(sha256sum "$1" | cut -d' ' -f1) == "$2" ]] || { echo "pin mismatch: $1" >&2; exit 2; }; }
if [[ -n ${BASE_SPEC:-} ]]; then   # another installed image (base_from_build_info.py); its inputs are re-hashed there
  eval "$(python3 - "$BASE_SPEC" <<'PY'
import json,shlex,sys
s=json.load(open(sys.argv[1]))
print('base_eboot_sha=%s base_pie=%s base_pie_sha=%s archive=%s archive_sha=%s base_extra=%s'%tuple(map(shlex.quote,
      (s['eboot_sha256'],s['pie'],s['pie_sha256'],s['archive'],s['archive_sha256'],s['extra']))))
print('runtime=(%s)'%' '.join(map(shlex.quote,s['runtime'])))
print('src_tree=%s'%shlex.quote(s['runtime'][0].split('/build/ps5/rt/')[0]))
PY
)"
  cp "$BASE_SPEC" "$out/base-spec.json"
else                               # r28b + MUSIC (8e4280f0, installed 30.10)
  base_eboot_sha=8e4280f0da65ec3d00cb77b559833f1e9c6e427009e79ec15b0fab45fbf5dc7e
  pin "$work/r28b-music/eboot.bin" "$base_eboot_sha"
  base_pie=$work/r28b-music/llvm-pie.elf; base_pie_sha=055b296c091ed906e2fa6b5bc3c8812d3c83130aa7d74d7f571d19da8cadf21b
  archive=$work/r28b/liblasgame-r28b-dlc-dex.a; archive_sha=18dbbadc50d2f4bc71df94238ab1bb4b2fcac9ff57e2d005bc213c5fe1fbb580
  base_extra="$(cat "$work/r28b-music/evidence/link-inputs.txt")"
  mapfile -t relative_inputs < "$work/r28b-music/evidence/runtime-inputs.txt"
  runtime=(); for r in "${relative_inputs[@]}"; do runtime+=("$work/source/$r"); done
  src_tree=$work/source
fi
pin "$base_pie" "$base_pie_sha"
pin "$archive" "$archive_sha"
[[ $archive_sha == 18dbbadc50d2f4bc71df94238ab1bb4b2fcac9ff57e2d005bc213c5fe1fbb580 ]] || { echo 'main_992 control is pinned to the r28b game archive' >&2; exit 2; }
pin "$out/in/main_992.c" 0ebea88b6e15dca8965c407caaf3e4e229085587015424942c51f183d607007e
pin "$here/src/rtl_engine.c" b79d0a4a8410cd5aa07c803550bf61b268ee554520c43899adc359ecc48070c9     # choice anchors + existing quest-counter anchor
mkdir -p "$out/image" "$out/control" "$out/obj/fribidi" "$out/evidence" "$out/src"
cp "$here/build-r29-hebrew.sh" "$here/src/rtl_engine.c" "$out/src/"
exec > >(tee "$out/evidence/build.log") 2>&1
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK; ar=/usr/lib/llvm-21/bin/llvm-ar; nm=/usr/lib/llvm-21/bin/llvm-nm
cc_unit(){  # the game-unit recipe of port/perf-r28 and port/rando-dexcount, optimisation as given
 /usr/bin/clang-21 -target x86_64-sie-ps5 -fvisibility-nodllstorageclass=default \
  -isysroot "$sdk" -isystem "$sdk/target/include/c++/v1" -isystem "$sdk/target/include" \
  -fno-stack-protector -fno-plt -femulated-tls -fdenormal-fp-math=ieee \
  -DGUEST_VOLATILE -fno-strict-aliasing -Wno-return-type -Wno-unused-label \
  -fvisibility=hidden -Iruntime -march=x86-64-v3 -DZA_PS5 "$@"
}
cd "$src_tree"

echo '== 1. control: the base link reproduces the installed image byte for byte'
ZA_PS5_EXTRA_INPUTS="$base_extra" bash tools/ps5/link-title.sh "$out/control/llvm-pie.elf" "${runtime[@]}" "$archive" > "$out/evidence/control-link.log" 2>&1
cmp "$out/control/llvm-pie.elf" "$base_pie" && echo 'base link reproduced exactly'

echo '== 2. control: the original main_992.c rebuilds its archive member byte for byte'
cc_unit -O1 -c "$out/in/main_992.c" -o "$out/control/main_992.o"
"$ar" p "$archive" main_992.o > "$out/control/main_992.member.o"
cmp "$out/control/main_992.o" "$out/control/main_992.member.o" && echo 'main_992.o reproduced exactly'

echo '== 3. main_992.c: rename the one definition of f_700264efe4'
[[ $(grep -c 'f_700264efe4' "$out/in/main_992.c") == 1 ]] || { echo 'f_700264efe4 must occur exactly once (its definition)'; exit 2; }
sed -E 's/^void f_700264efe4\(Cpu \*c\) \{(\r?)$/void original_700264efe4(Cpu *c) {\1/' "$out/in/main_992.c" > "$out/obj/main_992.c"  # AOT units use CRLF
[[ $(grep -cE '^void original_700264efe4\(Cpu \*c\) \{'$'\r''?$' "$out/obj/main_992.c") == 1 ]]
cc_unit -O1 -c "$out/obj/main_992.c" -o "$out/obj/main_992.o"
diff <("$nm" --defined-only "$out/control/main_992.o" | awk '{print $NF}' | sort) \
     <("$nm" --defined-only "$out/obj/main_992.o" | awk '{print $NF}' | sort) > "$out/evidence/main_992.defined.diff" || true
[[ $(grep -c '^[<>]' "$out/evidence/main_992.defined.diff") == 2 ]] && grep -q '^< f_700264efe4$' "$out/evidence/main_992.defined.diff" \
  && grep -q '^> original_700264efe4$' "$out/evidence/main_992.defined.diff" || { echo 'unexpected symbol change'; cat "$out/evidence/main_992.defined.diff"; exit 2; }
cmp <("$nm" -u "$out/control/main_992.o") <("$nm" -u "$out/obj/main_992.o") && echo 'main_992: only the rename; imports unchanged'

echo '== 4. FriBidi 1.0.16 for PS5 (configure on the host for its headers, then the PS5 compiler)'
fb=$out/fribidi/fribidi-1.0.16
[[ -f $fb/config.h ]] || (cd "$fb" && ./configure --disable-shared --enable-static --disable-docs > "$out/evidence/fribidi-configure.log" 2>&1)
for c in "$fb"/lib/*.c; do
 sh "$PS5_VULKAN/tooling/prospero-clang18" -std=c11 -O2 -ffunction-sections -fdata-sections -DHAVE_CONFIG_H \
   -I"$fb" -I"$fb/lib" -c "$c" -o "$out/obj/fribidi/$(basename "$c" .c).o"
done
rm -f "$out/obj/libfribidi-ps5.a"; "$ar" rcs "$out/obj/libfribidi-ps5.a" "$out"/obj/fribidi/*.o
echo "fribidi objects: $(ls "$out"/obj/fribidi/*.o | wc -l)"

echo '== 5. rtl_engine.o (PC-tested shared choice and quest-counter anchors)'
cc_unit -O2 -std=gnu11 -include string.h -I"$fb/lib" -c "$here/src/rtl_engine.c" -o "$out/obj/rtl_engine.o"
"$nm" --defined-only "$out/obj/rtl_engine.o" | grep -q ' T f_700264efe4$'
"$nm" -u "$out/obj/rtl_engine.o" | awk '{print $NF}' | sort | tee "$out/evidence/rtl_engine.imports"

echo '== 6. archive copy with main_992.o replaced'
cp --reflink=auto "$archive" "$out/obj/liblasgame-r29-hebrew.a"
tmpd=$(mktemp -d); cp "$out/obj/main_992.o" "$tmpd/"; (cd "$tmpd" && "$ar" rcs "$out/obj/liblasgame-r29-hebrew.a" main_992.o); rm -rf "$tmpd"
python3 "$project/port/rando-dexcount/ps5/compare_ar.py" "$archive" "$out/obj/liblasgame-r29-hebrew.a" main_992.o > "$out/evidence/archive-compare.json"
"$ar" p "$out/obj/liblasgame-r29-hebrew.a" main_992.o | cmp - "$out/obj/main_992.o" && echo 'archive: only main_992.o differs'

echo '== 7. link: the base inputs + rtl_engine.o + FriBidi'
extra="$base_extra $out/obj/rtl_engine.o $out/obj/libfribidi-ps5.a"
echo "$extra" > "$out/evidence/link-inputs.txt"
ZA_PS5_EXTRA_INPUTS="$extra" bash tools/ps5/link-title.sh "$out/image/llvm-pie.elf" "${runtime[@]}" "$out/obj/liblasgame-r29-hebrew.a"
"$nm" --defined-only "$out/image/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
for s in f_700264efe4 original_700264efe4 rtl_transform fribidi_log2vis; do grep -q " $s\$" "$out/evidence/defined-symbols.txt" || { echo "missing $s"; exit 2; }; done
python3 "$work/r28b/src/verify-registration.py" "$base_pie" "$out/image/llvm-pie.elf" > "$out/evidence/registration.json"
diff <("$nm" --defined-only "$base_pie" | awk '{print $NF}' | sort -u) <(awk '{print $NF}' "$out/evidence/defined-symbols.txt" | sort -u) \
  | grep '^<' > "$out/evidence/symbols-lost.txt" || true
[[ ! -s $out/evidence/symbols-lost.txt ]] || { echo 'symbols of the base image were lost:'; head "$out/evidence/symbols-lost.txt"; exit 2; }
echo 'every base symbol preserved'

echo '== 8. ELF to signed SELF'
"$sdk/bin/llvm-strip" --strip-debug -o "$out/image/title-stripped.elf" "$out/image/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/image/title-stripped.elf" --out "$out/image/eboot.elf" --stub-dir "$sdk/target/lib" \
 --stub "$out/image/ps5-link/stubs/libSceAgc.so" --stub "$out/image/ps5-link/stubs/libSceAgcDriver.so" \
 --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$work/r28b/shader-probe-r18/verify-image.py" "$out/image/title-stripped.elf" "$out/image/eboot.elf" "$out/evidence/defined-symbols.txt" > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/image/eboot.elf" --out "$out/image/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/image/eboot.bin" > "$out/evidence/self-inspection.txt"
(cd "$out" && sha256sum image/eboot.bin image/llvm-pie.elf obj/main_992.o obj/rtl_engine.o obj/libfribidi-ps5.a obj/liblasgame-r29-hebrew.a in/main_992.c src/*) > "$out/evidence/SHA256SUMS.txt"
cat "$out/evidence/SHA256SUMS.txt"
echo 'r29-hebrew image built and statically verified offline; no in-game or console test'
