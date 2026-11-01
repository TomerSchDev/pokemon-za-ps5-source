"""Local-path view and contained Linux execution of the canonical offline planner.

This module never installs, claims a resource, changes queue state or copies game
data. The Windows front door holds the canonical PC turn throughout execution.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

NATIVE_UNC = r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native'
NATIVE = '/home/tomer/ps5-za-native'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def linux_path(value):
    """One exact native UNC prefix, or the canonical queue's existing C: mapping."""
    text = str(value)
    if text == NATIVE_UNC or text.startswith(NATIVE_UNC + '\\'):
        return NATIVE + text[len(NATIVE_UNC):].replace('\\', '/')
    if re.match(r'^[A-Za-z]:[\\/]', text):
        return '/mnt/' + text[0].lower() + '/' + text[3:].replace('\\', '/')
    raise ValueError('Unreviewed local path mapping: ' + text)


def queue_module(repo):
    spec = importlib.util.spec_from_file_location('canonical_sideapp_queue', repo / 'tools/console-install-queue/console_queue.py')
    q = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(q)
    return q


def prepare(repo, out, target, ui, writer):
    if os.name != 'nt' or any(os.environ.get('PC_TEST_' + n) or os.environ.get('CONSOLE_INSTALL_' + n)
                             for n in ('AGENT', 'TICKET', 'TOKEN')):
        raise ValueError('Prepare on Windows outside both resource turns')
    if target.exists() or target.parent != out / 'evidence':
        raise ValueError('New evidence directory directly inside the owned staged bundle required')
    runtime = json.loads(subprocess.check_output(
        ['wsl.exe', '-d', 'Ubuntu', '-u', 'tomer', '--', 'python3', '-I', '-B', '-c',
         'import json,sys,os; print(json.dumps({"version":list(sys.version_info[:3]),"uid":os.getuid(),"executable":sys.executable}))'],
        timeout=10).decode('utf-8', errors='strict'))
    if runtime['version'] < [3, 11, 0] or runtime['uid'] == 0:
        raise ValueError('Prepared worker requires existing Python3.11+ as unprivileged tomer')
    prepared = read(out / 'evidence/prepared-result.json')
    if prepared['status'] != 'PREPARED_NOT_FRESH_GAME_VERIFIED':
        raise ValueError('Completed original preparation required')
    q = queue_module(repo)
    target.mkdir()
    rows = {}
    for name, filename, count in (('probe', 'fs-probe-with-launcher-job.json', 8), ('save', 'side-app-job.json', 1712)):
        original_path = out / filename
        if sha(original_path) != prepared['jobs'][name]['sha256']:
            raise ValueError('Original immutable job changed')
        original = read(original_path)
        view = json.loads(json.dumps(original))
        mappings = []
        for item in view['artifacts']:
            before = item['path']
            after = linux_path(before)
            mappings.append({'windows': before, 'linux': after, 'sha256': item['sha256'], 'remote_path': item['remote_path']})
            item['path'] = after
        # Replacing every path back must recover the entire original document.
        recovered = json.loads(json.dumps(view))
        for item, source in zip(recovered['artifacts'], original['artifacts'], strict=True):
            item['path'] = source['path']
        if recovered != original or len(view['artifacts']) != count:
            raise ValueError('The view changed more than local source path spelling')
        identity = q.candidate_hash(view)
        if identity != prepared['jobs'][name]['candidate_sha256']:
            raise ValueError('Destination/content identity changed')
        view_path = target / (name + '-linux-view-job.json')
        write(view_path, view)
        rows[name] = {'original_path': str(original_path), 'original_sha256': sha(original_path),
                      'view_windows_path': str(view_path), 'view_linux_path': linux_path(view_path),
                      'view_sha256': sha(view_path), 'candidate_sha256': identity, 'files': count,
                      'mappings': mappings}
    pins = []
    for path in (Path(__file__), Path(__file__).with_name('prepare_save_slots_side_app.py'),
                 repo / 'workbench/zw.py', repo / 'port/main-install/install-main.py',
                 repo / 'tools/console-install-queue/console_queue.py', repo / 'run_r3.py',
                 repo / 'port/r28b-dlc-dex/install-r28b.py', repo / 'tools/console-install-queue/install_guard.py',
                 repo / 'port/perf-r24/observer/client.py', repo / 'port/perf-r24/observer/analyze.py',
                 Path(prepared['preparer_source'])):
        pins.append({'path': str(path), 'linux_path': linux_path(path), 'sha256': sha(path)})
    manifest = {'schema': 'za-sideapp-linux-local-view-1', 'status': 'PREPARED_NOT_EXECUTED',
                'repo_linux': linux_path(repo), 'out_linux': linux_path(target), 'source_pins': pins,
                'ui_linux': linux_path(ui), 'writer_linux': linux_path(writer),
                'prepared_linux_runtime': runtime,
                'jobs': rows, 'no_game_data_copied': True, 'console_access': False,
                'ordered_commands': ['canonical zw install-bundle plan --job probe-linux-view-job.json',
                                     'canonical zw install-bundle plan --job save-linux-view-job.json'],
                'command_limit_seconds': 240, 'required_remaining_before_command_seconds': 275,
                'cleanup_remaining_seconds': 35, 'overall_execution_limit_seconds': 500,
                'stop_plan': 'Only recorded child process group, validated PID start ticks and exact command; TERM3s then KILL. Worker always writes cleanup. No console operation.'}
    write(target / 'view-manifest.json', manifest)
    return {'manifest': str(target / 'view-manifest.json'), 'sha256': sha(target / 'view-manifest.json'),
            'status': 'PREPARED_NOT_EXECUTED', 'candidate_sha256s': {k: v['candidate_sha256'] for k, v in rows.items()}}


def proc_record(pid, argv=True):
    try:
        stat = Path('/proc/%d/stat' % pid).read_text()
        fields = stat.rsplit(')', 1)[1].split()
        return {'pid': pid, 'start_ticks': fields[19], 'state': fields[0], 'group': int(fields[2]),
                'session': int(fields[3]),
                'argv': Path('/proc/%d/cmdline' % pid).read_bytes().split(b'\0')[:-1] if argv else []}
    except FileNotFoundError:
        return None


def group_members(pid):
    result = []
    for entry in Path('/proc').iterdir():
        if entry.name.isdigit():
            row = proc_record(int(entry.name), argv=False)
            if row and row['state'] != 'Z' and row['group'] == pid:
                result.append(row)
    return result


def wait_fixture_group(pid):
    deadline = time.monotonic() + 3
    while len(group_members(pid)) < 2:
        if time.monotonic() > deadline:
            raise RuntimeError('Synthetic child/grandchild fixture did not start')
        time.sleep(.02)


def matching_process(record):
    current = proc_record(record['pid'])
    if current and current['state'] != 'Z' and (current['start_ticks'] != record['start_ticks'] or
                                               current['argv'] != [x.encode() for x in record['argv']]):
        raise RuntimeError('Owned process identity changed; refuse to signal it')
    return current


def stop_group(record):
    current = matching_process(record)
    members = group_members(record['pid'])
    if not members:
        return
    if current is None or current['state'] == 'Z':
        raise RuntimeError('Live group leader identity unavailable; refuse to signal orphan session members')
    if current and current['state'] != 'Z' and current['group'] != record['pid']:
        raise RuntimeError('The recorded process is not its private process-group leader')
    if any(row['session'] != record['pid'] or int(row['start_ticks']) < int(record['start_ticks']) for row in members):
        raise RuntimeError('Unowned process found in the recorded private session')
    os.killpg(record['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if not group_members(record['pid']):
            return
        time.sleep(.05)
    current = matching_process(record)
    if group_members(record['pid']):
        if current is None or current['state'] == 'Z':
            raise RuntimeError('Live leader identity lost after TERM; refuse orphan-session KILL')
        os.killpg(record['pid'], signal.SIGKILL)
    deadline = time.monotonic() + 2
    while group_members(record['pid']):
        if time.monotonic() > deadline:
            raise RuntimeError('Owned process group did not stop')
        time.sleep(.05)


def stop_process(record):
    current = matching_process(record)
    if current is None or current['state'] == 'Z':
        return
    if record['pid'] == os.getpid():
        raise RuntimeError('Refuse to signal the stopping helper itself')
    os.kill(record['pid'], signal.SIGTERM)
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        current = matching_process(record)
        if current is None or current['state'] == 'Z':
            return
        time.sleep(.05)
    matching_process(record)
    os.kill(record['pid'], signal.SIGKILL)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = matching_process(record)
        if current is None or current['state'] == 'Z':
            return
        time.sleep(.05)
    raise RuntimeError('Owned Linux worker did not stop')


def worker(repo, manifest_path, expected_sha, stop=False, selftest=False):
    if os.name == 'nt':
        raise ValueError('Linux worker only')
    if not expected_sha or sha(manifest_path) != expected_sha:
        raise ValueError('Prepared view manifest changed')
    manifest = read(manifest_path)
    if manifest.get('schema') != 'za-sideapp-linux-local-view-1':
        raise ValueError('Unexpected manifest')
    target = Path(manifest['out_linux'])
    for pin in manifest['source_pins']:
        if sha(pin['linux_path']) != pin['sha256']:
            raise ValueError('Prepared source changed: ' + pin['linux_path'])
    q = queue_module(repo)
    agent, ticket, token = (os.environ.get('PC_TEST_' + n, '') for n in ('AGENT', 'TICKET', 'TOKEN'))
    if (not all((agent, ticket, token)) or os.environ.get('PC_TEST_STATE') or
            any(os.environ.get('CONSOLE_INSTALL_' + key) for key in ('STATE', 'AGENT', 'TICKET', 'TOKEN'))):
        raise ValueError('Canonical shared PC lease required; no private state')
    board = q.Board(resource='pc')
    if board.root.resolve() != (repo.parent / 'pc-test-state').resolve():
        raise ValueError('The Linux worker did not select the canonical shared PC state')
    board.authenticate(board.load(), agent, ticket, token, cleanup=stop)
    if stop:
        for path in sorted(target.glob('*-owned-process.json')):
            record = read(path)
            if not record.get('stopped'):
                stop_group(record)
                write(path, {**record, 'stopped': True})
        worker_path = target / 'worker-identity.json'
        if worker_path.exists():
            identity = read(worker_path)
            if not identity.get('stopped'):
                for record in identity['processes']:
                    stop_process(record)
                write(worker_path, {**identity, 'stopped': True})
        write(target / 'external-stop.json', {'own_processes_stopped': True, 'console_access': False})
        return
    identity = []
    for pid in (os.getpid(), os.getppid()):
        row = proc_record(pid)
        argv = [x.decode('utf-8', errors='strict') for x in row['argv']]
        if '--linux-worker' not in argv or str(manifest_path) not in argv:
            raise ValueError('The worker/parent is not the exact declared front-door invocation')
        identity.append({'pid': pid, 'start_ticks': row['start_ticks'], 'argv': argv})
    write(target / 'worker-identity.json', {'processes': identity, 'stopped': False})
    if selftest:
        if (target / 'cleanup-selftest.json').exists() or (target / 'cleanup-selftest-armed.json').exists():
            raise FileExistsError('Selftest already executed; preserve its evidence')
        board.heartbeat(agent, ticket, token)
        board.check(agent, ticket, token)
        command = [sys.executable, '-c', 'import subprocess,sys,time; subprocess.Popen([sys.executable,"-c","import time; time.sleep(30)"]); time.sleep(30)']
        with subprocess.Popen(command, start_new_session=True) as child:
            live = proc_record(child.pid)
            if live is None:
                child.wait()
                raise RuntimeError('Synthetic fixture exited before ownership was recorded')
            owned = {'pid': child.pid, 'start_ticks': live['start_ticks'], 'argv': command}
            try:
                wait_fixture_group(child.pid)
                try:
                    stop_group({**owned, 'argv': ['deliberately-different-command']})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Foreign command identity was accepted')
            finally:
                stop_group(owned)
                child.wait()
        result = {'status': 'PASS_SYNTHETIC_CLEANUP', 'cases': ['wrong_command_refused', 'owned_child_and_grandchild_stopped'],
                  'active_owned_group_members': len(group_members(child.pid)), 'console_access': False,
                  'canonical_shared_state': str(board.root), 'ticket': ticket,
                  'canonical_mutex_heartbeat_and_check_executed': True}
        write(target / 'cleanup-selftest.json', result)
        # Exercise the actual Windows->WSL stop route against a second owned group.
        with subprocess.Popen(command, start_new_session=True) as child:
            live = proc_record(child.pid)
            if live is None:
                child.wait()
                raise RuntimeError('External-stop fixture exited before recording')
            owned = {'pid': child.pid, 'start_ticks': live['start_ticks'], 'argv': command}
            record_path = target / 'selftest-owned-process.json'
            write(record_path, owned)
            try:
                wait_fixture_group(child.pid)
                write(target / 'cleanup-selftest-armed.json', {'pid': child.pid, 'worker': os.getpid()})
                child.wait(timeout=20)
            finally:
                if child.poll() is None or group_members(child.pid):
                    stop_group(owned)
                child.wait()
                write(record_path, {**owned, 'stopped': True})
        write(target / 'worker-identity.json', {'processes': identity, 'stopped': True})
        print(json.dumps(result))
        return
    results = {}
    for name in ('probe', 'save'):
        turn = board.check(agent, ticket, token)
        remaining = turn.get('seconds_to_yield')
        if turn.get('must_yield') or remaining is not None and remaining < 275:
            raise RuntimeError('Canonical command plus cleanup does not fit this PC turn')
        row = manifest['jobs'][name]
        if sha(row['view_linux_path']) != row['view_sha256'] or sha(linux_path(row['original_path'])) != row['original_sha256']:
            raise ValueError('Original/view job changed after preparation')
        command = [sys.executable, '-I', '-B', str(repo / 'workbench/zw.py'), 'install-bundle', 'plan', '--job', row['view_linux_path']]
        stdout = target / (name + '-linux-plan.json')
        stderr = target / (name + '-linux-stderr.txt')
        if stdout.exists() or stderr.exists():
            raise FileExistsError('Preserve prior evidence; prepare a new execution directory')
        with stdout.open('wb') as output, stderr.open('wb') as error:
            with subprocess.Popen(command, stdout=output, stderr=error, start_new_session=True) as child:
                live = proc_record(child.pid)
                if live is None:
                    child.wait()
                    raise RuntimeError('Child exited before ownership could be recorded')
                owned = {'pid': child.pid, 'start_ticks': live['start_ticks'], 'argv': command}
                write(target / (name + '-owned-process.json'), owned)
                started = time.monotonic()
                try:
                    while child.poll() is None:
                        turn = board.check(agent, ticket, token)
                        remaining = turn.get('seconds_to_yield')
                        if (turn.get('must_yield') or remaining is not None and remaining < 35
                                or time.monotonic() - started > 240):
                            raise RuntimeError('Owned canonical command reached its execution/cleanup limit')
                        time.sleep(.5)
                    if child.returncode:
                        raise RuntimeError('Canonical Linux plan failed: ' + name)
                finally:
                    if child.poll() is None or group_members(child.pid):
                        stop_group(owned)
                    child.wait()
                    stopped = child.poll() is not None and not group_members(child.pid)
                    write(target / (name + '-owned-process.json'), {**owned, 'stopped': stopped})
                    write(target / (name + '-cleanup.json'), {'own_processes_stopped': stopped,
                          'pid': child.pid, 'console_access': False})
        result = read(stdout)
        if result['candidate_sha256'] != row['candidate_sha256'] or result['files'] != row['files']:
            raise ValueError('Fresh policy result differs from original destination/content identity')
        results[name] = result
    # Record stat metadata after the successful canonical double digest, with no
    # extra game-file read. Reusers must reject a changed path/size/mtime tuple.
    game = []
    view = read(manifest['jobs']['save']['view_linux_path'])
    for item in view['artifacts']:
        if item['remote_path'].startswith('/data/homebrew/PPSA91781/game/'):
            stat = Path(item['path']).stat()
            game.append({'path': item['path'], 'sha256': item['sha256'], 'bytes': stat.st_size,
                         'mtime_ns': stat.st_mtime_ns, 'fresh_sha_enforced_by_canonical_plan': True})
    if len(game) != 6:
        raise ValueError('All six fresh game input records required')
    write(target / 'result.json', {'status': 'PASS_FRESH_ARTIFACT_BYTES_VERIFIED', 'plans': results,
          'original_bundle_identity_unchanged': True, 'game_files': game,
          'hardware_tested': False, 'console_access': False})
    write(target / 'worker-identity.json', {'processes': identity, 'stopped': True})
    print(json.dumps({'status': 'PASS_FRESH_ARTIFACT_BYTES_VERIFIED', 'evidence': str(target)}))


def windows_command(repo, manifest_path, expected_sha, stop=False, selftest=False):
    if os.name != 'nt' or sha(manifest_path) != expected_sha:
        raise ValueError('Prepared Windows manifest required')
    manifest = read(manifest_path)
    for pin in manifest['source_pins']:
        if sha(pin['path']) != pin['sha256']:
            raise ValueError('Prepared source changed: ' + pin['path'])
    command = ['wsl.exe', '-d', 'Ubuntu', '-u', 'tomer', '--', 'python3', '-I', '-B',
               linux_path(repo / 'workbench/zw.py'), 'save-slots-sideapp-prepare',
               '--repo', linux_path(repo), '--ui', manifest['ui_linux'], '--writer', manifest['writer_linux'],
               '--out', manifest['out_linux'], '--verification-readiness', linux_path(manifest_path),
               '--view-manifest-sha256', expected_sha, '--linux-worker']
    if stop:
        command.append('--linux-stop')
    if selftest:
        command.append('--linux-selftest')
    env = dict(os.environ)
    passed = env.get('WSLENV', '').split(':') if env.get('WSLENV') else []
    passed += ['PC_TEST_AGENT/u', 'PC_TEST_TICKET/u', 'PC_TEST_TOKEN/u']
    env['WSLENV'] = ':'.join(passed)
    return command, env


def windows_run(repo, manifest_path, expected_sha, stop=False, selftest=False):
    command, env = windows_command(repo, manifest_path, expected_sha, stop, selftest)
    timeout = 20 if stop else 30 if selftest else 500
    with subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as child:
        try:
            if selftest:
                target = Path(manifest_path).parent
                deadline = time.monotonic() + 15
                while not (target / 'cleanup-selftest-armed.json').exists():
                    if child.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Declared external-stop fixture did not become ready')
                    time.sleep(.1)
                stop_command, stop_env = windows_command(repo, manifest_path, expected_sha, stop=True)
                subprocess.run(stop_command, env=stop_env, check=True, capture_output=True, timeout=20)
            output, error = child.communicate(timeout=timeout)
        except BaseException:
            if not stop:
                stop_command, stop_env = windows_command(repo, manifest_path, expected_sha, stop=True)
                subprocess.run(stop_command, env=stop_env, check=True, capture_output=True, timeout=20)
            output, error = child.communicate(timeout=10)
            raise
    target = Path(manifest_path).parent
    prefix = 'stop' if stop else 'selftest' if selftest else 'worker'
    (target / (prefix + '-stdout.txt')).write_bytes(output)
    (target / (prefix + '-stderr.txt')).write_bytes(error)
    if selftest:
        proof = read(target / 'cleanup-selftest.json')
        external = read(target / 'external-stop.json')
        if (proof['status'] != 'PASS_SYNTHETIC_CLEANUP' or proof['active_owned_group_members'] != 0
                or external['own_processes_stopped'] is not True):
            raise RuntimeError('Contained Windows->Linux cleanup proof incomplete')
        write(target / 'cleanup-route-result.json', {'status': 'PASS_WINDOWS_LINUX_CLEANUP_ROUTE',
              'controlled_worker_returncode': child.returncode, 'source_manifest_sha256': expected_sha,
              'canonical_shared_state': proof['canonical_shared_state'], 'ticket': proof['ticket'],
              'native_group_cleanup': proof, 'external_stop': external, 'console_access': False})
        print(json.dumps({'status': 'PASS_WINDOWS_LINUX_CLEANUP_ROUTE'}))
        return
    if child.returncode:
        raise RuntimeError('Contained canonical Linux operation failed: ' + prefix)
    if not stop:
        print(output.decode('utf-8', errors='strict'), end='')
