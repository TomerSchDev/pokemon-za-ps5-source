#!/usr/bin/env bash
# Convert/sign the full native image; package only after an error-free link.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
vulkan=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
sdk=$vulkan/.deps/native/ps5-payload-sdk
tool=$vulkan/build/host/ps5-native-tool
linked=$work/source/build/ps5/title/llvm-pie.elf
stubs=$work/source/build/ps5/title/ps5-link/stubs
dist=${TITLE_DIST:-$root/deliverables/ZA-Native-Title-r1-20261027}
title_id=${TITLE_ID:-PPSA91761}
title_name=${TITLE_NAME:-Pokémon Legends: Z-A}
[[ $title_id =~ ^PPSA[0-9]{5}$ ]] || { echo 'Invalid title ID' >&2; exit 2; }
app=$dist/$title_id
[[ -f $linked ]] || { echo "Missing linked title: $linked" >&2; exit 2; }
mkdir -p "$work/package" "$app/sce_sys" "$app/sce_module" "$app/cache/spirv" "$dist/evidence"
readelf=${LLVM_READELF:-/usr/lib/llvm-21/bin/llvm-readelf}
"$readelf" -h -l -d "$linked" > "$dist/evidence/elf-inspection.txt"
"$sdk/bin/llvm-nm" --dynamic --undefined-only "$linked" > "$dist/evidence/imports.txt"
"$sdk/bin/llvm-nm" --defined-only "$linked" > "$work/evidence/defined-symbols.txt"
"$sdk/bin/llvm-strip" --strip-debug -o "$work/package/title-stripped.elf" "$linked"
"$tool" link --in "$work/package/title-stripped.elf" --out "$work/package/eboot.elf" \
    --stub-dir "$sdk/target/lib" --stub "$stubs/libSceAgc.so" --stub "$stubs/libSceAgcDriver.so" \
    --module-sdk 0x02000009 --companion-sdk 0x08050001 --file-name eboot.elf
python3 "$root/port/title/verify-image.py" "$work/package/title-stripped.elf" "$work/package/eboot.elf" "$work/evidence/defined-symbols.txt" \
    > "$dist/evidence/image-preservation.json"
"$tool" self --sign --in "$work/package/eboot.elf" --out "$work/package/eboot.bin" --magic 0x1D3D154F
if [[ -f $app/eboot.bin ]] && ! cmp -s "$work/package/eboot.bin" "$app/eboot.bin"; then
    echo 'Different final eboot already exists; choose a new versioned TITLE_DIST.' >&2
    exit 2
fi
cp "$work/package/eboot.bin" "$app/eboot.bin"
(cd "$vulkan/runtime" && sha256sum --check --strict --quiet libc.prx.sha256)
cp "$vulkan/runtime/libc.prx" "$app/sce_module/libc.prx"
"$tool" self --inspect --file "$app/eboot.bin" > "$dist/evidence/self-inspection.txt"
"$tool" self --inspect --file "$app/sce_module/libc.prx" > "$dist/evidence/libc-inspection.txt"
python3 - "$root/vk-probe/sce_sys/param.json" "$app/sce_sys/param.json" "$title_id" "$title_name" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
p.update(titleId=sys.argv[3],conceptId=sys.argv[3][4:],contentId='UP9000-'+sys.argv[3]+'_00-ZANATIVETITLER01',downloadDataSize=1024)
p['localizedParameters']['en-US']['titleName']=sys.argv[4]
with open(sys.argv[2],'w') as f: json.dump(p,f,indent=2)
PY
for asset in icon0.png pic0.dds pic1.dds snd0.at9; do
    if [[ -f $root/port/title/assets/branding-r13/$asset ]]; then
        cp "$root/port/title/assets/branding-r13/$asset" "$app/sce_sys/$asset"
    elif [[ -f $root/vk-probe/sce_sys/$asset ]]; then
        cp "$root/vk-probe/sce_sys/$asset" "$app/sce_sys/$asset"
    fi
done
cp "$work"/shaders/*.spv "$app/cache/spirv/"
mkdir -p "$app/fonts"
cp "$root/port/title/assets/DejaVuSans.ttf" "$root/port/title/assets/DejaVuSans-LICENSE.txt" "$app/fonts/"
cp "$work/evidence/shaders.json" "$dist/evidence/"
cp "$work/evidence/source-head.txt" "$work/evidence/source-status.txt" "$work/evidence/source-uncommitted.patch" "$dist/evidence/"
printf '%s\n' 'Hardware status: this newly packaged image has not been tested. Consult its matching title run evidence; probe results do not establish game compatibility.' > "$dist/HARDWARE-PENDING.txt"
echo "Native title converted and signed: $app"
