"""One local game worker; scheduling, canonical turns and execution stay separate."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from contracts import canonical, digest, fixture_files, read_json, validate
from evidence import CRASH, completed_record, runtime_exit_analysis, evaluate, metrics, png, shot_path
from store import atomic_json
import windows

HERE = Path(__file__).resolve().parent


class Outcome(Exception):
    def __init__(self, status, reason, evidence=None):
        self.status, self.reason, self.evidence = status, reason, evidence
        super().__init__(reason)


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def under(path, parent):
    return Path(path).resolve().is_relative_to(Path(parent).resolve())


def safe_roots(cfg, manifest):
    rt = manifest['runtime']
    protected = [cfg['canonical_checkout'], rt['game_directory'], Path(rt['executable']['path']).parent]
    cp = manifest['input']['checkpoint']
    if cp['kind'] == 'copied_save':
        protected.append(cp['path'])
    if manifest['screenshots']['mode'] == 'reference':
        protected.append(Path(manifest['screenshots']['baseline']['path']).parent)
    for key in ('state_root', 'results_root'):
        target = Path(cfg[key]).resolve()
        if str(target).startswith('\\\\'):
            raise ValueError('state/results must be on a local filesystem')
        for source in protected:
            if under(target, source) or under(source, target):
                raise ValueError(f'{key} overlaps protected source: {source}')
    # Legacy runner writes here, never in the canonical checkout.
    runs = Path(cfg['canonical_checkout']).parent / 'hebrew-lab' / 'runs'
    for source in protected:
        if under(runs, source) or under(source, runs):
            raise ValueError('legacy run destination overlaps protected inputs')


class CanonicalPC:
    def __init__(self, cfg):
        self.canonical = Path(cfg['canonical_checkout'])
        self.module = load_module('za_test_canonical_queue', self.canonical / 'tools/console-install-queue/console_queue.py')
        # Never use a private production PC queue or inherited STATE override.
        self.board = self.module.Board(resource='pc')

    def wait(self, job, store, out):
        agent = job['manifest']['agent_id']
        execution = job['execution_id']
        request = execution
        desc = out / 'pc-job.json'
        atomic_json(desc, {'name': job['manifest']['test_id'], 'notes': f'Local testing {execution}; exclusive contained game, timeout/cancellation and verified cleanup.'})
        store.update(job['id'], request_id=request)
        ticket = self.board.enqueue(agent, request, desc)['ticket']
        store.update(job['id'], ticket=ticket)
        deadline = job['submitted'] + job['manifest']['queue_timeout_seconds']
        while True:
            if store.get(job['id'])['cancel']:
                self.board.release(agent, ticket, reason='cancelled before claim', cancel_queued=True)
                raise Outcome('CANCELLED', 'cancelled while waiting for the canonical PC turn')
            if time.time() >= deadline:
                self.board.release(agent, ticket, reason='resource wait timeout', cancel_queued=True)
                raise Outcome('TIMEOUT', 'canonical PC queue wait exceeded queue_timeout_seconds')
            try:
                state = self.board.load()
                head = next((r for r in state['jobs'] if r['state'] == 'queued'), None)
                if state['active'] or not head or head['ticket'] != ticket:
                    time.sleep(1)
                    continue
                claim = self.board.claim(agent, ticket=ticket)
                if claim.get('ticket'):
                    private = Path(store.root) / 'private' / (execution + '.json')
                    atomic_json(private, {'agent': agent, **claim})
                    store.update(job['id'], 'PREPARING', lease_id=claim['lease_id'], resource_acquired_at=time.time())
                    return claim
            except self.module.Busy:
                pass
            time.sleep(1)

    def release(self, job, claim, out, proof):
        evidence = out / 'process-cleanup.json'
        atomic_json(evidence, proof)
        state = self.board.load()
        row = next((r for r in state['jobs'] if r['ticket'] == claim['ticket']), None)
        # Newer legacy runners can release their own turn at the cleanup margin.
        # Accept only the exact job's checksummed handoff after our tree is also empty.
        if row and row['state'] == 'released' and row['request_id'] == job['execution_id'] and row['requested_by'] == job['manifest']['agent_id']:
            ref = row.get('last_reconciliation', {})
            path = self.module.local_path(ref['path'])
            if digest(path) != ref['sha256']:
                raise RuntimeError('legacy handoff proof identity changed')
            handoff = read_json(path)
            if handoff.get('ticket') != claim['ticket'] or handoff.get('own_processes_stopped') is not True or proof.get('active_processes') != 0:
                raise RuntimeError('legacy handoff lacks verified process cleanup')
            return {'ticket': claim['ticket'], 'state': 'released', 'already_released_by_legacy_runner': True,
                    'legacy_reconciliation': ref, 'contained_tree_verified_empty': True}
        receipt = out / 'pc-completion.json'
        atomic_json(receipt, {'ticket': claim['ticket'], 'own_processes_stopped': True,
                             'evidence': {'path': str(evidence), 'sha256': digest(evidence)}})
        return self.board.complete(job['manifest']['agent_id'], claim['ticket'], claim['token'], receipt)


class Heartbeat:
    def __init__(self, adapter, agent, claim):
        self.adapter, self.agent, self.claim = adapter, agent, claim
        self.turn, self.error = {}, None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self.run, daemon=True)

    def run(self):
        while not self.stop_event.is_set():
            try:
                self.turn = self.adapter.board.heartbeat(self.agent, self.claim['ticket'], self.claim['token'])
            except Exception as exc:
                self.error = str(exc)
                return
            if self.stop_event.wait(10):
                return

    def start(self):
        self.thread.start()

    def check(self):
        if self.error:
            raise Outcome('ERROR', 'canonical resource heartbeat failed: ' + self.error)
        left = self.turn.get('seconds_to_yield')
        if left is not None and left <= 40:
            raise Outcome('CANCELLED', 'canonical PC handoff cleanup margin reached; resubmit at tail')

    def close(self):
        self.stop_event.set()
        self.thread.join(timeout=16)
        if self.thread.is_alive():
            raise RuntimeError('heartbeat did not finish; retain PC turn for recovery')


def input_identity(cfg, m):
    rt = m['runtime']
    lab = Path(cfg['canonical_checkout']).parent / 'hebrew-lab'
    legacy = load_module('za_test_legacy_readonly', lab / 'tools/run_poc.py')
    if Path(rt['executable']['path']).resolve() != legacy.EXE.resolve():
        raise Outcome('UNSUPPORTED', 'existing guarded runner supports its fixed EXE only; a configurable EXE adapter needs separate validation')
    facts = {'files': {}, 'asset_metadata': {}, 'tools': {}, 'fixture_files': None}
    for key in ('executable', 'game_module'):
        ref = rt[key]
        actual = digest(ref['path'])
        if actual != ref['sha256']:
            raise Outcome('ERROR', key + ' SHA-256 changed since job preparation',
                          {'reference': key, 'expected_sha256': ref['sha256'], 'actual_sha256': actual})
        facts['files'][ref['path']] = actual
    game = Path(rt['game_directory'])
    for rel in ('exefs/main', 'exefs/sdk'):
        file = game / rel
        if not file.is_file():
            raise Outcome('ERROR', 'missing game input: ' + rel)
        facts['files'][str(file)] = digest(file)
    if not (game / 'romfs.bin').is_file() or not (game / 'lasgame.dll').is_file():
        raise Outcome('ERROR', 'legacy runner requires romfs.bin and lasgame.dll in game directory')
    for file in sorted(game.rglob('*')):
        if not file.is_file():
            continue
        stat = file.stat()
        facts['asset_metadata'][str(file)] = {'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns, 'identity': 'metadata_only'}
    # Pin every shipped DLL the fixed EXE can load; never copy the runtime bundle.
    for file in sorted(legacy.EXE.parent.glob('*.dll')):
        facts['files'][str(file)] = digest(file)
    for file in (lab / 'tools/run_poc.py', Path(cfg['canonical_checkout']) / 'workbench/zw.py',
                 Path(cfg['canonical_checkout']) / 'tools/console-install-queue/console_queue.py', *HERE.glob('*.py')):
        facts['tools'][str(file)] = digest(file)
    cp = m['input']['checkpoint']
    if cp['kind'] == 'copied_save':
        actual = fixture_files(cp['path'])
        if actual != cp['files']:
            raise Outcome('ERROR', 'checkpoint contents changed since preparation')
        facts['fixture_files'] = actual
    if m['screenshots']['mode'] == 'reference':
        b = m['screenshots']['baseline']
        if digest(b['path']) != b['sha256']:
            raise Outcome('ERROR', 'baseline identity changed')
        png(b['path'])
    facts['resource_preflight'] = legacy.resource_status()
    if facts['resource_preflight']['disk_free_bytes'] < 2 * 1024**3 or facts['resource_preflight'].get('free_commit_bytes', 0) < legacy.MINIMUM_FREE_COMMIT:
        raise Outcome('ERROR', 'insufficient disk/free commit; existing 2GiB/18GiB limits preserved',
                      {'resource_preflight': facts['resource_preflight'], 'minimum_free_commit_bytes': legacy.MINIMUM_FREE_COMMIT,
                       'minimum_free_disk_bytes': 2 * 1024**3})
    return facts


def unchanged_inputs(facts, m):
    changes = []
    for path, sha in facts['files'].items():
        if digest(path) != sha:
            changes.append(path)
    for path, metadata in facts['asset_metadata'].items():
        stat = Path(path).stat()
        if (stat.st_size, stat.st_mtime_ns) != (metadata['bytes'], metadata['mtime_ns']):
            changes.append(path)
    now_names = {str(p) for p in Path(m['runtime']['game_directory']).rglob('*') if p.is_file()}
    changes.extend(sorted(now_names - facts['asset_metadata'].keys()))
    cp = m['input']['checkpoint']
    if cp['kind'] == 'copied_save' and fixture_files(cp['path']) != facts['fixture_files']:
        changes.append('fixture')
    return changes


def legacy_args(m, run_name):
    args = [run_name, '--game', m['runtime']['game_directory'], '--seconds', str(m['execution']['seconds']),
            '--input', m['input']['script'], '--shot-at', ','.join(map(str, m['screenshots']['frames'])),
            '--capture-every', str(m['screenshots']['every']), '--fps', str(m['graphics']['fps'])]
    if m['input']['checkpoint']['kind'] == 'copied_save':
        args += ['--save-src', m['input']['checkpoint']['path']]
    g = m['graphics']
    # Presence also suppresses the launcher's asynchronous prompt-asset generation for an empty script.
    env = ['LARECOMP_INPUT=' + m['input']['script'], 'LARECOMP_GAME_LIB=' + m['runtime']['game_module']['path'],
           f'LARECOMP_WINDOW={g["width"]}x{g["height"]}', 'LARECOMP_FPS_INTERVAL=1']
    if g['hidden']:
        env.append('LARECOMP_HIDDEN=1')
    if g['pace_trace']:
        env.append('LARECOMP_LOG_PACE=1')
    return args + ['--env', *env]


def try_record(path):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


def collect(root, out):
    artifacts = []
    if not root.exists():
        return artifacts
    paths = list(root.glob('*.log')) + list(root.glob('*.json')) + list((root / 'build').rglob('*.png'))
    for p in sorted(set(paths)):
        dest = out / 'evidence' / p.relative_to(root)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dest)
        artifacts.append({'path': dest.relative_to(out).as_posix(), 'bytes': dest.stat().st_size, 'sha256': digest(dest)})
    return artifacts


def shutdown_tree(container, proc, watch, current_pid=None):
    """A diagnostic failure invalidates evidence, but never prevents stopping our tree."""
    monitor = {'exits': [], 'warnings': [], 'tracked_runtimes': 0, 'error': None,
               'current_runtime_pid': current_pid, 'current_runtime_created_filetime': None}
    try:
        if watch:
            try:
                watch.observe(container.pids())
                monitor['exits'] = watch.exits()
                monitor['warnings'] = list(getattr(watch, 'warnings', []))
                monitor['tracked_runtimes'] = len(getattr(watch, 'handles', {}))
                monitor['current_runtime_created_filetime'] = next((created for pid, created in getattr(watch, 'handles', {}) if pid == current_pid), None)
            except Exception as exc:
                monitor['error'] = f'{type(exc).__name__}: {exc}'
        proof = container.stop()
        if proc and proc.poll() is None:
            # An unassigned bridge is still stdin-gated and belongs to this parent.
            proc.terminate()
            proc.wait(timeout=5)
        return proof, monitor
    finally:
        container.close()


def run_one(cfg, store, job):
    m = job['manifest']
    out = Path(cfg['results_root']) / m['result_directory'] / job['id'] / job['execution_id']
    out.mkdir(parents=True, exist_ok=False)
    store.update(job['id'], result_path=str(out / 'result.json'))
    atomic_json(out / 'manifest.json', m)
    result = {'schema_version': 1, 'job_id': job['id'], 'execution_id': job['execution_id'],
              'test_id': m['test_id'], 'type': m['type'], 'agent_id': m['agent_id'], 'build_id': m['build_id'],
              'manifest_sha256': job['manifest_sha256'], 'status': 'ERROR', 'reason': 'execution incomplete',
              'submitted_at': job['submitted'], 'started_at': time.time(), 'result_directory': str(out),
              'checks': [], 'artifacts': [], 'visual': {'status': 'NOT_EVALUATED'},
              'capabilities': {'logic_L1': False, 'logic_L2': False, 'logic_L3': False, 'independent_render': False},
              'reproducibility': {'host_platform': sys.platform, 'python': sys.version, 'game_inputs': None}}
    adapter = claim = heartbeat = container = proc = None
    facts = None
    run_root = None
    stopped = {'active_processes': 0, 'reason': 'no launch attempted'}
    samples = []
    execution_start = None
    stop_reason = None
    cleanup_ok = True
    watch = None
    try:
        if validate(m, Path.cwd()) != m or hashlib.sha256(canonical(m).encode()).hexdigest() != job['manifest_sha256']:
            raise Outcome('ERROR', 'stored manifest identity/validation mismatch')
        safe_roots(cfg, m)
        if store.get(job['id'])['cancel']:
            raise Outcome('CANCELLED', 'cancelled before execution')
        if m['type'] == 'logic':
            raise Outcome('UNSUPPORTED', 'no verified typed guest-state/tick adapter; use an explicit Full fallback; L1/L2/L3 not claimed')
        if os.name != 'nt':
            raise Outcome('UNSUPPORTED', 'only the local Windows execution adapter is implemented')
        from PIL import Image  # required evidence decoder; installed existing utility
        adapter = CanonicalPC(cfg)
        claim = adapter.wait(job, store, out)
        heartbeat = Heartbeat(adapter, m['agent_id'], claim)
        heartbeat.start()
        execution_start = time.monotonic()
        facts = input_identity(cfg, m)
        result['reproducibility']['game_inputs'] = facts
        atomic_json(out / 'reproducibility.json', facts)
        heartbeat.check()
        left = adapter.board.check(m['agent_id'], claim['ticket'], claim['token']).get('seconds_to_yield')
        budget = min(m['execution']['seconds'], m['timeout_seconds'])
        if left is not None and left < budget + 30:
            raise Outcome('CANCELLED', 'declared test budget cannot fit the remaining canonical handoff window')
        if store.get(job['id'])['cancel']:
            raise Outcome('CANCELLED', 'cancelled during preparation; no game launched')
        if time.monotonic() - execution_start >= m['timeout_seconds']:
            raise Outcome('TIMEOUT', 'hard deadline reached during preparation; no game launched')
        run_name = 'local-test-' + job['execution_id']
        run_root = Path(cfg['canonical_checkout']).parent / 'hebrew-lab' / 'runs' / run_name
        result['legacy_run_directory'] = str(run_root)
        store.update(job['id'], legacy_run_directory=str(run_root))
        env = {k: v for k, v in os.environ.items() if not k.startswith(('LARECOMP_', 'POKELAB_', 'PC_TEST_', 'CONSOLE_INSTALL_', 'ZW_QUEUE_'))}
        env.update(PC_TEST_AGENT=m['agent_id'], PC_TEST_TICKET=claim['ticket'], PC_TEST_TOKEN=claim['token'])
        env['PYTHONIOENCODING'] = 'utf-8'
        name = 'Local\\Codex-ZA-Test-' + job['execution_id']
        container = windows.Job(name)
        watch = windows.RuntimeWatch()
        with (out / 'supervisor.stdout.log').open('wb') as stdout, (out / 'supervisor.stderr.log').open('wb') as stderr:
            proc = subprocess.Popen([sys.executable, '-I', str(HERE / 'bridge.py')], stdin=subprocess.PIPE,
                                    stdout=stdout, stderr=stderr, env=env, cwd=out,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
            container.assign(proc)
            # Journal the armed containment before opening the gate. Crash recovery can prove no escape.
            store.update(job['id'], 'RUNNING', containment_armed=True, job_object=name,
                         bridge_pid=proc.pid, launched_at=time.time())
            payload = {'zw': str(Path(cfg['canonical_checkout']) / 'workbench/zw.py'),
                       'canonical': cfg['canonical_checkout'], 'args': legacy_args(m, run_name)}
            atomic_json(out / 'command.json', payload)
            proc.stdin.write(b'GO\n' + json.dumps(payload, ensure_ascii=True).encode() + b'\n')
            proc.stdin.close()
            next_sample = 0
            while True:
                now = time.monotonic()
                watch.observe(container.pids())
                if store.get(job['id'])['cancel']:
                    raise Outcome('CANCELLED', 'explicit cancellation requested')
                if now - execution_start >= m['timeout_seconds']:
                    raise Outcome('TIMEOUT', 'hard execution deadline exceeded')
                heartbeat.check()
                if now >= next_sample:
                    processes = [s for pid in container.pids() if (s := windows.process_sample(pid)) is not None]
                    samples.append({'elapsed_seconds': now - execution_start, 'processes': processes, 'system': windows.memory_status()})
                    with (out / 'samples.jsonl').open('a', encoding='utf-8') as sample_file:
                        sample_file.write(canonical(samples[-1]) + '\n')
                    next_sample = now + 1
                record = try_record(run_root / 'run.json')
                if proc.poll() is not None:
                    # Natural engine completion must be classified from its runtime record, not the Python exit code.
                    if proc.returncode != 0:
                        raise Outcome('ERROR', 'legacy runner failed; inspect supervisor.stderr.log')
                    if not completed_record(record):
                        raise Outcome('ERROR', 'legacy runner exited without completed runtime record')
                    if record.get('stop_reason'):
                        raise Outcome('CANCELLED', record['stop_reason'])
                    if record.get('terminated_by_harness'):
                        if m['execution'].get('stop_after_frame'):
                            raise Outcome('TIMEOUT', 'legacy duration budget ended before required frame completion')
                        stop_reason = 'duration_complete'
                    elif record['exit_code'] != 0:
                        raise Outcome('FAIL', f'runtime crashed/exited with code {record["exit_code"]}')
                    else:
                        target = m['execution'].get('stop_after_frame')
                        if target and shot_path(run_root, target).is_file():
                            png(shot_path(run_root, target))
                            stop_reason = 'frame_complete'
                        else:
                            raise Outcome('FAIL', 'runtime exited cleanly before the declared duration/frame completion')
                    break
                target = m['execution'].get('stop_after_frame')
                if target and shot_path(run_root, target).is_file():
                    try:
                        png(shot_path(run_root, target))
                    except (OSError, ValueError, SyntaxError):
                        pass  # still being written; the hard timeout remains authoritative
                    else:
                        stop_reason = 'frame_complete'
                        break
                time.sleep(0.2)
        result['status'], result['reason'] = 'PASS', 'all declared and mandatory checks must pass below'
    except Outcome as exc:
        result['status'], result['reason'] = exc.status, exc.reason
        if exc.evidence is not None:
            result['infrastructure_diagnostics'] = exc.evidence
    except KeyboardInterrupt:
        result['status'], result['reason'] = 'CANCELLED', 'worker interrupted'
    except Exception as exc:
        result['status'], result['reason'] = 'ERROR', f'{type(exc).__name__}: {exc}'
    finally:
        store.update(job['id'], 'FINALIZING', stop_reason=stop_reason)
        try:
            if container:
                progress = try_record(run_root / 'run.json') if run_root else None
                stopped, monitor = shutdown_tree(container, proc, watch, (progress or {}).get('pid'))
                result['runtime_exits_before_cleanup'] = monitor['exits']
                result['runtime_exit_monitor'] = monitor
                if monitor['error']:
                    result['status'], result['reason'] = 'ERROR', 'exit-monitor evidence unavailable: ' + monitor['error']
            elif proc and proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=5)
        except Exception as exc:
            cleanup_ok = False
            result['status'], result['reason'] = 'ERROR', 'cleanup not verified; canonical turn retained: ' + str(exc)
        finally:
            if watch:
                watch.close()
        result['cleanup'] = stopped if cleanup_ok else {'verified': False}
        result['stop_reason'] = stop_reason
        result['execution_wall_seconds'] = time.monotonic() - execution_start if execution_start else None
        try:
            log = ''
            run_record = None
            exit_info = runtime_exit_analysis(None, result.get('runtime_exit_monitor', {}))
            if run_root and run_root.exists():
                log = (run_root / 'stderr.log').read_text(encoding='utf-8', errors='replace') if (run_root / 'stderr.log').exists() else ''
                run_record = try_record(run_root / 'run.json')
                result['legacy_record'] = run_record
                result['artifacts'] = collect(run_root, out)
                if run_record and run_record.get('stop_reason') == 'pc_queue_cleanup_margin' and result['status'] == 'ERROR' and result['reason'].startswith('canonical resource heartbeat failed'):
                    result['status'], result['reason'] = 'CANCELLED', 'existing runner stopped for the canonical PC handoff'
                crash_lines = [line for line in log.splitlines() if CRASH.search(line)]
                exit_info = runtime_exit_analysis(run_record, result.get('runtime_exit_monitor', {}))
                result['runtime_exit_analysis'] = exit_info
                result['crash_information'] = {'lines': crash_lines[:30],
                    'runtime_exit_code': run_record['exit_code'] if completed_record(run_record) else None,
                    'legacy_record_complete': completed_record(run_record),
                    'partial_legacy_exit_code_not_a_verdict': run_record.get('exit_code') if run_record and not completed_record(run_record) else None,
                    'terminated_by_legacy_harness': run_record.get('terminated_by_harness') if completed_record(run_record) else None}
                unexpected_exit = exit_info['unexpected_exit']
                if (crash_lines or unexpected_exit) and result['status'] in ('PASS', 'TIMEOUT', 'CANCELLED'):
                    result['termination_context'] = result['status']
                    result['status'], result['reason'] = 'FAIL', 'runtime crash evidence observed before cleanup'
            measured = metrics(log, samples)
            measured['process_sampling_period_seconds'] = 1
            measured['execution_wall_seconds'] = result['execution_wall_seconds']
            if execution_start:
                acquired = store.get(job['id'])['detail'].get('resource_acquired_at', result['started_at'])
                measured['queue_wait_seconds'] = acquired - job['submitted']
            else:
                measured['queue_wait_seconds'] = time.time() - job['submitted']
            if measured['runtime_cpu_seconds_sampled'] is not None and result['execution_wall_seconds']:
                measured['cpu_usage_percent'] = measured['runtime_cpu_seconds_sampled'] / result['execution_wall_seconds'] * 100
                measured['cpu_usage_note'] += '; percentage of one logical CPU, over execution including preparation'
            result['metrics'] = measured
            if run_root and stop_reason:
                result['checks'], result['visual'] = evaluate(m, run_root, log, run_record, stop_reason, measured)
                if result['status'] == 'PASS' and not all(c['passed'] for c in result['checks']):
                    result['status'], result['reason'] = 'FAIL', 'one or more mandatory/declared assertions failed'
            if facts:
                changed = unchanged_inputs(facts, m)
                result['checks'].append({'name': 'protected_inputs_unchanged', 'passed': not changed, 'changed': changed})
                if changed:
                    result['status'], result['reason'] = 'ERROR', 'protected input identity changed during test'
            if run_root and result['status'] == 'PASS':
                has_exit_evidence = exit_info['known']
                result['checks'].append({'name': 'runtime_exit_evidence_available', 'passed': has_exit_evidence})
                if not has_exit_evidence:
                    result['status'], result['reason'] = 'ERROR', 'cannot validate runtime exit status; no retained handle or completed exit record'
            if result['status'] == 'PASS' and not result['checks']:
                result['status'], result['reason'] = 'ERROR', 'no evaluated assertions'
            atomic_json(out / 'samples.json', samples)
            atomic_json(out / 'metrics.json', measured)
            for p in (out / 'samples.json', out / 'samples.jsonl', out / 'metrics.json', out / 'manifest.json', out / 'command.json', out / 'reproducibility.json',
                      out / 'supervisor.stdout.log', out / 'supervisor.stderr.log'):
                if p.exists():
                    result['artifacts'].append({'path': p.relative_to(out).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)})
        except Exception as exc:
            result['status'], result['reason'] = 'ERROR', 'evidence finalization failed: ' + str(exc)
        if adapter and claim is None:
            try:
                state = adapter.board.load()
                row = next((r for r in state['jobs'] if r['request_id'] == job['execution_id']), None)
                if row and row['state'] == 'queued':
                    adapter.board.release(m['agent_id'], row['ticket'], reason='execution ended before PC claim', cancel_queued=True)
                elif row and row['state'] == 'reserved':
                    cleanup_ok = False
                    result['status'], result['reason'] = 'ERROR', 'PC claim interrupted before recovery token; exact lease needs recovery'
            except Exception as exc:
                cleanup_ok = False
                result['status'], result['reason'] = 'ERROR', 'waiting ticket cleanup requires recovery: ' + str(exc)
        if heartbeat:
            try:
                heartbeat.close()
            except Exception as exc:
                cleanup_ok = False
                result['status'], result['reason'] = 'ERROR', 'heartbeat cleanup requires recovery: ' + str(exc)
        if claim and cleanup_ok:
            try:
                result['resource_release'] = adapter.release(job, claim, out, stopped)
                (Path(store.root) / 'private' / (job['execution_id'] + '.json')).unlink(missing_ok=True)
            except Exception as exc:
                result['status'], result['reason'] = 'ERROR', 'PC turn release requires recovery: ' + str(exc)
                cleanup_ok = False
        result['finished_at'] = time.time()
        result['total_wall_seconds'] = result['finished_at'] - job['submitted']
        if store.get(job['id'])['cancel'] and result['status'] == 'PASS':
            result['status'], result['reason'] = 'CANCELLED', 'cancellation requested during evidence finalization'
        if result['status'] == 'PASS':
            result['reason'] = 'all mandatory and declared assertions passed; see visual verdict separately'
        atomic_json(out / 'result.json', result)
        if cleanup_ok:
            store.finish(job['id'], result)
        else:
            store.update(job['id'], recovery_required=True)
    return result


def recover(cfg, store):
    """Recover only this journal's executions, with OS identity and containment evidence."""
    recovered = []
    adapter = CanonicalPC(cfg)
    for job in store.list():
        if job['phase'] in ('QUEUED', 'FINISHED'):
            continue
        detail = job['detail']
        if windows.identity_alive(detail['worker']):
            raise RuntimeError('execution still has a live worker; recovery refused')
        # Before arming, bridge is stdin-gated. A crash closes stdin; it cannot start the runtime.
        proof = {'active_processes': 0, 'reason': 'worker died before opening containment gate'}
        if detail.get('containment_armed'):
            container = windows.Job(detail['job_object'], existing=True)
            try:
                proof = container.stop()
            finally:
                container.close()
        out = Path(detail.get('result_path', str(Path(cfg['results_root']) / 'recovery' / job['execution_id'] / 'result.json'))).parent
        out.mkdir(parents=True, exist_ok=True)
        previous_result = None
        if (out / 'result.json').exists():
            previous = out / f'pre-recovery-{time.time_ns()}.json'
            shutil.copy2(out / 'result.json', previous)
            old = try_record(previous) or {}
            previous_result = {'path': previous.name, 'sha256': digest(previous),
                               'original_status': old.get('status'), 'original_reason': old.get('reason')}
        state = adapter.board.load()
        row = next((r for r in state['jobs'] if r['request_id'] == detail.get('request_id', job['execution_id'])), None)
        if row and row['state'] == 'queued':
            adapter.board.release(job['manifest']['agent_id'], row['ticket'], reason='interrupted worker recovery', cancel_queued=True)
        elif row and state['active'] and state['active']['ticket'] == row['ticket']:
            active = state['active']
            private = Path(store.root) / 'private' / (job['execution_id'] + '.json')
            lease = try_record(private)
            cleanup = out / 'recovery-process-cleanup.json'
            atomic_json(cleanup, proof)
            resolution = out / 'recovery-resolution.json'
            atomic_json(resolution, {'ticket': row['ticket'], 'lease_id': active['lease_id'],
                                     'own_processes_stopped': True, 'pc_handoff_confirmed': True,
                                     'evidence': {'path': str(cleanup), 'sha256': digest(cleanup)}})
            args = {'resolution': resolution, 'reason': 'verified interrupted local worker cleanup'}
            if adapter.board.expired(active):
                args['expected_lease_id'] = active['lease_id']
            elif lease and lease['lease_id'] == active['lease_id']:
                args['token'] = lease['token']
            else:
                raise RuntimeError('claim interrupted before private token write; exact lease must expire before evidenced reconciliation')
            adapter.board.release(job['manifest']['agent_id'], row['ticket'], **args)
            private.unlink(missing_ok=True)
        m = job['manifest']
        available = []
        run_dir = detail.get('legacy_run_directory')
        log = ''
        record = None
        if run_dir and Path(run_dir).exists():
            available = collect(Path(run_dir), out)
            record = try_record(Path(run_dir) / 'run.json')
            if (Path(run_dir) / 'stderr.log').exists():
                log = (Path(run_dir) / 'stderr.log').read_text(encoding='utf-8', errors='replace')
        samples = []
        if (out / 'samples.jsonl').exists():
            for line in (out / 'samples.jsonl').read_text(encoding='utf-8').splitlines():
                try:
                    samples.append(json.loads(line))
                except ValueError:
                    break  # last sample may have been interrupted; it is never fabricated
        measured = metrics(log, samples)
        facts = try_record(out / 'reproducibility.json')
        checks = []
        if facts:
            try:
                changed = unchanged_inputs(facts, m)
                checks.append({'name': 'protected_inputs_unchanged', 'passed': not changed, 'changed': changed})
            except Exception as exc:
                checks.append({'name': 'protected_inputs_unchanged', 'passed': False, 'reason': str(exc)})
        for name in ('manifest.json', 'reproducibility.json', 'samples.jsonl', 'supervisor.stdout.log', 'supervisor.stderr.log'):
            file = out / name
            if file.exists():
                available.append({'path': name, 'bytes': file.stat().st_size, 'sha256': digest(file)})
        for file in sorted(out.glob('pre-recovery-*.json')):
            available.append({'path': file.name, 'bytes': file.stat().st_size, 'sha256': digest(file)})
        result = {'schema_version': 1, 'job_id': job['id'], 'execution_id': job['execution_id'],
                  'test_id': job['manifest']['test_id'], 'type': job['manifest']['type'], 'status': 'ERROR',
                  'reason': 'worker interrupted; execution was not validated', 'cleanup': proof,
                  'agent_id': m['agent_id'], 'build_id': m['build_id'], 'legacy_record': record,
                  'reproducibility': {'game_inputs': facts, 'manifest': m}, 'checks': checks, 'metrics': measured,
                  'pre_recovery_result': previous_result,
                  'finished_at': time.time(), 'artifacts': available, 'visual': {'status': 'NOT_EVALUATED'},
                  'legacy_run_directory': detail.get('legacy_run_directory'),
                  'result_directory': str(out), 'manifest_sha256': job['manifest_sha256']}
        atomic_json(out / 'result.json', result)
        store.finish(job['id'], result)
        recovered.append(result)
    return recovered
