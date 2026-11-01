#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 - <<'PY'
from pathlib import Path
root = Path('/home/tomer/ps5-za-native/title-r1-20261027/source')
def patch(name, old, new):
    p = root/name
    s = p.read_text()
    b = p.with_name(p.name+'.before-r6')
    if not b.exists(): b.write_text(s)
    if new not in s:
        assert s.count(old) == 1, name
        p.write_text(s.replace(old, new))
patch('runtime/platform/ps5.c', 'void plat_stack_free(void *base, size_t size) {', '''// pthread's first instructions need a real stack before thread_main can install
// its per-thread alternate signal stack. Otherwise the initial lazy page fault
// recurses into signal delivery on that same unbacked stack (title r5 hardware).
// Commit only its top 64 KiB; deeper growth still uses the existing lazy handler.
int plat_stack_prepare_thread(void *base, size_t size) {
    const uint64_t start = (uint64_t)(uintptr_t)base;
    if (!in_range(&g_arena, start)) return 1; // mmap fallback is already backed
    const uint64_t top = start + size;
    if (!size || top < start || !in_range(&g_arena, top - 1)) return 0;
    const uint64_t last = (top - 1) & ~(CHUNK - 1);
    lock();
    const bool ok = commit_locked(&g_arena, last, CHUNK);
    unlock();
    return ok;
}

void plat_stack_free(void *base, size_t size) {''')
patch('runtime/platform/ps5_compat.h', 'void plat_stack_free(void *base, size_t size);', '''void plat_stack_free(void *base, size_t size);
int plat_stack_prepare_thread(void *base, size_t size);''')
patch('runtime/kernel.c', '    pthread_attr_setstack(&attr, stack, stack_size);', '''    if (!plat_stack_prepare_thread(stack, stack_size))
        FATAL("[kernel] cannot back initial thread stack page\\n");
    if (pthread_attr_setstack(&attr, stack, stack_size) != 0)
        FATAL("[kernel] pthread_attr_setstack refused host stack\\n");''')
patch('runtime/kernel.c', '    pthread_create(&t->host, &attr, thread_main, t);', '''    const int thread_rc = pthread_create(&t->host, &attr, thread_main, t);
    if (thread_rc != 0) FATAL("[kernel] pthread_create failed: %d\\n", thread_rc);''')
PY
TITLE_REV=r6 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r6-hardware" bash "$root/port/title/package-title.sh"
