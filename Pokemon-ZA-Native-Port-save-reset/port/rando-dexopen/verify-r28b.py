"""r28b-play checks against r28a-play's final tree (build-r28b.sh calls each mode at its step).

    verify-r28b.py base    <r28a final tree> <r28b tree> <evidence dir>
    verify-r28b.py dexopen <dexopen out dir> <base archive (r28a's dexcount archive)> <evidence dir> <r28a llvm-pie.elf>
    verify-r28b.py inputs  <r28a final tree> <r28b tree> <dexopen out dir> <evidence dir>
    verify-r28b.py image   <r28a llvm-pie.elf> <r28b llvm-pie.elf> <evidence dir>
    verify-r28b.py repro   <SHA256SUMS.txt of build 1> <SHA256SUMS.txt of build 2> <evidence dir>

base:    the copied inputs are r28a's own files byte for byte: the 64 runtime objects of r28a's runtime list, the title
         objects, the dexcount archive (1f0c586e...) and za_dexcount.o (207e7a1a...).
dexopen: the apply script's outputs match its manifest: exactly main_287.o and main_115.o changed in the archive, same
         member order; za_dexopen.o defines the two entry points and imports only symbols r28a's PIE already defines
         or imports (no new dynamic import); the patched members import only those entry points beyond the originals.
inputs:  the link line is r28a's (objects folders renamed) plus za_dexopen.o appended; every runtime and title object
         and za_dexcount.o identical to r28a's; the game archive is the dexopen archive.
image:   dynamic imports identical to r28a's (hence r28-play's); no global of r28a lost; the globals added are
         za_dexopen's only; the dexopen calls are linked (f_70008d4178 -> za_dexopen_hyperspace_dex_enabled,
         f_700033f8d8 -> za_dexopen_mega_dex_flag), the dexcount calls still are, the [dexopen] klog strings exist.
repro:   two builds from the same inputs gave the same eboot.bin and PIE.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

NM = '/usr/lib/llvm-21/bin/llvm-nm'
OBJDUMP = '/usr/lib/llvm-21/bin/llvm-objdump'
AR = '/usr/lib/llvm-21/bin/llvm-ar'
DEXCOUNT_ARCHIVE_SHA = '1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc'
DEXCOUNT_OBJECT_SHA = '207e7a1ad5d8f26a8d95673b7d6414df6af99f36201168c412a5c4df9b9ce06f'
UNITS = ['main_115.o', 'main_287.o']
ENTRY_POINTS = {'za_dexopen_hyperspace_dex_enabled', 'za_dexopen_mega_dex_flag'}
ALL_DEXOPEN_GLOBALS = ENTRY_POINTS | {'za_dexopen_enabled', 'za_dexopen_set_enabled', 'za_dexopen_calls', 'za_dexopen_forced',
                                      'za_dexopen_last_flag', 'za_dexopen_trace_lines'}
DEXOPEN_CALLS = [('f_70008d4178', 'za_dexopen_hyperspace_dex_enabled'), ('f_700033f8d8', 'za_dexopen_mega_dex_flag')]
DEXCOUNT_CALLS = [('f_7000a1158c', 'za_dexcount_extra_enabled'), ('f_7000a1158c', 'za_dexcount_combine'),
                  ('f_700082b5c4', 'za_dexcount_extra_enabled'), ('f_700082b5c4', 'za_dexcount_display')]
KLOG_STRINGS = ['[dexopen] %s: FLAG_DLC_DEX_ENABLE=%u -> %u%s (call %llu)',
                '[dexopen] %s: flag manager not ready, FLAG_DLC_DEX_ENABLE not read -> %u (call %llu)',
                'DLC::IsHyperspaceDexEnabled (f_70008d4178)', 'Pokedex::GetMegaDexCount (f_700033f8d8)',
                ' (forced: Hyperspace Pokedex list open)']


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise SystemExit('FAILED: ' + message)


def out(cmd):
    return subprocess.check_output([str(c) for c in cmd], text=True)


def r27():
    spec = importlib.util.spec_from_file_location('r27', Path(__file__).resolve().parents[1] / 'perf-r27/verify-r27-build.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def base(r28a, work, evidence):
    r28a, work, evidence = Path(r28a), Path(work), Path(evidence)
    rel = (r28a / 'r28a/evidence/runtime-inputs.txt').read_text().split()
    runtime = [dict(input=r, sha256=sha(r28a / 'source' / r), identical=sha(r28a / 'source' / r) == sha(work / 'source' / r)) for r in rel]
    require(all(e['identical'] for e in runtime), 'a copied runtime object differs from r28a: %s' % [e['input'] for e in runtime if not e['identical']])
    titles = []
    for p in sorted((r28a / 'r28a/objects').glob('*.o')):
        titles.append(dict(object=p.name, sha256=sha(p), identical=sha(p) == sha(work / 'r28b/objects' / p.name)))
    require(titles and all(t['identical'] for t in titles), 'a copied title object differs from r28a')
    arc = work / 'rando-dexcount/liblasgame-r28-dexcount.a'
    obj = work / 'rando-dexcount/za_dexcount.o'
    require(sha(arc) == DEXCOUNT_ARCHIVE_SHA == sha(r28a / 'rando-dexcount/liblasgame-r28-dexcount.a'), 'the dexcount archive is not r28a\'s (1f0c586e...)')
    require(sha(obj) == DEXCOUNT_OBJECT_SHA == sha(r28a / 'rando-dexcount/za_dexcount.o'), 'za_dexcount.o is not r28a\'s (207e7a1a...)')
    report = dict(runtime_objects=len(runtime), runtime_identical=True, title_objects=len(titles), title_identical=True,
                  dexcount_archive_sha256=sha(arc), dexcount_object_sha256=sha(obj), runtime=runtime, titles=titles)
    (evidence / 'base-copy.json').write_text(json.dumps(report, indent=2))
    print('base: %d runtime objects, %d title objects, the dexcount archive and za_dexcount.o are r28a\'s byte for byte'
          % (len(runtime), len(titles)))


def dexopen(dexout, base_archive, evidence, r28a_pie):
    dexout, evidence = Path(dexout), Path(evidence)
    manifest = json.loads((dexout / 'dexopen-r28b-manifest.json').read_text())
    archive = dexout / 'liblasgame-r28-dexopen.a'
    mod = r27()
    a, b = mod.archive_members(Path(base_archive)), mod.archive_members(archive)
    require(list(a) == list(b), 'archive member list / order changed')
    changed = sorted(n for n in a if a[n] != b[n])
    require(changed == UNITS, 'archive members changed %s, expected %s' % (changed, UNITS))
    require(sorted(manifest['archive']['changed_members']) == UNITS and manifest['archive']['new_sha256'] == sha(archive),
            'manifest does not describe this archive')
    require(manifest['archive']['base_sha256'] == sha(base_archive) == DEXCOUNT_ARCHIVE_SHA, 'the base archive is not r28a\'s dexcount archive')
    obj = dexout / 'za_dexopen.o'
    require(obj.is_file() and manifest['new_object']['sha256'] == sha(obj), 'za_dexopen.o missing or not the manifest\'s')
    defined = {l.split()[-1] for l in out([NM, '--defined-only', '--extern-only', obj]).splitlines() if l.split()}
    require(ENTRY_POINTS <= defined, 'za_dexopen.o does not define %s' % sorted(ENTRY_POINTS - defined))
    undefined = sorted({l.split()[-1] for l in out([NM, '-u', obj]).splitlines() if l.split()})
    pie_defined = {x[-1] for l in out([NM, '--defined-only', r28a_pie]).splitlines() if (x := l.split())}
    pie_imports = {x[-1] for l in out([NM, '--dynamic', '--undefined-only', r28a_pie]).splitlines() if (x := l.split())}
    unresolved = [s for s in undefined if s not in pie_defined and s not in pie_imports]
    require(not unresolved, 'za_dexopen.o imports symbols r28a\'s PIE neither defines nor imports (would become new dynamic imports): %s' % unresolved)
    with tempfile.TemporaryDirectory() as td:
        new_imports = {}
        for u in UNITS:
            for label, arc in (('base', base_archive), ('new', archive)):
                subprocess.run([AR, 'x', str(arc), u], cwd=td, check=True)
                (Path(td) / u).rename(Path(td) / (label + '-' + u))
            und = lambda n: {l.split()[-1] for l in out([NM, '-u', Path(td) / n]).splitlines() if l.split()}
            dfn = lambda n: {l.split()[-1] for l in out([NM, '--defined-only', Path(td) / n]).splitlines() if l.split()}
            new_imports[u] = sorted(und('new-' + u) - und('base-' + u))
            require(dfn('new-' + u) == dfn('base-' + u), '%s: defined symbols changed' % u)
            require(sha(Path(td) / ('new-' + u)) == manifest['game_units'][u[:-2]]['object_patched_sha256'], '%s is not the manifest\'s object' % u)
    want = {'main_287.o': ['za_dexopen_hyperspace_dex_enabled'], 'main_115.o': ['za_dexopen_mega_dex_flag']}
    require(new_imports == want, 'patched units import %s, expected %s' % (new_imports, want))
    report = dict(archive=str(archive), archive_sha256=sha(archive), base_archive_sha256=sha(base_archive), members=len(a),
                  changed_members=changed, object_sha256=sha(obj), object_defined=sorted(defined), object_undefined=undefined,
                  undefined_resolved_by_r28a_pie=True, patched_units_new_imports=new_imports, manifest=manifest)
    (evidence / 'dexopen-checks.json').write_text(json.dumps(report, indent=2))
    print('dexopen: archive members changed %s only (%d members, same order); za_dexopen.o defines %s, imports %s (all in r28a\'s PIE)'
          % (changed, len(a), sorted(ENTRY_POINTS), undefined))


def inputs(r28a, work, dexout, evidence):
    r28a, work, dexout, evidence = Path(r28a), Path(work), Path(dexout), Path(evidence)
    rel = (r28a / 'r28a/evidence/runtime-inputs.txt').read_text().split()
    require(rel == (work / 'r28b/evidence/runtime-inputs.txt').read_text().split(), 'runtime list differs from r28a')
    runtime = [dict(input=r, identical=sha(r28a / 'source' / r) == sha(work / 'source' / r)) for r in rel]
    require(all(e['identical'] for e in runtime), 'a runtime object differs from r28a: %s' % [e['input'] for e in runtime if not e['identical']])
    link_a = (r28a / 'r28a/evidence/link-inputs.txt').read_text().split()
    link_b = (work / 'r28b/evidence/link-inputs.txt').read_text().split()
    renamed = [t.replace(str(r28a / 'r28a/objects') + '/', str(work / 'r28b/objects') + '/')
                .replace(str(r28a / 'rando-dexcount') + '/', str(work / 'rando-dexcount') + '/') for t in link_a]
    require(link_b[:len(renamed)] == renamed, 'the link line is not r28a\'s followed by the dexopen object')
    extra = link_b[len(renamed):]
    require(extra == [str(dexout / 'za_dexopen.o')], 'unexpected link additions: %s' % extra)
    titles, others = [], []
    for tok in renamed:
        if tok.startswith(str(work / 'r28b/objects') + '/'):
            titles.append(dict(object=Path(tok).name, identical=sha(r28a / 'r28a/objects' / Path(tok).name) == sha(Path(tok))))
        elif tok.endswith('.o') or tok.endswith('.a'):
            others.append(dict(input=tok, sha256=sha(tok)))
    require(all(t['identical'] for t in titles), 'a title object differs from r28a')
    require(sha(work / 'rando-dexcount/za_dexcount.o') == DEXCOUNT_OBJECT_SHA, 'za_dexcount.o on the link line is not r28a\'s')
    report = dict(runtime_objects=len(runtime), runtime_identical_to_r28a=True, title_objects=len(titles), title_identical_to_r28a=True,
                  other_link_inputs=others, link_additions=extra, dexcount_object_sha256=DEXCOUNT_OBJECT_SHA,
                  game_archive='the dexopen archive (dexopen-checks.json) in place of r28a\'s dexcount archive')
    (evidence / 'inputs.json').write_text(json.dumps(report, indent=2))
    print('inputs: %d runtime objects, %d title objects and za_dexcount.o identical to r28a; link additions %s'
          % (len(runtime), len(titles), [Path(t).name for t in extra]))


def calls_seen(pie, functions):
    asm = out([OBJDUMP, '-d', '--no-show-raw-insn', '--disassemble-symbols=' + ','.join(sorted(functions)), pie])
    seen, caller = set(), None
    for line in asm.splitlines():
        if m := re.match(r'^\s*[0-9a-f]+ <([^>]+)>:$', line):
            caller = m[1]
        elif caller and re.search(r'\b(?:callq?|jmpq?)\b', line):
            if m := re.search(r'<([^>]+)>', line):
                seen.add((caller, m[1]))
    return asm, seen


def image(r28a_pie, pie, evidence):
    r28a_pie, pie, evidence = Path(r28a_pie), Path(pie), Path(evidence)
    imports = {}
    for label, path in (('r28a', r28a_pie), ('r28b', pie)):
        imports[label] = sorted(l.split()[-1] for l in out([NM, '--dynamic', '--undefined-only', path]).splitlines() if l.split())
    require(imports['r28a'] == imports['r28b'], 'dynamic imports differ from r28a')
    def strong(path):
        return [f[2] for l in out([NM, '--defined-only', '--extern-only', path]).splitlines() if len(f := l.split()) == 3 and f[1] in 'ABCDGRST']
    s_a, s_b = strong(r28a_pie), strong(pie)
    dup = sorted(n for n, c in Counter(s_b).items() if c > 1)
    require(not dup, 'duplicate strong globals: %s' % dup)
    removed = sorted(set(s_a) - set(s_b))
    require(not removed, 'globals of r28a gone: %s' % removed)
    added = sorted(set(s_b) - set(s_a))
    require(ENTRY_POINTS <= set(added) <= ALL_DEXOPEN_GLOBALS, 'globals added are not za_dexopen\'s only: %s' % added)
    defined = {x[-1] for l in out([NM, '--defined-only', pie]).splitlines() if (x := l.split())}
    required = DEXOPEN_CALLS + DEXCOUNT_CALLS
    functions = ({a for a, _ in required} | {s for s in defined if s.startswith('za_dexopen')}) & defined
    asm, seen = calls_seen(pie, functions)
    (evidence / 'r28b-callers.s').write_text(asm)
    missing = [p for p in required if p not in seen]
    require(not missing, 'required linked calls missing: %s' % missing)
    # the trace's libc/klog calls go through the GOT (-fno-plt): named in the disassembly only when objdump resolves the
    # slot, so this is recorded, not required (dexopen mode proved the object imports exactly those five symbols)
    dex_asm = '\n'.join(block for block in re.split(r'\n(?=[0-9a-f]+ <)', asm) if re.match(r'^[0-9a-f]+ <za_dexopen', block))
    trace_named = sorted(n for n in ('sceKernelDebugOutText', 'snprintf', 'fputs', 'fflush') if n in dex_asm)
    strings = out(['strings', '-a', pie])
    for s in KLOG_STRINGS:
        require(s in strings, 'klog string missing: %s' % s)
    report = dict(dynamic_imports_identical_to_r28a=True, dynamic_imports=len(imports['r28b']), strong_duplicates=dup, globals_added=added,
                  globals_removed=removed, required_calls=[list(p) for p in required], trace_calls_named_in_disassembly=trace_named,
                  klog_strings_present=KLOG_STRINGS)
    (evidence / 'image-r28b.json').write_text(json.dumps(report, indent=2))
    print('image: imports = r28a (%d), %d globals added (%s), none removed, %d required calls linked, trace calls named: %s'
          % (len(imports['r28b']), len(added), ', '.join(added), len(required), ', '.join(trace_named) or 'none (GOT)'))


def repro(sums1, sums2, evidence):
    """Each input is a SHA256SUMS.txt or a build.log containing its `sha256sum` lines (the lines the build printed)."""
    def parse(p):
        out = {}
        for l in Path(p).read_text(errors='replace').splitlines():
            if m := re.match(r'^([0-9a-f]{64})\s+(\S+)$', l.strip()):
                if m[2].endswith(('.bin', '.elf', '.a', '.o')) and not m[2].startswith('./'):
                    out[Path(m[2]).name] = m[1]
        return out
    a, b = parse(sums1), parse(sums2)
    require(a and b, 'no sha256sum lines found in %s / %s' % (sums1, sums2))
    report = {n: dict(build1=a[n], build2=b.get(n), identical=a[n] == b.get(n)) for n in a}
    (Path(evidence) / 'reproducibility.json').write_text(json.dumps(report, indent=2))
    bad = [n for n, r in report.items() if not r['identical']]
    require(not bad, 'the second build differs: %s' % bad)
    print('repro: %d files identical across the two builds (%s)' % (len(report), ', '.join(report)))


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'base':
        base(*sys.argv[2:5])
    elif mode == 'dexopen':
        dexopen(*sys.argv[2:6])
    elif mode == 'inputs':
        inputs(*sys.argv[2:6])
    elif mode == 'image':
        image(*sys.argv[2:5])
    elif mode == 'repro':
        repro(*sys.argv[2:5])
    else:
        sys.exit(__doc__)
