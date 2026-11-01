#!/usr/bin/env bash
# relink-game-dll.sh - lasgame-uiv2.dll: the reference PC game code (the 2.0.2 AOT objects) with the r28 hook units,
# linked against lasrecomp-uiv2.exe's import library so that the DLL IMPORTS the cheat helpers (za_items_pump,
# za_items_reset, za_cheat_money_component, za_money_lifecycle_reset, za_items_pc_batch, za_money_pc_start) from the exe
# instead of carrying them (the r28 proof's pc-build-05 had za_items.o / za_money.o / pc_command.o inside the DLL).
#
#   relink-game-dll.sh verify-aot      compare the local AOT object copy with the NAS reference (count, bytes, a few sha256)
#   relink-game-dll.sh link            write objects.rsp (local paths, helper objects dropped) and link $OUT/lasgame-uiv2.dll
#   relink-game-dll.sh all             both
#   relink-game-dll.sh symbols         report the distinct non-game symbols every AOT object imports (what the exe must export)
#
# Inputs (read-only): the AOT objects copied once from the NAS (ZA_WORK/aot-obj), the reference objects.rsp (ZA_WORK/dll),
# the audited hook objects of port/cheats-r28/work/pc-build-05/obj (main_097 main_220 main_339 main_333 main_303 main_315
# main_384 main_1035 gamelib_entry, built against aot/source/runtime with -O1 -DGUEST_VOLATILE ... -DZA_ITEMS_TRACE=1,
# see its build-result.json) and pc_compat.o (__imp__setjmp -> __intrinsic_setjmp for Zig's retained objects).
# Environment: ZA_PORT, ZA_WORK, OUT as in build-pc-runtime.sh; AOT_NAS [the NAS update-2.0.2-20261025 folder];
#   HOOKS_SRC [port/cheats-r28/work/pc-build-05/obj]; GAMELIB_ID [7b03da558e0b6144].
set -euo pipefail
export PATH="/c/msys64/ucrt64/bin:/c/msys64/usr/bin:$PATH"

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ZA_PORT="${ZA_PORT:-$(cd "$HERE/../../.." && pwd)}"
BASE="$(dirname "$ZA_PORT")"
ZA_WORK="${ZA_WORK:-$BASE/ui-v2-work/pc}"
OUT="${OUT:-$ZA_WORK/out}"
GAMELIB_ID="${GAMELIB_ID:-7b03da558e0b6144}"
AOT_NAS="${AOT_NAS:-//TheOnePiece/Software/Pokemon-ZA-All-Models/Workstation-Data-20261030-v1/Research/pokeza-pc/update-2.0.2-20261025}"
HOOKS_SRC="${HOOKS_SRC:-$ZA_PORT/port/cheats-r28/work/pc-build-05/obj}"
AOT_OBJ="$ZA_WORK/aot-obj"
DLL="$ZA_WORK/dll"
LOGS="$ZA_WORK/logs"
EXE_NAME="lasrecomp-uiv2.exe"
DLL_NAME="lasgame-uiv2.dll"
HOOK_STEMS=(gamelib_entry main_097 main_220 main_339 main_333 main_303 main_315 main_384 main_1035)
DROPPED=(za_items za_money pc_command)   # live in the exe now (build-pc-runtime.sh: the cheat helpers); pc_command is PC-diagnostic only
KEPT_EXTRA=(pc_compat)

say() { printf '==> %s\n' "$*"; }
die() { printf 'relink-game-dll: %s\n' "$*" >&2; exit 1; }
sha() { sha256sum "$1" | cut -c1-64; }

verify_aot() {
    [ -d "$AOT_OBJ" ] || die "no local AOT object copy: $AOT_OBJ (copy $AOT_NAS/aot/obj there first)"
    mkdir -p "$LOGS"
    local n_local n_nas b_local b_nas rep="$DLL/aot-verify.txt"
    n_local=$(ls "$AOT_OBJ" | grep -c '\.o$'); n_nas=$(ls "$AOT_NAS/aot/obj" | grep -c '\.o$')
    b_local=$(cd "$AOT_OBJ" && stat -c %s *.o | awk '{s+=$1} END{print s}'); b_nas=$(cd "$AOT_NAS/aot/obj" && stat -c %s *.o | awk '{s+=$1} END{print s}')
    { echo "verified: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "nas: $AOT_NAS/aot/obj  objects=$n_nas bytes=$b_nas";
      echo "local: $AOT_OBJ  objects=$n_local bytes=$b_local"; } | tee "$rep"
    [ "$n_local" = "$n_nas" ] && [ "$b_local" = "$b_nas" ] || die "AOT copy differs from the NAS (count / bytes)"
    local f ok=0 bad=0
    for f in main_table.o sdk_table.o gamelib_entry.o main_000.o main_097.o main_220.o main_700.o main_1035.o sdk_000.o sdk_203.o \
             $(ls "$AOT_OBJ" | grep '\.o$' | awk 'NR % 97 == 0'); do  # (+ every 97th object: 14 more)
        local a b; a=$(sha "$AOT_OBJ/$f"); b=$(sha "$AOT_NAS/aot/obj/$f")
        if [ "$a" = "$b" ]; then ok=$((ok+1)); echo "same $a $f" >> "$rep"; else bad=$((bad+1)); echo "DIFF $f local=$a nas=$b" | tee -a "$rep"; fi
    done
    echo "sha256 checked: $ok same, $bad different" | tee -a "$rep"
    [ "$bad" = 0 ] || die "AOT copy differs from the NAS"
    cmp -s "$DLL/objects.rsp" "$AOT_NAS/aot/objects.rsp" || die "$DLL/objects.rsp is not the NAS objects.rsp"
    echo "objects.rsp: same as the NAS ($(wc -l < "$DLL/objects.rsp") lines)" | tee -a "$rep"
}

symbols() {
    say "distinct non-game undefined symbols across the AOT objects (nm -u; f_<addr> are game functions, left out)"
    ( cd "$AOT_OBJ" && nm -u *.o 2>/dev/null | awk '$1=="U" && $2 !~ /^f_[0-9a-f]+$/ {print $2}' | sort | uniq -c | sort -rn ) | tee "$DLL/aot-undefined-symbols.txt"
}

link_dll() {
    [ -f "$OUT/lasrecomp.dll.a" ] || die "no import library $OUT/lasrecomp.dll.a (build-pc-runtime.sh first)"
    [ -f "$DLL/objects.rsp" ] || die "no reference objects.rsp in $DLL"
    mkdir -p "$DLL/hooks" "$LOGS"
    local s
    for s in "${HOOK_STEMS[@]}" "${KEPT_EXTRA[@]}"; do
        [ -f "$HOOKS_SRC/$s.o" ] || die "hook object missing: $HOOKS_SRC/$s.o"
        cp -p "$HOOKS_SRC/$s.o" "$DLL/hooks/$s.o"
    done
    ( cd "$DLL/hooks" && sha256sum *.o ) > "$DLL/hooks/SHA256SUMS.txt"
    say "hook objects: ${HOOK_STEMS[*]} + ${KEPT_EXTRA[*]} from $HOOKS_SRC"
    # the reference rsp names the objects at a path that no longer exists: same basenames, local copy; the hook units
    # replaced by the audited r28 objects; za_items / za_money / pc_command NOT appended (they are in the exe)
    local rsp="$DLL/objects-uiv2.rsp" n replaced missing
    # (clang reads the response file itself: Windows-style paths, C:/..., as the reference rsp has - MSYS2's /c/... form is
    # only translated on the command line)
    awk -v aot="$(cygpath -m "$AOT_OBJ")" -v hooks="$(cygpath -m "$DLL/hooks")" -v stems="${HOOK_STEMS[*]}" '
        BEGIN { split(stems, a, " "); for (i in a) hook[a[i] ".o"] = 1 }
        { gsub(/["\r]/, ""); if ($0 == "") next; n = split($0, p, "/"); name = p[n];   # (the reference rsp has CRLF line ends)
          if (name in hook) printf "\"%s/%s\"\n", hooks, name; else printf "\"%s/%s\"\n", aot, name }' "$DLL/objects.rsp" > "$rsp"
    for s in "${KEPT_EXTRA[@]}"; do echo "\"$(cygpath -m "$DLL/hooks")/$s.o\"" >> "$rsp"; done
    n=$(wc -l < "$rsp"); replaced=$(grep -c "/hooks/" "$rsp")
    missing=$(tr -d '"' < "$rsp" | while IFS= read -r f; do [ -f "$f" ] || echo "$f"; done)
    [ -z "$missing" ] || { echo "$missing" | sed 's/^/   missing: /'; die "objects missing"; }
    say "objects-uiv2.rsp: $n objects ($((replaced - ${#KEPT_EXTRA[@]})) hook units replaced, + ${KEPT_EXTRA[*]}); dropped: ${DROPPED[*]}"
    local t0=$SECONDS
    say "link: clang++ -shared -fuse-ld=lld -static-libstdc++ -static-libgcc -Wl,--stack,8388608 @objects-uiv2.rsp lasrecomp.dll.a -o $DLL_NAME"
    ( cd "$DLL" && clang++ -shared -fuse-ld=lld -static-libstdc++ -static-libgcc -Wl,--stack,8388608 "@$(cygpath -m "$rsp")" "$(cygpath -m "$OUT/lasrecomp.dll.a")" -o "$(cygpath -m "$OUT/$DLL_NAME")" ) 2>&1 | tee "$LOGS/link-dll.log"
    [ -f "$OUT/$DLL_NAME" ] || die "DLL link failed (see $LOGS/link-dll.log)"
    echo "$GAMELIB_ID" > "$OUT/$DLL_NAME.id"
    say "linked in $((SECONDS - t0)) s: $OUT/$DLL_NAME ($(stat -c %s "$OUT/$DLL_NAME") bytes), id $GAMELIB_ID"
    verify_dll
}

verify_dll() {
    say "verify: $DLL_NAME imports from $EXE_NAME, exports lasgame_tables"
    local imports rep="$DLL/dll-verify.txt" bad=0 s
    # objdump's import rows: "<vma>  <none>  <hint>  <name>" under their "DLL Name:" line
    imports="$(cd "$OUT" && objdump -p "$DLL_NAME" | awk -v exe="$EXE_NAME" '/DLL Name:/{f=($3==exe); next} f && NF>=3 && $1 ~ /^[0-9a-f]+$/ && $NF ~ /^[A-Za-z_]/ {print $NF}' | sort -u)"
    { echo "verified: $(date -u +%Y-%m-%dT%H:%M:%SZ)"; echo "imports from $EXE_NAME ($(echo "$imports" | grep -c .)):"; echo "$imports" | sed 's/^/  /';
      echo "other DLLs imported:"; (cd "$OUT" && objdump -p "$DLL_NAME" | awk '/DLL Name:/{print "  " $3}'); } > "$rep"
    for s in za_items_pump za_items_reset za_items_pc_batch za_cheat_money_component za_money_lifecycle_reset za_money_pc_start rt_dispatch rt_udf fnprof_hit g_fnprof; do
        if echo "$imports" | grep -qx "$s"; then echo "   imports $s from $EXE_NAME"; else echo "   NOT imported from $EXE_NAME: $s"; bad=1; fi
    done
    local exp; exp="$(cd "$OUT" && objdump -p "$DLL_NAME" | awk '/\[Ordinal\/Name Pointer\] Table/{f=1;next} f&&/^\s*\[ *[0-9]+\]/{print $NF}' | tr '\n' ' ')"
    echo "   exports: $exp" | tee -a "$rep"
    echo "$exp" | grep -qw lasgame_tables || bad=1
    { echo "sha256:"; (cd "$OUT" && sha256sum "$DLL_NAME" "$DLL_NAME.id" lasrecomp.dll.a "$EXE_NAME" | sed 's/^/  /'); echo "hooks:"; sed 's/^/  /' "$DLL/hooks/SHA256SUMS.txt"; } | tee -a "$rep"
    [ "$bad" = 0 ] || die "DLL verification failed (see $rep)"
}

case "${1:-}" in
    verify-aot) verify_aot ;;
    symbols) symbols ;;
    link) link_dll ;;
    all) verify_aot; link_dll ;;
    *) sed -n '2,20p' "$0"; exit 2 ;;
esac
