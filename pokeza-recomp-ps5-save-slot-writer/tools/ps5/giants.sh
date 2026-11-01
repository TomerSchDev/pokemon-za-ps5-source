#!/usr/bin/env bash
# ZA Recomp -> PS5: which generated units compile at -O0 - the PC build's giant-function policy (runtime/gamebuild.c,
# cold_giant), applied to a generated set as a make fragment the Makefile includes (PLATFORM=ps5).
#
# The rule, read from gamebuild.c itself so the two cannot drift: a unit that defines exactly one function
# ("void f_<addr>(Cpu *c) {") with more than GIANT_INSNS labels ("L_<addr>:;" lines) is a giant - clang -O1 takes
# minutes on some (2.0.2's main_655.c: 631 s at -O1, 1.3 s at -O0; 166 such units were half the PC build's time) -
# unless its function is in HOT_GIANTS (runs every frame: stays at -O1). LARECOMP_GAMEBUILD_GIANT=<labels> overrides
# the threshold as there (0: no giants). The 2.0.2 set built on the PC (aot/build-result.json: 160 of 1,412 at -O0,
# giant_policy_revision 4d82d89) is the reference this must reproduce.
#
# Usage: tools/ps5/giants.sh <aot dir> <out.mk>        (the Makefile runs it; JOBS parallel readers, default nproc)
# Writes <out.mk>: GIANTS := <unit stems relative to the aot dir, without .c>, the counts in comments. Each unit is
# read once, a multi-function unit only up to its second definition (the files are read where they are: over 9p from
# /mnt/c that is the cost - about a minute for 2.0.2's 1 GB).
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
[[ $# -eq 2 ]] || { echo "usage: $0 <aot dir> <out.mk>" >&2; exit 2; }
aot=${1%/}
out=$2
gb=$root/runtime/gamebuild.c
JOBS=${JOBS:-$(nproc)}
[[ -d $aot/main || -d $aot/sdk ]] || { echo "$0: no main/ or sdk/ under $aot" >&2; exit 2; }
limit=$(sed -n 's/^#define GIANT_INSNS \([0-9][0-9]*\).*/\1/p' "$gb")
[[ -n $limit ]] || { echo "$0: no GIANT_INSNS in $gb" >&2; exit 2; }
if [[ -n ${LARECOMP_GAMEBUILD_GIANT:-} ]]; then limit=$LARECOMP_GAMEBUILD_GIANT; fi
hot=$(sed -n '/^static const char \*const HOT_GIANTS\[\] = {/,/^};/p' "$gb" | grep -oE '"f_[0-9a-f]+"' | tr -d '"' | tr '\n' ' ')
[[ -n $hot ]] || { echo "$0: no HOT_GIANTS in $gb" >&2; exit 2; }
awk=$(command -v gawk || command -v awk)
mkdir -p "$(dirname "$out")"
tmp=$(mktemp "${TMPDIR:-/tmp}/giants.XXXXXX")
prog=$(mktemp "${TMPDIR:-/tmp}/giants-awk.XXXXXX")
trap 'rm -f "$tmp" "$prog"' EXIT
# per unit: "<kind>\t<stem>\t<labels>\t<function>" for every one-function unit over the threshold (kind: giant, or hot)
cat > "$prog" <<'AWK'
function report(   stem) {
    if (defs != 1 || labels <= limit || prev == "") return
    stem = prev
    if (index(stem, aot "/") == 1) stem = substr(stem, length(aot) + 2)
    sub(/\.c$/, "", stem)
    printf "%s\t%s\t%d\t%s\n", (name in hot) ? "hot" : "giant", stem, labels, name
}
BEGIN { n = split(hotlist, h, " "); for (i = 1; i <= n; i++) if (h[i] != "") hot[h[i]] = 1 }
FNR == 1 { report(); prev = FILENAME; defs = 0; labels = 0; name = "" }
/^L_/ { labels++; next }
/^void f_/ {
    if (index($0, "(Cpu *c) {") == 0) next   # (a prototype)
    if (++defs > 1) nextfile                 # several functions: never a giant, the rest unread
    name = substr($0, 6)
    sub(/\(.*$/, "", name)
}
END { report() }
AWK
if (( limit > 0 )); then
    find "$aot/main" "$aot/sdk" -maxdepth 1 -name '*.c' -print0 2>/dev/null | sort -z |
        xargs -0 -r -P "$JOBS" -n 24 "$awk" -v limit="$limit" -v hotlist="$hot" -v aot="$aot" -f "$prog" > "$tmp"
fi
units=$(find "$aot/main" "$aot/sdk" -maxdepth 1 -name '*.c' 2>/dev/null | wc -l)
giants=$(awk -F'\t' '$1 == "giant"' "$tmp" | sort -k2,2 | wc -l)
hots=$(awk -F'\t' '$1 == "hot"' "$tmp" | wc -l)
{
    echo "# tools/ps5/giants.sh: the generated units compiled at -O0 (runtime/gamebuild.c's giant policy): one function,"
    echo "# more than $limit labels, not in HOT_GIANTS. $aot: $units units, $giants giants, $hots hot giants kept at GENOPT."
    echo "# Remade when the units, the script or gamebuild.c change (Makefile PLATFORM=ps5)."
    awk -F'\t' '$1 == "hot" { printf "# hot: %s (%s labels, %s)\n", $2, $3, $4 }' "$tmp" | sort
    printf 'GIANTS_AOT := %s\n' "$aot"
    printf 'GIANTS :='
    awk -F'\t' '$1 == "giant" { print $2 }' "$tmp" | sort | tr '\n' ' ' | sed 's/^/ /; s/ *$//'
    echo
} > "$out.tmp"
mv -f "$out.tmp" "$out"
echo "$out: $units units, $giants at -O0 (${hots} hot giants stay at GENOPT; threshold $limit labels)"
