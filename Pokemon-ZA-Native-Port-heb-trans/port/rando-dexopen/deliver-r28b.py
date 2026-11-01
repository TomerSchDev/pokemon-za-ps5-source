"""Assemble artifacts/randomizer-r28b-play from a finished r28b build.

    py -3 deliver-r28b.py <build dir: .../r28b> <docs dir with README-HE.md, INSTALL-HE.md, TEST-HE.md, MERGE-HE.md, BUILD-INFO.json>
                          [--extra-evidence <dir> ...] [--extra-file <file> ...]

Copies PPSA91762/eboot.bin (checked against the build's SHA256SUMS.txt), rollback/r28a-play/eboot.bin (5c6777ec...,
from artifacts/randomizer-r28a-play) and rollback/r28-play/eboot.bin (65f6745f..., from artifacts/randomizer-r28-play),
the build's evidence (text files only), the docs; writes SHA256SUMS.txt over every file. Refuses an existing destination.
Nothing is sent anywhere.
"""
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DEST = PROJECT / 'artifacts/randomizer-r28b-play'
R28A_EBOOT = PROJECT / 'artifacts/randomizer-r28a-play/PPSA91762/eboot.bin'
R28A_SHA = '5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea'
R28_EBOOT = PROJECT / 'artifacts/randomizer-r28-play/PPSA91762/eboot.bin'
R28_SHA = '65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
EVIDENCE = ['build.log', 'SHA256SUMS.txt', 'link-inputs.txt', 'runtime-inputs.txt', 'source-SHA256SUMS.txt', 'dexopen-sources.sha256',
            'defined-symbols.txt', 'imports.json', 'registration.json', 'image-preservation.json', 'image-checks.json', 'image-r28b.json',
            'r28b-callers.s', 'inputs.json', 'base-copy.json', 'dexopen-checks.json', 'dexopen-r28b-manifest.json',
            'self-inspection.txt', 'self-inspection-vs-r28a.diff',
            # the r28a build this one stands on (its own records, copied by build-r28b.sh)
            'r28a-SHA256SUMS.txt', 'r28a-link-inputs.txt', 'r28a-runtime-inputs.txt', 'r28a-image-checks.json', 'r28a-final-image.json',
            'r28a-final-inputs.json', 'r28a-dexcount-checks.json', 'r28a-dexcount-HANDOFF.json', 'r28a-source-SHA256SUMS.txt']
EVIDENCE_OPTIONAL = ['reproducibility.json', 'repro-build-2.log']
EVIDENCE_DIRS = ['dexopen']  # (the apply script's own evidence folder)


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def place(src, dst):
    """The rollback eboots already exist in artifacts/ on the same NTFS volume: hard-link them (same bytes, no extra
    space); fall back to a copy where a link is not possible. The package's own eboot is always a copy."""
    try:
        os.link(src, dst)
        return 'hardlink'
    except OSError:
        shutil.copyfile(src, dst)
        return 'copy'


def main():
    build, docs = Path(sys.argv[1]), Path(sys.argv[2])
    args = sys.argv[3:]
    extra_dirs = [Path(args[i + 1]) for i, a in enumerate(args) if a == '--extra-evidence']
    extra_files = [Path(args[i + 1]) for i, a in enumerate(args) if a == '--extra-file']
    if DEST.exists():
        sys.exit('refusing: %s exists' % DEST)
    sums = dict(line.split()[::-1] for line in (build / 'evidence/SHA256SUMS.txt').read_text().splitlines() if line.strip())
    eboot = build / 'eboot.bin'
    want = next(v for k, v in sums.items() if k.endswith('/eboot.bin'))
    assert sha(eboot) == want, 'eboot.bin does not match the build record'
    assert sha(R28A_EBOOT) == R28A_SHA, "r28a-play's eboot.bin in artifacts does not match"
    assert sha(R28_EBOOT) == R28_SHA, "r28-play's eboot.bin in artifacts does not match"
    free = shutil.disk_usage(PROJECT).free
    if free < eboot.stat().st_size + 64 * 1024 * 1024:
        sys.exit('refusing: %d MB free on the artifacts volume, the package eboot needs %d MB (+ the small files); nothing written'
                 % (free // 2**20, eboot.stat().st_size // 2**20))
    (DEST / 'PPSA91762').mkdir(parents=True)
    shutil.copyfile(eboot, DEST / 'PPSA91762/eboot.bin')
    (DEST / 'rollback/r28a-play').mkdir(parents=True)
    how_a = place(R28A_EBOOT, DEST / 'rollback/r28a-play/eboot.bin')
    (DEST / 'rollback/r28-play').mkdir(parents=True)
    how_b = place(R28_EBOOT, DEST / 'rollback/r28-play/eboot.bin')
    (DEST / 'evidence').mkdir()
    for name in EVIDENCE:
        shutil.copyfile(build / 'evidence' / name, DEST / 'evidence' / name)
    for name in EVIDENCE_OPTIONAL:
        if (build / 'evidence' / name).is_file():
            shutil.copyfile(build / 'evidence' / name, DEST / 'evidence' / name)
    for name in EVIDENCE_DIRS:
        shutil.copytree(build / 'evidence' / name, DEST / 'evidence' / name)
    for d in extra_dirs:
        shutil.copytree(d, DEST / 'evidence' / d.name)
    for f in extra_files:
        shutil.copyfile(f, DEST / 'evidence' / f.name)
    for name in ('README-HE.md', 'INSTALL-HE.md', 'TEST-HE.md', 'MERGE-HE.md', 'BUILD-INFO.json'):
        shutil.copyfile(docs / name, DEST / name)
    assert sha(DEST / 'PPSA91762/eboot.bin') == want
    assert sha(DEST / 'rollback/r28a-play/eboot.bin') == R28A_SHA and sha(DEST / 'rollback/r28-play/eboot.bin') == R28_SHA
    files = sorted(p for p in DEST.rglob('*') if p.is_file())
    with (DEST / 'SHA256SUMS.txt').open('w', encoding='utf-8', newline='\n') as f:  # (LF: sha256sum -c reads it)
        f.write(''.join('%s  %s\n' % (sha(p), p.relative_to(DEST).as_posix()) for p in files))
    print(json.dumps(dict(destination=str(DEST), files=len(files) + 1, eboot_sha256=want,
                          rollback_r28a=how_a, rollback_r28=how_b), indent=1))


if __name__ == '__main__':
    main()
