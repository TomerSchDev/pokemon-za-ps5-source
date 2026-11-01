"""Synthetic offline tests for both resource queues, deadlines and baseline handoff."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('legacy_tests', Path(__file__).with_name('test_console_queue.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
q = fixture.q


class Turns(unittest.TestCase):
    # Reuse proof fixtures without running the original suite twice.
    setUp = fixture.QueueTests.setUp
    tearDown = fixture.QueueTests.tearDown
    file = fixture.QueueTests.file
    write_json = fixture.QueueTests.write_json
    ready = fixture.QueueTests.ready
    receipt = fixture.QueueTests.receipt
    handoff = fixture.QueueTests.handoff
    submit = fixture.QueueTests.submit
    def test_uncontested_turn_is_unlimited_with_heartbeats(self):
        ticket = self.submit()
        lease = self.board.claim('owner')
        for _ in range(30):
            self.clock[0] += 500
            status = self.board.heartbeat('owner', ticket, lease['token'])
            self.assertIsNone(status['yield_by'])

    def test_first_waiter_sets_deadline_renew_cancel_and_more_waiters_cannot_extend(self):
        ticket = self.submit()
        lease = self.board.claim('owner')
        self.clock[0] += 60
        waiting = self.submit('waiting')
        deadline = self.clock[0] + 600
        self.assertEqual(self.board.status()['active']['yield_by'], deadline)
        self.clock[0] += 300
        self.submit('another')
        self.board.release('submitter', waiting, reason='cancel', cancel_queued=True)
        self.assertEqual(self.board.heartbeat('owner', ticket, lease['token'])['yield_by'], deadline)
        self.clock[0] = deadline
        with self.assertRaises(q.LostLease): self.board.check('owner', ticket, lease['token'])
        self.assertTrue(self.board.heartbeat('owner', ticket, lease['token'])['must_yield'])
        with self.assertRaises(q.Busy): self.board.claim('next')
        self.board.release('owner', ticket, lease['token'], reason='yield')
        self.assertEqual(self.board.claim('next')['ticket'], '00000003')

    def test_waiter_already_queued_at_claim_starts_full_window(self):
        self.submit()
        self.submit('two')
        claim = self.board.claim('owner')
        self.assertEqual(claim['yield_by'], self.clock[0] + 600)

    def test_expired_deadline_allows_safe_completion_but_not_new_install(self):
        ticket = self.submit()
        lease = self.board.claim('owner')
        self.board.heartbeat('owner', ticket, lease['token'], begin_install=self.ready(ticket))
        self.submit('waiting')
        self.clock[0] += 500
        self.board.heartbeat('owner', ticket, lease['token'])
        self.clock[0] += 101
        self.board.complete('owner', ticket, lease['token'], self.receipt(ticket))
        self.assertIsNone(self.board.status()['active'])
        with self.assertRaises(q.QueueError): self.board.claim('next')  # queued base now obsolete

    def test_promotion_requires_handoff_and_blocks_old_base(self):
        ticket = self.submit()
        lease = self.board.claim('owner')
        self.board.heartbeat('owner', ticket, lease['token'], begin_install=self.ready(ticket))
        receipt = self.receipt(ticket)
        data = q.read_json(receipt)
        del data['baseline_handoff']
        receipt.write_text(json.dumps(data))
        with self.assertRaises(q.QueueError): self.board.complete('owner', ticket, lease['token'], receipt)
        self.board.complete('owner', ticket, lease['token'], self.receipt(ticket))
        baseline = self.board.status()['baselines']['PPSA91762']
        self.assertEqual(baseline['files'][self.remote], q.digest(self.artifact))
        old_ticket = self.submit('old-base')
        with self.assertRaises(q.QueueError): self.board.claim('next', old_ticket)
        self.board.release('submitter', old_ticket, reason='rebuild on new base', cancel_queued=True)
        data = q.read_json(self.job)
        data['expected_base'][0]['sha256'] = q.digest(self.artifact)
        self.board.enqueue('rebuilder', 'new-base', self.write_json('new-base-job.json', data))
        self.assertIsNotNone(self.board.claim('rebuilder')['token'])

    def test_restore_requires_actual_old_readback_and_preserves_waiter(self):
        ticket = self.submit()
        lease = self.board.claim('owner')
        self.board.heartbeat('owner', ticket, lease['token'], begin_install=self.ready(ticket))
        next_ticket = self.submit('waiter')
        receipt = self.receipt(ticket)
        data = q.read_json(receipt)
        data['baseline_handoff'] = self.handoff('restore')
        receipt.write_text(json.dumps(data))
        self.board.complete('owner', ticket, lease['token'], receipt)
        self.assertEqual(self.board.status()['baselines']['PPSA91762']['files'][self.remote], q.digest(self.old))
        self.assertEqual(self.board.claim('next')['ticket'], next_ticket)

    def test_pc_bypass_requires_recorded_user_approval(self):
        ticket = self.submit()
        ready = self.ready(ticket)
        data = q.read_json(ready)
        del data['pc_validation']
        ready.write_text(json.dumps(data))
        with self.assertRaises(q.QueueError): self.board.readiness(ready, self.board.load()['jobs'][0])
        data['pc_bypass'] = {'approved_by': 'Tomer', 'reason': 'urgent_fix', 'approval_evidence': self.file(self.proof)}
        ready.write_text(json.dumps(data))
        self.board.readiness(ready, self.board.load()['jobs'][0])


class PcTurns(unittest.TestCase):
    def test_pc_release_requeues_at_tail_and_stale_needs_exact_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = [1000.]
            pc = q.Board(root / 'state', clock=lambda: now[0], resource='pc')
            job = root / 'job.json'
            job.write_text('{"name":"synthetic PC test"}')
            first = pc.enqueue('a', 'one', job)['ticket']
            lease = pc.claim('a', lease_seconds=30)
            second = pc.enqueue('b', 'two', job)['ticket']
            proof = root / 'proof.txt'
            proof.write_text('Synthetic stopped process fixture.')
            receipt = root / 'handoff.json'
            record = {'ticket': first, 'own_processes_stopped': True,
                      'evidence': {'path': str(proof), 'sha256': q.digest(proof)}}
            receipt.write_text(json.dumps(record))
            pc.release('a', first, lease['token'], reason='yield', resolution=receipt)
            third = pc.enqueue('a', 'remaining-work', job)['ticket']
            self.assertGreater(third, second)
            lease = pc.claim('b')
            now[0] += 601
            record.update(ticket=second, lease_id=lease['lease_id'], pc_handoff_confirmed=True)
            receipt.write_text(json.dumps(record))
            pc.release('coordinator', second, reason='observed no processes', resolution=receipt,
                       expected_lease_id=lease['lease_id'])
            self.assertEqual(pc.claim('a')['ticket'], third)

    def test_separate_resources_300_seconds_and_cleanup_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            now = [1000.]
            pc = q.Board(root / 'pc', clock=lambda: now[0], resource='pc')
            console = q.Board(root / 'console', clock=lambda: now[0])
            job = root / 'job.json'
            job.write_text(json.dumps({'name': 'synthetic PC test'}))
            first = pc.enqueue('a', 'one', job)['ticket']
            lease = pc.claim('a')
            self.assertIsNone(console.status()['active'])
            with self.assertRaises(q.RecoveryRequired): q.Board(root / 'pc').status()
            pc.enqueue('b', 'two', job)
            self.assertEqual(pc.status()['active']['yield_by'], 1300.)
            now[0] = 1301.
            with self.assertRaises(q.LostLease): pc.check('a', first, lease['token'])
            with self.assertRaises(q.Busy): pc.claim('b')
            with self.assertRaises(q.QueueError): pc.release('a', first, lease['token'], reason='yield')
            proof = root / 'stopped.txt'
            proof.write_text('Synthetic fixture: no processes launched.')
            receipt = root / 'pc-receipt.json'
            receipt.write_text(json.dumps({'ticket': first, 'own_processes_stopped': True,
                'evidence': {'path': str(proof), 'sha256': q.digest(proof)}}))
            pc.complete('a', first, lease['token'], receipt)
            self.assertEqual(pc.claim('b')['ticket'], '00000002')


if __name__ == '__main__':
    unittest.main(verbosity=2)
