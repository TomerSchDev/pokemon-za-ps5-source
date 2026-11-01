#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
TITLE_REV=r12 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r12-hardware" bash "$root/port/title/package-title.sh"
