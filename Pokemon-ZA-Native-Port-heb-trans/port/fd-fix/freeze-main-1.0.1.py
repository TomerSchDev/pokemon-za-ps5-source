#!/usr/bin/env python3
"""Freeze the main-1.0.1 candidate built by build-main-1.0.1.py as a za release profile.  WSL only, offline.

  python3 port/fd-fix/freeze-main-1.0.1.py --build /home/tomer/ps5-za-native/main-1.0.1-build-20261031-05 \
      --project-commit <commit of this repo's main holding port/fd-fix> --package-name main-1.0.1-20261031-01 \
      --frozen /home/tomer/ps5-za-native/za-main-1.0.1-frozen-20261031 --reproduce /home/tomer/ps5-za-native/za-main-1.0.1-reproduce-NEW

1. package {za-repo}/artifacts/<package-name> (NEW): main-1.0.0's pinned package, eboot.bin replaced by the 1.0.1 eboot,
   evidence-1.0.1/ added, SHA256SUMS.json regenerated (every 1.0.0 file except eboot.bin keeps its 1.0.0 hash).
2. evidence/release-link.log (NEW): the single release link-title.sh line of the build log, as freeze_release.py reads it.
3. freeze_release.py --name main-1.0.1 (new lock; releases/MAIN is NOT changed).
4. za reproduce main-1.0.1 + za check-proof: the frozen inputs relink the 1.0.1 PIE/eboot byte for byte.
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
BASE_PACKAGE = 'artifacts/randomizer-r29-ui-codex-20261031-01'


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
    res = json.loads((build / 'evidence/build-result.json').read_text())
    eboot = build / 'program/eboot.bin'
    assert sha(eboot) == res['eboot_sha256'] and sha(build / 'program/llvm-pie.elf') == res['pie_sha256']
    for f in ['tools/za/za.py', 'tools/za/freeze_release.py', 'tools/za/releases/main-1.0.0.lock.json']:
        assert sha(ZA_REPO / f) == sha(PROJECT / f), 'za tooling of the shared tree differs from this checkout: ' + f

    # 1. package
    src = ZA_REPO / BASE_PACKAGE
    dst = ZA_REPO / 'artifacts' / a.package_name
    if dst.exists():
        sys.exit('package exists: ' + str(dst))
    sums = json.loads((src / 'SHA256SUMS.json').read_text())
    bad = [r for r, d in sums.items() if sha(src / r) != d]
    assert not bad, bad
    dst.mkdir(parents=True)
    out = {}
    for rel in sums:
        (dst / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(eboot if rel == 'eboot.bin' else src / rel, dst / rel)
        out[rel] = sha(dst / rel)
    (dst / 'evidence-1.0.1').mkdir()
    for f in ['build-result.json', 'registration.json', 'image-preservation.json', 'self-inspection-release.txt',
              'symbols-added.txt', 'symbols-lost.txt', 'SHA256SUMS.txt']:
        shutil.copyfile(build / 'evidence' / f, dst / 'evidence-1.0.1' / f)
        out['evidence-1.0.1/' + f] = sha(dst / 'evidence-1.0.1' / f)
    assert out['eboot.bin'] == res['eboot_sha256']
    changed = sorted(r for r in sums if out[r] != sums[r])
    assert changed == ['eboot.bin'], changed
    (dst / 'SHA256SUMS.json').write_text(json.dumps(dict(sorted(out.items())), indent=2) + '\n')

    # 2. the release link line
    lines = (build / 'evidence/build.log').read_text(encoding='utf-8').splitlines()
    link = [l for l in lines if l.startswith('$ [') and 'link-title.sh' in l and str(build / 'program/llvm-pie.elf') in l]
    assert len(link) == 1, len(link)
    (build / 'evidence/release-link.log').open('x').write(link[0] + '\n')

    # 3. freeze
    release = {
        'version': '1.0.1', 'branch': 'main',
        'build': 'main-1.0.0 (r29-ui) + RomFS overlay-fd fix: runtime ipc.o, kernel.o, services/fs.o rebuilt; '
                 '61 runtime objects, the game archive and every extra input unchanged',
        'eboot_sha256': res['eboot_sha256'], 'pie_sha256': res['pie_sha256'],
        'base_release': 'main-1.0.0', 'base_eboot_sha256': res['base_eboot_sha256'],
        'builder': 'port/fd-fix/build-main-1.0.1.py + port/fd-fix/freeze-main-1.0.1.py',
        'runtime_repo': 'pokeza-recomp-ps5', 'runtime_main_commit': res['runtime_main_commit'],
        'runtime_branch': 'fd-fix', 'runtime_fix_commit': res['runtime_fix_commit'],
        'project_commit': a.project_commit, 'package': 'artifacts/' + a.package_name,
        'build_dir': str(build), 'hardware_verified': False,
        'hardware_note': 'Console gate pending (Tomer coordinates). releases/MAIN stays main-1.0.0 until it passes.',
        'overlay_fd_fix': True, 'hebrew_rtl': False,
        'host_test': 'tools/test_fs_overlay_fds.sh on fd-fix: PASS (2500 files, fd bound 64, 1024 limit)',
    }
    rj = build / 'evidence/release-1.0.1.json'
    rj.open('x').write(json.dumps(release, indent=2) + '\n')
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/freeze_release.py', '--name', 'main-1.0.1', '--tree', build,
                    '--link-log', 'evidence/release-link.log', '--extra', 'evidence/link-inputs.txt',
                    '--program', 'program', '--eboot-sha', res['eboot_sha256'], '--pie-sha', res['pie_sha256'],
                    '--delivered', '{repo}/artifacts/%s/eboot.bin' % a.package_name, '--frozen', a.frozen,
                    '--description', 'main 1.0.1 = main-1.0.0 (r29-ui) + overlay-fd fix (fs/ipc/kernel); '
                    'NOT hardware-verified; no RTL',
                    '--package-sums', '{repo}/artifacts/%s/SHA256SUMS.json' % a.package_name,
                    '--release-json', rj], check=True)

    # 4. reproduce from the frozen inputs
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/za.py', 'reproduce', 'main-1.0.1', '--out', a.reproduce], check=True)
    subprocess.run([sys.executable, ZA_REPO / 'tools/za/za.py', 'check-proof',
                    str(Path(a.reproduce) / 'main-1.0.1/proof.json')], check=True)
    print('main-1.0.1 frozen and reproduced; lock:', ZA_REPO / 'tools/za/releases/main-1.0.1.lock.json')


if __name__ == '__main__':
    main()
