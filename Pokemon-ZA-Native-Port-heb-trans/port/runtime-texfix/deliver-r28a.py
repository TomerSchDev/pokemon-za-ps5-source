"""Assemble artifacts/randomizer-r28a-play from a finished r28a build (FINAL step - after the dexcount layer).

    py -3 deliver-r28a.py <build dir: .../r28a> <docs dir with README-HE.md, INSTALL-HE.md, TEST-HE.md, BUILD-INFO.json>
                          [--extra-evidence <dir> ...]

Copies PPSA91762/eboot.bin (checked against the build's SHA256SUMS.txt), rollback/r28-play/eboot.bin (r28-play's,
65f6745f..., from artifacts/randomizer-r28-play), the build's evidence (text files only), the docs; writes
SHA256SUMS.txt over every file. Refuses an existing destination. Nothing is sent anywhere.
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
DEST = PROJECT / 'artifacts/randomizer-r28a-play'
R28_EBOOT = PROJECT / 'artifacts/randomizer-r28-play/PPSA91762/eboot.bin'
R28_SHA = '65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
EVIDENCE = ['build.log', 'SHA256SUMS.txt', 'link-inputs.txt', 'runtime-inputs.txt', 'source-SHA256SUMS.txt',
            'defined-symbols.txt', 'imports.json', 'registration.json', 'image-preservation.json', 'image-checks.json',
            'self-inspection.txt', 'self-inspection-vs-candidate.diff',
            # the texfix candidate this build stands on (its control, inputs, patch)
            'candidate-control.txt', 'candidate-inputs.json', 'candidate-image-checks.json', 'candidate-apply.txt',
            'candidate-patched-objects.sha256', 'candidate-runtime-texfix.patch', 'candidate-SHA256SUMS.txt',
            'candidate-r28-SHA256SUMS.txt',
            # dexcount on top, and the final checks
            'dexcount-HANDOFF.json', 'dexcount-sources.sha256', 'dexcount-checks.json', 'dexcount-r28a-manifest.json',
            'final-inputs.json', 'final-image.json']
EVIDENCE_DIRS = ['dexcount']  # (the apply script's own evidence folder)


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def main():
    build, docs = Path(sys.argv[1]), Path(sys.argv[2])
    extra = [Path(p) for p in sys.argv[sys.argv.index('--extra-evidence') + 1:]] if '--extra-evidence' in sys.argv else []
    if DEST.exists():
        sys.exit('refusing: %s exists' % DEST)
    sums = dict(line.split()[::-1] for line in (build / 'evidence/SHA256SUMS.txt').read_text().splitlines() if line.strip())
    eboot = build / 'eboot.bin'
    want = sums[str(eboot)] if str(eboot) in sums else next(v for k, v in sums.items() if k.endswith('/eboot.bin'))
    assert sha(eboot) == want, 'eboot.bin does not match the build record'
    assert sha(R28_EBOOT) == R28_SHA, "r28-play's eboot.bin in artifacts does not match"
    (DEST / 'PPSA91762').mkdir(parents=True)
    shutil.copyfile(eboot, DEST / 'PPSA91762/eboot.bin')
    (DEST / 'rollback/r28-play').mkdir(parents=True)
    shutil.copyfile(R28_EBOOT, DEST / 'rollback/r28-play/eboot.bin')
    (DEST / 'evidence').mkdir()
    for name in EVIDENCE:
        shutil.copyfile(build / 'evidence' / name, DEST / 'evidence' / name)
    for name in EVIDENCE_DIRS:
        shutil.copytree(build / 'evidence' / name, DEST / 'evidence' / name)
    for d in extra:
        shutil.copytree(d, DEST / 'evidence' / d.name)
    for name in ('README-HE.md', 'INSTALL-HE.md', 'TEST-HE.md', 'MERGE-HE.md', 'BUILD-INFO.json'):
        shutil.copyfile(docs / name, DEST / name)
    assert sha(DEST / 'PPSA91762/eboot.bin') == want and sha(DEST / 'rollback/r28-play/eboot.bin') == R28_SHA
    files = sorted(p for p in DEST.rglob('*') if p.is_file())
    with (DEST / 'SHA256SUMS.txt').open('w', encoding='utf-8', newline='\n') as f:  # (LF: sha256sum -c reads it)
        f.write(''.join('%s  %s\n' % (sha(p), p.relative_to(DEST).as_posix()) for p in files))
    print(json.dumps(dict(destination=str(DEST), files=len(files) + 1, eboot_sha256=want), indent=1))


if __name__ == '__main__':
    main()
