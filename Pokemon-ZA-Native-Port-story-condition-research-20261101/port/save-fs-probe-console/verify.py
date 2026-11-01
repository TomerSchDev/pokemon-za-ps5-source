"""Four prepared offline verification blocks; canonical PC lease, no hardware.

Uses the existing Windows Job Object helper to contain only our test processes.
Does not enqueue/claim/complete, build, install or change canonical sources.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write(path, data):
    Path(path).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def proof(path):
    return {'path': str(Path(path).resolve()), 'sha256': digest(path)}


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def gated_child():
    if sys.stdin.buffer.readline() != b'GO\n':
        return 125
    payload = json.loads(sys.stdin.buffer.readline())
    cmd = payload['command']
    if len(cmd) < 5 or Path(cmd[3]).name != 'zw.py' or cmd[4] not in ('save-fs-console', 'save-install-defer-test', 'install-guard-test'):
        return 126
    # No shell; inherited stdout/stderr and guarded PC environment.
    return subprocess.call(cmd, cwd=payload['cwd'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs', type=Path, required=True)
    p.add_argument('--inputs-sha256', required=True)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if digest(args.inputs) != args.inputs_sha256:
        raise ValueError('Prepared verification contract changed')
    inputs = read(args.inputs)
    root = Path(inputs['repo']).resolve()
    out = args.out.resolve()
    if out.drive.upper() != 'C:' or out.exists():
        raise ValueError('NEW local C: output required; no NAS journals during a turn')
    def pins():
        for item in inputs['files']:
            if digest(item['path']) != item['sha256']:
                raise ValueError('Staged input changed: ' + item['path'])
    pins()
    if inputs.get('schema') != 'fs-driver-verification-inputs-1' or inputs.get('runner_sha256') != digest(__file__):
        raise ValueError('Verification runner/contract mismatch')
    q = module('fs_verify_pc_queue', root / 'tools/console-install-queue/console_queue.py')
    agent, ticket, token = (os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        raise ValueError('Canonical PC lease required; no tests executed')
    if os.environ.get('PC_TEST_STATE'):
        raise ValueError('Private resource queues are forbidden')
    board = q.Board(resource='pc')
    timing = board.check(agent, ticket, token)
    if timing.get('seconds_to_yield') is not None and timing['seconds_to_yield'] < 90:
        raise ValueError('Prepared verification/cleanup90s budget does not fit')
    windows = module('fs_verify_existing_job', root / 'tools/local-testing/windows.py')
    out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(('CONSOLE_INSTALL_', 'LARECOMP_', 'POKELAB_', 'ZW_QUEUE_'))}
    env['PYTHONIOENCODING'] = 'utf-8'
    started = time.monotonic()
    records, stopped, owned = [], [], []
    result = {'schema': 'fs-driver-pc-verification-result-1', 'result': 'FAILED', 'ticket': ticket,
              'console_access': False, 'game_launched': False, 'hardware_tested': False,
              'python': sys.executable, 'python_sha256': digest(sys.executable), 'python_version': sys.version}
    def execute(step):
        pins()
        board.heartbeat(agent, ticket, token)
        command = [sys.executable, '-I', '-B', str(root / 'workbench/zw.py')] + [v.replace('{out}', str(out)) for v in step['args']]
        proc, assigned = None, False
        name = 'Local\\Codex-ZA-FS-Verify-' + uuid.uuid4().hex
        container = windows.Job(name)
        stdout, stderr = out / (step['name'] + '.stdout.log'), out / (step['name'] + '.stderr.log')
        record = {'name': step['name'], 'command': command}
        try:
            with stdout.open('wb') as so, stderr.open('wb') as se:
                proc = subprocess.Popen([sys.executable, '-I', '-B', str(Path(__file__).resolve()), '--gated-child'],
                                        stdin=subprocess.PIPE, stdout=so, stderr=se, env=env, cwd=root,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
                owned.append(proc)
                record['bridge_pid'] = proc.pid
                container.assign(proc)
                assigned = True
                write(out / (step['name'] + '-containment.json'), {'job_object': name, 'pid': proc.pid, 'armed': True})
                proc.stdin.write(b'GO\n' + json.dumps({'command': command, 'cwd': str(root)}).encode() + b'\n')
                proc.stdin.close()
                deadline = time.monotonic() + step['timeout_seconds']
                last = time.monotonic()
                while proc.poll() is None:
                    board.check(agent, ticket, token)
                    if time.monotonic() - last >= 15:
                        board.heartbeat(agent, ticket, token)
                        last = time.monotonic()
                    if time.monotonic() >= deadline:
                        raise TimeoutError('Owned offline test exceeded prepared timeout')
                    time.sleep(.1)
                record['exit_code'] = proc.returncode
        finally:
            if proc is not None and not assigned and proc.poll() is None:
                proc.terminate(); proc.wait(timeout=3)
            stop = container.stop()
            stopped.append(stop)
            container.close()
            if proc is not None:
                proc.wait(timeout=3)
            record.update(stdout=proof(stdout), stderr=proof(stderr), cleanup=stop)
            records.append(record)
        if record['exit_code'] != 0:
            raise RuntimeError('Offline test failed: ' + step['name'])
        text = stdout.read_text(encoding='utf-8', errors='replace') + stderr.read_text(encoding='utf-8', errors='replace')
        if step.get('expected_unittest_count') is not None:
            if not re.search(r'Ran\s+' + str(step['expected_unittest_count']) + r'\s+tests?\s+in', text) or not re.search(r'^OK\s*$', text, re.M):
                raise ValueError('Expected actual unittest count/OK not found')
        return record
    try:
        for step in inputs['steps']:
            execute(step)
        pins()
        identity_path = out / 'identity-tests.json'
        identity = read(identity_path)
        if (identity.get('result') != 'passed' or len(identity.get('cases', [])) != 8
                or not all(c.get('result') == 'passed' for c in identity['cases'])
                or identity.get('driver_sha256') != inputs['driver_sha256']
                or identity.get('installer_sha256') != inputs['installer_sha256']):
            raise ValueError('Eight exact identity guard cases did not pass')
        write(out / 'defer-tests.json', {'status': 'PASS', 'tests': 3, 'scenarios': 4,
              'candidate_sha256': inputs['installer_sha256'], 'test_sha256': inputs['defer_test_sha256'],
              'stdout': records[1]['stdout'], 'stderr': records[1]['stderr'], 'exit_code': records[1]['exit_code'],
              'command': records[1]['command'], 'console_access': False})
        write(out / 'stream-tests.json', {'status': 'PASS', 'tests': 2, 'selection': 'stream_comparison',
              'test_sha256': inputs['stream_test_sha256'], 'stdout': records[2]['stdout'], 'stderr': records[2]['stderr'],
              'exit_code': records[2]['exit_code'], 'command': records[2]['command'], 'console_access': False})
        write(out / 'http-tests.json', {'status': 'PASS', 'tests': 1, 'selection': 'http_application_error',
              'test_sha256': inputs['stream_test_sha256'], 'stdout': records[3]['stdout'], 'stderr': records[3]['stderr'],
              'exit_code': records[3]['exit_code'], 'command': records[3]['command'], 'console_access': False})
        write(out / 'guard-verification.json', {'schema': 'fs-driver-verification-1',
              'identity_tests': proof(identity_path), 'defer_tests': proof(out / 'defer-tests.json'),
              'stream_tests': proof(out / 'stream-tests.json'), 'http_tests': proof(out / 'http-tests.json')})
        result.update(result='PASS', identity_cases=8, defer_tests=3, defer_scenarios=4, stream_tests=2, http_tests=1,
                      guard_verification=proof(out / 'guard-verification.json'))
    except Exception as error:
        result['error'] = str(error)
    finally:
        result.update(elapsed_seconds=time.monotonic() - started, steps=records,
                      own_processes_stopped=(len(stopped) == len(owned)
                          and all(proc.poll() is not None for proc in owned)
                          and all(r.get('active_processes') == 0 for r in stopped)))
        write(out / 'verification-result.json', result)
        write(out / 'pc-completion.json', {'ticket': ticket, 'own_processes_stopped': result['own_processes_stopped'],
              'evidence': proof(out / 'verification-result.json'), 'result': result['result']})
    print(json.dumps({'result': result['result'], 'out': str(out), 'own_processes_stopped': result['own_processes_stopped']}))
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(gated_child() if sys.argv[1:] == ['--gated-child'] else main())
