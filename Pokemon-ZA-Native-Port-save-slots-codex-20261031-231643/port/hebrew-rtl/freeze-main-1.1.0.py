#!/usr/bin/env python3
"""Freeze the console-gated main-1.1.0 build (build-r29-hebrew.sh, BASE_SPEC=base-main-1.0.1.json) as a za release.
WSL only, offline.  Modelled on port/fd-fix/freeze-main-1.0.1.py.

  python3 port/hebrew-rtl/freeze-main-1.1.0.py --build /home/tomer/ps5-za-native/hebrew-1.1.0-candidate-20261031-r1 \
      --project-commit <main commit holding this script> --package-name main-1.1.0-20261031-01 \
      --frozen /home/tomer/ps5-za-native/za-main-1.1.0-frozen-20261031 --reproduce /home/tomer/ps5-za-native/za-main-1.1.0-reproduce-NEW

1. package {za-repo}/artifacts/<package-name> (NEW): main-1.0.1's pinned package, eboot.bin replaced by the 1.1.0 eboot,
   mods/hebrew (564 files, from the gated candidate package, each checked against its PACKAGE.json), evidence-1.1.0/,
   SHA256SUMS.json regenerated (every 1.0.1 file except eboot.bin keeps its hash).
2. evidence/release-link.log (NEW) in the build tree: the release link-title.sh command as one '$ [...]' line
   (build-r29-hebrew.sh calls link-title.sh from bash, so the list is rebuilt from base-spec.json, exactly as the script does).
3. freeze_release.py --name main-1.1.0 (new lock).
4. za reproduce main-1.1.0 + za check-proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
ZA_REPO = Path('/mnt/c/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/Pokemon-ZA-Native-Port')
BASE_PACKAGE = 'artifacts/main-1.0.1-20261031-01'
CANDIDATE_PACKAGE = 'artifacts/main-1.1.0-candidate-20261031-r1'
EBOOT = '7d837a58acb83c5513ee3e2b3e6b3b5a5042379a92b7300ccc1e955148d2ac0f'
PIE = 'ce7a3c75f810f18a79480d87c80c8e25dcb0afb95709e0b286053966a596aaee'
GATE = r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\main-releases\main-1.1.0-gate-20261031-182438Z'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as f:
        for b in iter(lambda: f.read(1 << 22), b''):
            h.update(b)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for k in ['build', 'project-commit', 'package-name', 'frozen', 'reproduce']:
        ap.add_argument('--' + k, required=True)
    a = ap.parse_args()
    build = Path(a.build)
    eboot, pie = build / 'image/eboot.bin', build / 'image/llvm-pie.elf'
    assert sha(eboot) == EBOOT and sha(pie) == PIE
    for f in ['tools/za/za.py', 'tools/za/freeze_release.py', 'tools/za/releases/main-1.0.1.lock.json']:
        assert sha(ZA_REPO / f) == sha(PROJECT / f), 'za tooling of the shared tree differs from this checkout: ' + f
    spec = json.loads((build / 'base-spec.json').read_text())
    assert spec['release'] == 'main-1.0.1' and spec['eboot_sha256'].startswith('ecaf1965')

    # 1. package
    src, cand = ZA_REPO / BASE_PACKAGE, ZA_REPO / CANDIDATE_PACKAGE
    dst = ZA_REPO / 'artifacts' / a.package_name
    if dst.exists():
        sys.exit('package exists: ' + str(dst))
    sums = json.loads((src / 'SHA256SUMS.json').read_text())
    bad = [r for r, d in sums.items() if sha(src / r) != d]
    assert not bad, bad
    cpkg = json.loads((cand / 'PACKAGE.json').read_text())
    assert cpkg['eboot_sha256'] == EBOOT and sha(cand / 'PPSA91762/eboot.bin') == EBOOT and len(cpkg['mods']) == 564
    bad = [m['path'] for m in cpkg['mods'] if sha(cand / 'mods' / m['path']) != m['sha256']]
    assert not bad, bad
    dst.mkdir(parents=True)
    out = {}
    for rel in sums:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(eboot if rel == 'eboot.bin' else src / rel, dst / rel)
        out[rel] = sha(dst / rel)
    for m in cpkg['mods']:
        rel = 'mods/' + m['path']
        assert rel not in out
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cand / 'mods' / m['path'], dst / rel)
        out[rel] = sha(dst / rel)
    (dst / 'evidence-1.1.0').mkdir()
    for f in ['registration.json', 'image-preservation.json', 'self-inspection.txt', 'symbols-lost.txt',
              'archive-compare.json', 'main_992.defined.diff', 'rtl_engine.imports', 'SHA256SUMS.txt']:
        shutil.copyfile(build / 'evidence' / f, dst / 'evidence-1.1.0' / f)
    shutil.copyfile(cand / 'PACKAGE.json', dst / 'evidence-1.1.0/candidate-PACKAGE.json')
    for f in (dst / 'evidence-1.1.0').iterdir():
        out['evidence-1.1.0/' + f.name] = sha(f)
    assert out['eboot.bin'] == EBOOT
    changed = sorted(r for r in sums if out[r] != sums[r])
    assert changed == ['eboot.bin'], changed
    (dst / 'SHA256SUMS.json').write_text(json.dumps(dict(sorted(out.items())), indent=2) + '\n')

    # 2. the release link line, rebuilt from base-spec.json exactly as build-r29-hebrew.sh step 7 runs it
    extra = (build / 'evidence/link-inputs.txt').read_text().strip()
    assert extra == '%s %s/obj/rtl_engine.o %s/obj/libfribidi-ps5.a' % (spec['extra'], build, build)
    log = (build / 'evidence/build.log').read_text(encoding='utf-8')
    assert 'base link reproduced exactly' in log and 'every base symbol preserved' in log
    cmd = ['bash', spec['src_tree'] + '/tools/ps5/link-title.sh', str(pie), *spec['runtime'],
           str(build / 'obj/liblasgame-r29-hebrew.a')]
    assert sha(spec['src_tree'] + '/tools/ps5/link-title.sh') == spec['link_title_sha256']
    (build / 'evidence/release-link.log').open('x').write('$ ' + repr(cmd) + '\n')

    # 3. freeze
    release = {
        'version': '1.1.0', 'branch': 'main',
        'build': 'main-1.0.1 + Hebrew RTL: game unit main_992.o (f_700264efe4 renamed original_700264efe4) in a copy of '
                 'the game archive, + rtl_engine.o + FriBidi 1.0.16 (18 objects); runtime and every other input of 1.0.1 '
                 'unchanged; data: mods/hebrew (564 files, Assistant font, translation r195), linked as mods/0-hebrew',
        'eboot_sha256': EBOOT, 'pie_sha256': PIE,
        'base_release': 'main-1.0.1', 'base_eboot_sha256': spec['eboot_sha256'],
        'builder': 'port/hebrew-rtl/build-r29-hebrew.sh (BASE_SPEC=base-main-1.0.1.json) + port/hebrew-rtl/freeze-main-1.1.0.py',
        'runtime_repo': 'pokeza-recomp-ps5', 'runtime_main_commit': '7ce9654121b6f1614ae74ecb57004314c3de9404',
        'runtime_note': 'runtime main fast-forwarded to fd-fix 7ce9654 (= 1.0.1 runtime); 1.1.0 changes no runtime object',
        'project_commit': a.project_commit, 'project_branch_merged': 'heb-trans 67986f2',
        'package': 'artifacts/' + a.package_name,
        'mods': {'files': 564, 'manifest_sha256': cpkg['mods_manifest_sha256'], 'app0_folder': cpkg['app0_folder'],
                 'link': 'mods/0-hebrew'},
        'build_dir': str(build), 'hardware_verified': True,
        'hardware': {'queue_ticket': '00000009', 'verified_utc': '2026-10-31T18:44:38Z', 'console': '192.168.1.135 / PPSA91762',
                     'evidence': GATE, 'runner': 'port/main-install/gate_r29.py port/hebrew-rtl/install-1.1.0.py <step>',
                     'result': 'Hebrew RTL in the world and the menu, no crash, saves unchanged'},
        'covers': 'main-1.0.1 (ecaf1965, not gated on its own; every 1.0.1 input is part of 1.1.0)',
        'overlay_fd_fix': True, 'hebrew_rtl': True,
        'host_test': 'port/hebrew-rtl/test-host.sh 5/5; tools/test_fs_overlay_fds.sh PASS',
    }
    rj = build / 'evidence/release-1.1.0.json'
    rj.open('x').write(json.dumps(release, indent=2) + '\n')
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/freeze_release.py', '--name', 'main-1.1.0', '--tree', build,
                    '--link-log', 'evidence/release-link.log', '--extra', 'evidence/link-inputs.txt',
                    '--program', 'image', '--eboot-sha', EBOOT, '--pie-sha', PIE,
                    '--delivered', '{repo}/artifacts/%s/eboot.bin' % a.package_name, '--frozen', a.frozen,
                    '--description', 'main 1.1.0 = main-1.0.1 + Hebrew RTL (FriBidi) + mods/0-hebrew; '
                    'hardware-verified 31.10.2026 (queue ticket 9)',
                    '--package-sums', '{repo}/artifacts/%s/SHA256SUMS.json' % a.package_name,
                    '--release-json', rj], check=True)

    # 4. reproduce from the frozen inputs
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/za.py', 'reproduce', 'main-1.1.0', '--out', a.reproduce], check=True)
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/za.py', 'check-proof',
                    str(Path(a.reproduce) / 'main-1.1.0/proof.json')], check=True)
    print('main-1.1.0 frozen and reproduced; lock:', ZA_REPO / 'tools/za/releases/main-1.1.0.lock.json')


if __name__ == '__main__':
    main()
