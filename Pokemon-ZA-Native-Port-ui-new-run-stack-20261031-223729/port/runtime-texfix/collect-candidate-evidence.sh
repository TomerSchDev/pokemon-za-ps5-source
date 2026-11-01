#!/usr/bin/env bash
# Copies a texfix build's small evidence files (no binaries) from its WSL work tree into the repository's evidence/.
# Usage (WSL): collect-candidate-evidence.sh <work tree> <evidence dir name under evidence/r28a-texfix/>
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=${1:?work tree}
dest=$project/evidence/r28a-texfix/${2:?name}
[[ ! -e $dest ]] || { echo "exists: $dest" >&2; exit 2; }
mkdir -p "$dest"
e=$work/r28a/evidence
for f in build.log control.txt apply.txt runtime-texfix.patch patched-objects.sha256 inputs.json image-checks.json \
         imports.json registration.json image-preservation.json self-inspection.txt self-inspection-vs-r28.diff \
         SHA256SUMS.txt link-inputs.txt runtime-inputs.txt source-SHA256SUMS.txt r28-SHA256SUMS.txt; do
    cp "$e/$f" "$dest/"
done
(cd "$dest" && sha256sum * > MANIFEST.sha256)
echo "copied to $dest"
