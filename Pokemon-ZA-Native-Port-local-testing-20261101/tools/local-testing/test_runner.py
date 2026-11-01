"""Synthetic infrastructure checks only. These cannot certify game correctness."""
from __future__ import annotations
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from contracts import ContractError, canonical, digest, fixture_files, read_json, validate
from evidence import compare, completed_record, runtime_exit_analysis, evaluate, metrics, png
from store import Store, atomic_json, worker_lock
from worker import legacy_args
from worker import load_module
import worker
import windows


def manifest():
    return {'schema_version': 1, 'test_id': 'synthetic-contract', 'type': 'full', 'agent_id': 'unit', 'build_id': 'synthetic',
            'runtime': {'executable': {'path': 'test.exe', 'sha256': '0' * 64},
                        'game_module': {'path': 'test.dll', 'sha256': '0' * 64}, 'game_directory': 'game'},
            'timeout_seconds': 15, 'queue_timeout_seconds': 30,
            'input': {'script': '1:A,12:STICK_90:8,12:B:4', 'checkpoint': {'kind': 'new_game'}},
            'execution': {'seconds': 10}, 'graphics': {'width': 1280, 'height': 720, 'hidden': False, 'fps': 30, 'pace_trace': True},
            'screenshots': {'frames': [120], 'every': 0, 'mode': 'capture_only'},
            'assertions': [{'kind': 'screenshot_exists', 'frame': 120}],
            'resources': {'game_instances': 1, 'gpu': 1},
            'artifacts': {'logs': True, 'screenshots': True, 'metrics': True}, 'result_directory': 'unit'}


class Contracts(unittest.TestCase):
    def test_valid_and_no_mutation(self):
        m = manifest()
        v = validate(m, Path.cwd())
        self.assertTrue(Path(v['runtime']['executable']['path']).is_absolute())
        self.assertEqual(m['runtime']['executable']['path'], 'test.exe')

    def test_unknown_fields_and_missing_assertions(self):
        for edit in (lambda m: m.update(shell='bad'), lambda m: m.update(assertions=[]),
                     lambda m: m['execution'].update(made_up=True), lambda m: m.update(timeout_seconds=True)):
            m = manifest()
            edit(m)
            with self.assertRaises(ContractError):
                validate(m, Path.cwd())

    def test_reject_unrecognized_legacy_input(self):
        for script in ('0:A', '1:NOT_A_BUTTON:5', '1:A:-1', '1:a:5', '1:STICK_360:2', '1:A:5,', '1:A:0'):
            m = manifest()
            m['input']['script'] = script
            with self.assertRaises(ContractError, msg=script):
                validate(m, Path.cwd())

    def test_screenshot_order_and_stop_boundary(self):
        for frames in ([4, 2], [2, 2], [True], [0]):
            m = manifest()
            m['screenshots']['frames'] = frames
            with self.assertRaises(ContractError):
                validate(m, Path.cwd())
        m = manifest()
        m['execution']['stop_after_frame'] = 121
        with self.assertRaises(ContractError):
            validate(m, Path.cwd())

    def test_fixture_and_no_path_traversal(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'save_0').mkdir()
            (root / 'save_0/main').write_bytes(b'synthetic test fixture')
            files = fixture_files(root)
            self.assertEqual(files['save_0/main'], hashlib.sha256(b'synthetic test fixture').hexdigest())
            m = manifest()
            m['input']['checkpoint'] = {'kind': 'copied_save', 'path': t, 'files': {'../escape': '0' * 64, **files}}
            with self.assertRaises(ContractError):
                validate(m, root)

    def test_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            path = Path(t) / 'm.json'
            path.write_text('{"a":1,"a":2}')
            with self.assertRaises(ContractError):
                read_json(path)

    def test_legacy_arguments_preserve_interfaces(self):
        m = manifest()
        m['screenshots']['every'] = 60
        args = legacy_args(m, 'unique')
        self.assertEqual(args[args.index('--input') + 1], m['input']['script'])
        self.assertEqual(args[args.index('--shot-at') + 1], '120')
        self.assertEqual(args[args.index('--capture-every') + 1], '60')
        self.assertNotIn('LARECOMP_PRESENT_INTERVAL=0', args)


class Journal(unittest.TestCase):
    def test_journal_rejects_empty_pass_and_unknown_verdict(self):
        with tempfile.TemporaryDirectory() as t:
            s = Store(t)
            job = s.submit(manifest(), 'sha')
            for result in ({'status': 'PASS'}, {'status': 'looks-fine'},
                           {'status': 'PASS', 'checks': [{'passed': False}], 'reproducibility': {'x': 1}}):
                with self.assertRaises(ValueError):
                    s.finish(job['id'], result)
            self.assertIsNone(s.get(job['id'])['verdict'])

    def test_separate_processes_can_submit_concurrently(self):
        with tempfile.TemporaryDirectory() as t:
            s = Store(t)
            source = Path(t) / 'synthetic.json'
            atomic_json(source, manifest())
            code = (f'import sys,json;sys.path.insert(0,{str(Path(__file__).parent)!r}); '
                    f'from store import Store; s=Store({t!r}); '
                    f'm=json.load(open({str(source)!r}));print(s.submit(m,"synthetic")["id"])')
            procs = [subprocess.Popen([sys.executable, '-I', '-B', '-c', code], stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)]
            ids = []
            for proc in procs:
                stdout, stderr = proc.communicate(timeout=5)
                self.assertEqual(proc.returncode, 0, stderr)
                ids.append(stdout.strip())
            self.assertEqual(len(set(ids)), 4)
            self.assertEqual(len(s.list()), 4)

    def test_metadata_sharing_retry_preserves_ownership_errors(self):
        queue = load_module('synthetic_queue_retry', Path(__file__).resolve().parents[1] / 'console-install-queue/console_queue.py')
        calls = []
        def transient():
            calls.append(1)
            if len(calls) < 3:
                exc = PermissionError('synthetic sharing violation')
                exc.winerror = 32
                raise exc
            return 'ok'
        self.assertEqual(queue.retry_sharing(transient), 'ok')
        self.assertEqual(len(calls), 3)
        with self.assertRaises(PermissionError):
            queue.retry_sharing(lambda: (_ for _ in ()).throw(PermissionError('ACL denied')))

    def test_concurrent_submission_fifo_and_persistence(self):
        with tempfile.TemporaryDirectory() as t:
            s = Store(t)
            def submit(n):
                m = manifest()
                m['test_id'] += str(n)
                return Store(t).submit(m, str(n))
            with ThreadPoolExecutor(max_workers=6) as pool:
                rows = list(pool.map(submit, range(30)))
            self.assertEqual(len({r['id'] for r in rows}), 30)
            reopened = Store(t)
            rows = reopened.list()
            self.assertEqual([r['sequence'] for r in rows], list(range(1, 31)))
            job = reopened.claim({'pid': 0, 'created_filetime': 0})
            self.assertEqual(job['id'], rows[0]['id'])
            with self.assertRaises(RuntimeError):
                reopened.claim({})
            reopened.finish(job['id'], {'status': 'ERROR'})
            self.assertEqual(reopened.claim({})['id'], rows[1]['id'])

    def test_cancel_does_not_create_pass(self):
        with tempfile.TemporaryDirectory() as t:
            s = Store(t)
            job = s.submit(manifest(), 'sha')
            s.cancel(job['id'])
            self.assertEqual(s.get(job['id'])['cancel'], 1)
            self.assertIsNone(s.get(job['id'])['verdict'])
            self.assertIsNone(s.get(job['id'])['result'])


class Evidence(unittest.TestCase):
    def test_stale_aslr_attempt_exit_is_not_current_runtime_exit(self):
        partial = {'pid': 9, 'address_collisions': 2, 'exit_code': 1, 'terminated_by_harness': False}
        monitor = {'current_runtime_pid': 9, 'current_runtime_created_filetime': 300,
                   'exits': [{'pid': 1, 'created_filetime': 100, 'exit_code': 1}]}
        analysis = runtime_exit_analysis(partial, monitor)
        self.assertFalse(completed_record(partial))
        self.assertTrue(analysis['known'])
        self.assertFalse(analysis['unexpected_exit'])
        self.assertEqual(len(analysis['prior_attempt_exits']), 1)
        self.assertEqual(partial['exit_code'], 1)  # raw evidence is retained, never rewritten
        monitor['exits'].append({'pid': 9, 'created_filetime': 300, 'exit_code': 7})
        self.assertTrue(runtime_exit_analysis(partial, monitor)['unexpected_exit'])
        self.assertFalse(runtime_exit_analysis(partial, {})['known'])

    def test_completed_record_and_reexec_child_exit_scopes(self):
        final = {'pid': 9, 'exit_code': 7, 'terminated_by_harness': False, 'finished_utc': '2026-11-01T00:00:00Z'}
        self.assertTrue(runtime_exit_analysis(final, {})['unexpected_exit'])
        final.update(exit_code=1, terminated_by_harness=True)
        self.assertFalse(runtime_exit_analysis(final, {})['unexpected_exit'])
        monitor = {'current_runtime_pid': 9, 'current_runtime_created_filetime': 300,
                   'exits': [{'pid': 10, 'created_filetime': 400, 'exit_code': 7}]}
        self.assertTrue(runtime_exit_analysis({'pid': 9}, monitor)['unexpected_exit'])

    def test_missing_periodic_frame_fails_even_when_another_capture_exists(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'build/frames').mkdir(parents=True)
            Image.new('RGB', (8, 8), 'red').save(root / 'build/frames/frame_00120.png')
            Image.new('RGB', (8, 8), 'red').save(root / 'build/frame_00180.png')
            m = manifest()
            m['screenshots']['every'] = 90
            checks, _ = evaluate(m, root, '[gamelib]\n[vk]', {'exit_code': 0}, 'frame_complete', metrics('', []))
            coverage = next(c for c in checks if c['name'] == 'periodic_capture_coverage')
            self.assertFalse(coverage['passed'])
            self.assertEqual(coverage['missing_frames'], [90])

    def test_missing_evidence_and_crash_never_pass(self):
        with tempfile.TemporaryDirectory() as t:
            m = manifest()
            checks, visual = evaluate(m, t, '[gamelib] loaded\n[vk] device\nFATAL: synthetic negative control',
                                      {'exit_code': 0}, 'natural_exit', metrics('', []))
            self.assertFalse(all(c['passed'] for c in checks))
            self.assertFalse(next(c['passed'] for c in checks if c['name'] == 'no_crash_markers'))
            self.assertEqual(visual['status'], 'NOT_EVALUATED')

    def test_capture_is_not_visual_approval(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'build/frames').mkdir(parents=True)
            Image.new('RGB', (8, 8), 'red').save(root / 'build/frames/frame_00120.png')
            checks, visual = evaluate(manifest(), root, '[gamelib] loaded\n[vk] device', {'exit_code': 0},
                                      'frame_complete', metrics('', []))
            self.assertTrue(all(c['passed'] for c in checks))
            self.assertEqual(visual['status'], 'NOT_EVALUATED')

    def test_visual_tolerances_size_and_baseline_integrity(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            base, shot = Path(t) / 'base.png', Path(t) / 'shot.png'
            Image.new('RGB', (8, 8), (10, 10, 10)).save(base)
            Image.new('RGB', (8, 8), (11, 10, 10)).save(shot)
            b = {'path': str(base), 'sha256': digest(base), 'rmse_max': .01,
                 'changed_fraction_max': 0, 'pixel_threshold': 1}
            self.assertTrue(compare(shot, b)['passed'])
            b['pixel_threshold'] = 0
            self.assertFalse(compare(shot, b)['passed'])
            Image.new('RGB', (4, 4), 'red').save(shot)
            self.assertFalse(compare(shot, b)['passed'])
            Image.new('RGB', (8, 8), 'blue').save(base)
            with self.assertRaises(ValueError):
                compare(shot, b)

    def test_reference_check_and_corrupt_png(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / 'build/frames').mkdir(parents=True)
            shot = root / 'build/frames/frame_00120.png'
            Image.new('RGB', (8, 8), 'red').save(shot)
            m = manifest()
            m['screenshots'].update(mode='reference', baseline={'path': str(shot), 'sha256': digest(shot), 'frame': 120,
                                    'rmse_max': 0, 'changed_fraction_max': 0, 'pixel_threshold': 0})
            checks, visual = evaluate(m, root, '[gamelib]\n[vk]', {'exit_code': 0}, 'frame_complete', metrics('', []))
            self.assertTrue(all(c['passed'] for c in checks))
            self.assertEqual(visual['status'], 'PASS')
            shot.write_bytes(b'corrupt')
            with self.assertRaises(OSError):
                png(shot)

    def test_metrics_unknown_vs_sampled(self):
        log = '[vk] t=2.0 frame 60 30.0 fps max 35ms\n[vk] t=4.0 frame 120 30.0 fps max 40ms\n[pace] period 33.2 blocked 2.0 busy 31.2 ms'
        m = metrics(log, [])
        self.assertEqual(m['presentation_fps_from_rounded_counters_estimate'], 30)
        self.assertEqual(m['pace_period_ms']['99'], 33.2)
        self.assertIsNone(m['simulation_ticks'])
        self.assertIsNone(m['gpu_utilization_percent'])


@unittest.skipUnless(os.name == 'nt', 'Windows process adapter')
class NativeContainment(unittest.TestCase):
    def test_exit_handle_retains_nonzero_exit_after_pid_is_gone(self):
        p = subprocess.Popen([sys.executable, '-c', 'import sys;sys.stdin.readline();sys.exit(7)'], stdin=subprocess.PIPE)
        watch = windows.RuntimeWatch(Path(sys.executable).name)
        try:
            original = windows.process_sample(p.pid)
            watch.observe([p.pid])
            p.stdin.write(b'GO\n')
            p.stdin.close()
            p.wait(timeout=3)
            watch.observe([p.pid])  # observing an already terminated, retained process is harmless
            self.assertEqual(watch.exits()[0]['exit_code'], 7)
            self.assertFalse(windows.identity_alive(original))
        finally:
            watch.close()
            if p.poll() is None:
                p.kill()
                p.wait()

    def recovery_fixture(self, root):
        q = load_module('synthetic_recovery_board', Path(__file__).resolve().parents[1] / 'console-install-queue/console_queue.py')
        board = q.Board(root / 'synthetic-pc-state', resource='pc')
        store = Store(root / 'journal')
        # A real terminated process identity proves the original worker is dead.
        child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
        dead = windows.process_sample(child.pid)
        child.terminate()
        child.wait(timeout=3)
        row = store.submit(manifest(), '0' * 64)
        job = store.claim({k: dead[k] for k in ('pid', 'created_filetime')})
        out = root / 'results' / job['execution_id']
        store.update(job['id'], result_path=str(out / 'result.json'), request_id=job['execution_id'])
        adapter = type('SyntheticAdapter', (), {'board': board, 'module': q})()
        return adapter, store, store.get(job['id']), out

    def test_recovery_releases_only_own_exact_turn(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            adapter, store, job, out = self.recovery_fixture(root)
            request = root / 'synthetic-request.json'
            atomic_json(request, {'name': 'synthetic recovery only'})
            ticket = adapter.board.enqueue('unit', job['execution_id'], request)['ticket']
            claim = adapter.board.claim('unit', ticket)
            atomic_json(store.root / 'private' / (job['execution_id'] + '.json'), {'agent': 'unit', **claim})
            out.mkdir(parents=True)
            atomic_json(out / 'result.json', {'status': 'ERROR', 'reason': 'original failure must survive recovery'})
            with patch.object(worker, 'CanonicalPC', return_value=adapter):
                results = worker.recover({'results_root': str(root / 'results')}, store)
            self.assertEqual(results[0]['status'], 'ERROR')
            self.assertIsNone(adapter.board.load()['active'])
            self.assertEqual(store.get(job['id'])['phase'], 'FINISHED')
            self.assertTrue((out / 'recovery-process-cleanup.json').is_file())
            self.assertEqual(results[0]['pre_recovery_result']['original_reason'], 'original failure must survive recovery')
            self.assertTrue((out / results[0]['pre_recovery_result']['path']).is_file())

    def test_recovery_preserves_another_agents_turn(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            adapter, store, job, out = self.recovery_fixture(root)
            request = root / 'foreign-request.json'
            atomic_json(request, {'name': 'synthetic other agent'})
            ticket = adapter.board.enqueue('other-agent', 'different-request', request)['ticket']
            claim = adapter.board.claim('other-agent', ticket)
            with patch.object(worker, 'CanonicalPC', return_value=adapter):
                worker.recover({'results_root': str(root / 'results')}, store)
            self.assertEqual(adapter.board.load()['active']['lease_id'], claim['lease_id'])
            self.assertEqual(store.get(job['id'])['verdict'], 'ERROR')

    def test_already_released_legacy_handoff_preserves_next_owner(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            adapter, store, job, out = self.recovery_fixture(root)
            out.mkdir(parents=True)
            request = root / 'synthetic-request.json'
            atomic_json(request, {'name': 'synthetic legacy handoff'})
            ticket = adapter.board.enqueue('unit', job['execution_id'], request)['ticket']
            claim = adapter.board.claim('unit', ticket)
            proof = out / 'legacy-processes.json'
            atomic_json(proof, {'active_processes': 0})
            handoff = out / 'legacy-handoff.json'
            atomic_json(handoff, {'ticket': ticket, 'own_processes_stopped': True,
                                 'evidence': {'path': str(proof), 'sha256': digest(proof)}})
            adapter.board.release('unit', ticket, claim['token'], reason='synthetic legacy release', resolution=handoff)
            other_ticket = adapter.board.enqueue('other', 'next-turn', request)['ticket']
            other = adapter.board.claim('other', other_ticket)
            result = worker.CanonicalPC.release(adapter, job, claim, out, {'active_processes': 0})
            self.assertTrue(result['already_released_by_legacy_runner'])
            self.assertEqual(adapter.board.load()['active']['lease_id'], other['lease_id'])

    def test_gate_and_stop_own_process(self):
        job = windows.Job('Local\\ZA-Synthetic-' + uuid.uuid4().hex)
        p = subprocess.Popen([sys.executable, '-c', 'import sys,time; sys.stdin.readline(); time.sleep(30)'], stdin=subprocess.PIPE)
        try:
            job.assign(p)
            self.assertIn(p.pid, job.pids())
            self.assertIsNotNone(windows.process_sample(p.pid))
            self.assertEqual(job.stop()['active_processes'], 0)
            p.wait(timeout=3)
        finally:
            p.stdin.close()
            job.close()
            if p.poll() is None:
                p.kill()
                p.wait()

    def test_diagnostic_failure_cannot_block_real_process_cleanup(self):
        job = windows.Job('Local\\ZA-Synthetic-' + uuid.uuid4().hex)
        p = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(30)'])
        class FaultyWatch:
            def observe(self, pids):
                raise PermissionError('injected diagnostic failure')
        try:
            job.assign(p)
            proof, monitor = worker.shutdown_tree(job, p, FaultyWatch())
            self.assertEqual(proof['active_processes'], 0)
            self.assertIn('injected diagnostic failure', monitor['error'])
            self.assertIsNotNone(p.poll())
        finally:
            job.close()
            if p.poll() is None:
                p.kill()
                p.wait()

    def test_kill_on_supervisor_crash_includes_descendant(self):
        with tempfile.TemporaryDirectory() as t:
            marker = Path(t) / 'child.json'
            code = ('import sys,subprocess,time,json,os; from pathlib import Path; '
                    f'sys.path.insert(0,{str(Path(__file__).parent)!r}); import windows; '
                    f'j=windows.Job({"Local-ZA-Synthetic-" + uuid.uuid4().hex!r}); '
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(60)"]); '
                    'j.assign(p); '
                    f'Path({str(marker)!r}).write_text(json.dumps(windows.process_sample(p.pid))); '
                    'time.sleep(60)')
            supervisor = subprocess.Popen([sys.executable, '-I', '-B', '-c', code])
            try:
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline:
                    time.sleep(.05)
                child = read_json(marker)
                supervisor.kill()
                supervisor.wait(timeout=3)
                deadline = time.monotonic() + 5
                while windows.identity_alive(child) and time.monotonic() < deadline:
                    time.sleep(.05)
                self.assertFalse(windows.identity_alive(child))
            finally:
                if supervisor.poll() is None:
                    supervisor.kill()
                    supervisor.wait()

    def test_os_worker_lock_excludes_second_process(self):
        with tempfile.TemporaryDirectory() as t:
            code = (f'import sys;sys.path.insert(0,{str(Path(__file__).parent)!r}); '
                    f'from store import worker_lock; ctx=worker_lock({t!r});ctx.__enter__()')
            with worker_lock(t):
                p = subprocess.run([sys.executable, '-I', '-B', '-c', code], capture_output=True)
                self.assertNotEqual(p.returncode, 0)


if __name__ == '__main__':
    unittest.main()
