#!/usr/bin/env bash
set -euo pipefail
renice 10 -p $$ >/dev/null
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for script in "$here/"*.sh; do bash -n "$script"; done
python3 "$here/prepare-merge-tree.py" \
 --runtime-tree /home/tomer/ps5-za-native/r28a-play-final-20261030 \
 --base-out /home/tomer/ps5-za-native/r28a-play-final-20261030/r28a \
 --archive /home/tomer/ps5-za-native/r28a-play-final-20261030/rando-dexcount/liblasgame-r28-dexcount.a \
 --work /home/tomer/ps5-za-native/r28b-dlc-dex-merge-audit-only \
 --eboot-sha256 5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea \
 --pie-sha256 4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85 \
 --archive-sha256 1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc \
 --audit-only
