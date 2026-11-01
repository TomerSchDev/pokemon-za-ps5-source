"""Read-only installer audit: AST-load its functions; all console/queue I/O is synthetic.

Run: py -3 -I port/r28b-dlc-dex/test/test_install_transaction.py
No imports of the real console API, observer or queue module are executed.
"""
import ast
import contextlib
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest

SOURCE = Path(__file__).resolve().parents[1] / "install-r28b.py"

def digest(data):
    return hashlib.sha256(data).hexdigest()

def load_functions():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8-sig"), filename=str(SOURCE))
    tree.body = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef))]
    env = dict(Path=Path, json=json, hashlib=hashlib, os=os, threading=threading, time=time,
               AGENT="synthetic-installer", APP="/app", EBOOT="/app/eboot.bin")
    env["api"] = SimpleNamespace(HOST="synthetic-console", utc_now=lambda: "2026-10-30T00:00:00Z", stamp=lambda: "synthetic")
    exec(compile(tree, str(SOURCE), "exec"), env)
    return env

class FakeLease:
    def __init__(self, fail_on=None):
        self.data = {"ticket": "synthetic-ticket", "token": "synthetic-token"}
        self.beats = 0
        self.failed = None
        self.fail_on = fail_on
    def check(self):
        if self.failed:
            raise RuntimeError("Lost queue lease")
    def authorize_install(self):
        self.check()  # Policy rejection is exercised with the real queue/guard in test_install_enforcement.py.
    def heartbeat(self, begin_install=None):
        self.check()
        self.beats += 1
        if self.beats == self.fail_on:
            self.failed = RuntimeError("synthetic lease revoked")
            self.check()

class FakeFTP:
    def __init__(self, lease, base, new):
        self.lease = lease
        self.files = {"/app/eboot.bin": base}
        self.new = new
        self.events = []
        self.corrupt_stage = False
        self.corrupt_installed = False
        self.fail_new = False
        self.mutate_then_fail_new = False
        self.corrupt_backup_on_failure = False
    def mutate(self, what):
        self.lease.check()
        self.events.append(what)
    def storbinary(self, command, source, blocksize, callback):
        path = command.removeprefix("STOR ")
        data = source.read()
        callback(data)
        self.mutate(("store", path))
        self.files[path] = b"corrupted-stage" if self.corrupt_stage else data
    def retrbinary(self, command, callback, blocksize):
        path = command.removeprefix("RETR ")
        self.events.append(("read", path))
        callback(self.files[path])
    def rename(self, old, new):
        self.lease.check()
        self.events.append(("rename-attempt", old, new))
        if self.fail_new and ".new-" in old:
            if self.mutate_then_fail_new:
                self.mutate(("rename", old, new))
                self.files[new] = self.files.pop(old)
            if self.corrupt_backup_on_failure:
                for path in list(self.files):
                    if ".before-r28b-" in path:
                        self.files[path] = b"unexpected backup modification"
            raise OSError("synthetic new-image rename failed")
        if old not in self.files:
            raise FileNotFoundError(old)
        self.mutate(("rename", old, new))
        self.files[new] = self.files.pop(old)
        if self.corrupt_installed and ".new-" in old:
            self.files[new] = b"corrupted-after-rename"

class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="r28b-install-synthetic-")
        self.root = Path(self.temp.name)
        self.out = self.root / "evidence"
        self.out.mkdir()
        self.base = b"synthetic original image\0\1\2"
        self.new = b"synthetic replacement image\3\4\5"
        self.e = load_functions()
        self.e.update(BASE=digest(self.base), NEW=digest(self.new), PACKAGE=self.root / "package")
        artifact = self.root / "package/PPSA91762/eboot.bin"
        artifact.parent.mkdir(parents=True)
        artifact.write_bytes(self.new)
        (self.out / "original").mkdir()
        (self.out / "original/eboot.bin").write_bytes(self.base)
        (self.out / "external-handoff.json").write_text('{"synthetic": true}')
        backup = self.out / "synthetic-save"
        backup.write_bytes(b"synthetic save data")
        self.e["write"](self.out / "save-backup-manifest.json", dict(all_runs=True, double_read_verified=True,
                         files=[dict(path=str(backup), sha256=digest(backup.read_bytes()))]))
        self.processes = []
        self.kills = []
        self.e["api"].eboot_processes = lambda: self.processes
        self.e["api"].http_json = lambda url: self.kills.append(url)
        self.e["emit"] = lambda record: None
    def tearDown(self):
        self.temp.cleanup()
    def setup_console(self, fail_on=None):
        lease = FakeLease(fail_on)
        ftp = FakeFTP(lease, self.base, self.new)
        c = SimpleNamespace(ftp=ftp)
        c.sha256 = lambda path: digest(ftp.files[path]) if path in ftp.files else None
        c.chmod = lambda path, mode: ftp.mutate(("chmod", path, mode))
        c.listing = lambda path: [name.rsplit("/", 1)[1] for name in ftp.files if name.rsplit("/", 1)[0] == path]
        return c, lease
    def invoke(self, c, lease):
        self.e["install"](c, lease, self.out)
    def renames(self, c):
        return [x for x in c.ftp.events if x[0] == "rename"]
    def test_success_actual_readbacks(self):
        c, lease = self.setup_console()
        self.invoke(c, lease)
        transaction = self.e["read"](self.out / "transaction.json")
        self.assertTrue(transaction["installed_readback_verified"])
        for kind in ("staged", "installed"):
            record = transaction[kind + "_readback"]
            actual = Path(record["path"]).read_bytes()
            self.assertEqual(actual, self.new)
            self.assertEqual(record["sha256"], digest(actual))
        self.assertEqual(c.ftp.files[transaction["remote_backup"]], self.base)
        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.new)
        self.assertEqual(len(self.renames(c)), 2)
        self.assertEqual(self.kills, [])
    def test_stage_hash_mismatch_no_rename(self):
        c, lease = self.setup_console()
        c.ftp.corrupt_stage = True
        with self.assertRaisesRegex(RuntimeError, "Staged image"):
            self.invoke(c, lease)
        self.assertEqual(self.renames(c), [])
        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.base)
    def test_lost_lease_at_each_heartbeat_no_further_remote_write(self):
        for beat in range(1, 7):
            with self.subTest(beat=beat):
                # Distinct local evidence avoids prior-test readback reuse.
                original_out = self.out
                self.out = original_out / ("lease-" + str(beat))
                self.out.mkdir()
                for name in ("save-backup-manifest.json", "external-handoff.json"):
                    (self.out / name).write_bytes((original_out / name).read_bytes())
                (self.out / "original").mkdir()
                (self.out / "original/eboot.bin").write_bytes(self.base)
                c, lease = self.setup_console(beat)
                try:
                    with self.assertRaisesRegex(RuntimeError, "Lost queue lease"):
                        self.invoke(c, lease)
                    if beat <= 5:
                        self.assertEqual(self.renames(c), [])
                        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.base)
                    else:
                        self.assertEqual(len(self.renames(c)), 1)
                        self.assertNotIn("/app/eboot.bin", c.ftp.files)
                finally:
                    self.out = original_out
    def test_failed_new_rename_restores_only_just_renamed_original(self):
        c, lease = self.setup_console()
        c.ftp.fail_new = True
        with self.assertRaisesRegex(OSError, "new-image rename"):
            self.invoke(c, lease)
        renames = self.renames(c)
        self.assertEqual(len(renames), 2)
        self.assertEqual(renames[0][1], "/app/eboot.bin")
        self.assertEqual(renames[1], ("rename", renames[0][2], "/app/eboot.bin"))
        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.base)
        self.assertTrue(self.e["read"](self.out / "transaction.json")["original_restored_after_rename_failure"])
    def test_lost_lease_during_rollback_does_not_restore(self):
        for beat in (7, 8):
            with self.subTest(heartbeat=beat):
                (self.out / "readbacks/staged-eboot.bin").unlink(missing_ok=True)
                c, lease = self.setup_console(beat)
                c.ftp.fail_new = True
                with self.assertRaisesRegex(RuntimeError, "Lost queue lease"):
                    self.invoke(c, lease)
                self.assertEqual(len(self.renames(c)), 1)
                self.assertNotIn("/app/eboot.bin", c.ftp.files)
    def test_installed_mismatch_never_claims_verified(self):
        c, lease = self.setup_console()
        c.ftp.corrupt_installed = True
        with self.assertRaisesRegex(RuntimeError, "Installed readback"):
            self.invoke(c, lease)
        self.assertFalse(self.e["read"](self.out / "transaction.json")["installed_readback_verified"])
    def test_unknown_process_prevents_any_mutation(self):
        c, lease = self.setup_console()
        self.processes = [{"pid": 999, "name": "unknown eboot"}]
        with self.assertRaisesRegex(RuntimeError, "unidentified process"):
            self.invoke(c, lease)
        self.assertEqual(c.ftp.events, [])
        self.assertEqual(self.kills, [])
    def test_close_owned_identity_mismatch_never_kills(self):
        c, lease = self.setup_console()
        self.e["owned"] = lambda *_: (_ for _ in ()).throw(RuntimeError("identity mismatch"))
        with self.assertRaisesRegex(RuntimeError, "identity mismatch"):
            self.e["close_owned"](c, {"pid": 123}, lease, self.out, "synthetic")
        self.assertEqual(self.kills, [])
    def test_metadata_write_failure_after_new_rename_never_rolls_back(self):
        c, lease = self.setup_console()
        write = self.e["write"]
        def failing_write(path, record):
            if Path(path).name == "transaction.json" and record.get("renamed_new"):
                raise OSError("synthetic local metadata write failed")
            return write(path, record)
        self.e["write"] = failing_write
        with self.assertRaisesRegex(OSError, "local metadata"):
            self.invoke(c, lease)
        self.assertEqual(len(self.renames(c)), 2)
        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.new)
        self.assertFalse(self.e["read"](self.out / "transaction.json")["installed_readback_verified"])
    def test_ambiguous_new_rename_does_not_overwrite_existing_target(self):
        c, lease = self.setup_console()
        c.ftp.fail_new = c.ftp.mutate_then_fail_new = True
        with self.assertRaisesRegex(RuntimeError, "Ambiguous rename"):
            self.invoke(c, lease)
        self.assertEqual(len(self.renames(c)), 2)
        self.assertEqual(c.ftp.files["/app/eboot.bin"], self.new)
    def test_changed_backup_never_restored(self):
        c, lease = self.setup_console()
        c.ftp.fail_new = c.ftp.corrupt_backup_on_failure = True
        with self.assertRaisesRegex(RuntimeError, "rollback image changed"):
            self.invoke(c, lease)
        self.assertEqual(len(self.renames(c)), 1)
        self.assertNotIn("/app/eboot.bin", c.ftp.files)
    def test_real_lease_class_remembers_board_failure(self):
        def rejected(*_):
            raise RuntimeError("synthetic board rejected lease")
        self.e["queue"] = SimpleNamespace(Board=lambda: SimpleNamespace(heartbeat=rejected))
        local = self.root / "synthetic-lease"
        local.mkdir()
        (local / ".lease.json").write_text('{"ticket":"synthetic-ticket","token":"synthetic-token"}')
        lease = self.e["Lease"](local)
        with self.assertRaisesRegex(RuntimeError, "board rejected"):
            lease.heartbeat()
        with self.assertRaisesRegex(RuntimeError, "Lost queue lease"):
            lease.check()

if __name__ == "__main__":
    unittest.main(verbosity=2)
