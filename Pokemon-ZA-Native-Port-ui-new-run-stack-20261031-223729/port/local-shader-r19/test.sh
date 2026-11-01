#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=/home/tomer/ps5-za-native/compiler-r19-20261028/host-tests-$(date -u +%Y%m%d-%H%M%S)
glsl=/home/tomer/ps5-za-native/shader-prewarm-research
mkdir -p "$work"
exec > >(tee "$work/test.log") 2>&1
cc=/usr/bin/clang-21
flags=(-std=c11 -O1 -g -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer -pthread -I"$root" -I"$project/port/shaderc-cache/include")
export ASAN_OPTIONS=detect_leaks=1:abort_on_error=1
"$cc" "${flags[@]}" -DZA_LOCAL_SKIP_WARMUP=1 -DZA_LOCAL_TIMEOUT_MS=1000 "$root/worker.c" "$root/test-worker.c" -o "$work/test-worker"
"$work/test-worker"
for name in worker shaderc_cache compiler_adapter test-api; do
    "$cc" "${flags[@]}" -I"$glsl/glslang" -c "$root/$name.c" -o "$work/$name.o"
done
libs=("$glsl/host-build/glslang/glslang/libglslang.a" "$glsl/host-build/glslang/glslang/libMachineIndependent.a" \
      "$glsl/host-build/glslang/glslang/libGenericCodeGen.a" "$glsl/host-build/glslang/glslang/libglslang-default-resource-limits.a" "$glsl/host-build/glslang/SPIRV/libSPIRV.a")
/usr/bin/clang++-21 -fsanitize=address,undefined -pthread "$work/worker.o" "$work/shaderc_cache.o" "$work/compiler_adapter.o" "$work/test-api.o" \
    -Wl,--start-group "${libs[@]}" -Wl,--end-group -o "$work/test-api"
export ZA_SHADERC_CACHE_DIRS="$work/cache"
export ZA_SHADERC_MISSING_DIR="$work/missing"
export ZA_SHADERC_HOST_WAIT_MS=0
export ZA_SHADERC_LOCAL=1
"$work/test-api" "$project/evidence/randomizer-shaders-20261028-041124Z" "$work/results"
python3 - "$project" "$work" <<'PY'
from pathlib import Path
import hashlib,json,subprocess,sys
root,work=map(Path,sys.argv[1:])
m=json.loads((root/'evidence/randomizer-shaders-20261028-041124Z/manifest.json').read_text())
for i in range(3):
    for e in m:
        p=work/f'results/{i:02d}-{e["source"]}.spv'
        assert hashlib.sha256(p.read_bytes()).hexdigest()==e['spv_sha256'],p
        subprocess.run(['spirv-val','--target-env','vulkan1.3',str(p)],check=True)
subprocess.run(['spirv-val','--target-env','vulkan1.2',str(work/'results/compute-vulkan12.spv')],check=True)
(work/'verification.json').write_text(json.dumps(dict(captured_hashes_passed=36,spirv_validations=37,asan_ubsan=True,work=str(work)),indent=2)+'\n')
print('36 matching captured outputs, 37 spirv-val passes')
PY
printf 'HOST_TEST_WORK=%s\n' "$work"
