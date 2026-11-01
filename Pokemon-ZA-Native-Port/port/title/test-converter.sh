#!/usr/bin/env bash
set -euo pipefail
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
vulkan=${PS5_VULKAN:-/home/tomer/ps5-za-native/PS5_Vulkan}
sdk=$vulkan/.deps/native/ps5-payload-sdk
smoke=$work/source/build/ps5/smoke
"$sdk/bin/llvm-strip" --strip-debug -o "$smoke/stripped.elf" "$smoke/llvm-pie.elf"
"$vulkan/build/host/ps5-native-tool" link --in "$smoke/stripped.elf" --out "$smoke/eboot.elf" \
    --stub-dir "$sdk/target/lib" --stub "$smoke/ps5-link/stubs/libSceAgc.so" \
    --stub "$smoke/ps5-link/stubs/libSceAgcDriver.so" --module-sdk 0x02000009 \
    --companion-sdk 0x08050001 --file-name eboot.elf
echo 'PASS: runtime-only link converts to native ELF (not a game build; not for deployment)'
