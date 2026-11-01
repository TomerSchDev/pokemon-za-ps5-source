"""The known PRX-load failure only; exact FS launch/PID/app/title provenance.

Reuses the existing prebuilt close_failed_side payload and canonical sender.
No guess, PID discovery by name alone, upload, install, save write or SDK build.
"""
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.error


def manifest(config, driver, installer, job):
    reference = config['cleanup_manifest']
    installer.queue.evidence_file(reference, Path(config['repo']))
    if reference not in job.get('external_dependencies', []):
        raise ValueError('Exact cleanup manifest is not declared by this immutable job')
    record = driver.read(reference['path'])
    if record.get('title') != driver.TITLE or record.get('dynamic_identity') is not True:
        raise ValueError('Cleanup is not the prebuilt dynamic FS helper')
    if record.get('app_id') is not None or record.get('pid') is not None:
        raise ValueError('Dynamic helper must not bake in an old app/PID')
    installer.queue.evidence_file(record['payload'], Path(reference['path']).parent)
    installer.queue.evidence_file(record['source'], Path(reference['path']).parent)
    if Path(record['payload']['path']).name != 'close-failed-side.elf':
        raise ValueError('Unexpected cleanup payload')
    installed = [r for r in job['artifacts'] if r['remote_path'] == driver.APP + '/close-failed-side.elf']
    if (len(installed) != 1 or installed[0]['sha256'] != record['payload']['sha256']
            or Path(installed[0]['path']).resolve() != Path(record['payload']['path']).resolve()):
        raise ValueError('Cleanup ELF is not the exact declared ninth side artifact')
    return record


def identify(c, config, driver, installer, job, out, startup_offset):
    """Return no identity without ALL evidence of this single failed launch."""
    manifest(config, driver, installer, job)
    processes = installer.api.eboot_processes()
    if len(processes) != 1:
        raise RuntimeError('No unique fresh failed process; no automatic cleanup')
    pid = installer.api.process_pid(processes[0])
    param = c.read(driver.SANDBOX + '/app0/sce_sys/param.json', 65536)
    if param is None or json.loads(param).get('titleId') != driver.TITLE:
        raise RuntimeError('Failed process is not mounted as the FS side title')
    pins = {r['remote_path']: r['sha256'] for r in job['artifacts']}
    param_sha = hashlib.sha256(param).hexdigest()
    if param_sha != pins[driver.APP + '/sce_sys/param.json']:
        raise RuntimeError('Failed mounted param differs')
    eboot = c.sha256(driver.APP + '/eboot.bin')
    if eboot != pins[driver.APP + '/eboot.bin']:
        raise RuntimeError('Failed mounted executable differs')
    launch = c.read(driver.APP + '/launch.log', 65536)
    if not launch:
        raise RuntimeError('No fresh fixed-title launcher log; do not guess an app ID')
    launch_text = launch.decode('utf-8', errors='replace')
    ids = [int(v, 16) for v in re.findall(r'sce(?:LncUtil|SystemService)LaunchApp rc=0x([0-9a-fA-F]{8})', launch_text)]
    ids = [v for v in ids if 1 < v < 0x80000000]
    if len(ids) != 1:
        raise RuntimeError('No unique successful original app ID; manual coordinated stop required')
    app_id = ids[0]
    raw = (out / 'probe.klog.log').read_bytes()
    if type(startup_offset) is not int or not 0 <= startup_offset <= len(raw):
        raise ValueError('Single-launch log boundary missing')
    log = raw[startup_offset:]
    text = log.decode('utf-8', errors='replace')
    if not (re.search(r'<' + str(pid) + r'> EXEC /app0/eboot\.bin\b', text)
            and 'titleId[' + driver.TITLE + ']' in text
            and ('appId={0x%08x}' % app_id) in text
            and 'PRX_SCE_MODULE_LOAD_ERROR' in text):
        raise RuntimeError('Not the exact known PRX-load failure of this FS launch')
    (out / 'failed-startup-snapshot.log').write_bytes(log)
    (out / 'failed-launcher-snapshot.log').write_bytes(launch)
    identity = {'kind': 'fs_prx_load_failed_before_report', 'title': driver.TITLE, 'pid': pid, 'app_id': app_id,
                'eboot_sha256': eboot, 'param_sha256': param_sha, 'startup_offset': startup_offset,
                'startup_log': installer.m.proof(out / 'failed-startup-snapshot.log'),
                'launcher_log': installer.m.proof(out / 'failed-launcher-snapshot.log')}
    verify(c, identity, driver, installer)
    installer.m.write(out / 'failed-identity.json', identity)
    return identity


def verify(c, identity, driver, installer):
    if identity.get('title') != driver.TITLE or identity.get('kind') != 'fs_prx_load_failed_before_report':
        raise ValueError('Not this exact failed FS identity')
    if any(type(identity.get(k)) is not int or not 1 < identity[k] < 0x80000000 for k in ('pid', 'app_id')):
        raise ValueError('Invalid owned PID/app ID')
    for key in ('startup_log', 'launcher_log'):
        installer.queue.evidence_file(identity[key], Path(identity[key]['path']).parent)
    text = Path(identity['startup_log']['path']).read_text(encoding='utf-8', errors='replace')
    if not (re.search(r'<' + str(identity['pid']) + r'> EXEC /app0/eboot\.bin\b', text)
            and 'titleId[' + driver.TITLE + ']' in text
            and ('appId={0x%08x}' % identity['app_id']) in text
            and 'PRX_SCE_MODULE_LOAD_ERROR' in text):
        raise ValueError('Crash snapshot no longer binds the exact launch')
    processes = installer.api.eboot_processes()
    if len(processes) != 1 or installer.api.process_pid(processes[0]) != identity['pid']:
        raise RuntimeError('Failed PID changed; never close another process')
    param = c.read(driver.SANDBOX + '/app0/sce_sys/param.json', 65536)
    if (param is None or hashlib.sha256(param).hexdigest() != identity['param_sha256']
            or json.loads(param).get('titleId') != driver.TITLE
            or c.sha256(driver.APP + '/eboot.bin') != identity['eboot_sha256']):
        raise RuntimeError('Failed FS mount/executable changed')
    launch = c.read(driver.APP + '/launch.log', 65536)
    if launch is None or hashlib.sha256(launch).hexdigest() != identity['launcher_log']['sha256']:
        raise RuntimeError('Fresh launcher identity changed')


def close(c, config, driver, installer, job, identity, lease, out):
    payload = manifest(config, driver, installer, job)
    lease.check()
    verify(c, identity, driver, installer)
    if c.sha256(driver.APP + '/close-failed-side.elf') != payload['payload']['sha256']:
        raise RuntimeError('Installed cleanup ELF differs from the prebuilt helper')
    sender = driver.load_sender(config)
    lease.check()
    # Existing helper ABI is app_id FIRST, pid SECOND. No alternate/repeated send.
    try:
        response = sender.send_websrv_payload(Path(payload['payload']['path']), out,
                        payload['payload']['sha256'], (identity['app_id'], identity['pid']),
                        allowed_names=('close-failed-side.elf',))
    except urllib.error.HTTPError:
        raise
    except OSError as error:
        if isinstance(error, (urllib.error.URLError, ConnectionError, TimeoutError)):
            installer.api.install_guard().observe_connection('offline', 'HTTP: ' + str(error))
        raise
    if response.get('http_status') != 200 or response.get('payload_sha256') != payload['payload']['sha256']:
        raise RuntimeError('Cleanup transport did not confirm the exact payload; never resend')
    installer.m.write(out / 'failed-close-request.json', {'identity': identity, 'response': response,
                                                       'at': installer.api.utc_now()})
    deadline = time.monotonic() + 20
    while True:
        lease.check()
        procs = installer.api.eboot_processes()
        if not procs:
            break
        if len(procs) != 1 or installer.api.process_pid(procs[0]) != identity['pid']:
            raise RuntimeError('Different app appeared; no second cleanup is sent')
        if time.monotonic() > deadline:
            raise RuntimeError('Known failed app did not close; retain ownership for coordinated resolution')
        time.sleep(.5)
    installer.m.write(out / 'failed-closed.json', {'identity': identity, 'at': installer.api.utc_now(),
                                                'game_closed': True, 'response': response})
