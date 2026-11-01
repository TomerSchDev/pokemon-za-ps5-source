#!/usr/bin/env bash
# PS5 objects of the slot.zrs writer against main-1.0.0's frozen runtime objects - compile only, no link, no eboot.
#
#   compile-ps5-objects.sh <new out dir>      (WSL)
#
# Work trees are copies of the r29-ui merge tree's source/runtime (the sources main-1.0.0's runtime objects were built
# from; checked equal to runtime main 1655be8 here) with its include dirs. The compile command is the one that
# reproduces the pinned objects byte for byte (Pokemon-ZA-Native-Port port/ui-v2/tools/compile-runtime-object.sh).
#   control: unchanged units of both trees rebuilt and cmp'd against the frozen objects (stop on any mismatch)
#   changed: services/fs.o (Commit -> save_slot_commit) and the new services/save_slot.o
# Output: <out>/objects/{fs.o,save_slot.o}, <out>/controls/*, SHA256SUMS, nm-fs.diff, build.log.
set -euo pipefail
[[ $# -eq 1 ]] || { echo "usage: $0 <new out dir>" >&2; exit 2; }
out=$1
[[ ! -e $out ]] || { echo "refusing: $out exists (new builds go to a new folder)" >&2; exit 2; }
src=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)    # this runtime worktree
port=${ZA_PORT:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port}
main_src=${ZA_RUNTIME_MAIN:-/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pokeza-recomp-ps5-main}
base=${ZA_BASE_TREE:-/home/tomer/ps5-za-native/r29ui-codex-20261031-final-01/tree}
frozen=${ZA_FROZEN:-/home/tomer/ps5-za-native/za-main-1.0.0-frozen-20261031}
compile=$port/port/ui-v2/tools/compile-runtime-object.sh
nm=${PS5_NM:-/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk/bin/llvm-nm}
for f in "$compile" "$frozen/source/build/ps5/rt/services/fs.o" "$base/source/runtime/services/fs.c" "$nm"; do
    [[ -e $f ]] || { echo "missing $f" >&2; exit 2; }
done
mkdir -p "$out"/{objects,controls}
exec > >(tee "$out/build.log") 2>&1
echo "save-slot-writer PS5 objects: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "runtime worktree: $src ($(git -C "$src" rev-parse HEAD 2>/dev/null || echo ?); dirty: $(git -C "$src" status --porcelain -- runtime | wc -l) paths)"
echo "base tree: $base   frozen: $frozen"

# the base tree's runtime sources are runtime main's (backup files *.before-* aside)
if ! diff -rq -x '*.before-*' "$base/source/runtime" "$main_src/runtime"; then echo "base tree runtime != runtime main" >&2; exit 1; fi
echo "base tree source/runtime == $main_src/runtime (runtime main 1655be8; excluding *.before-* backups)"

for t in control new; do
    mkdir -p "$out/$t/source"
    cp -a --reflink=auto "$base/inc" "$base/port" "$out/$t/"
    cp -a --reflink=auto "$base/source/runtime" "$base/source/third_party" "$out/$t/source/"
done
for f in fs.c save_slot.c save_slot.h za_slot.h; do cp -p "$src/runtime/services/$f" "$out/new/source/runtime/services/$f"; done
echo "new tree: runtime/services/{fs.c,save_slot.c,save_slot.h,za_slot.h} from the worktree"
diff -rq "$out/control/source/runtime" "$out/new/source/runtime" || true

fail=0
control() {  # <tree> <unit>
    local o="$out/controls/$1-$(echo "$2" | tr / _).o" ref="$frozen/source/build/ps5/rt/$2.o"
    bash "$compile" "$out/$1" "$2" "$o"
    if cmp -s "$o" "$ref"; then echo "control $1 $2: identical to frozen ($(sha256sum < "$o" | cut -c1-64))"
    else echo "CONTROL MISMATCH $1 $2: $(sha256sum < "$o" | cut -c1-16) vs frozen $(sha256sum < "$ref" | cut -c1-16)"; fail=1; fi
}
control control services/fs
control control services/time
control control rando
control new rando
control new services/time
[[ $fail == 0 ]] || { echo "controls failed: stop" >&2; exit 1; }

bash "$compile" "$out/new" services/fs "$out/objects/fs.o"
bash "$compile" "$out/new" services/save_slot "$out/objects/save_slot.o"
echo "changed objects:"
(cd "$out/objects" && sha256sum fs.o save_slot.o | tee ../SHA256SUMS)
(cd "$out/controls" && sha256sum *.o | sed 's/  /  controls\//' >> ../SHA256SUMS)
echo "frozen fs.o: $(sha256sum < "$frozen/source/build/ps5/rt/services/fs.o" | cut -c1-64)" | tee -a "$out/SHA256SUMS"

# symbols: fs.o keeps every frozen symbol; save_slot.o's undefined symbols are what the link must provide
"$nm" "$frozen/source/build/ps5/rt/services/fs.o" | awk '{print $NF" "$(NF-1)}' | sort > "$out/nm-fs-frozen.txt"
"$nm" "$out/objects/fs.o" | awk '{print $NF" "$(NF-1)}' | sort > "$out/nm-fs-new.txt"
diff "$out/nm-fs-frozen.txt" "$out/nm-fs-new.txt" > "$out/nm-fs.diff" || true
echo "fs.o symbol diff (frozen -> new):"; cat "$out/nm-fs.diff"
# (local .L.str.N / reset_entry_N / svc_def_N renumber with the line numbers: only the global symbols must all stay)
"$nm" --extern-only --defined-only "$frozen/source/build/ps5/rt/services/fs.o" | awk '{print $NF}' | sort > "$out/nm-fs-frozen-global.txt"
"$nm" --extern-only --defined-only "$out/objects/fs.o" | awk '{print $NF}' | sort > "$out/nm-fs-new-global.txt"
lost=$(comm -23 "$out/nm-fs-frozen-global.txt" "$out/nm-fs-new-global.txt" | wc -l)
echo "fs.o global defined symbols: frozen $(wc -l < "$out/nm-fs-frozen-global.txt"), new $(wc -l < "$out/nm-fs-new-global.txt"), lost $lost"
[[ $lost == 0 ]] || { echo "fs.o lost $lost frozen global symbols" >&2; exit 1; }
"$nm" "$out/objects/save_slot.o" > "$out/nm-save_slot.txt"
echo "save_slot.o defined: $(awk '$2 ~ /^[TDBR]$/ {print $3}' "$out/nm-save_slot.txt" | tr '\n' ' ')"
echo "save_slot.o undefined: $(awk '$1 == "U" {print $2}' "$out/nm-save_slot.txt" | tr '\n' ' ')"
echo "done: $out"
