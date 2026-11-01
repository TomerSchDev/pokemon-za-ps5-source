#!/usr/bin/env bash
# Copies the FINAL r28a build's small evidence files (no binaries) from its WSL work tree into evidence/r28a-texfix/<name>/.
# Usage (WSL): collect-final-evidence.sh <final work tree> <name>
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
project=$(cd "$root/../.." && pwd)
work=${1:?final work tree}
dest=$project/evidence/r28a-texfix/${2:?name}
[[ ! -e $dest ]] || { echo "exists: $dest" >&2; exit 2; }
mkdir -p "$dest"
e=$work/r28a/evidence
for f in build.log inputs.json final-inputs.json image-checks.json final-image.json imports.json registration.json \
         image-preservation.json self-inspection.txt self-inspection-vs-candidate.diff SHA256SUMS.txt link-inputs.txt \
         runtime-inputs.txt source-SHA256SUMS.txt dexcount-sources.sha256 dexcount-HANDOFF.json dexcount-checks.json \
         dexcount-r28a-manifest.json candidate-SHA256SUMS.txt candidate-r28-SHA256SUMS.txt candidate-control.txt \
         candidate-inputs.json candidate-image-checks.json candidate-runtime-texfix.patch; do
    [[ -f $e/$f ]] && cp "$e/$f" "$dest/" || echo "note: no $f"
done
[[ -d $e/dexcount ]] && cp -r "$e/dexcount" "$dest/dexcount"
(cd "$dest" && find . -type f ! -name MANIFEST.sha256 | sort | xargs sha256sum > MANIFEST.sha256)
echo "copied to $dest"
