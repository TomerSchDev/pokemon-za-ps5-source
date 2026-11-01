"""Audit and patch TWO translated 2.0.2 units for rando-dexopen; never edits its inputs.

The Mega Dimension (Hyperspace) Pokedex list is gated by the save flag FLAG_DLC_DEX_ENABLE (descriptor object at
0x7003e26880 = {hash, name pointer, length 0x13}), which DLC story event data sets. za-atlas (30.10.2026) finds exactly
two translated readers of that descriptor and no writer. Both are patched so the flag counts as set whenever the flag
manager's readiness word is non-zero; the flag itself and the save are never written.

  main_287.c  f_70008d4178  DLC::IsHyperspaceDexEnabled: reads the readiness word *(0x700610df00+0x200) -> w20, then
                            the flag via f_700000421c(descriptor) + f_70000393b8(flagmgr, &key) -> w19, releases the
                            key's refcounted holder, and returns w8 & w19 (w8 = readiness != 0). The final AND is
                            replaced by za_dexopen_hyperspace_dex_enabled(w8, w19) (= w8 when the switch is on).
                            The getter call and the refcount release are untouched. 14 callers, all Pokedex UI.
  main_115.c  f_700033f8d8  Pokedex::GetMegaDexCount: the same readiness/getter pattern; the getter's result w22 is
                            ANDed with the readiness bit and stored at sp+0x1c as the "include Hyperspace rows" filter.
                            w22 is passed through za_dexopen_mega_dex_flag(w22) (= 1 when the switch is on) right
                            after it is captured. 3 callers (counter telemetry, two Pokedex UI units).
Both helpers live in za_dexopen.c with one switch (default on). Nothing writes game data, flags or the save.

usage: prepare-dexopen-hooks.py AOT_MAIN_DIR GAME_NSO OUT_DIR
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

BUILD_ID = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
FUNC_RE = re.compile(r'^void (f_[0-9a-f]+)\(Cpu \*c\) \{$', re.M)
EXTERNS = ['za_dexopen_hyperspace_dex_enabled', 'za_dexopen_mega_dex_flag']

UNITS = [
    dict(name='main_287.c', sha256='1c8e0186dd2b993060f63d1e381f9765fed756d0e0f71031007c6a2f91e7f442',
         function='f_70008d4178', extern='za_dexopen_hyperspace_dex_enabled',
         must_contain=[
             # the readiness word of the flag manager singleton (0x700610df00 + 0x200) -> w20, checked before the getter
             'c->x[8] = (uint64_t)(0x700610d000ull);\n    c->x[8] = (uint64_t)(c->x[8] + 0xf00ull);\n',
             '{ uint64_t ea = c->x[8] + 0x200ull; uint64_t v = LD32(ea); c->x[20] = (uint64_t)(v); }',
             'if ((uint32_t)c->x[20] == 0) { goto L_70008d4238; }',
             # the FLAG_DLC_DEX_ENABLE descriptor (0x7003e26880), the key maker, the flag manager (GOT 0x7003ec3328), the getter
             'c->x[0] = (uint64_t)(0x7003e26000ull);\n    c->x[0] = (uint64_t)(c->x[0] + 0x880ull);\n',
             'c->x[30] = 0x70008d41acull; f_700000421c(c);',
             '{ uint64_t ea = c->x[0] + 0x328ull; uint64_t v = LD64(ea); c->x[0] = (uint64_t)(v); }',
             'c->x[30] = 0x70008d41bcull; f_70000393b8(c);\n    c->x[19] = (uint32_t)(0u | (uint32_t)c->x[0]);\n',
             # the release of the key's refcounted holder, untouched
             'c->x[30] = 0x70008d4234ull; f_7000095a40(c);',
             # the return site: w8 = readiness != 0
             'L_70008d41c8:;\n    (void)(subs32(c, (uint32_t)c->x[20], 0x0ull));\n',
         ],
         anchor=(
             '    c->x[8] = (uint32_t)((COND_EQ(c)) ? 0u : (uint32_t)(0u + 1));\n'
             '    c->x[0] = (uint32_t)((uint32_t)c->x[8] & (uint32_t)c->x[19]);\n'
             '    { uint64_t ea = c->sp + 48; uint64_t a = LD64(ea), b = LD64(ea + 8); c->x[20] = (uint64_t)(a); c->x[19] = (uint64_t)(b); }\n'),
         replacement=(
             '    c->x[8] = (uint32_t)((COND_EQ(c)) ? 0u : (uint32_t)(0u + 1));\n'
             '    /* rando-dexopen: DLC::IsHyperspaceDexEnabled = readiness (w8); FLAG_DLC_DEX_ENABLE (w19) not required */\n'
             '    { extern uint32_t za_dexopen_hyperspace_dex_enabled(uint32_t, uint32_t);\n'
             '      c->x[0] = (uint64_t)za_dexopen_hyperspace_dex_enabled((uint32_t)c->x[8], (uint32_t)c->x[19]); }\n'
             '    { uint64_t ea = c->sp + 48; uint64_t a = LD64(ea), b = LD64(ea + 8); c->x[20] = (uint64_t)(a); c->x[19] = (uint64_t)(b); }\n')),
    dict(name='main_115.c', sha256='598e9785c9ff3f64a426049eecef964083f0bf989f51361d1deaf63e82adaba6',
         function='f_700033f8d8', extern='za_dexopen_mega_dex_flag',
         must_contain=[
             # readiness word of the flag manager (GOT 0x7003ec3328 -> +0x200) -> w19; no getter when it is 0
             '{ uint64_t ea = c->x[8] + 0x200ull; uint64_t v = LD32(ea); c->x[19] = (uint64_t)(v); }',
             'if ((uint32_t)c->x[19] == 0) { goto L_700033fe04; }',
             'L_700033fe04:;\n    goto L_700033f954;\n',
             # the same descriptor, key maker and getter
             'c->x[0] = (uint64_t)(0x7003e26000ull);\n    c->x[0] = (uint64_t)(c->x[0] + 0x880ull);\n',
             'c->x[30] = 0x700033f938ull; f_700000421c(c);',
             # the filter: w8 = (w19 != 0) & w22, stored at sp+0x1c; w22 is then reused (0x198) - the flag's life ends here
             'L_700033f954:;\n',
             '(void)(subs32(c, (uint32_t)c->x[19], 0x0ull));\n    c->x[8] = (uint32_t)((COND_EQ(c)) ? 0u : (uint32_t)(0u + 1));\n',
             'c->x[8] = (uint32_t)((uint32_t)c->x[8] & (uint32_t)c->x[22]);',
             '{ uint64_t ea = c->sp + 0x1cull; ST32(ea, (uint32_t)c->x[8]); }',
             'c->x[22] = (uint32_t)(0x198ull);',
             # the refcount release of the key holder, untouched
             'c->x[30] = 0x700033fd18ull; f_7000095a40(c);',
         ],
         anchor=(
             '    c->x[30] = 0x700033f948ull; f_70000393b8(c);\n'
             '    c->x[22] = (uint32_t)(0u | (uint32_t)c->x[0]);\n'),
         replacement=(
             '    c->x[30] = 0x700033f948ull; f_70000393b8(c);\n'
             '    c->x[22] = (uint32_t)(0u | (uint32_t)c->x[0]);\n'
             '    /* rando-dexopen: Pokedex::GetMegaDexCount includes the Hyperspace rows (FLAG_DLC_DEX_ENABLE treated as set) */\n'
             '    { extern uint32_t za_dexopen_mega_dex_flag(uint32_t);\n'
             '      c->x[22] = (uint64_t)za_dexopen_mega_dex_flag((uint32_t)c->x[22]); }\n')),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def function_span(text, name):
    starts = [(m.group(1), m.start()) for m in FUNC_RE.finditer(text)]
    for i, (fn, pos) in enumerate(starts):
        if fn == name:
            return pos, starts[i + 1][1] if i + 1 < len(starts) else len(text)
    raise ValueError('function not found: ' + name)


def patch_unit_text(spec, text):
    if text.count(spec['anchor']) != 1:
        raise ValueError('hook anchor is not unique in ' + spec['name'])
    start, end = function_span(text, spec['function'])
    at = text.index(spec['anchor'])
    if not start < at < end:
        raise ValueError('hook anchor is outside ' + spec['function'])
    body = text[start:end]
    if 'L_dispatch' in body:
        raise ValueError(spec['function'] + ' has an indirect-dispatch section; inline patch not allowed')
    if 'za_' in body:
        raise ValueError(spec['function'] + ' already carries a za_ hook')
    for needle in spec['must_contain']:
        if body.count(needle) != 1:
            raise ValueError(spec['function'] + ' no longer matches the audited code: ' + needle)
    return text.replace(spec['anchor'], spec['replacement'])


def prepare(source, nso, out):
    source, nso, out = Path(source), Path(nso), Path(out)
    raw = nso.read_bytes()
    if raw[:4] != b'NSO0' or raw[0x40:0x60].rstrip(b'\0').hex() != BUILD_ID:
        raise ValueError('unapproved game NSO/build ID')
    prepared = []
    for spec in UNITS:  # validate and prepare everything before any write
        data = (source / spec['name']).read_bytes()
        if sha(data) != spec['sha256']:
            raise ValueError('unapproved source SHA-256: ' + spec['name'])
        # CRLF normalised to LF after the raw hash check, as port/rando-dexcount/prepare-dexcount-hooks.py does
        encoded = patch_unit_text(spec, data.decode('utf-8').replace('\r\n', '\n')).encode('utf-8')
        target = out / spec['name']
        if target.resolve() == (source / spec['name']).resolve():
            raise ValueError('output aliases source')
        if target.exists() and target.read_bytes() != encoded:
            raise ValueError('refusing to overwrite: ' + str(target))
        prepared.append((spec, data, encoded))
    report = dict(build_id=BUILD_ID, console_tested=False, baseline_unchanged=True, externs=EXTERNS,
                  units=[dict(name=s['name'], function=s['function'], new_import=s['extern'],
                              original_sha256=sha(d), patched_sha256=sha(e)) for s, d, e in prepared])
    out.mkdir(parents=True, exist_ok=True)
    for spec, _, encoded in prepared:
        if not (out / spec['name']).exists():
            (out / spec['name']).write_bytes(encoded)
    (out / 'dexopen-hook-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('source', type=Path)
    p.add_argument('nso', type=Path)
    p.add_argument('out', type=Path)
    a = p.parse_args()
    print(json.dumps(prepare(a.source, a.nso, a.out), indent=2))
