"""Recover the existing fifty-species QA window with durable, verified checkpoints."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib, json, re, sys, time
from console_fifty_live import OUT, LOCAL, APP, STATE, api, lease_guard, guard

REV = 'resume-20261031-r2'
DEST = OUT / REV
BASE_SHA = '8e4280f0da65ec3d00cb77b559833f1e9c6e427009e79ec15b0fab45fbf5dc7e'
FIX_SHA = '4b4d1b502e217a578b687c2e5016d718b0c95c246f69c6b78d4187f9f25c10b4'

def now(): return datetime.now(timezone.utc).isoformat()
def sha(path):
    with path.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def record(name, data):
    DEST.mkdir(parents=True, exist_ok=True)
    path = DEST / name
    if path.exists(): raise FileExistsError(path)
    path.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(json.dumps({'checkpoint': name, **data}), flush=True)
    return path
def readback(c, remote, relative):
    lease_guard()
    path = DEST / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    assert not path.exists(), path
    digest = hashlib.sha256()
    with path.open('xb') as stream:
        def receive(block): digest.update(block); stream.write(block)
        c.ftp.retrbinary('RETR ' + remote, receive, 1 << 20)
    result = {'remote': remote, 'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest.hexdigest()}
    assert sha(path) == result['sha256']
    return result
def require_closed():
    lease_guard()
    assert not api.eboot_processes(), 'A title is running.'
def backup(c, data):
    # download0 exists only while the title is mounted. Back up in its idle
    # launcher, before continuing the game, then close it for replacement.
    state = json.loads(STATE.read_text())
    guard(c, state)
    for name in c.listing(data + '/observer/session_' + state['session']):
        if name.startswith('ack_'):
            ack = json.loads(c.read(data + '/observer/session_' + state['session'] + '/' + name, 4096))
            assert ack.get('op') != 'continue', 'Backup requires a fresh idle launcher.'
    root = data + '/rando'
    active = c.read(root + '/active.json', 16384)
    assert active
    rows, runs = [], []
    def walk(remote, relative, depth=0):
        assert depth < 6
        c.ftp.cwd(remote)
        items = list(c.ftp.mlsd())
        c.ftp.cwd('/')
        for name, facts in items:
            if name in ('.', '..'): continue
            assert '/' not in name and '\\' not in name
            if facts.get('type') == 'dir': walk(remote + '/' + name, relative / name, depth + 1)
            elif facts.get('type') not in ('cdir', 'pdir'):
                row = readback(c, remote + '/' + name, Path('backup') / relative / name)
                assert c.sha256(row['remote']) == row['sha256'], 'Save changed during backup'
                rows.append(row)
    for name in c.listing(root):
        if not re.fullmatch('r[0-9a-f]+-[0-9a-f]+', name): continue
        if c.read(root + '/' + name + '/save/save_0/main', 16 << 20) is None: continue
        runs.append(name)
        walk(root + '/' + name + '/save', Path(name) / 'save')
        report = c.read(root + '/' + name + '/report.json', 16 << 20)
        if report:
            row = readback(c, root + '/' + name + '/report.json', Path('backup') / name / 'report.json')
            assert c.sha256(row['remote']) == row['sha256']
            rows.append(row)
    assert runs and json.loads(active)['id'] in runs
    row = readback(c, root + '/active.json', 'backup/active.json')
    assert Path(row['path']).read_bytes() == active == c.read(root + '/active.json', 16384)
    rows.append(row)
    return record('save-backup.json', {'utc': now(), 'all_runs': True, 'readback_verified': True,
        'active': json.loads(active), 'run_ids': runs, 'files': rows})

def install():
    lease_guard()
    assert not (DEST / 'deployment.json').exists(), 'Deployment already recorded; inspect rather than reinstall.'
    state = json.loads(STATE.read_text())
    identity = json.loads((OUT / 'trial-identity.json').read_text())
    source = OUT / 'mod-file-handles-build-20261031-r1/eboot.bin'
    assert sha(source) == FIX_SHA
    c = api.Console()
    try:
        guard(c, state)
        active = json.loads(c.read(state['data'] + '/rando/active.json', 16384))
        assert active['id'] == identity['run'], 'Only the existing QA run may be used.'
        record('takeover-mounted-launcher.json', {'utc': now(), 'user_requested_recovery_of_previous_agent': True,
            'owned_session': state, 'active_qa_run': active, 'processes': api.eboot_processes(),
            'existing_lease_continued': True, 'fix_source': str(source), 'fix_sha256': FIX_SHA})
        backup_path = backup(c, state['data'])
        guard(c, state)
        print(json.dumps(api.http_json('/process_kill?pid=%d' % state['pid'])), flush=True)
        deadline = time.monotonic() + 20
        while api.eboot_processes():
            assert time.monotonic() < deadline
            time.sleep(.3)
        require_closed()
        before = readback(c, APP + '/eboot.bin', 'eboot-before.bin')
        record('base-readback.json', before)
        assert before['sha256'] == BASE_SHA, 'Installed build changed: a new merge is required.'
        staged_remote = APP + '/eboot.fd-fix-20261031-r2.part'
        old_remote = APP + '/eboot.before-fd-fix-20261031-r2.bin'
        assert c.read(staged_remote, 1) is None
        assert c.read(old_remote, 1) is None
        require_closed()
        with source.open('rb') as stream: c.ftp.storbinary('STOR ' + staged_remote, stream, 1 << 20)
        staged = readback(c, staged_remote, 'eboot-staged.bin')
        record('staged-readback.json', staged)
        assert staged['sha256'] == FIX_SHA
        require_closed()
        c.ftp.rename(APP + '/eboot.bin', old_remote)
        try: c.ftp.rename(staged_remote, APP + '/eboot.bin')
        except Exception:
            c.ftp.rename(old_remote, APP + '/eboot.bin')
            raise
        installed = readback(c, APP + '/eboot.bin', 'eboot-installed.bin')
        assert installed['sha256'] == FIX_SHA
        assert c.sha256(old_remote) == BASE_SHA
        require_closed()
        record('deployment.json', {'utc': now(), 'console': api.HOST, 'title': 'PPSA91762',
            'base': before, 'staged': staged, 'installed': installed,
            'previous_executable_preserved_remote': old_remote,
            'save_backup': str(backup_path), 'save_backup_sha256': sha(backup_path),
            'only_executable_replaced': True, 'user_saves_modified': False,
            'console_installed': True, 'gameplay_verified': False})
    finally: c.close()

if __name__ == '__main__':
    assert sys.argv[1] == 'install'
    install()
