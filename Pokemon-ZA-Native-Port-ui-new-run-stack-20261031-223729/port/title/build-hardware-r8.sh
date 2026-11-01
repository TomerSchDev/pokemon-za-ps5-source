#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 - <<'PY'
from pathlib import Path
p=Path('/home/tomer/ps5-za-native/title-r1-20261027/source/runtime/platform/ps5.c')
s=p.read_text(); b=p.with_name(p.name+'.before-r8')
if not b.exists(): b.write_text(s)
old='        void *want = (void *)(uintptr_t)(l->base + i * CHUNK), *at = want;'
new='''        // Direct allocations are NOT zero-filled (title r7: SDK BSS had
        // 793116 nonzero bytes out of 846624). Clear through a temporary mapping
        // before publishing the guest address, including for concurrent faults.
        // Never clear a chunk already marked backed: it contains live guest data.
        void *clear_at = NULL;
        rc = sceKernelMapDirectMemory(&clear_at, bytes, RW, 0, phys, CHUNK);
        if (rc != 0) {
            LOGP("%s: cannot map fresh memory for clearing: 0x%08x\\n", l->name, (unsigned)rc);
            sceKernelReleaseDirectMemory(phys, bytes);
            return false;
        }
        memset(clear_at, 0, bytes);
        const int clear_unmap_rc = sceKernelMunmap(clear_at, bytes);
        if (clear_unmap_rc != 0) {
            LOGP("%s: cannot unmap cleared staging memory: 0x%08x\\n", l->name, (unsigned)clear_unmap_rc);
            sceKernelReleaseDirectMemory(phys, bytes);
            return false;
        }
        void *want = (void *)(uintptr_t)(l->base + i * CHUNK), *at = want;'''
if new not in s:
    assert s.count(old)==1
    p.write_text(s.replace(old,new))
PY
TITLE_REV=r8 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r8-hardware" bash "$root/port/title/package-title.sh"
