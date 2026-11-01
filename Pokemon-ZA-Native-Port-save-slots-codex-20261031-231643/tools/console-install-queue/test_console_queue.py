#!/usr/bin/env python3
"""Host-only protocol tests. Every queue and artifact lives in a fresh temp dir."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("console_queue.py")
spec = importlib.util.spec_from_file_location("install_queue", SCRIPT)
q = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = q
spec.loader.exec_module(q)


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="console-queue-test-")
        self.base = Path(self.temporary.name)
        self.root = self.base / "state"
        self.clock = [10000.0]
        self.board = q.Board(self.root, clock=lambda: self.clock[0])
        self.artifact = self.base / "candidate.bin"
        self.artifact.write_bytes(b"synthetic-new-artifact")
        self.old = self.base / "previous-readback.bin"
        self.old.write_bytes(b"synthetic-installed-base")
        self.proof = self.base / "observations.txt"
        self.proof.write_text("Synthetic test fixture only. No console contact.\n")
        self.remote = "/data/homebrew/PPSA91762/eboot.bin"
        self.job = self.write_json("job.json", {"console": q.CONSOLE, "title_id": "PPSA91762", "name": "test only",
            "artifacts": [{**self.file(self.artifact), "remote_path": self.remote}],
            "expected_base": [{"remote_path": self.remote, "sha256": q.digest(self.old)}],
            "external_dependencies": [{"kind": "agent_thread", "state": "unknown", "thread_id": "test-thread"}]})

    def tearDown(self):
        self.temporary.cleanup()

    def file(self, path):
        return {"path": str(path), "sha256": q.digest(path)}

    def write_json(self, name, value):
        path = self.base / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def ready(self, ticket):
        return self.write_json("ready.json", {"console": q.CONSOLE, "ticket": ticket,
            "checked_at": datetime.fromtimestamp(self.clock[0], timezone.utc).isoformat(),
            "external_owner_handoff": {"confirmed": True, "evidence": self.file(self.proof)},
            "game_closed": {"verified": True, "evidence": self.file(self.proof)},
            "save_backup": {"fresh": True, "all_runs": True, "readback_verified": True, "evidence": self.file(self.proof)},
            "base_readbacks": [{"remote_path": self.remote, "sha256": q.digest(self.old), "evidence": self.file(self.old)}]})

    def receipt(self, ticket):
        return self.write_json("receipt.json", {"console": q.CONSOLE, "ticket": ticket,
            "save_backup_still_verified": True, "console_handoff_complete": True,
            "readbacks": [{"remote_path": self.remote, "staged": self.file(self.artifact), "installed": self.file(self.artifact)}]})

    def submit(self, request="one"):
        return self.board.enqueue("submitter", request, self.job)["ticket"]

    def cli(self, *args):
        result = subprocess.run([sys.executable, "-I", str(SCRIPT), "--root", str(self.root), *args],
                                capture_output=True, text=True, timeout=30)
        return result.returncode, json.loads(result.stdout)

    def test_status_does_not_create_state_and_no_hardware_imports(self):
        self.assertFalse(self.board.status()["initialized"])
        self.assertFalse(self.root.exists())
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("ftplib", source)
        self.assertNotIn("urllib", source)
        self.assertNotIn("socket.connect", source)

    def test_idempotent_enqueue_and_changed_identity_rejected(self):
        ticket = self.submit()
        self.assertEqual(self.board.enqueue("submitter", "one", self.job)["ticket"], ticket)
        self.assertEqual(self.board.load()["next_ticket"], 2)
        with self.assertRaises(q.QueueError): self.board.enqueue("different-agent", "one", self.job)
        self.assertEqual(self.board.status()["jobs"][0]["job"]["external_dependencies"][0]["state"], "unknown")

    def test_concurrent_enqueue_assigns_unique_monotonic_tickets(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: self.cli("enqueue", "--agent", "worker", "--request-id", f"parallel-{i}", "--job", str(self.job)), range(16)))
        self.assertTrue(all(code == 0 for code, _ in results), results)
        tickets = sorted(row["ticket"] for _, row in results)
        self.assertEqual(tickets, [f"{i:08d}" for i in range(1, 17)])
        self.assertEqual([r["ticket"] for r in self.board.load()["jobs"]], tickets)

    def test_concurrent_claim_has_one_winner_console_wide(self):
        self.submit()
        self.submit("two")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda i: self.cli("claim", "--agent", f"worker-{i}"), range(8)))
        winners = [row for code, row in results if code == 0]
        self.assertEqual(len(winners), 1, results)
        self.assertEqual(winners[0]["ticket"], "00000001")
        self.assertTrue(all(code in (0, 4) for code, _ in results))
        self.assertEqual(self.board.load()["jobs"][1]["state"], "queued")

    def test_fifo_no_skip_release_keeps_ticket_and_cancel_with_owner(self):
        first, second = self.submit(), self.submit("two")
        with self.assertRaises(q.Busy): self.board.claim("installer", second)
        claim = self.board.claim("installer", first)
        self.board.release("installer", first, claim["token"], "not ready")
        self.assertEqual(self.board.claim("installer")["ticket"], first)
        with self.assertRaises(q.QueueError): self.board.release("other", second, reason="withdraw", cancel_queued=True)
        self.board.release("submitter", second, reason="withdraw", cancel_queued=True)

    def test_bad_token_expiry_cannot_renew_or_take_over(self):
        ticket = self.submit()
        lease = self.board.claim("owner", lease_seconds=30)
        with self.assertRaises(q.LostLease): self.board.heartbeat("owner", ticket, "bad-token")
        self.clock[0] += 31
        with self.assertRaises(q.LostLease): self.board.heartbeat("owner", ticket, lease["token"])
        with self.assertRaises(q.Busy): self.board.claim("next")
        self.assertTrue(self.board.status()["active"]["expired"])
        with self.assertRaises(q.LostLease): self.board.release("owner", ticket, lease["token"], "expired")

    def test_installing_stale_requires_explicit_matching_resolution(self):
        ticket = self.submit()
        lease = self.board.claim("owner", lease_seconds=30)
        self.board.heartbeat("owner", ticket, lease["token"], begin_install=self.ready(ticket))
        with self.assertRaises(q.QueueError): self.board.release("owner", ticket, lease["token"], "cannot silently release")
        self.clock[0] += 31
        with self.assertRaises(q.QueueError): self.board.release("coordinator", ticket, reason="reconcile", expected_lease_id=lease["lease_id"])
        resolution = self.write_json("resolution.json", {"console": q.CONSOLE, "ticket": ticket,
            "lease_id": lease["lease_id"], "no_active_installation": True, "console_handoff_confirmed": True, "evidence": self.file(self.proof)})
        self.board.release("coordinator", ticket, reason="explicit fixture reconciliation", resolution=resolution, expected_lease_id=lease["lease_id"])
        newer = self.board.claim("new-owner")
        self.assertNotEqual(newer["lease_id"], lease["lease_id"])
        with self.assertRaises(q.LostLease): self.board.heartbeat("owner", ticket, lease["token"])

    def test_readiness_is_concrete_and_base_mismatch_blocks_without_state_change(self):
        ticket = self.submit()
        lease = self.board.claim("owner")
        path = self.ready(ticket)
        document = q.read_json(path)
        document["game_closed"]["verified"] = False
        path.write_text(json.dumps(document))
        with self.assertRaises(q.QueueError): self.board.heartbeat("owner", ticket, lease["token"], begin_install=path)
        self.assertEqual(self.board.status()["active"]["phase"], "reserved")
        path = self.ready(ticket)
        document = q.read_json(path)
        document["base_readbacks"][0]["sha256"] = "0" * 64
        path.write_text(json.dumps(document))
        with self.assertRaises(q.QueueError): self.board.heartbeat("owner", ticket, lease["token"], begin_install=path)
        self.clock[0] += 301
        with self.assertRaises(q.QueueError): self.board.heartbeat("owner", ticket, lease["token"], begin_install=path)

    def test_changed_artifact_blocks_claim_and_begin_install(self):
        ticket = self.submit()
        self.artifact.write_bytes(b"changed after enqueue")
        with self.assertRaises(q.QueueError): self.board.claim("owner")
        self.assertIsNone(self.board.load()["active"])

    def test_complete_checks_both_readbacks_and_double_complete_idempotent(self):
        ticket = self.submit()
        lease = self.board.claim("owner")
        receipt = self.receipt(ticket)
        with self.assertRaises(q.QueueError): self.board.complete("owner", ticket, lease["token"], receipt)
        self.board.heartbeat("owner", ticket, lease["token"], begin_install=self.ready(ticket))
        document = q.read_json(receipt)
        document["readbacks"][0]["installed"] = self.file(self.old)
        receipt.write_text(json.dumps(document))
        with self.assertRaises(q.QueueError): self.board.complete("owner", ticket, lease["token"], receipt)
        receipt = self.receipt(ticket)
        self.board.complete("owner", ticket, lease["token"], receipt)
        generation = self.board.load()["generation"]
        self.assertTrue(self.board.complete("owner", ticket, lease["token"], receipt)["already_completed"])
        self.assertEqual(self.board.load()["generation"], generation)
        self.assertEqual(sum(e["event"] == "completed" for e in self.board.load()["jobs"][0]["events"]), 1)

    def test_concurrent_double_complete_commits_once(self):
        ticket = self.submit()
        lease = self.board.claim("owner")
        self.board.heartbeat("owner", ticket, lease["token"], begin_install=self.ready(ticket))
        receipt = self.receipt(ticket)
        # CLI uses wall time; replace only the test lease timestamps with current time.
        with self.board.transaction("test-fixture") as state:
            state["active"]["heartbeat_at"] = q.time.time()
            self.board.save(state)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.cli("complete", "--agent", "owner", "--ticket", ticket, "--token", lease["token"], "--receipt", str(receipt)), range(2)))
        self.assertTrue(all(code == 0 for code, _ in results), results)
        self.assertEqual(sum(r.get("already_completed", False) for _, r in results), 1)

    def test_corrupted_state_fails_closed_does_not_restore_previous(self):
        self.submit()
        self.submit("two")
        previous = (self.root / "state.prev.json").read_bytes()
        envelope = json.loads(self.board.path.read_bytes())
        envelope["payload"]["next_ticket"] = 100
        self.board.path.write_text(json.dumps(envelope))
        with self.assertRaises(q.RecoveryRequired): self.board.status()
        self.assertEqual((self.root / "state.prev.json").read_bytes(), previous)

    def test_failure_before_atomic_replace_keeps_valid_previous_state(self):
        self.submit()
        before = self.board.path.read_bytes()
        original = q.os.replace
        def fail(source, target):
            if Path(target) == self.board.path: raise OSError("simulated crash before commit")
            return original(source, target)
        with patch.object(q.os, "replace", side_effect=fail):
            with self.assertRaises(OSError): self.submit("two")
        self.assertEqual(self.board.path.read_bytes(), before)
        self.assertEqual(len(self.board.load()["jobs"]), 1)
        self.assertFalse(self.board.mutex.exists())

    def test_abandoned_metadata_mutex_is_not_stolen(self):
        self.submit()
        self.board.mutex.mkdir()
        owner = {"nonce": "abandoned-test-only", "agent": "test-crashed-process", "pid": -1}
        (self.board.mutex / "owner.json").write_text(json.dumps(owner))
        with self.assertRaises(q.Busy):
            with self.board.transaction("new", wait_seconds=0): pass
        self.assertEqual(self.board.status()["metadata_mutex"]["nonce"], "abandoned-test-only")

    def test_failure_after_atomic_replace_is_valid_and_retry_does_not_duplicate(self):
        self.submit()
        original = q.os.replace
        def commit_then_fail(source, target):
            result = original(source, target)
            if Path(target) == self.board.path: raise OSError("simulated interruption immediately after commit")
            return result
        with patch.object(q.os, "replace", side_effect=commit_then_fail):
            with self.assertRaises(OSError): self.submit("two")
        self.assertEqual(len(self.board.load()["jobs"]), 2)
        retry = self.board.enqueue("submitter", "two", self.job)
        self.assertTrue(retry["already_enqueued"])
        self.assertEqual(len(self.board.load()["jobs"]), 2)

    def test_lease_cannot_expire_during_readiness_and_then_be_revived(self):
        ticket = self.submit()
        lease = self.board.claim("owner", lease_seconds=30)
        original = self.board.readiness
        def slow_validation(path, row):
            result = original(path, row)
            self.clock[0] += 31
            return result
        with patch.object(self.board, "readiness", side_effect=slow_validation):
            with self.assertRaises(q.LostLease):
                self.board.heartbeat("owner", ticket, lease["token"], begin_install=self.ready(ticket))
        self.assertEqual(self.board.load()["active"]["phase"], "reserved")

    def test_different_titles_share_the_same_exclusive_console_reservation(self):
        first = self.submit()
        document = q.read_json(self.job)
        document["title_id"] = "PPSA91763"
        document["artifacts"][0]["remote_path"] = "/data/homebrew/PPSA91763/eboot.bin"
        document["expected_base"][0]["remote_path"] = "/data/homebrew/PPSA91763/eboot.bin"
        second = self.board.enqueue("other-title", "other", self.write_json("other-title.json", document))["ticket"]
        self.board.claim("first-installer", first)
        with self.assertRaises(q.Busy): self.board.claim("second-installer", second)

    def test_real_process_crash_leaves_valid_state_and_blocks_new_writers(self):
        self.submit()
        code = ("import importlib.util,os\n"
                f"s=importlib.util.spec_from_file_location('q',{str(SCRIPT)!r})\n"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
                f"b=m.Board({str(self.root)!r})\n"
                "with b.transaction('crashed-test') as state:\n"
                " state['crash_fixture']=True\n"
                " b.save(state)\n"
                " os._exit(77)\n")
        result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 77, result.stderr)
        self.assertTrue(self.board.load()["crash_fixture"])
        self.assertEqual(self.board.status()["metadata_mutex"]["agent"], "crashed-test")
        with self.assertRaises(q.Busy):
            with self.board.transaction("new-writer", wait_seconds=0): pass


if __name__ == "__main__":
    unittest.main(verbosity=2)
