"""Assemble an r29-music package from a verified WSL build, the host tests and the PC proof.
No console access, no NAS copy, no game data (no BGM.bnk, no plan JSON, no audio) in the package.
Usage: prepare-r29-delivery.py OUT_NAME BUILD_DIR HOST_TEST_DIR MENU_TEST_LOG PC_PROOF.json READS_DIR VANILLA.json BASE_LABEL
  OUT_NAME   artifacts/<OUT_NAME> (must be new), e.g. randomizer-r29-music-on-r28
  BUILD_DIR  \\\\wsl.localhost\\Ubuntu\\home\\tomer\\ps5-za-native\\r29-music-...\\r29
  BASE_LABEL r28-play | r28a-play | r27b-play (recorded in BUILD-INFO with the base eboot SHA-256 from the build log)
"""
import datetime
import hashlib
import json
import re
import shutil
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[2]
music = root / 'port/rando-music'
out_name, build, host, menu_log, proof_path, reads, vanilla, base_label = sys.argv[1:9]
build, host, menu_log, proof_path, reads, vanilla = map(Path, (build, host, menu_log, proof_path, reads, vanilla))
out = root / 'artifacts' / out_name
assert not out.exists(), 'destination must be new'
R28 = '65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
R27B = 'c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153'
HEB = 'cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618'


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def copy(src, rel):
    target = out / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    assert sha(src) == sha(target), rel
    return target


proof = json.loads(proof_path.read_text(encoding='utf-8'))
assert proof['verdict'] == 'pass' and all(c['ok'] for c in proof['checks']), 'PC proof must pass'
for n in ['objects.json', 'registration.json', 'imports.json', 'linked-calls.json', 'image-preservation.json',
          'controls.txt', 'SHA256SUMS.txt', 'self-inspection.txt', 'build.log', 'base-before.txt', 'base-after.txt']:
    assert (build / 'evidence' / n).is_file(), n
assert (build / 'evidence/base-before.txt').read_bytes() == (build / 'evidence/base-after.txt').read_bytes()
controls = (build / 'evidence/controls.txt').read_text()
assert controls.count('byte-identical') == 3, controls
host_log = (host / 'host-tests.log').read_text(encoding='utf-8')
assert '== all r29-music host tests passed' in host_log
assert 'PASS: real menu source on host' in menu_log.read_text(encoding='utf-8')
build_log = (build / 'evidence/build.log').read_text(encoding='utf-8', errors='replace')
assert 'candidate built and verified' in build_log
copy(build / 'eboot.bin', 'PPSA91762/eboot.bin')
for src in sorted((build / 'evidence').iterdir()):
    if src.is_file() and src.suffix in ('.json', '.txt', '.log') and src.name != 'defined-symbols.txt':
        copy(src, 'evidence/build/' + src.name)
copy(host / 'host-tests.log', 'evidence/host-tests.log')
copy(menu_log, 'evidence/menu-host-test.log')
copy(proof_path, 'evidence/pc-proof.json')
copy(vanilla, 'evidence/pc/vanilla-summary.json')
for src in sorted(reads.glob('music-reads-*.txt')):
    copy(src, 'evidence/pc/' + src.name)
for run in proof['runs']:
    rd = Path(run['dir'])
    copy(rd / 'run.json', 'evidence/pc/%s-run.json' % run['name'])
    for png in run.get('screenshots', [])[-2:]:
        copy(rd / png, 'evidence/pc/%s-%s' % (run['name'], Path(png).name))
eboot = sha(out / 'PPSA91762/eboot.bin')
pie = sha(build / 'llvm-pie.elf')
objects = json.loads((build / 'evidence/objects.json').read_text())
plan_sha = proof['plan_sha256']
head = build_log.splitlines()[0]
info = dict(
    revision='randomizer-r29-music', package=out_name, created_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
    title_id='PPSA91762', game_version='2.0.2 + Mega Dimension', eboot_sha256=eboot, llvm_pie_sha256=pie,
    base=dict(label=base_label, build_log_head=head,
              eboot_sha256=R28 if base_label == 'r28-play' else None,
              note='candidate on r28-play (r27b + ITEMS page + HEBREW TRIAL); every menu and cheat row is kept. '
                   'The final base is r28a-play: rebuild with build-r29-music.sh PLAN PLAN_SHA tree=<r28a work tree> '
                   'and R29_BASE_OUT / R29_BASE_ARCHIVE / R29_BASE_REV / R29_BASE_EBOOT_SHA256 / R29_BASE_ARCHIVE_SHA256.'),
    music=dict(algorithm='za202-bgm-leaf-shuffle-v1', plan_sha256=plan_sha, modes=['off', 'category', 'chaos'],
               default='off', categories=proof['categories'], slots=proof['slots'],
               file='romfs/audio/wwise/bin/Switch/BGM.bnk inside the run folder (report: native_music)',
               unchanged=['story/event music', 'cutscene (demo) music', 'ST/NET', 'VS_BOSS_03 adaptive',
                          'victory loops', 'silence', 'loops under 30 s', 'songs with user cues (city intro)',
                          'direct event Play targets incl. battle-BGM select', 'ME.bnk jingles/fanfares']),
    objects=objects, controls=controls.strip().splitlines(), console_access_performed=False, console_tested=False,
    real_saves_written=False, game_data_in_package=False,
    host_tests=[l for l in host_log.splitlines() if l.startswith('PASS')] +
               [l for l in menu_log.read_text(encoding='utf-8').splitlines() if l.startswith('PASS')],
    pc_proof=dict(verdict=proof['verdict'], summary=proof['summary'], checks=len(proof['checks']),
                  runtime_sha256=proof['runtime_sha256']),
    installation='eboot replacement only (no asset files), by the console operator with the game closed',
    rollback=dict(r28=R28, r27b=R27B, r27b_hebrew_trial=HEB, note='restore the eboot backed up right before installing'))
(out / 'BUILD-INFO.json').write_text(json.dumps(info, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
subs = dict(EBOOT=eboot, R28=R28, R27B=R27B, HEB=HEB, PLAN=plan_sha)
for name in ('README-HE.md', 'INSTALL-HE.md', 'TEST-HE.md'):
    text = (music / 'delivery' / name).read_text(encoding='utf-8')
    for k, v in subs.items():
        text = text.replace('{{%s}}' % k, v)
    assert not re.search(r'\{\{[A-Z0-9]+\}\}', text), name
    (out / name).write_text(text, encoding='utf-8', newline='\n')
lines = ['%s  %s' % (sha(p), p.relative_to(out).as_posix()) for p in sorted(out.rglob('*')) if p.is_file()]
(out / 'SHA256SUMS.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8', newline='\n')
print('package', out)
print('eboot', eboot)
