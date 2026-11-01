#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
python3 - <<'PY'
from pathlib import Path
root = Path('/home/tomer/ps5-za-native/title-r1-20261027/source')
def patch(name, old, new):
    p = root/name; s = p.read_text(); b = p.with_name(p.name+'.before-r7')
    if not b.exists(): b.write_text(s)
    if new not in s:
        assert s.count(old)==1, name
        p.write_text(s.replace(old,new))
patch('runtime/loader.c', '    free(raw);\n    m->base = base;', '''#ifdef ZA_PS5
    if (base == SDK_BASE) {
        unsigned nonzero = 0;
        const volatile uint8_t *zero = (const volatile uint8_t *)(base + seg[2][1] + seg[2][2]);
        for (uint32_t k = 0; k < bss; k++) nonzero += zero[k] != 0;
        LOG("[za-sdk] after load: GOT_b78d38=%llx BSS_nonzero=%u/%u\\n",
            *(unsigned long long *)(base + 0xb78d38), nonzero, bss);
    }
#endif
    free(raw);
    m->base = base;''')
patch('runtime/loader.c', '                *where = s ? s + r[i].addend : 0;', '''                *where = s ? s + r[i].addend : 0;
#ifdef ZA_PS5
                if (m->base == SDK_BASE && r[i].off == 0xb78d38)
                    LOG("[za-sdk] bind GOT_b78d38=%llx symbol=%s\\n", *where, symname(m, sym(m, si)));
#endif''')
patch('runtime/main.c', '    if (m->init) guest_call(c, m->init);', '''#ifdef ZA_PS5
    if (m->base == SDK_BASE)
        LOG("[za-sdk] before init: GOT_b78d38=%llx\\n", *(unsigned long long *)(m->base + 0xb78d38));
#endif
    if (m->init) guest_call(c, m->init);''')
patch('runtime/dispatch.c', '        uint64_t off;\n        const char *s = loader_symbol_at(c->x[30], &off);', '''#ifdef ZA_PS5
        extern int sceKernelDebugOutText(int, const char *);
        char report[320];
        snprintf(report, sizeof report, "[za-dispatch] missing=%llx x16=%llx x17=%llx lr=%llx sp=%llx sdk_GOT=%llx\\n",
                 c->pc, c->x[16], c->x[17], c->x[30], c->sp,
                 *(unsigned long long *)(SDK_BASE + 0xb78d38));
        sceKernelDebugOutText(0, report);
#endif
        uint64_t off;
        const char *s = loader_symbol_at(c->x[30], &off);''')
PY
TITLE_REV=r7 bash "$root/port/title/build-runtime.sh" offline-title
TITLE_DIST="$root/artifacts/title-r7-hardware" bash "$root/port/title/package-title.sh"
