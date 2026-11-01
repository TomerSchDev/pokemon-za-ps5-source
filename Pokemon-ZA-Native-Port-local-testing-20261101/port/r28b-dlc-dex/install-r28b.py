"""Scoped r28b full-image installation, backed by the shared console queue.

No game-save writes, no unknown-process termination, no historical-save restore.
The original launcher is used only to mount the current download0 data at its
menu, so every run can be read twice. All large evidence streams directly to NAS.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import ftplib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_r3 as api
sys.path.insert(0, str(ROOT / "port/perf-r24/observer"))
import client as observer
spec = importlib.util.spec_from_file_location("console_queue", ROOT / "tools/console-install-queue/console_queue.py")
queue = importlib.util.module_from_spec(spec)
spec.loader.exec_module(queue)

APP = "/data/homebrew/PPSA91762"
SANDBOX = "/mnt/sandbox/PPSA91762_000"
DATA = SANDBOX + "/download0/zarecomp/rando"
EBOOT = APP + "/eboot.bin"
BASE = "65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568"
NEW = "8e4280f0da65ec3d00cb77b559833f1e9c6e427009e79ec15b0fab45fbf5dc7e"
PACKAGE = ROOT / "artifacts/randomizer-r28b-dlc-dex-delivery-20261030-1640/randomizer-r28b-dlc-dex-music"
AGENT = "codex-r28b-installer"
LAUNCH = api.PAYLOAD_MANAGER + "/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf"


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write(path, record):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(record, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def proof(path):
    return {"path": str(Path(path).resolve()), "sha256": sha(path)}


def emit(record):
    print(json.dumps(record, ensure_ascii=False), flush=True)


def idle():
    processes = api.eboot_processes()
    if processes:
        raise RuntimeError("A game is running; no unidentified process will be closed: " + json.dumps(processes))
    return processes


class Lease:
    def __init__(self, local):
        self.local = local
        self.data = read(local / ".lease.json")
        self.board = queue.Board()
        self.failed = None
        self.stop = threading.Event()
        self.lock = threading.Lock()

    def heartbeat(self, begin_install=None):
        with self.lock:
            self.check()
            try:
                return self.board.heartbeat(AGENT, self.data["ticket"], self.data["token"], begin_install)
            except Exception as error:
                self.failed = error
                raise

    def check(self):
        if self.failed:
            raise RuntimeError("Lost queue lease; stop console writes") from self.failed

    def loop(self):
        while not self.stop.wait(20):
            try:
                self.heartbeat()
            except Exception:
                return

    def __enter__(self):
        self.heartbeat()
        self.thread = threading.Thread(target=self.loop, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *_):
        self.stop.set()
        self.thread.join(timeout=5)


def bounded_file(c, remote, local, lease, limit=512 << 20):
    """Actual readback file, not a file containing a claimed digest."""
    local = Path(local)
    local.parent.mkdir(parents=True, exist_ok=True)
    temporary = local.with_name(local.name + ".partial")
    if local.exists() or temporary.exists():
        raise FileExistsError(local)
    total = 0
    with temporary.open("xb") as target:
        def chunk(data):
            nonlocal total
            lease.check()
            total += len(data)
            if total > limit:
                raise RuntimeError("Readback exceeds bounded size: " + remote)
            target.write(data)
        c.ftp.retrbinary("RETR " + remote, chunk, 1 << 20)
        target.flush()
        os.fsync(target.fileno())
    os.replace(temporary, local)
    return {"remote_path": remote, **proof(local), "bytes": total}


def listing(c, path):
    c.ftp.cwd(path)
    try:
        records = sorted((name, facts) for name, facts in c.ftp.mlsd() if name not in (".", ".."))
    finally:
        c.ftp.cwd("/")
    for name, facts in records:
        if not name or "/" in name or "\\" in name or name in (".", ".."):
            raise RuntimeError("Invalid FTP directory member")
        if facts.get("type") not in ("dir", "file"):
            raise RuntimeError("Unknown FTP member type: " + repr((name, facts)))
    return records


def inventory(c, path, relative="", depth=0):
    if depth > 12:
        raise RuntimeError("Unexpected save-directory nesting")
    result = []
    for name, facts in listing(c, path):
        child = relative + "/" + name if relative else name
        if facts["type"] == "dir":
            result.extend(inventory(c, path + "/" + name, child, depth + 1))
        else:
            result.append(child)
    if len(result) > 10000:
        raise RuntimeError("Unexpected save-file count")
    return result


def owned(c, identity):
    processes = api.eboot_processes()
    if len(processes) != 1 or api.process_pid(processes[0]) != identity["pid"]:
        raise RuntimeError("Owned game PID changed")
    if observer.status(c.ftp)["session"] != identity["session"]:
        raise RuntimeError("Owned game session changed")
    param = json.loads(observer.get(c.ftp, SANDBOX + "/app0/sce_sys/param.json", 65536))
    if param.get("titleId") != "PPSA91762":
        raise RuntimeError("Mounted title changed")
    current = json.loads(observer.get(c.ftp, DATA + "/active.json", 4096))["id"]
    if identity.get("run") and current != identity["run"]:
        raise RuntimeError("Active run changed; do not close or automate this session")
    return current


def mount_at_menu(c, lease, out, expected, label):
    lease.heartbeat()
    idle()
    if c.sha256(EBOOT) != expected:
        raise RuntimeError("Executable changed before launcher")
    empty_cleanup = []
    for name in c.listing("/mnt/sandbox"):
        if not re.fullmatch(r"PPSA91762_[0-9]{3}", name):
            continue
        path = "/mnt/sandbox/" + name
        if c.listing(path):
            raise RuntimeError("Existing nonempty title sandbox; obtain a fresh handoff")
        # Nonrecursive RMD cannot delete save files or a nonempty mount. The
        # original launcher treats even stale empty directories as active.
        lease.heartbeat()
        idle()
        empty_cleanup.append({"path": path, "empty_verified": True, "response": c.ftp.rmd(path)})
    write(out / (label + "-empty-sandbox-cleanup.json"), {"at": api.utc_now(), "records": empty_cleanup})
    try:
        old_session = observer.status(c.ftp)["session"]
    except ftplib.error_perm:
        old_session = None
    capture = api.KlogCapture(out / (label + ".klog.log"))
    capture.start()
    time.sleep(1)
    idle()
    response = api.http_text(LAUNCH)
    emit({"stage": "launcher-menu", "label": label, "response": response})
    deadline = time.monotonic() + 100
    identity = None
    last_identity = None
    stable_since = None
    while time.monotonic() < deadline:
        lease.check()
        try:
            processes = api.eboot_processes()
            status = observer.status(c.ftp)
            log = (out / (label + ".klog.log")).read_text(encoding="utf-8", errors="replace")
            boot_ready = ("main reached" in log and "[za-observer-r17] opt-in" in log
                          and "native controller menu opened" in log)
            if len(processes) == 1 and status["session"] != old_session and boot_ready:
                candidate = {"pid": api.process_pid(processes[0]), "session": status["session"], "run": None,
                             "at": api.utc_now(), "eboot_sha256": expected, "label": label}
                candidate["run"] = owned(c, candidate)
                key = (candidate["pid"], candidate["session"], candidate["run"])
                if key != last_identity:
                    last_identity, stable_since = key, time.monotonic()
                elif time.monotonic() - stable_since >= 2:
                    identity = candidate
                    break
        except (ftplib.error_perm, ValueError, KeyError):
            pass
        time.sleep(.5)
    if identity is None:
        capture.stop()
        raise RuntimeError("Launcher did not reach an identified menu; no unknown process is closed")
    write(out / (label + "-identity.json"), identity)
    return identity, capture


def close_owned(c, identity, lease, out, label):
    lease.heartbeat()
    owned(c, identity)
    result = api.http_json("/process_kill?pid=" + str(identity["pid"]))
    deadline = time.monotonic() + 20
    while api.eboot_processes():
        if time.monotonic() > deadline:
            raise RuntimeError("Owned process did not stop")
        time.sleep(.5)
    write(out / (label + "-close.json"), {"at": api.utc_now(), "identity": identity, "response": result})


def backup(c, lease, out, resume_identity=None):
    initial = read(out / "initial-probe.json")
    assert initial["base_sha256"] == BASE and initial["second_readback_verified"]
    assert sha(Path(initial["readback_path"])) == BASE
    if resume_identity is None:
        identity, capture = mount_at_menu(c, lease, out, BASE, "original-save-backup")
    else:
        identity = resume_identity
        owned(c, identity)
        assert identity["eboot_sha256"] == BASE and c.sha256(EBOOT) == BASE
        capture = api.KlogCapture(out / "original-save-backup-resumed.klog.log")
        capture.start()
    try:
        top = listing(c, DATA)
        runs = [name for name, facts in top if facts["type"] == "dir" and re.fullmatch(r"r[0-9a-f]+-[0-9a-f]+", name)]
        if not runs or identity["run"] not in runs:
            raise RuntimeError("Active run missing from complete run listing")
        root_files = [name for name, facts in top if facts["type"] == "file"]
        if "active.json" not in root_files:
            raise RuntimeError("No active.json in mounted save")
        save_root = out / "save-backup"
        files = sorted(root_files + [run + "/" + f for run in runs for f in inventory(c, DATA + "/" + run)])
        records = []
        for index, relative in enumerate(files):
            owned(c, identity)
            record = bounded_file(c, DATA + "/" + relative, save_root / relative, lease, 128 << 20)
            record["relative"] = relative
            record["second_readback_sha256"] = c.sha256(record["remote_path"])
            if record["second_readback_sha256"] != record["sha256"]:
                raise RuntimeError("Save changed during double-read: " + relative)
            records.append(record)
            if index % 20 == 0:
                emit({"stage": "save-backup", "done": index + 1, "files": len(files), "runs": len(runs)})
        if [name for name, facts in listing(c, DATA) if facts["type"] == "dir" and re.fullmatch(r"r[0-9a-f]+-[0-9a-f]+", name)] != runs:
            raise RuntimeError("Run list changed while backing up")
        for run in runs:
            if not any(r["relative"].startswith(run + "/save/") for r in records):
                raise RuntimeError("No save files found for run: " + run)
        if files != sorted(root_files + [run + "/" + f for run in runs for f in inventory(c, DATA + "/" + run)]):
            raise RuntimeError("Run inventory changed while backing up")
        for record in records:
            if sha(record["path"]) != record["sha256"] or c.sha256(record["remote_path"]) != record["sha256"]:
                raise RuntimeError("Save changed before closing backup menu")
        result = {"at": api.utc_now(), "active_run": identity["run"], "runs": runs, "all_runs": True,
                  "double_read_verified": True, "fresh": True, "files": records, "save_files_written": False}
        write(out / "save-backup-manifest.json", result)
        close_owned(c, identity, lease, out, "original-save-backup")
        emit({"stage": "all-runs-backed-up-and-closed", "runs": len(runs), "files": len(records), "active_run": identity["run"]})
    finally:
        capture.stop()


def install(c, lease, out):
    idle()
    saved = read(out / "save-backup-manifest.json")
    assert saved["all_runs"] and saved["double_read_verified"]
    for record in saved["files"]:
        assert sha(record["path"]) == record["sha256"]
    assert sha(PACKAGE / "PPSA91762/eboot.bin") == NEW
    assert c.sha256(EBOOT) == BASE
    # Original save mount is now unmounted, as expected after closing the menu.
    observed = out / "game-closed.json"
    write(observed, {"at": api.utc_now(), "processes": idle(), "verified": True})
    ready = {"console": api.HOST, "ticket": lease.data["ticket"], "checked_at": api.utc_now(),
             "external_owner_handoff": {"confirmed": True, "evidence": proof(out / "external-handoff.json")},
             "game_closed": {"verified": True, "evidence": proof(observed)},
             "save_backup": {"fresh": True, "all_runs": True, "readback_verified": True,
                             "evidence": proof(out / "save-backup-manifest.json")},
             "base_readbacks": [{"remote_path": EBOOT, "sha256": BASE, "evidence": proof(out / "original/eboot.bin")}]}
    write(out / "readiness.json", ready)
    lease.heartbeat(out / "readiness.json")
    tag = api.stamp()
    staged = EBOOT + ".r28b-new-" + tag
    previous = EBOOT + ".before-r28b-" + tag
    transaction = {"at": api.utc_now(), "old_sha256": BASE, "new_sha256": NEW, "staged": staged,
                   "remote_backup": previous, "ticket": lease.data["ticket"], "renamed_old": False,
                   "renamed_new": False, "installed_readback_verified": False}
    write(out / "transaction.json", transaction)
    lease.heartbeat()
    idle()
    with (PACKAGE / "PPSA91762/eboot.bin").open("rb") as source:
        c.ftp.storbinary("STOR " + staged, source, 1 << 20, lambda _: lease.check())
    lease.heartbeat()
    c.chmod(staged, "755")
    stage_record = bounded_file(c, staged, out / "readbacks/staged-eboot.bin", lease)
    if stage_record["sha256"] != NEW:
        raise RuntimeError("Staged image readback differs; original image unchanged")
    transaction["staged_readback"] = stage_record
    write(out / "transaction.json", transaction)
    lease.heartbeat()
    idle()
    assert c.sha256(EBOOT) == BASE
    if previous.rsplit("/", 1)[1] in c.listing(APP):
        raise RuntimeError("Unique rollback filename already exists")
    lease.heartbeat()
    c.ftp.rename(EBOOT, previous)
    transaction["renamed_old"] = True
    write(out / "transaction.json", transaction)
    try:
        lease.heartbeat()
        idle()
        c.ftp.rename(staged, EBOOT)
    except Exception:
        # Only our just-renamed image is eligible for restoration. A lost lease
        # forbids further writes; a coordinator must reconcile that case.
        lease.check()
        lease.heartbeat()
        idle()
        names = c.listing(APP)
        if "eboot.bin" in names or c.sha256(previous) != BASE:
            raise RuntimeError("Ambiguous rename result or rollback image changed; preserve evidence and reconcile")
        lease.heartbeat()
        c.ftp.rename(previous, EBOOT)
        transaction["original_restored_after_rename_failure"] = True
        write(out / "transaction.json", transaction)
        raise
    transaction["renamed_new"] = True
    write(out / "transaction.json", transaction)
    installed = bounded_file(c, EBOOT, out / "readbacks/installed-eboot.bin", lease)
    if installed["sha256"] != NEW:
        raise RuntimeError("Installed readback differs; do not launch; retain lease for recovery")
    assert c.sha256(previous) == BASE
    transaction["installed_readback_verified"] = True
    transaction["installed_readback"] = installed
    write(out / "transaction.json", transaction)
    emit({"stage": "installed-readback-verified", "sha256": NEW, "rollback": previous})


def smoke(c, lease, out):
    transaction = read(out / "transaction.json")
    assert transaction["installed_readback_verified"]
    saved = read(out / "save-backup-manifest.json")
    identity, capture = mount_at_menu(c, lease, out, NEW, "r28b-startup")
    try:
        if identity["run"] != saved["active_run"]:
            raise RuntimeError("User changed active run; do not close or continue gameplay")
        time.sleep(5)
        owned(c, identity)
        log = (out / "r28b-startup.klog.log").read_text(encoding="utf-8", errors="replace")
        for marker in ("native controller menu opened", "[za-randomizer] music plan verified"):
            if marker not in log:
                raise RuntimeError("Startup marker missing: " + marker)
        for record in saved["files"]:
            if c.sha256(record["remote_path"]) != record["sha256"]:
                raise RuntimeError("Menu boot changed saved run data: " + record["relative"])
        close_owned(c, identity, lease, out, "r28b-startup")
        write(out / "startup-verification.json", {"at": api.utc_now(), "menu_boot_passed": True,
              "save_backup_still_verified": True, "game_closed": True, "active_run": identity["run"],
              "continued_into_gameplay": False, "dlc_dex_in_game_tested": False, "save_persistence_tested": False,
              "texguard_marker_observed": "[za-texguard] r28a texfix active" in log,
              "texguard_note": "The active marker is emitted by the first NVN texture allocation, which a native-menu-only test need not execute.",
              "music_plan_verified": True})
    finally:
        capture.stop()


def complete(c, lease, out):
    idle()
    assert c.sha256(EBOOT) == NEW
    transaction = read(out / "transaction.json")
    assert transaction["installed_readback_verified"]
    saved = read(out / "save-backup-manifest.json")
    for record in saved["files"]:
        assert sha(record["path"]) == record["sha256"]
    receipt = {"console": api.HOST, "ticket": lease.data["ticket"], "save_backup_still_verified": True,
               "console_handoff_complete": True, "readbacks": [{"remote_path": EBOOT,
               "staged": proof(out / "readbacks/staged-eboot.bin"), "installed": proof(out / "readbacks/installed-eboot.bin")}]}
    write(out / "receipt.json", receipt)
    lease.heartbeat()
    # No competing heartbeat may race the queue's exclusive metadata mutex
    # while complete verifies large evidence files and commits its receipt.
    lease.stop.set()
    lease.thread.join(timeout=5)
    result = lease.board.complete(AGENT, lease.data["ticket"], lease.data["token"], out / "receipt.json")
    write(out / "queue-completion.json", result)
    write(out / "installation.json", {"at": api.utc_now(), "installed": True, "title_id": "PPSA91762",
        "installed_sha256": NEW, "old_sha256": BASE, "queue_ticket": lease.data["ticket"],
        "only_replaced": [EBOOT], "game_closed": True, "all_runs_backed_up": True,
        "run_count": len(saved["runs"]), "file_count": len(saved["files"]), "saves_restored": False,
        "startup_verification": read(out / "startup-verification.json") if (out / "startup-verification.json").exists() else None,
        "rollback_remote": transaction["remote_backup"], "evidence": str(out)})
    emit({"stage": "installation-completed", "ticket": lease.data["ticket"], "sha256": NEW, "game_closed": True})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("backup", "install", "smoke", "complete"))
    parser.add_argument("--local", required=True, type=Path)
    args = parser.parse_args()
    local = args.local.resolve()
    out = Path(read(local / "nas-location.json")["evidence"])
    with Lease(local) as lease:
        c = api.Console()
        try:
            globals()[args.operation](c, lease, out)
        except Exception as error:
            write(out / ("error-" + args.operation + "-" + api.stamp() + ".json"),
                  {"at": api.utc_now(), "type": type(error).__name__, "error": str(error), "operation": args.operation})
            raise
        finally:
            c.close()
