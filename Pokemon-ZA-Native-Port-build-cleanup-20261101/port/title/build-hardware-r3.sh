#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 "$root/port/title/apply-hardware-r3.py"
bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r3-hardware" bash "$root/port/title/package-title.sh"
