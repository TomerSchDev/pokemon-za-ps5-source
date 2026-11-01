"""Audit and patch TWO translated 2.0.2 units for rando-dexcount; never edits its inputs.

The game counts "registered species" for main mission 2 ("Register at least five species", step 2_1_50, its two lab
triggers in trigger_main_02) and Mable's 46 "Filling Your Pokedex" research requests with
have_pokemon_encyclopedia_total_condition, and that condition only counts the LUMIOSE list of the Pokedex
(f_700033e770(manager, kind 0, 0)). Species of the Mega Dimension (Hyperspace, kind 1) list never count, although
the game registers them in the same Pokedex save block when they are caught before the DLC.

  main_310.c  f_7000a1158c  evaluator of have_pokemon_encyclopedia_total_condition (its vtable slot +0x78):
                            after the Lumiose count, also asks f_700033e770(manager, 1, 0) and compares the sum.
  main_261.c  f_700082b5c4  current value of a quest item for the mission panels ("Number Registered N/5"):
                            item type 2 (the same condition) shows the same sum. Type 18 (the Hyperspace dex's own
                            have_dimension_encyclopedia_total item) and every other type are unchanged.
Both sums go through za_dexcount.c. Each species is in exactly one of the two lists (232 + 132, disjoint), so a
species counts once. Nothing writes game data or the save; the Pokedex screens and the completion conditions
(complete_pokemon/dimension_encyclopedia, other callers of f_700033e770) are untouched.

usage: prepare-dexcount-hooks.py AOT_MAIN_DIR GAME_NSO OUT_DIR
"""
from pathlib import Path
import argparse
import hashlib
import json
import re

BUILD_ID = 'b1f12fd919eae86ab8a978317677e64bce443d1f'
FUNC_RE = re.compile(r'^void (f_[0-9a-f]+)\(Cpu \*c\) \{$', re.M)
EXTERNS = '{ extern int za_dexcount_extra_enabled(void); extern uint32_t za_dexcount_combine(uint32_t, uint32_t);\n'

UNITS = [
    dict(name='main_310.c', sha256='bac882ee95d59715b476e0b0ae600837a2fa0466f9fdb1647ce15044d8c44214',
         function='f_7000a1158c', allow_dispatch=False,
         must_contain=['c->x[1] = (uint32_t)(0u | 0u);', 'c->x[2] = (uint32_t)(0u | 0u);', 'f_7000a11604(c);',
                       'f_7000a11670(c);', '{ uint64_t ea = c->x[8] + 0x230ull;'],
         anchor=(
             '    c->x[0] = (uint64_t)((COND_EQ(c)) ? 0ull : (uint64_t)(c->x[8]));\n'
             '    c->x[30] = 0x7000a115d8ull; f_700033e770(c);\n'
             '    { uint64_t ea = c->sp + 0xcull; ST32(ea, (uint32_t)c->x[0]); }\n'),
         replacement=(
             '    c->x[0] = (uint64_t)((COND_EQ(c)) ? 0ull : (uint64_t)(c->x[8]));\n'
             '    { uint64_t za_dex_mgr = c->x[0];\n'
             '    c->x[30] = 0x7000a115d8ull; f_700033e770(c);\n'
             '    /* rando-dexcount: have_pokemon_encyclopedia_total_condition also counts the Hyperspace (DLC) dex */\n'
             '    ' + EXTERNS +
             '      if (za_dex_mgr != 0 && za_dexcount_extra_enabled()) {\n'
             '        uint32_t za_dex_lumiose = (uint32_t)c->x[0];\n'
             '        c->x[0] = za_dex_mgr; c->x[1] = 1ull; c->x[2] = 0ull;\n'
             '        c->x[30] = 0x7000a115d8ull; f_700033e770(c);\n'
             '        c->x[0] = (uint64_t)za_dexcount_combine(za_dex_lumiose, (uint32_t)c->x[0]);\n'
             '      } } }\n'
             '    { uint64_t ea = c->sp + 0xcull; ST32(ea, (uint32_t)c->x[0]); }\n')),
    dict(name='main_261.c', sha256='87a899bbdf466ca3d53912af402341b0d6a425b3a77b32f4eb74e472bf84b91d',
         function='f_700082b5c4', allow_dispatch=True,
         must_contain=['{ uint64_t ea = c->x[0] + 0x28ull; uint64_t v = LD32(ea); c->x[8] = (uint64_t)(v); }',
                       'if (COND_EQ(c)) { goto L_700082b700; }', 'c->x[1] = (uint32_t)(0x1ull);',
                       'L_700082b6ac:;\n    goto L_700082b71c;\n', '__attribute__((musttail)) return f_700033e770(c);',
                       'c->x[9] = (uint64_t)(c->x[9] + 0x2e4ull);'],
         anchor=(
             'L_700082b714:;\n'
             '    c->x[0] = (uint64_t)(0x7003ec6000ull);\n'
             'L_700082b718:;\n'
             '    c->x[1] = (uint32_t)(0u | 0u);\n'
             'L_700082b71c:;\n'),
         replacement=(
             'L_700082b714:;\n'
             '    c->x[0] = (uint64_t)(0x7003ec6000ull);\n'
             'L_700082b718:;\n'
             '    c->x[1] = (uint32_t)(0u | 0u);\n'
             '    /* rando-dexcount: quest item type 2 (have_pokemon_encyclopedia_total) shows Lumiose + Hyperspace */\n'
             '    { extern int za_dexcount_extra_enabled(void); extern uint32_t za_dexcount_display(uint32_t, uint32_t);\n'
             '      if (za_dexcount_extra_enabled()) {\n'
             '        uint64_t za_dex_mgr = LD64(c->x[0] + 0x230ull);\n'
             '        c->x[0] = za_dex_mgr; c->x[2] = 0ull;\n'
             '        f_700033e770(c);\n'
             '        uint32_t za_dex_lumiose = (uint32_t)c->x[0];\n'
             '        c->x[0] = za_dex_mgr; c->x[1] = 1ull; c->x[2] = 0ull;\n'
             '        f_700033e770(c);\n'
             '        c->x[0] = (uint64_t)za_dexcount_display(za_dex_lumiose, (uint32_t)c->x[0]);\n'
             '        return;\n'
             '      } }\n'
             'L_700082b71c:;\n')),
]
UNIT = UNITS[0]['name']          # (kept for older callers)
FUNCTION = UNITS[0]['function']


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
    if not spec['allow_dispatch'] and 'L_dispatch' in body:
        raise ValueError(spec['function'] + ' has an indirect-dispatch section; inline patch not allowed')
    for needle in spec['must_contain']:
        if body.count(needle) != 1:
            raise ValueError(spec['function'] + ' no longer matches the audited code: ' + needle)
    return text.replace(spec['anchor'], spec['replacement'])


def patch_text(text):  # main_310.c (used by the host tests)
    return patch_unit_text(UNITS[0], text)


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
        # CRLF normalised to LF after the raw hash check, as port/cheats-r27/prepare-money-hooks.py does
        encoded = patch_unit_text(spec, data.decode('utf-8').replace('\r\n', '\n')).encode('utf-8')
        target = out / spec['name']
        if target.resolve() == (source / spec['name']).resolve():
            raise ValueError('output aliases source')
        if target.exists() and target.read_bytes() != encoded:
            raise ValueError('refusing to overwrite: ' + str(target))
        prepared.append((spec, data, encoded))
    report = dict(build_id=BUILD_ID, console_tested=False, baseline_unchanged=True,
                  externs=['za_dexcount_extra_enabled', 'za_dexcount_combine', 'za_dexcount_display'],
                  units=[dict(name=s['name'], function=s['function'], original_sha256=sha(d), patched_sha256=sha(e))
                         for s, d, e in prepared])
    out.mkdir(parents=True, exist_ok=True)
    for spec, _, encoded in prepared:
        if not (out / spec['name']).exists():
            (out / spec['name']).write_bytes(encoded)
    (out / 'dexcount-hook-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('source', type=Path)
    p.add_argument('nso', type=Path)
    p.add_argument('out', type=Path)
    a = p.parse_args()
    print(json.dumps(prepare(a.source, a.nso, a.out), indent=2))
