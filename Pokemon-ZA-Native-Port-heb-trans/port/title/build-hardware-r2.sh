#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=/home/tomer/ps5-za-native/title-r1-20261027
dst=$work/port/sdl3-shim/src/sdl3_ps5_video.c
[[ -f $work/SNAPSHOT-COMPLETE && -f $dst ]]
# Preserve the original snapshot file; the published r1 package stays intact.
[[ -f $dst.before-r2 ]] || cp "$dst" "$dst.before-r2"
cp "$root/port/sdl3-shim/src/sdl3_ps5_video.c" "$dst"
sha256sum "$dst.before-r2" "$dst" "$root/port/title/title_entry.c" > "$work/evidence/hardware-r2-source-sha256.txt"
bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r2-hardware" bash "$root/port/title/package-title.sh"
python3 - "$root/artifacts/title-r2-hardware/PPSA91761/sce_sys/param.json" <<'PY'
import json,sys
p=json.load(open(sys.argv[1]))
p['localizedParameters']['en-US']['titleName']='ZA Native Title R2 (Test)'
with open(sys.argv[1],'w') as f:json.dump(p,f,indent=2)
PY
printf '%s\n' 'R2 hardware test overlay. Game assets come unchanged from the verified r1 package.' > "$root/artifacts/title-r2-hardware/README.txt"
