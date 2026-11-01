#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 - <<'PY'
from pathlib import Path
p=Path('/home/tomer/ps5-za-native/title-r1-20261027/source/runtime/services/time.c')
s=p.read_text(); b=p.with_name(p.name+'.before-r10')
if not b.exists(): b.write_text(s)
changes=[
('    struct tm tm;\n    if (utc) gmtime_r(&tt, &tm); else localtime_r(&tt, &tm);',
 '''    struct tm tm = {0};
    if (!(utc ? gmtime_r(&tt, &tm) : localtime_r(&tt, &tm)))
        FATAL("host could not convert calendar timestamp %lld\\n", (long long)t);'''),
('    memcpy(o + 16, utc ? "UTC" : tm.tm_zone, 4);',
 '''    // PS5 libc can return valid fields with tm_zone == NULL (title r9).
    // Preserve the numerical UTC offset; an absent label is not a failed date.
    const char *zone = utc ? "UTC" : tm.tm_zone;
    if (!zone || !*zone) zone = "LCL";
    memset(o + 16, 0, 8);
    snprintf((char *)o + 16, 8, "%s", zone);''')]
for old,new in changes:
    if new not in s:
        assert s.count(old)==1
        s=s.replace(old,new)
p.write_text(s)
PY
TITLE_REV=r10 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r10-hardware" bash "$root/port/title/package-title.sh"
