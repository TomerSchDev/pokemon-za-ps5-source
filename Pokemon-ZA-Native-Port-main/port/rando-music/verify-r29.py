"""r29-music build checks (no console access).
  verify-r29.py objects BASE_OBJECTS R29_OBJECTS OUT.json
      only native_menu.o, run_store.o and title_entry.o differ; za_music.o and za_music_plan.o are new; every other
      file of the base object folder is byte-identical.
  verify-r29.py image BASE_PIE R29_PIE EVIDENCE_DIR PROJECT PLAN_SHA256 BASE(r28|r27b)
      dynamic imports identical to the base image, unique global definitions, every linked call the base build's
      verifier requires (timing, MONEY, FPS/menu, and for r28 ITEMS/Hebrew trial) still present, plus the music
      path: generateJob -> randomizeMusic, the embedded plan and its SHA-256 string.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def require(ok, msg):
    if not ok:
        raise RuntimeError(msg)


mode = sys.argv[1]
if mode == 'objects':
    base, new, out = map(Path, sys.argv[2:5])
    a = {p.name: sha(p) for p in base.iterdir() if p.is_file()}
    b = {p.name: sha(p) for p in new.iterdir() if p.is_file()}
    changed = sorted(n for n in a if n in b and a[n] != b[n])
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    require(changed == ['native_menu.o', 'run_store.o', 'title_entry.o'], 'unexpected changed objects %s' % changed)
    require(added == ['za_music.o', 'za_music_plan.o'] and not removed, 'unexpected added/removed %s %s' % (added, removed))
    out.write_text(json.dumps(dict(changed={n: dict(base=a[n], r29=b[n]) for n in changed},
                                   added={n: b[n] for n in added}, unchanged=len(a) - len(changed)), indent=2))
    print('objects: %d unchanged, changed %s, added %s' % (len(a) - len(changed), changed, added))
elif mode == 'image':
    base, cand, evid, project = map(Path, sys.argv[2:6])
    plan_sha, which = sys.argv[6], sys.argv[7]
    spec = importlib.util.spec_from_file_location('old', project / 'port/perf-r27/verify-r27-build.py')
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    nm = '/usr/lib/llvm-21/bin/llvm-nm'
    objdump = '/usr/lib/llvm-21/bin/llvm-objdump'

    def imports(p):
        return sorted(l.split()[-1] for l in subprocess.check_output([nm, '-D', '--undefined-only', str(p)], text=True).splitlines() if l.split())
    ia, ib = imports(base), imports(cand)
    require(ia == ib, 'dynamic imports differ from the base image')
    (evid / 'imports.json').write_text(json.dumps(dict(unchanged=True, count=len(ib)), indent=2))
    defined = subprocess.check_output([nm, '--defined-only', '--extern-only', str(cand)], text=True)
    names = [l.split()[-1] for l in defined.splitlines() if l.split()]
    require(len(names) == len(set(names)), 'duplicate global definitions')
    pairs = old.TIMING_CALLS + old.MONEY_CALLS + old.MENU_CALLS
    if which == 'r28':
        pairs += [('f_70002bc8ec', 'za_items_pump'), ('f_7000bba2cc', 'za_items_pump'), ('f_7000b49360', 'za_items_reset'),
                  ('za_items_pump', 'f_700048963c'), ('menu_handle_event', 'za_items_request'),
                  ('menu_handle_event', 'za_hebrew_trial_request')]
    allsyms = subprocess.check_output([nm, '--defined-only', str(cand)], text=True)

    def symbol(pattern):
        found = sorted({l.split()[-1] for l in allsyms.splitlines() if l.split() and re.search(pattern, l.split()[-1])})
        require(found, 'missing symbol ' + pattern)
        return found
    gen = symbol(r'generateJob')
    randomize = symbol(r'^_ZN2za6native14randomizeMusic')
    for f in ('_ZN2za6native12shuffleMusic', '_ZN2za6native17readBankFromRomfs', '_ZN2za6native15zaMusicPlanJson',
              '_ZN2za6native17zaMusicPlanSha256', '^za_randomizer_boot$'):
        symbol(f)
    pairs += [(gen[0], randomize[0]), ('za_randomizer_boot', '_ZN2za6native8bootMenuEv')]
    # r27b's observer entry is kept (r28 links it through the Hebrew trial's --wrap=za_observer_menu)
    pairs += [('_ZN2za6native8bootMenuEv', '__wrap_za_observer_menu' if which == 'r28' else 'za_observer_menu')]
    report = []
    for caller, callee in pairs:
        dump = subprocess.run([objdump, '-d', '--no-show-raw-insn', '--disassemble-symbols=' + caller, str(cand)],
                              capture_output=True, text=True, check=True).stdout
        require(re.search(r'\b(?:callq?|jmpq?)\s+[^\n]*<' + re.escape(callee) + r'[>+]', dump), 'missing call %s -> %s' % (caller, callee))
        report.append([caller, callee])
    data = cand.read_bytes()
    require(plan_sha.encode() in data, 'embedded plan SHA-256 string missing')
    require(b'"za202-bgm-leaf-shuffle-v1"' in data, 'embedded plan text missing')
    require(b'randomizer-r29-music' in data, 'revision label missing')
    (evid / 'linked-calls.json').write_text(json.dumps(report, indent=2))
    print('image: imports unchanged (%d), unique globals, %d linked calls incl. music path, plan %s embedded' % (len(ib), len(report), plan_sha))
else:
    raise ValueError(mode)
