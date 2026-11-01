#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work_tree=${1:?work tree required}
for script in "$here/"*.sh; do bash -n "$script"; done
python3 "$here/summarize-build.py" "$work_tree"
sha256sum "$work_tree/r28b/feature-src/prepare_dlc_dex_hook.py" "$work_tree/r28b/feature-src/za_dlc_dex_unlock.c"
df -h /mnt/c
echo 'Offline build audit completed; no console access and no save file access.'
