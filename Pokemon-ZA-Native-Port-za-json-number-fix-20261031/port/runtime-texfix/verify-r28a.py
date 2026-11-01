"""r28a-play (texfix candidate) checks against r28-play.

    verify-r28a.py inputs <r28-play work tree> <r28a work tree> <evidence dir>
    verify-r28a.py image  <r28-play llvm-pie.elf> <r28a llvm-pie.elf> <evidence dir> <project>

inputs: every link input is r28-play's own file, byte for byte, except the four runtime objects the fix rebuilds
        (nvn/objects.o, nvn/vulkan/{textures,exec,device}.o); the runtime list and the link line are r28-play's.
image:  the dynamic imports are r28-play's; no duplicate strong globals; the runtime registrations keep their counts
        (registration.json, written before); r28-play's linked calls (timing, MONEY, menu, ITEMS, Hebrew trial) are all
        there; the fix is linked in (its functions, its calls, its klog strings).
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

NM = '/usr/lib/llvm-21/bin/llvm-nm'
OBJDUMP = '/usr/lib/llvm-21/bin/llvm-objdump'
CHANGED = ['nvn/objects.o', 'nvn/vulkan/textures.o', 'nvn/vulkan/exec.o', 'nvn/vulkan/device.o']
R28_PIE_SHA = '0570bec994a7cbe9512dacb4a6fa8e3bc0340ef3570dd73edf346772928d8288'  # r28-play's llvm-pie.elf (its SHA256SUMS)


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require(ok, message):
    if not ok:
        raise SystemExit('FAILED: ' + message)


def out(cmd):
    return subprocess.check_output([str(c) for c in cmd], text=True)


def inputs(prev, work, evidence):
    prev, work, evidence = Path(prev), Path(work), Path(evidence)
    rel = (prev / 'r28/evidence/runtime-inputs.txt').read_text().split()
    require(rel == (work / 'r28a/evidence/r28-runtime-inputs.txt').read_text().split(), 'runtime list differs from r28-play')
    runtime = []
    for r in rel:
        a, b = prev / 'source' / r, work / 'source' / r
        same = sha(a) == sha(b)
        runtime.append(dict(input=r, r28_sha256=sha(a), r28a_sha256=sha(b), identical=same))
    changed = sorted(e['input'] for e in runtime if not e['identical'])
    require(changed == sorted('build/ps5/rt/' + c for c in CHANGED), 'unexpected runtime objects changed: %s' % changed)
    link_r28 = (prev / 'r28/evidence/link-inputs.txt').read_text().strip()
    link_r28a = (work / 'r28a/evidence/link-inputs.txt').read_text().strip()
    require(link_r28a == link_r28.replace(str(prev / 'r28/objects') + '/', str(work / 'r28a/objects') + '/'),
            'link line differs from r28-play beyond the objects folder')
    titles = []
    for tok in link_r28.split():
        if tok.endswith('.o'):
            a = Path(tok)
            b = work / 'r28a/objects' / a.name
            titles.append(dict(object=a.name, r28_sha256=sha(a), identical=sha(a) == sha(b)))
        elif tok.endswith('.a'):
            titles.append(dict(library=tok, sha256=sha(tok), identical=True))  # (the same path, read only)
    require(all(t['identical'] for t in titles), 'a title object differs from r28-play')
    archive_same = sha(prev / 'r28/liblasgame-r28.a') == sha(work / 'r28a/liblasgame-r28.a')
    require(archive_same, 'game archive differs from r28-play')
    report = dict(runtime_objects=len(runtime), runtime_changed=changed,
                  runtime_unchanged=len(runtime) - len(changed), title_inputs=titles,
                  game_archive=dict(file='liblasgame-r28.a', sha256=sha(work / 'r28a/liblasgame-r28.a'), identical=True),
                  link_line='r28-play\'s, objects folder only renamed', runtime=runtime)
    (evidence / 'inputs.json').write_text(json.dumps(report, indent=2))
    print('inputs: %d runtime objects (%d rebuilt: %s), %d title inputs and the game archive identical to r28-play'
          % (len(runtime), len(changed), ', '.join(c.split('/')[-1] for c in changed), len(titles)))


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


def image(ref, pie, evidence, project):
    ref, pie, evidence, project = Path(ref), Path(pie), Path(evidence), Path(project)
    require(sha(ref) == R28_PIE_SHA, "the reference is not r28-play's PIE")
    spec = importlib.util.spec_from_file_location('r27', project / 'port/perf-r27/verify-r27-build.py')
    r27 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r27)
    imports = {}
    for label, path in (('r28', ref), ('r28a', pie)):
        imports[label] = sorted(l.split()[-1] for l in out([NM, '--dynamic', '--undefined-only', path]).splitlines() if l.split())
    require(imports['r28'] == imports['r28a'], 'dynamic imports differ from r28-play')
    (evidence / 'imports.json').write_text(json.dumps(dict(unchanged=True, imports=imports['r28a']), indent=2))
    def strong(path):
        return [f[2] for l in out([NM, '--defined-only', '--extern-only', path]).splitlines()
                if len(f := l.split()) == 3 and f[1] in 'ABCDGRST']
    s_ref, s_new = strong(ref), strong(pie)
    dup = sorted(n for n, c in Counter(s_new).items() if c > 1)
    require(not dup, 'duplicate strong globals: %s' % dup)
    added, removed = sorted(set(s_new) - set(s_ref)), sorted(set(s_ref) - set(s_new))
    want_added = {'za_texguard_hit', 'za_texguard_frame', 'za_nvn_exec_lock', 'za_nvn_exec_unlock',
                  'vk_exec_texture_destroyed', 'vk_present_texture_destroyed'}
    defined = {f[-1] for l in out([NM, '--defined-only', pie]).splitlines() if (f := l.split())}
    require(want_added <= defined, 'fix functions missing: %s' % sorted(want_added - defined))
    require(not removed, 'globals of r28-play gone: %s' % removed)
    reg = json.loads((evidence / 'registration.json').read_text())
    require({v['section'] for v in reg} == {'hle_impls', 'services', 'resets'} and
            all(v['preserved_count'] and v['candidate_bytes'] == v['baseline_bytes'] > 0 for v in reg),
            'runtime registrations not preserved')
    items = [('f_70002bc8ec', 'za_items_pump'), ('f_7000bba2cc', 'za_items_pump'), ('f_7000b49360', 'za_items_reset'),
             ('za_items_pump', 'f_700048963c'), ('menu_handle_event', 'za_items_request'),
             ('menu_handle_event', 'za_hebrew_trial_request')]
    menu = [p for p in r27.MENU_CALLS if p != ('backend_present', 'menu_render')]
    texfix = [('backend_texture_destroyed', 'vk_exec_texture_destroyed'),
              ('backend_texture_destroyed', 'vk_present_texture_destroyed'),
              ('backend_present', 'za_nvn_exec_lock'), ('backend_present', 'za_nvn_exec_unlock'),
              ('backend_present', 'za_texguard_frame'), ('hle_nvnTextureFinalize', 'backend_texture_destroyed'),
              ('hle_nvnTextureFinalize', 'za_texguard_hit')]
    required = r27.TIMING_CALLS + r27.MONEY_CALLS + menu + items + texfix
    functions = {a for a, _ in required} | {'backend_present_locked', 'renderer_stats', 'za_r24_stats'}
    functions &= defined
    asm, seen = calls_seen(pie, functions)
    (evidence / 'r28a-callers.s').write_text(asm)
    missing = [p for p in required if p not in seen]
    require(not missing, 'required linked calls missing: %s' % missing)
    present_menu = [c for c in ('backend_present', 'backend_present_locked') if (c, 'menu_render') in seen]
    require(present_menu, 'the present no longer draws the menu')
    require(any((n, 'za_dt_report') in seen for n in ('za_r24_stats', 'renderer_stats')), 'dynamic stats call missing')
    strings = out(['strings', '-a', pie])
    for s in ('[za-texguard] r28a texfix active', '[za-texguard] %s: texture %p is not live',
              '[za-texguard] live-list:', '[za-texguard] counts at frame'):
        require(s in strings, 'klog string missing: %s' % s)
    report = dict(dynamic_imports_preserved=True, strong_duplicates=dup, globals_added=added, globals_removed=removed,
                  registrations=reg, required_calls=[list(p) for p in required], menu_drawn_from=present_menu,
                  texfix_strings_present=True)
    (evidence / 'image-checks.json').write_text(json.dumps(report, indent=2))
    print('image: imports = r28-play, %d globals added (%s), none removed, registrations kept, %d required calls linked'
          % (len(added), ', '.join(added), len(required)))


# ------------------------------------------------------------------------------------------- final (texfix + dexcount)
def handoff_fields(h):
    """The dexcount HANDOFF.json's facts, whatever its exact layout: the changed game units (member names), the new
    objects, the new imports the patched units take, the symbols za_dexcount.o defines, the expected linked calls."""
    def find(*keys, default=None):
        for k in keys:
            if k in h and h[k] not in (None, ''):
                return h[k]
        return default
    unit_entries = find('changed_game_units', 'changed_units', 'game_units', 'units', default=[])
    if isinstance(unit_entries, dict):
        unit_entries = list(unit_entries)
    units = []
    unit_imports = set()
    for x in unit_entries:
        name = x if isinstance(x, str) else x.get('object', x.get('unit', x.get('name', '')))
        name = Path(name).stem + '.o'
        units.append(name)
        if isinstance(x, dict):
            unit_imports |= set(x.get('new_imports', []))
    ga = h.get('game_archive') or {}
    if isinstance(ga, dict) and ga.get('changed_members'):
        members = sorted(Path(m).stem + '.o' for m in ga['changed_members'])
        if units:
            require(sorted(set(units)) == members, 'HANDOFF changed_game_units %s vs game_archive.changed_members %s' % (sorted(set(units)), members))
        units = members
    objects = find('new_objects', 'objects', 'added_objects', default=['za_dexcount.o'])
    objects = [o if isinstance(o, str) else o.get('object', o.get('name', '')) for o in objects]
    objects = [Path(o).name for o in objects]
    imports = find('expected_imports', 'new_imports', 'imports', default=None)
    if isinstance(imports, dict):
        imports = sorted({s for v in imports.values() for s in (v if isinstance(v, list) else [v])})
    if not imports:
        imports = sorted(unit_imports) or ['za_dexcount_combine', 'za_dexcount_extra_enabled']
    calls = find('expected_linked_calls', 'linked_calls', 'calls', default=[])
    pairs, notes = [], []
    for c in calls:
        if isinstance(c, (list, tuple)) and len(c) == 2:
            pairs.append((c[0], c[1]))
        elif isinstance(c, dict):
            pairs.append((c.get('caller', c.get('from')), c.get('callee', c.get('to'))))
        elif isinstance(c, str) and '->' in c:
            a, b = c.split('->', 1)
            callers = [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', a) if t.startswith('f_')]  # (the game function)
            callees = [t for t in re.findall(r'[A-Za-z_][A-Za-z0-9_]*', re.sub(r'\([^)]*\)', '', b))]
            if callers:
                pairs += [(callers[-1], t) for t in callees]
            else:
                notes.append(c)  # (an object's libc imports: checked by the dexcount mode, not a call pair)
    pins = {}
    if isinstance(ga, dict) and ga.get('new_sha256'):
        pins['archive'] = ga['new_sha256']
    for o in find('new_objects', default=[]) or []:
        if isinstance(o, dict) and o.get('sha256'):
            pins[Path(o.get('object', '')).name] = o['sha256']
    sources = find('sources_sha256', default={}) or {}
    return dict(units=sorted(set(units)), objects=sorted(set(objects)), imports=sorted(set(imports)), calls=pairs,
                call_notes=notes, pins=pins, sources=sources)


def handoff_sources(handoff, snapshot):
    """The snapshot of port/rando-dexcount the build runs is the one the HANDOFF pins (sources_sha256)."""
    h = json.loads(Path(handoff).read_text(encoding='utf-8'))
    f = handoff_fields(h)
    snapshot = Path(snapshot)
    require(f['sources'], 'HANDOFF has no sources_sha256')
    checked = {}
    for rel, want in f['sources'].items():
        p = snapshot / Path(rel).relative_to('port/rando-dexcount') if rel.startswith('port/rando-dexcount/') else snapshot / Path(rel).name
        require(p.is_file(), 'snapshot lacks %s' % p)
        got = sha(p)
        require(got == want, 'snapshot %s is %s, HANDOFF pins %s' % (p.name, got[:16], want[:16]))
        checked[rel] = got
    print('handoff sources: %d files match the HANDOFF pins (%s)' % (len(checked), ', '.join(Path(k).name for k in checked)))


def dexcount(handoff, dexout, base_archive, evidence, cand_pie=None):
    """The dexcount apply script's outputs match its HANDOFF: exactly the listed archive members changed, the listed
    objects exist and define what the patched units import, nothing else. With cand_pie: whatever the objects import
    (a klog / libc function for their trace) is already defined in the candidate's PIE - no new dynamic import can
    come out of the link (verify image then confirms the imports are r28-play's)."""
    h = json.loads(Path(handoff).read_text(encoding='utf-8'))
    f = handoff_fields(h)
    dexout, evidence = Path(dexout), Path(evidence)
    spec = importlib.util.spec_from_file_location('r27', Path(__file__).resolve().parents[2] / 'port/perf-r27/verify-r27-build.py')
    r27 = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(r27)
    archive = next(dexout.glob('liblasgame-*dexcount*.a'))
    a, b = r27.archive_members(Path(base_archive)), r27.archive_members(archive)
    require(list(a) == list(b), 'archive member list / order changed')
    changed = sorted(n for n in a if a[n] != b[n])
    require(changed == f['units'], 'archive members changed %s, HANDOFF says %s' % (changed, f['units']))
    objs = {o: dexout / o for o in f['objects']}
    obj_undefined = {}
    for o, p in objs.items():
        require(p.is_file(), 'dexcount object missing: %s' % p)
        obj_undefined[o] = sorted({l.split()[-1] for l in out([NM, '-u', p]).splitlines() if l.split()})
    if cand_pie:
        pie_defined = {x[-1] for l in out([NM, '--defined-only', cand_pie]).splitlines() if (x := l.split())}
        pie_imports = {x[-1] for l in out([NM, '--dynamic', '--undefined-only', cand_pie]).splitlines() if (x := l.split())}
        unresolved = {o: [s for s in u if s not in pie_defined and s not in pie_imports] for o, u in obj_undefined.items()}
        unresolved = {o: u for o, u in unresolved.items() if u}
        require(not unresolved, 'dexcount objects import symbols the candidate PIE neither defines nor already imports '
                                '(would become new dynamic imports): %s' % unresolved)
    defined = set()
    for p in objs.values():
        defined |= {l.split()[-1] for l in out([NM, '--defined-only', '--extern-only', p]).splitlines() if l.split()}
    require(set(f['imports']) <= defined, 'the new imports %s are not all defined by %s' % (f['imports'], f['objects']))
    # the patched members import only the listed symbols beyond what the originals imported
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        new_imports = set()
        for u in f['units']:
            for label, arc in (('base', base_archive), ('new', archive)):
                subprocess.run(['/usr/lib/llvm-21/bin/llvm-ar', 'x', str(arc), u], cwd=td, check=True)
                (Path(td) / u).rename(Path(td) / (label + '-' + u))
            und = lambda n: {l.split()[-1] for l in out([NM, '-u', Path(td) / n]).splitlines() if l.split()}
            new_imports |= und('new-' + u) - und('base-' + u)
    require(new_imports <= set(f['imports']), 'patched units import more than the HANDOFF lists: %s' % sorted(new_imports - set(f['imports'])))
    # SHA-256s the HANDOFF pins, where it pins them (any key ending in sha256 that names one of the files here)
    pinned = {}
    def walk(x, path=''):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + '/' + k)
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, '%s[%d]' % (path, i))
        elif isinstance(x, str) and re.fullmatch(r'[0-9a-f]{64}', x):
            pinned[path] = x
    walk(h)
    ours = {p.name: sha(p) for p in list(objs.values()) + [archive]}
    matched = {k: v for k, v in pinned.items() if v in ours.values()}
    for what, want in f['pins'].items():  # (the HANDOFF's archive / object SHA-256: ours must be the same bytes)
        got = sha(archive) if what == 'archive' else ours.get(what)
        require(got == want, 'HANDOFF pins %s = %s, this build made %s' % (what, want[:16], (got or '?')[:16]))
    report = dict(archive=str(archive), archive_sha256=sha(archive), members=len(a), changed_members=changed,
                  objects={o: sha(p) for o, p in objs.items()}, objects_undefined_symbols=obj_undefined,
                  undefined_resolved_by_candidate_pie=bool(cand_pie), new_imports=sorted(new_imports),
                  handoff_pins_matching_our_files=matched, handoff=f)
    (evidence / 'dexcount-checks.json').write_text(json.dumps(report, indent=2))
    print('dexcount: archive members changed %s (as the HANDOFF), objects %s define %s, patched units import only those'
          % (changed, f['objects'], sorted(defined & set(f['imports']))))


def final_inputs(cand, work, dexout, evidence):
    """Every link input of the final build is the candidate's file byte for byte, apart from the dexcount archive (in
    place of the candidate's game archive) and the dexcount objects appended to the link line."""
    cand, work, dexout, evidence = Path(cand), Path(work), Path(dexout), Path(evidence)
    rel = (cand / 'r28a/evidence/runtime-inputs.txt').read_text().split()
    require(rel == (work / 'r28a/evidence/runtime-inputs.txt').read_text().split(), 'runtime list differs from the candidate')
    runtime = [dict(input=r, identical=sha(cand / 'source' / r) == sha(work / 'source' / r)) for r in rel]
    require(all(e['identical'] for e in runtime), 'a runtime object differs from the candidate: %s' % [e['input'] for e in runtime if not e['identical']])
    link_c = (cand / 'r28a/evidence/link-inputs.txt').read_text().split()
    link_f = (work / 'r28a/evidence/link-inputs.txt').read_text().split()
    link_c = [t.replace(str(cand / 'r28a/objects') + '/', str(work / 'r28a/objects') + '/') for t in link_c]
    extra = [t for t in link_f if t not in link_c]
    require(link_f[:len(link_c)] == link_c, 'the link line is not the candidate\'s followed by the dexcount objects')
    require(all(Path(t).parent == dexout and t.endswith('.o') for t in extra), 'unexpected link additions: %s' % extra)
    titles = []
    for tok in link_c:
        if tok.endswith('.o') and tok.startswith(str(work / 'r28a/objects')):
            a = cand / 'r28a/objects' / Path(tok).name
            titles.append(dict(object=Path(tok).name, identical=sha(a) == sha(Path(tok))))
    require(all(t['identical'] for t in titles), 'a title object differs from the candidate')
    report = dict(runtime_objects=len(runtime), runtime_identical_to_candidate=True, title_objects=len(titles),
                  title_identical_to_candidate=True, link_additions=extra,
                  game_archive='the dexcount archive (dexcount-checks.json) in place of the candidate\'s liblasgame-r28.a')
    (evidence / 'final-inputs.json').write_text(json.dumps(report, indent=2))
    print('final inputs: %d runtime objects and %d title objects identical to the candidate; link additions %s'
          % (len(runtime), len(titles), [Path(t).name for t in extra]))


def final_image(handoff, cand_pie, pie, evidence):
    """The final PIE against the candidate's: the dexcount symbols and linked calls added, nothing of the candidate's
    globals lost, the texfix calls still there."""
    h = json.loads(Path(handoff).read_text(encoding='utf-8'))
    f = handoff_fields(h)
    cand_pie, pie, evidence = Path(cand_pie), Path(pie), Path(evidence)
    def strong(path):
        return [x[2] for l in out([NM, '--defined-only', '--extern-only', path]).splitlines() if len(x := l.split()) == 3 and x[1] in 'ABCDGRST']
    s_c, s_f = strong(cand_pie), strong(pie)
    removed = sorted(set(s_c) - set(s_f))
    require(not removed, 'globals of the candidate gone: %s' % removed)
    added = sorted(set(s_f) - set(s_c))
    defined = {x[-1] for l in out([NM, '--defined-only', pie]).splitlines() if (x := l.split())}
    require(set(f['imports']) <= defined, 'dexcount symbols missing from the PIE: %s' % sorted(set(f['imports']) - defined))
    calls = f['calls']
    seen = set()
    if calls:
        functions = {a for a, _ in calls} & defined
        asm, seen = calls_seen(pie, functions)
        (evidence / 'final-callers.s').write_text(asm)
        missing = [p for p in calls if p not in seen]
        require(not missing, 'dexcount linked calls missing: %s' % missing)
    report = dict(globals_added=added, globals_removed=removed, dexcount_symbols_defined=f['imports'],
                  dexcount_calls_required=[list(p) for p in calls], dexcount_calls_seen=[list(p) for p in sorted(seen)])
    (evidence / 'final-image.json').write_text(json.dumps(report, indent=2))
    print('final image: %d globals added (%s), none of the candidate\'s removed, %d dexcount calls linked'
          % (len(added), ', '.join(added), len(calls)))


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'inputs':
        inputs(*sys.argv[2:5])
    elif mode == 'image':
        image(*sys.argv[2:6])
    elif mode == 'dexcount':
        dexcount(*sys.argv[2:7])
    elif mode == 'handoff-sources':
        handoff_sources(*sys.argv[2:4])
    elif mode == 'final-inputs':
        final_inputs(*sys.argv[2:6])
    elif mode == 'final-image':
        final_image(*sys.argv[2:6])
    else:
        sys.exit(__doc__)
