#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work=${TITLE_WORK:-/home/tomer/ps5-za-native/title-r1-20261027}
python3 "$root/port/title/apply-hardware-r14.py" "$work/source"
TITLE_REV=r14 TITLE_GAMELIB="$work/fps-r13/liblasgame-r13.a" bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r14-hardware" bash "$root/port/title/package-title.sh"
