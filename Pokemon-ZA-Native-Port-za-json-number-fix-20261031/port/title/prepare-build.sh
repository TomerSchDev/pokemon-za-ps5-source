#!/usr/bin/env bash
# Isolated, offline title build. Does not access or deploy to the PS5.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
source_tree=${POKEZA_RECOMP:-$(dirname "$root")/pokeza-recomp-ps5}
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
mkdir -p "$work"
if [[ ! -f $work/SNAPSHOT-COMPLETE ]]; then
    [[ ! -d $work/source ]] || { echo 'Incomplete existing snapshot; inspect before reusing' >&2; exit 2; }
    mkdir -p "$work/source" "$work/port" "$work/evidence"
    git -C "$source_tree" rev-parse HEAD > "$work/evidence/source-head.txt"
    git -C "$source_tree" status --short > "$work/evidence/source-status.txt"
    git -C "$source_tree" diff --binary > "$work/evidence/source-uncommitted.patch"
    rsync -a --exclude=.git --exclude=build --exclude=tools/venv "$source_tree/" "$work/source/"
    rsync -a "$root/port/" "$work/port/"
    (cd "$work/source" && find runtime tools -type f -print0 | sort -z | xargs -0 sha256sum) > "$work/evidence/source-sha256.txt"
    date -u +%FT%TZ > "$work/SNAPSHOT-COMPLETE"
fi
cd "$work/source"
exec make PLATFORM=ps5 -j"${JOBS:-12}" ps5-gamelib
