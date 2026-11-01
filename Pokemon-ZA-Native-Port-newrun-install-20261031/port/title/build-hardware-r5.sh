#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
names='getcwd fopen freopen open opendir realpath unlink remove rmdir stat lstat mkdir chmod access rename'
wrap=()
for name in $names; do wrap+=("-Wl,--wrap=$name"); done
clang-21 -std=c11 -O2 -Wall -Wextra -Werror "$root/port/title/title_fs.c" \
    "$root/port/title/test-title-fs.c" "${wrap[@]}" -o /tmp/za-test-title-fs
/tmp/za-test-title-fs | tee "$root/evidence/title-r5-host-fs.txt"
python3 - <<'PY'
from pathlib import Path
root = Path('/home/tomer/ps5-za-native/title-r1-20261027/source')
p = root/'runtime/paths.c'
s = p.read_text()
backup = p.with_name(p.name+'.before-r5')
if not backup.exists(): backup.write_text(s)
old = '    const int root_chdir_rc = chdir(root);'
new = '    extern int za_title_fs_set_root(const char *);\n    const int root_chdir_rc = za_title_fs_set_root(root);'
if new not in s:
    assert s.count(old) == 1
    s = s.replace(old, new).replace(' chdir=%d errno=%d', ' virtual_root=%d errno=%d')
    p.write_text(s)
p = root/'tools/ps5/link-title.sh'
s = p.read_text()
backup = p.with_name(p.name+'.before-r5')
if not backup.exists(): backup.write_text(s)
old = '# shellcheck disable=SC2206'
new = '''# Native titles refuse chdir; the title_fs wrappers resolve relative paths.
for name in getcwd fopen freopen open opendir realpath unlink remove rmdir stat lstat mkdir chmod access rename; do
    radv_link_flags+=("--wrap=$name")
done
# shellcheck disable=SC2206'''
if new not in s:
    assert s.count(old) == 1
    s = s.replace(old, new)
visibility = '''printf '{ local: __wrap_*; za_title_fs_set_root; };\\n' > "$work/title-fs-symbols.map"
radv_link_flags+=(--version-script "$work/title-fs-symbols.map")
'''
if visibility not in s:
    s = s.replace('# shellcheck disable=SC2206', visibility + '# shellcheck disable=SC2206')
p.write_text(s)
PY
TITLE_REV=r5 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r5-hardware" bash "$root/port/title/package-title.sh"
