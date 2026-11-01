#!/usr/bin/env bash
# Reuse the five pinned r29 music objects only after proving their three base
# objects are exactly the ones in our preserved r28a inputs. No extra tree clone.
set -euo pipefail
renice 10 -p $$ >/dev/null
project='/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'
work_tree=${1:?completed r28b work tree required}
base_out=$work_tree/r28b
out=$work_tree/r28b-music
music=/home/tomer/ps5-za-native/r29-music-20261030-r28-play-20261030/r29
[[ $work_tree == /home/tomer/ps5-za-native/r28b-dlc-dex-* && -f $base_out/eboot.bin && ! -e $out ]] || { echo 'completed base/new output required' >&2; exit 2; }
mkdir -p "$out/objects" "$out/evidence" "$out/src"
exec > >(tee "$out/evidence/build.log") 2>&1
cp "$project/port/r28b-dlc-dex/build-music-variant.sh" "$out/src/"
cp "$project/port/rando-music/verify-r29.py" "$out/src/"
cp "$project/artifacts/randomizer-r29-music-on-r28/BUILD-INFO.json" "$out/evidence/music-input-build-info.json"
echo '== pinned r29 music overrides, only after matching their exact base object hashes'
python3 - "$work_tree" "$out" "$music" <<'PY'
from pathlib import Path
import hashlib,json,shutil,sys
work,out,music=map(Path,sys.argv[1:])
info=json.loads((out/'evidence/music-input-build-info.json').read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
records=[]
for name,pins in info['objects']['changed'].items():
    current=work/'r28a/objects'/name
    assert sha(current)==pins['base'],'music would overwrite another change in '+name
    incoming=music/'objects'/name
    assert sha(incoming)==pins['r29'],'music object changed: '+name
    target=out/'objects'/name;shutil.copy2(incoming,target)
    records.append({'name':name,'base':pins['base'],'new':pins['r29'],'kind':'changed','identical_to_published_music':sha(target)==pins['r29']})
for name,pin in info['objects']['added'].items():
    incoming=music/'objects'/name
    assert sha(incoming)==pin,'new music object changed: '+name
    target=out/'objects'/name;shutil.copy2(incoming,target)
    records.append({'name':name,'new':pin,'kind':'added','identical_to_published_music':sha(target)==pin})
extra=(work/'r28b/evidence/link-inputs.txt').read_text().strip()
for name in info['objects']['changed']:
    old=str(work/'r28a/objects'/name)
    assert extra.split().count(old)==1,'unexpected base link record for '+name
    extra=extra.replace(old,str(out/'objects'/name))
extra+=' '+str(out/'objects/za_music.o')+' '+str(out/'objects/za_music_plan.o')
(out/'evidence/link-inputs.txt').write_text(extra+'\n')
shutil.copy2(work/'r28b/evidence/runtime-inputs.txt',out/'evidence/runtime-inputs.txt')
(out/'evidence/music-override-inputs.json').write_text(json.dumps({'overrides':records,'base_runtime_archive_dexcount_early_dex_helper_preserved':True,'plan_sha256':info['music']['plan_sha256']},indent=2)+'\n')
print(json.dumps({'music_objects':len(records),'all_pins_match':True,'base_object_controls_match':True}))
PY
export PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan
export PS5_PAYLOAD_SDK=$PS5_VULKAN/.deps/native/ps5-payload-sdk
export PS5_CLANG=/usr/bin/clang-21
sdk=$PS5_PAYLOAD_SDK
export ZA_PS5_EXTRA_INPUTS="$(cat "$out/evidence/link-inputs.txt")"
mapfile -t relative_inputs < "$out/evidence/runtime-inputs.txt"
runtime=(); for relative in "${relative_inputs[@]}"; do runtime+=("$work_tree/source/$relative"); done
cd "$work_tree/source"
bash tools/ps5/link-title.sh "$out/llvm-pie.elf" "${runtime[@]}" "$base_out/liblasgame-r28b-dlc-dex.a"
ref=/home/tomer/ps5-za-native/r28-play-20261030/r28/llvm-pie.elf
python3 "$base_out/src/verify-registration.py" "$ref" "$out/llvm-pie.elf" > "$out/evidence/registration.json"
python3 "$base_out/src/verify-r28a.py" image "$ref" "$out/llvm-pie.elf" "$out/evidence" "$project"
python3 "$base_out/src/verify-r28a.py" final-image "$project/port/rando-dexcount/ps5/HANDOFF.json" "$base_out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
python3 "$base_out/src/verify-feature-image.py" "$base_out/control/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence"
python3 "$out/src/verify-r29.py" image "$base_out/llvm-pie.elf" "$out/llvm-pie.elf" "$out/evidence" "$project" fcef0023680e21a305b962d9962bcdafe518d0c9c899d50f841692f9d6471c70 r28
nm=/usr/lib/llvm-21/bin/llvm-nm
"$nm" --defined-only "$out/llvm-pie.elf" > "$out/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$out/title-stripped.elf" "$out/llvm-pie.elf"
tool=$PS5_VULKAN/build/host/ps5-native-tool
"$tool" link --in "$out/title-stripped.elf" --out "$out/eboot.elf" --stub-dir "$sdk/target/lib" \
 --stub "$out/ps5-link/stubs/libSceAgc.so" --stub "$out/ps5-link/stubs/libSceAgcDriver.so" \
 --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$base_out/src/verify-image.py" "$out/title-stripped.elf" "$out/eboot.elf" "$out/evidence/defined-symbols.txt" > "$out/evidence/image-preservation.json"
"$tool" self --sign --in "$out/eboot.elf" --out "$out/eboot.bin" --magic 0x1D3D154F
"$tool" self --inspect --file "$out/eboot.bin" > "$out/evidence/self-inspection.txt"
sha256sum "$out/eboot.bin" "$out/llvm-pie.elf" > "$out/evidence/SHA256SUMS.txt"
cat "$out/evidence/SHA256SUMS.txt"
echo 'r28b + MUSIC candidate built and statically verified; not tested in-game'
