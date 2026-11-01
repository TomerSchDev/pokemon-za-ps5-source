#!/usr/bin/env python3
"""main-1.2.0 candidate = main-1.1.0 (frozen, console-gated) + save slots (slot menu, delete, slot.zrs on every save).
WSL only, offline, never touches a console.

  python3 port/ui-v2/tools/build-main-1.2.0.py --out /home/tomer/ps5-za-native/main-1.2.0-build-NEW \
      --runtime-main-tar MAIN.tar --runtime-tar SLOT.tar --names slot-names.json [--package NEW]

MAIN.tar / SLOT.tar: `git archive` of runtime pokeza-recomp-ps5 `main` (7ce9654 = 1.1.0's runtime, fd-fix) and of
`save-slot-writer` rebased onto it (fs.c holds BOTH the overlay-fd change and the Commit hook). `git get-tar-commit-id`
must name the expected commits.

Base = the frozen main-1.1.0 inputs (tools/za/releases/main-1.1.0.lock.json). Steps (all must pass; nothing repinned):
  A. control: link-title.sh over the frozen 1.1.0 inputs -> PIE ce7a3c75 and, signed, eboot 7d837a58 byte for byte.
  B. runtime controls (compile-runtime-object.sh, the recipe of the pinned objects): services/fs from MAIN.tar = the
     frozen fs.o; ipc, kernel, services/time, rando from SLOT.tar = frozen. Changed: services/fs.o; new: services/save_slot.o.
  C. host: gen-capabilities / embed-font, build-host.sh (ASan/UBSan UI tests, flow, test_saves, goldens); sources unchanged.
  D. title objects (compile-title-objects.sh) twice: label r29-ui (control) and the release label. Every UI object except
     launcher_core / ui_launcher (changed) and launcher_ps5 / title_entry (build label) must equal the frozen 1.1.0
     object (byte-identical, or identical without debug info).
  E. release link: the frozen 1.1.0 command with ONLY fs.o, launcher_core.o, ui_launcher.o, launcher_ps5.o,
     title_entry.o replaced and save_slot.o added. The game archive (Hebrew main_992), rtl_engine.o and FriBidi are
     the frozen inputs (pins checked). Registration + image verifiers; every lost symbol must be one only a replaced
     object defined; required symbols present (RTL hook, FriBidi, slot writer, launcher).
  F. sign; package (optional): main-1.1.0's package with eboot.bin replaced, randomizer-assets/slot-names.json added,
     evidence-1.2.0/; SHA256SUMS.json regenerated (every other 1.1.0 file keeps its hash).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
UI = HERE.parent
PROJECT = UI.parents[1]
sys.path.insert(0, str(PROJECT / 'tools/za'))
import za  # noqa: E402

NATIVE = Path('/home/tomer/ps5-za-native')
RELEASE = 'main-1.1.0'
BASE_EBOOT = '7d837a58acb83c5513ee3e2b3e6b3b5a5042379a92b7300ccc1e955148d2ac0f'
BASE_PIE = 'ce7a3c75f810f18a79480d87c80c8e25dcb0afb95709e0b286053966a596aaee'
BASE_LOCK_SHA = '7ccc2d7674a5c3e618f267bf0aa5edffbbbc5c87148872ede83141aae39969b1'
RUNTIME_MAIN = '7ce9654121b6f1614ae74ecb57004314c3de9404'
LINK_TREE = NATIVE / 'main-1.0.1-build-20261031-05/work-fix/source'          # the pinned link-title.sh tree of 1.0.1/1.1.0
LINK_TITLE_SHA = '4e543d1390e433443de99a6213e5ddcf19992d46f0e893eda11e77068218d20f'
HEADER_TREE = NATIVE / 'r29ui-codex-20261031-final-01/tree'                   # inc, port/*/include, third_party (headers)
PREPARED_TREE = NATIVE / 'r28b-dlc-dex-r29ui-20261031'                        # compile-title-objects.sh include set
BASE_PACKAGE_DEFAULT = Path('/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port/artifacts/main-1.1.0-20261031-01')
SHARED = '/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port'  # where 1.0.0's title objects compiled
VULKAN = NATIVE / 'PS5_Vulkan'
SDK = VULKAN / '.deps/native/ps5-payload-sdk'
NM = '/usr/lib/llvm-21/bin/llvm-nm'
STRIP = str(SDK / 'bin/llvm-strip')
LABEL = 'main-1.2.0-rc1'
TITLE_STEMS = ['ui_canvas', 'ui_widgets', 'ui_model', 'settings_codes', 'items_picker', 'ui_launcher', 'ui_overlay', 'ui_pad',
               'fonts_embedded', 'ui_platform', 'launcher_core', 'launcher_ps5', 'overlay_ps5', 'ui_quad', 'title_entry']
CHANGED_TITLE = {'launcher_core', 'ui_launcher'}
LABEL_TITLE = {'launcher_ps5', 'title_entry'}
REQUIRED = ['f_700264efe4', 'original_700264efe4', 'rtl_transform', 'fribidi_log2vis', 'launcher_run', 'menu_render',
            'za_items_pump', 'randomizeMusic', 'za_dlc_dex_unlock_pump', 'save_slot_commit', 'save_slot_arm',
            'rt_za_slot_rebuild', 'za_slot_read_summary_file']


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def stem(path):
    return re.sub(r'^(\d{3}-)+', '', Path(path).name)[:-2]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', required=True, type=Path)
    ap.add_argument('--runtime-main-tar', required=True, type=Path)
    ap.add_argument('--runtime-tar', required=True, type=Path)
    ap.add_argument('--runtime-commit', required=True, help='save-slot-writer commit (rebased on runtime main)')
    ap.add_argument('--names', required=True, type=Path)
    ap.add_argument('--assets', type=Path, default=PROJECT.parent / 'rando-v3-lab/assets')
    ap.add_argument('--package', type=Path)
    ap.add_argument('--base-package', type=Path, default=BASE_PACKAGE_DEFAULT)
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists() or (a.package and a.package.exists()):
        sys.exit('--out / --package must be NEW directories')
    names = json.loads(a.names.read_text(encoding='utf-8'))
    if names.get('schema') != 'za-slot-names-1' or names.get('game_build') != 'b1f12fd919eae86ab8a978317677e64bce443d1f':
        sys.exit('--names is not a za-slot-names-1 table for this game build')

    lock_path = za.RELEASES / (RELEASE + '.lock.json')
    assert sha(lock_path) == BASE_LOCK_SHA, 'main-1.1.0 lock differs from its recorded sha'
    lock = json.loads(lock_path.read_text())
    prof = lock['profiles'][RELEASE]
    pinned = lambda tok: lock['files'][tok]['sha256']
    for tok in prof['inputs']:
        if tok.startswith('{native}') and sha(za.expand(tok)) != pinned(tok):
            sys.exit('frozen 1.1.0 input changed: ' + tok)
    runtime = [Path(za.expand(t)) for t in prof['runtime']]
    archive = Path(za.expand(prof['archive']))
    extra = [za.expand(t) for t in prof['extra']]
    base_pie = Path(za.expand(prof['references']['pie']))
    assert sha(base_pie) == BASE_PIE and sha(za.expand(prof['references']['eboot'])) == BASE_EBOOT
    assert sha(LINK_TREE / 'tools/ps5/link-title.sh') == LINK_TITLE_SHA

    out.mkdir(parents=True)
    ev = out / 'evidence'
    ev.mkdir()
    logf = (ev / 'build.log').open('w', encoding='utf-8')
    env = os.environ.copy()

    def log(msg):
        print(msg, flush=True)
        logf.write(msg + '\n')
        logf.flush()

    def run(cmd, cwd=None, capture=None, extra_env=None):
        cmd = [str(c) for c in cmd]
        logf.write('\n$ ' + repr(cmd) + '\n')
        logf.flush()
        e = dict(env, **(extra_env or {}))
        r = subprocess.run(cmd, cwd=cwd, env=e, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        logf.write(r.stdout)
        logf.flush()
        if capture:
            Path(capture).write_text(r.stdout, encoding='utf-8')
        if r.returncode:
            print(r.stdout[-4000:])
            raise RuntimeError('command failed: ' + shlex.join(cmd))
        return r.stdout

    def facade(where):
        f = where / 'vulkan-facade'
        f.mkdir(parents=True)
        for sub in ('tooling', '.deps', 'vendor'):
            (f / sub).symlink_to(VULKAN / sub, target_is_directory=True)
        (f / 'tools').mkdir()
        shutil.copy2(VULKAN / 'tools/radv-link.sh', f / 'tools/radv-link.sh')
        return f

    link_env = {'PS5_VULKAN': str(facade(out)), 'PS5_PAYLOAD_SDK': str(SDK), 'PS5_CLANG': '/usr/bin/clang-21'}

    def link_and_sign(program, run_objs, extras, arch):
        program.mkdir(parents=True)
        pie = program / 'llvm-pie.elf'
        run(['bash', LINK_TREE / 'tools/ps5/link-title.sh', pie, *run_objs, arch], cwd=LINK_TREE,
            extra_env=dict(link_env, ZA_PS5_EXTRA_INPUTS=' '.join(extras)))
        run([STRIP, '--strip-debug', '-o', program / 'title-stripped.elf', pie])
        tool = VULKAN / 'build/host/ps5-native-tool'
        stubs = program / 'ps5-link/stubs'
        run([tool, 'link', '--in', program / 'title-stripped.elf', '--out', program / 'eboot.elf', '--stub-dir', SDK / 'target/lib',
             '--stub', stubs / 'libSceAgc.so', '--stub', stubs / 'libSceAgcDriver.so', '--module-sdk', '0x02000009',
             '--companion-sdk', '0x08050001', '--file-name', 'eboot.elf'])
        run([tool, 'self', '--sign', '--in', program / 'eboot.elf', '--out', program / 'eboot.bin', '--magic', '0x1D3D154F'])
        return pie, program / 'eboot.bin'

    result = {'candidate': 'main-1.2.0 (save slots) on main-1.1.0', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'base_release': RELEASE, 'base_lock_sha256': BASE_LOCK_SHA, 'base_eboot_sha256': BASE_EBOOT}

    log('== A. control: frozen main-1.1.0 inputs relink 7d837a58')
    cpie, cboot = link_and_sign(out / 'control', runtime, extra, archive)
    assert sha(cpie) == BASE_PIE, 'control PIE differs'
    assert sha(cboot) == BASE_EBOOT, 'control eboot differs'
    log('control: PIE %s and eboot %s reproduced byte for byte' % (BASE_PIE[:8], BASE_EBOOT[:8]))
    result['control'] = {'pie_sha256': BASE_PIE, 'eboot_sha256': BASE_EBOOT, 'byte_for_byte': True}

    log('== B. runtime objects')
    frozen_rt = {str(p).split('/build/ps5/rt/')[1][:-2]: p for p in runtime}
    commits = {}
    for name, tar in (('main', a.runtime_main_tar), ('slot', a.runtime_tar)):
        with tar.open('rb') as stream:
            cid = subprocess.run(['git', 'get-tar-commit-id'], stdin=stream, stdout=subprocess.PIPE, text=True).stdout.strip()
        commits[name] = cid
        t = out / ('rt-' + name)
        (t / 'source').mkdir(parents=True)
        for d in ('inc', 'port'):
            run(['cp', '-a', '--reflink=auto', HEADER_TREE / d, t / d])
        run(['cp', '-a', '--reflink=auto', HEADER_TREE / 'source/third_party', t / 'source/third_party'])
        run(['tar', '-xf', tar, '-C', t / 'source', 'runtime'])
    assert commits['main'] == RUNTIME_MAIN, commits
    assert commits['slot'] == a.runtime_commit, commits
    diff = run(['bash', '-c', 'diff -rq "$0" "$1" || true', out / 'rt-main/source/runtime', out / 'rt-slot/source/runtime'])
    log('runtime main..slot source diff:\n' + diff.strip())
    allowed = {'services/fs.c', 'services/save_slot.c', 'services/save_slot.h', 'services/za_slot.h'}
    seen = set()
    for l in diff.splitlines():
        m1 = re.match(r'Files .*/rt-main/source/runtime/(\S+) and', l)
        m2 = re.match(r'Only in .*/rt-slot/source/runtime/?(\S*): (\S+)', l)
        if m1:
            seen.add(m1.group(1))
        elif m2:
            seen.add((m2.group(1) + '/' if m2.group(1) else '') + m2.group(2))
        else:
            raise RuntimeError('unexpected runtime diff line: ' + l)
    assert seen <= allowed and 'services/fs.c' in seen, seen
    compile_sh = UI / 'tools/compile-runtime-object.sh'
    ctl = out / 'runtime-controls'
    ctl.mkdir()
    rt_controls = {}
    for tree, unit in (('main', 'services/fs'), ('slot', 'ipc'), ('slot', 'kernel'), ('slot', 'services/time'), ('slot', 'rando')):
        o = ctl / ('%s-%s.o' % (tree, unit.replace('/', '_')))
        run(['bash', compile_sh, out / ('rt-' + tree), unit, o])
        ok = sha(o) == sha(frozen_rt[unit])
        verdict = 'byte-identical to frozen 1.1.0' if ok else 'DIFFERS'
        if not ok and unit == 'services/time':
            # services/time includes ipc.h, which the fd fix changed: the release keeps the 1.0.0 object (1.0.1 builder,
            # IPC_H_DWARF) - machine code must be equal, only the DWARF line table may differ
            x, y = ctl / 'time.strip.o', ctl / 'time.frozen.strip.o'
            run([STRIP, '--strip-debug', '-o', x, o])
            run([STRIP, '--strip-debug', '-o', y, frozen_rt[unit]])
            ok = sha(x) == sha(y)
            verdict = 'identical without debug info (ipc.h DWARF, as in 1.0.1)' if ok else 'DIFFERS'
        rt_controls['%s:%s' % (tree, unit)] = verdict
        log('runtime control %s %s: %s' % (tree, unit, rt_controls['%s:%s' % (tree, unit)]))
        assert ok, 'runtime control differs: %s %s' % (tree, unit)
    newrt = out / 'runtime-new'
    newrt.mkdir()
    run(['bash', compile_sh, out / 'rt-slot', 'services/fs', newrt / 'fs.o'])
    run(['bash', compile_sh, out / 'rt-slot', 'services/save_slot', newrt / 'save_slot.o'])
    result['runtime'] = {'main_commit': commits['main'], 'slot_commit': commits['slot'], 'source_changes': sorted(seen),
                         'controls': rt_controls, 'fs.o': sha(newrt / 'fs.o'), 'save_slot.o': sha(newrt / 'save_slot.o'),
                         'frozen_fs.o': sha(frozen_rt['services/fs'])}

    log('== C. host build and tests')
    host_env = {'ZA_UI_ASSETS': str(a.assets), 'ZA_REQUIRE_HANDOFF': '1', 'PIN_GOLDENS': '0', 'PS5_CHECK': '0',
                'ZA_MUSIC_PLAN': str(NATIVE / 'r29-music-plan-v2.json')}
    env.update(host_env)
    run([sys.executable, HERE / 'gen-capabilities.py', PROJECT / 'port/rando-v3/capabilities.json', UI / 'src/capabilities_generated.inc'])
    run([sys.executable, HERE / 'embed-font.py', UI / 'fonts', UI / 'src/fonts_embedded.inc'])
    def src_hashes():
        return {str(p.relative_to(PROJECT)): sha(p) for p in sorted((UI / 'src').rglob('*')) if p.is_file()}
    before = src_hashes()
    run(['bash', HERE / 'build-host.sh', out / 'host'])
    assert before == src_hashes(), 'UI sources changed during host validation'
    (ev / 'source-hashes.json').write_text(json.dumps(before, indent=2) + '\n')
    host_logs = sorted(p.name for p in (out / 'host').glob('*.log'))
    result['host'] = {'logs': host_logs}

    log('== D. title objects')
    frozen_extra = {stem(t): t for t in extra if t.endswith('.o')}
    prefix = {'ZA_TITLE_PREFIX_MAP': str(PROJECT) + '=' + SHARED}
    titles = {}
    for label in ('r29-ui', LABEL):
        d = out / ('title-' + label)
        run(['bash', HERE / 'compile-title-objects.sh', PREPARED_TREE, d, a.assets, label], extra_env=prefix)
        titles[label] = d
    title_controls = {}
    for s in TITLE_STEMS:
        ref = frozen_extra[s]
        res = {}
        for label, d in titles.items():
            mine = d / (s + '.o')
            if sha(mine) == sha(ref):
                res[label] = 'byte-identical'
                continue
            x, y = out / 'controls-strip' / (label + '-' + s + '.o'), out / 'controls-strip' / ('frozen-' + s + '.o')
            x.parent.mkdir(exist_ok=True)
            run([STRIP, '--strip-debug', '-o', x, mine])
            run([STRIP, '--strip-debug', '-o', y, ref])
            res[label] = 'identical without debug info' if sha(x) == sha(y) else 'differs'
        title_controls[s] = res
        if s not in CHANGED_TITLE and s not in LABEL_TITLE:
            assert res['r29-ui'] != 'differs' and res[LABEL] != 'differs', 'unchanged UI object differs: ' + s
        # launcher_ps5 / title_entry: replaced anyway (build label; launcher_ps5 also includes the changed
        # launcher_core.h / ui_launcher.h), so their control result is recorded, not required
        log('title %-15s %s' % (s, res))
    (ev / 'title-controls.json').write_text(json.dumps(title_controls, indent=2) + '\n')
    result['title_controls'] = title_controls

    log('== E. release link')
    rel_title = titles[LABEL]
    swap = {s: str(rel_title / (s + '.o')) for s in CHANGED_TITLE | LABEL_TITLE}
    new_extra, replaced = [], []
    for t in extra:
        s = stem(t) if t.endswith('.o') else None
        if s in swap:
            new_extra.append(swap[s])
            replaced.append(t)
        else:
            new_extra.append(t)
    assert len(replaced) == 4, replaced
    for t in extra:   # Hebrew RTL hook + FriBidi: the frozen inputs themselves
        if t.endswith(('rtl_engine.o', 'libfribidi-ps5.a')):
            assert sha(t) == pinned(za.tokenize(t)), t
    new_runtime = [newrt / 'fs.o' if str(p).endswith('/build/ps5/rt/services/fs.o') else p for p in runtime] + [newrt / 'save_slot.o']
    assert sum(1 for p in new_runtime if p == newrt / 'fs.o') == 1
    (ev / 'link-inputs.txt').write_text(' '.join(new_extra) + '\n')
    (ev / 'runtime-inputs.txt').write_text('\n'.join(map(str, new_runtime)) + '\n')
    pie, eboot = link_and_sign(out / 'program', new_runtime, new_extra, archive)
    run([sys.executable, PROJECT / 'port/local-shader-r19/verify-registration.py', base_pie, pie], capture=ev / 'registration.json')
    defs = lambda f: set(l.split()[-1] for l in run([NM, '--defined-only', f]).splitlines() if l.strip())
    new_defs = defs(pie)
    (ev / 'defined-symbols.txt').write_text('\n'.join(sorted(new_defs)) + '\n')
    alltext = '\n'.join(new_defs)
    missing = [s for s in REQUIRED if s not in alltext]   # substring: C++ names are mangled
    assert not missing, missing
    base_defs = defs(base_pie)
    lost, added = sorted(base_defs - new_defs), sorted(new_defs - base_defs)
    old_obj_defs = set().union(*[defs(o) for o in replaced + [str(frozen_rt['services/fs'])]])
    new_obj_defs = set().union(*[defs(o) for o in list(swap.values()) + [newrt / 'fs.o', newrt / 'save_slot.o']])
    bad_lost = [s for s in lost if s not in old_obj_defs or s in new_obj_defs]
    (ev / 'symbols-lost.txt').write_text('\n'.join(lost) + '\n')
    (ev / 'symbols-added.txt').write_text('\n'.join(added) + '\n')
    assert not bad_lost, 'base symbols lost outside the replaced objects: %s' % bad_lost[:20]
    run([sys.executable, PROJECT / 'port/title/verify-image.py', out / 'program/title-stripped.elf', out / 'program/eboot.elf',
         ev / 'defined-symbols.txt'], capture=ev / 'image-preservation.json')
    run([VULKAN / 'build/host/ps5-native-tool', 'self', '--inspect', '--file', eboot], capture=ev / 'self-inspection.txt')
    result.update(eboot_sha256=sha(eboot), pie_sha256=sha(pie), eboot_bytes=eboot.stat().st_size,
                  symbols={'base': len(base_defs), 'new': len(new_defs), 'lost': len(lost), 'added': len(added)},
                  replaced_extra=[Path(t).name for t in replaced], runtime_replaced=['services/fs.o'],
                  runtime_added=['services/save_slot.o'], unchanged_inputs='game archive (Hebrew main_992), rtl_engine.o, '
                  'libfribidi-ps5.a, 62 runtime objects and every other extra input = frozen main-1.1.0',
                  label=LABEL, slot_names_sha256=sha(a.names), hardware_tested=False, console_access=False)
    log('release: eboot %s PIE %s; symbols %d -> %d (lost %d, all from replaced objects; added %d)' % (
        result['eboot_sha256'], result['pie_sha256'], len(base_defs), len(new_defs), len(lost), len(added)))
    (ev / 'build-result.json').write_text(json.dumps(result, indent=2) + '\n')

    if a.package:
        log('== F. package')
        src = a.base_package
        sums = json.loads((src / 'SHA256SUMS.json').read_text())
        bad = [r for r, d in sums.items() if sha(src / r) != d]
        assert not bad and sums['eboot.bin'] == BASE_EBOOT, bad
        dst = a.package
        dst.mkdir(parents=True)
        outsums = {}
        for rel in sums:
            (dst / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(eboot if rel == 'eboot.bin' else src / rel, dst / rel)
            outsums[rel] = sha(dst / rel)
        shutil.copyfile(a.names, dst / 'randomizer-assets/slot-names.json')
        outsums['randomizer-assets/slot-names.json'] = sha(dst / 'randomizer-assets/slot-names.json')
        (dst / 'evidence-1.2.0').mkdir()
        for f in sorted(ev.iterdir()):
            if f.name != 'build.log':
                shutil.copyfile(f, dst / 'evidence-1.2.0' / f.name)
        for f in host_logs:
            shutil.copyfile(out / 'host' / f, dst / 'evidence-1.2.0' / ('host-' + f))
        for f in (dst / 'evidence-1.2.0').iterdir():
            outsums['evidence-1.2.0/' + f.name] = sha(f)
        changed = sorted(r for r in sums if outsums[r] != sums[r])
        assert changed == ['eboot.bin'], changed
        (dst / 'SHA256SUMS.json').write_text(json.dumps(dict(sorted(outsums.items())), indent=2) + '\n')
        log('package %s: %d files (1.1.0: %d; changed eboot.bin; added slot-names.json + evidence-1.2.0)' % (dst, len(outsums), len(sums)))
    logf.close()
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
