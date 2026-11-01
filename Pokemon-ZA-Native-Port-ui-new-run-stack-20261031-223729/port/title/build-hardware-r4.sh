#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 - <<'PY'
from pathlib import Path
p=Path('/home/tomer/ps5-za-native/title-r1-20261027/source/runtime/paths.c')
s=p.read_text()
b=p.with_name(p.name+'.before-r4')
if not b.exists():b.write_text(s)
old='    if (!is_dir(root) || !writable(root) || chdir(root) != 0) {'
new='''#ifdef ZA_PS5
    errno = 0;
    const bool root_dir_ok = is_dir(root);
    const int root_stat_errno = errno;
    errno = 0;
    const bool root_write_ok = writable(root);
    const int root_write_errno = errno;
    errno = 0;
    const int root_chdir_rc = chdir(root);
    const int root_chdir_errno = errno;
    extern int sceKernelDebugOutText(int, const char *);
    char diagnostic[1400];
    snprintf(diagnostic, sizeof diagnostic, "[za-paths] root=%s dir=%d errno=%d write=%d errno=%d chdir=%d errno=%d\\n",
             root, root_dir_ok, root_stat_errno, root_write_ok, root_write_errno, root_chdir_rc, root_chdir_errno);
    sceKernelDebugOutText(0, diagnostic);
    if (!root_dir_ok || !root_write_ok || root_chdir_rc != 0) {
#else
    if (!is_dir(root) || !writable(root) || chdir(root) != 0) {
#endif'''
if new not in s:
    assert s.count(old)==1
    p.write_text(s.replace(old,new))
PY
TITLE_REV=r4 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r4-hardware" bash "$root/port/title/package-title.sh"
