"""Scoped r28 installer over the exact r27b Hebrew-trial baseline.

Reuses the exercised r27b transaction, current-save backup and observer helpers.
Only PPSA91762/eboot.bin is replaced. No save, Hebrew pack or setting is written.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'port/perf-r27'))
import install_r27 as previous
i, h = previous.i, previous.h
OLD = 'cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618'
NEW = '65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
previous.BASE_SHA = OLD
base_startup = previous.startup


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def configure(package):
    package = package.resolve()
    record = json.loads((package / 'BUILD-INFO.json').read_text(encoding='utf-8'))
    assert record['revision'] == 'randomizer-r28-play' and record['title_id'] == 'PPSA91762'
    assert record['eboot_sha256'] == NEW and record['latest_hebrew_trial_baseline_sha256'] == OLD
    hashes = {}
    for line in (package / 'SHA256SUMS.txt').read_text().splitlines():
        digest, rel = line.split(None, 1)
        path = (package / rel).resolve()
        assert re.fullmatch('[0-9a-f]{64}', digest) and path.is_relative_to(package)
        assert sha(path) == digest, rel
        hashes[rel] = digest
    assert hashes['PPSA91762/eboot.bin'] == NEW
    proof = json.loads((package / 'evidence/pc-proof.json').read_text())
    assert all(proof[k] for k in ('items_verified', 'save_verified', 'reload_verified', 'cap_verified'))
    assert proof['alpha']['enabled'] is False and record['alpha']['enabled'] is False
    assert record['items']['count'] == 199
    for rel, digest in proof['source_hashes'].items():
        path = (ROOT / 'port/cheats-r28' / rel).resolve()
        assert path.is_relative_to(ROOT / 'port/cheats-r28') and sha(path) == digest, rel
    audit = json.loads((package / 'evidence/final-audit.json').read_text())
    assert audit['eboot_sha256'] == NEW
    assert all(audit[k] is True for k in ('hebrew_objects_byte_identical', 'pc_ps5_item_helper_sources_identical',
                                        'observer_aware_launcher_call_preserved'))
    i.OLD, i.NEW, i.CHANGED = OLD, NEW, ('eboot.bin',)
    i.SOURCE = package / 'PPSA91762'
    i.startup = startup
    return dict(version='r28-play', eboot_sha256=NEW, base_eboot_sha256=OLD,
                build_info=record, pc_items_proof=proof, package_hashes=hashes, final_audit=audit)


def hebrew_state(c):
    data = h.SANDBOX + '/download0/zarecomp'
    paths = [h.APP + '/hebrew-trial-assets-r1/trial-manifest.json',
             h.APP + '/hebrew-trial-force-off-r1.txt',
             data + '/hebrew-trial-install-r1.json', data + '/hebrew-trial-reload.json',
             data + '/mods/000-hebrew-trial/trial-manifest.json',
             data + '/mods/_000-hebrew-trial/trial-manifest.json']
    result = {}
    for path in paths:
        content = bytearray()
        try:
            def append(chunk):
                content.extend(chunk)
                assert len(content) <= 65536
            c.ftp.retrbinary('RETR ' + path, append)
            result[path] = dict(readable=True, bytes=len(content), sha256=i.hw.digest(content))
        except h.ftplib.error_perm as error:
            # Permission denied is not evidence that a file is missing.
            result[path] = dict(readable=False, error=str(error))
    return result


def init(c, receipt):
    close_original = i.hw.close
    def capture_then_close(console, state):
        state['initial_hebrew_state'] = hebrew_state(console)
        assert state['initial_hebrew_state'][h.APP + '/hebrew-trial-assets-r1/trial-manifest.json']['readable']
        i.save(state)
        h.write(h.OUT / 'hebrew-before.json', state['initial_hebrew_state'])
        i.nas_copy(h.OUT / 'hebrew-before.json')
        close_original(console, state)
    i.hw.close = capture_then_close
    try:
        previous.init(c, receipt)
    finally:
        i.hw.close = close_original


def startup(state):
    base_startup(state)
    log = i.hw.bootlog(state)
    assert '[za-r26] dyn=off' in log and '[za-r24-options] ticks=tsc' in log
    assert 'randomizer-r28-play' in log
    result = json.loads((h.OUT / 'startup-verification.json').read_text())
    result.update(dyn_off=True, ticks_tsc=True, items_pc_proof_verified=True,
                  items_interaction_hardware_verified=False, alpha_enabled=False,
                  hebrew_log=[line for line in log.splitlines() if '[za-hebrew-' in line])
    h.write(h.OUT / 'startup-verification.json', result)


previous.startup = startup


def complete(c, state):
    h.owned(c, state)
    assert state['smoke_test_passed'] and not state.get('rolled_back')
    assert c.sha256(h.APP + '/eboot.bin') == NEW
    for name, content in state['initial_configs'].items():
        assert c.read(h.APP + '/' + name, 4096) == content.encode(), name
    assert c.read(i.hw.INI, 65536) == (None if state['initial_ini'] is None else state['initial_ini'].encode())
    for name, remote in [('active.json', h.DATA + '/active.json'),
                         ('cheats.txt', h.DATA + '/' + state['current']['run'] + '/cheats.txt'),
                         ('player-name.txt', h.DATA + '/player-name.txt')]:
        data = c.read(remote, 65536)
        expected = state['save_extras'][name]
        assert (None if data is None else i.hw.digest(data)) == (None if expected is None else expected['sha256']), name
    hebrew = hebrew_state(c)
    assert hebrew == state['initial_hebrew_state'], 'Hebrew state changed'
    h.write(h.OUT / 'hebrew-after.json', hebrew)
    saves = h.verify_save(c, state)
    startup(state)
    visual = json.loads((h.OUT / 'visual-review.json').read_text())
    assert visual['no_obvious_corruption'] and visual['gameplay_loaded']
    result = dict(at=h.r.utc_now(), installed=True, version='r28-play', installed_sha256=NEW,
                  previous_sha256=OLD, only_replaced=['eboot.bin'], save_check=saves,
                  configs_unchanged=True, ini_unchanged=True, active_run_and_preferences_unchanged=True,
                  hebrew_metadata_observation_unchanged=True,
                  hebrew_file_hash_verification_complete=all(v.get('readable') for v in hebrew.values()),
                  smoke_test=json.loads((h.OUT / '30fps-verification.json').read_text()),
                  package_verification=state['package_verification'], visual_review=visual,
                  hardware_items_add_save_reload_verified=False, alpha_enabled=False,
                  application_running=True, nas=str(i.hw.NAS))
    h.write(h.OUT / 'installation.json', result)
    state['installation_complete'] = True
    i.save(state)
    for name in ('installation.json', 'transaction.json', 'startup-verification.json',
                 '30fps-verification.json', 'hebrew-after.json', 'visual-review.json', 'state.json'):
        i.nas_copy(h.OUT / name)
    i.emit(dict(stage='r28 installed, current save/configs/Hebrew preserved, NAS receipts verified', sha256=NEW))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', required=True, type=Path)
    p.add_argument('--package', type=Path, default=ROOT / 'artifacts/randomizer-r28-play')
    p.add_argument('op', choices=('log', 'init', 'install', 'ready', 'measure', 'complete', 'rollback'))
    a = p.parse_args()
    h.OUT = a.out.resolve()
    assert h.OUT.parent == ROOT / 'evidence' and h.OUT.name.startswith('r28-hardware-')
    h.OUT.mkdir(exist_ok=True)
    i.hw.NAS = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port') / h.OUT.name
    if a.op == 'log':
        i.hw.logger(h.OUT)
        return
    assert not (h.OUT / 'automation-suspended.json').exists(), 'Run changed during testing; inspect current play and use a fresh workflow instead of resuming old automation'
    if a.op == 'rollback':
        previous.configure_rollback(i.readstate())
        receipt = None
    else:
        receipt = configure(a.package)
    c = h.r.Console()
    try:
        if a.op == 'init':
            init(c, receipt)
        else:
            state = i.readstate()
            assert state['requested_sha256'] == NEW and state['initial_eboot_sha256'] == OLD
            if a.op == 'install': previous.install(c, state)
            elif a.op == 'ready': i.ready(c, state)
            elif a.op == 'measure': i.measure(c, state)
            elif a.op == 'complete': complete(c, state)
            elif a.op == 'rollback': previous.rollback(c, state, 'Requested r28 rollback')
    except Exception as error:
        h.write(h.OUT / ('error-' + h.r.stamp() + '.json'),
                dict(at=h.r.utc_now(), op=a.op, type=type(error).__name__, error=str(error)))
        if (h.OUT / 'state.json').exists():
            state = i.readstate()
            if state.get('transaction_started_at') and not state.get('installation_complete') and a.op not in ('complete', 'rollback'):
                previous.rollback(c, state, str(error))
        raise
    finally:
        c.close()


if __name__ == '__main__':
    main()
