"""Read-only completion evidence when play changes the run during installation.

Never sends controller/observer commands, kills a process, or writes console files.
The original fixed-run acceptance remains incomplete and is not fabricated.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('r28installer', ROOT / 'port/perf-r28/install-r28.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
h, i = m.h, m.i


def read_status(c, path):
    data = bytearray()
    try:
        def append(chunk):
            data.extend(chunk)
            assert len(data) <= 65536
        c.ftp.retrbinary('RETR ' + path, append)
        return dict(readable=True, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
    except h.ftplib.error_perm as error:
        return dict(readable=False, error=str(error))


def main():
    out = Path(sys.argv[1]).resolve()
    assert out.parent == ROOT / 'evidence' and out.name.startswith('r28-hardware-')
    h.OUT = out
    state = i.readstate()
    assert state['requested_sha256'] == m.NEW and state['initial_eboot_sha256'] == m.OLD
    c = h.r.Console()
    try:
        h.title(c)
        processes = h.r.eboot_processes()
        assert len(processes) == 1 and h.r.process_pid(processes[0]) == state['current']['pid']
        sid = h.client.status(c.ftp)['session']
        assert sid == state['current']['session']
        assert c.sha256(h.APP + '/eboot.bin') == m.NEW
        current_bytes = c.read(h.DATA + '/active.json', 4096)
        current = json.loads(current_bytes)['id']
        assert re.fullmatch('[a-z0-9-]{1,80}', current)
        backups = json.loads((out / 'save-backup/verification.json').read_text())
        checks = []
        for f in backups['files']:
            actual = c.sha256(h.DATA + '/' + backups['run'] + '/' + f['path'])
            assert actual == f['sha256'], 'Original backed-up run changed'
            checks.append(dict(path=f['path'], run=backups['run'], sha256=actual, unchanged=True))
        for name, text in state['initial_configs'].items():
            assert c.read(h.APP + '/' + name, 4096) == text.encode(), name
        preferences = {}
        for name, remote in [('cheats.txt', h.DATA + '/' + backups['run'] + '/cheats.txt'),
                             ('player-name.txt', h.DATA + '/player-name.txt')]:
            result = read_status(c, remote)
            expected = state['save_extras'][name]
            result['matches_before'] = result.get('sha256') == (expected or {}).get('sha256')
            preferences[name] = result
        source_manifest = h.APP + '/hebrew-trial-assets-r1/trial-manifest.json'
        hebrew = {path: read_status(c, path) for path in state['initial_hebrew_state']}
        assert hebrew[source_manifest]['sha256'] == state['initial_hebrew_state'][source_manifest]['sha256']
        log = (out / 'all.klog.log').read_bytes()[state['current']['klog_offset']:].decode('utf-8', 'replace')
        assert '[za-title-randomizer-r28-play] main reached' in log
        assert 'ZA Recomp v0.1.4-local202-ps5-title-randomizer-r28-play' in log
        assert '[za-randomizer] boot selected run=' + current in log
        assert 'existing_disabled_verified result=1 reason=none files=20' in log
        assert '[za-hebrew-trial] installer ready; mode=0' in log
        baseline_log = (out / 'r26p1-latest-save-backup/boot.klog.log').read_text(encoding='utf-8')
        assert 'existing_disabled_verified result=1 reason=none files=20' in baseline_log
        assert '[za-hebrew-trial] installer ready; mode=0' in baseline_log
        frame_lines = [line for line in log.splitlines() if '[vk] t=' in line][-4:]
        assert frame_lines
        assert c.read(h.DATA + '/active.json', 4096) == current_bytes
        assert h.client.status(c.ftp)['session'] == sid
        receipt = dict(at=h.r.utc_now(), installed=True, version='r28-play', installed_sha256=m.NEW,
                       previous_sha256=m.OLD, only_replaced=['eboot.bin'], running_pid=state['current']['pid'],
                       session=sid, current_run=current, original_run=backups['run'], original_save_checks=checks,
                       original_run_preferences=preferences, configuration_files_unchanged=True,
                       hebrew_checks=hebrew, ini_check=read_status(c, i.hw.INI),
                       hebrew_runtime_verified_twice=dict(files=20, mode='disabled', existing_pack=True),
                       source_hebrew_manifest_unchanged=True,
                       current_run_changed_during_test=current != backups['run'],
                       fixed_run_30fps_acceptance_completed=False, hardware_items_add_save_reload_verified=False,
                       user_confirmation_of_new_run_pending=True, alpha_enabled=False,
                       loaded_game_and_advancing_frames=True, latest_runtime_frame_lines=frame_lines,
                       rollback_performed=False, automation_suspended=True,
                       note='Run changed before automated Continue, so no controller command or rollback was executed. '
                            'Current-play log windows are not a fixed-scene FPS benchmark. FTP permission errors '
                            'do not prove missing/unchanged files; Hebrew verification uses both runtime checks.')
        h.write(out / 'installation-observed.json', receipt)
        h.write(out / 'automation-suspended.json', dict(at=h.r.utc_now(), current_run=current,
                reason='Active run changed; do not resume original fixed-run automation or rollback.'))
        print(json.dumps(dict(installed=True, original_save_unchanged=True, configuration_files_unchanged=True,
                              current_run=current, loaded_game=True, acceptance='observational, fixed-run test interrupted')))
    finally:
        c.close()


if __name__ == '__main__':
    main()
