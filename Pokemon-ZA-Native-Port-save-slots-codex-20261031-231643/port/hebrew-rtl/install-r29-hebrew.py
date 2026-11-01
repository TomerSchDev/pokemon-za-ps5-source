"""Install r29-hebrew (r28b + MUSIC + Hebrew RTL) on PPSA91762, with the Hebrew mods package, through the shared queue.

Reuses port/r28b-dlc-dex/install-r28b.py unchanged (lease, all-runs save backup, staged/readback/rename eboot swap,
launch-to-menu identity, owned close) with its constants re-pinned. Adds only:
  upload    mods tree -> /data/homebrew/PPSA91762/<PACKAGE_DIR> (staged .part folder, every file read back)
  activate  payload links mods/hebrew -> ../../../app0/<PACKAGE_DIR>/hebrew while the title is mounted at its menu
  shot      launch, continue the active run through the observer, verified screenshots, close the owned process
Order: init -> close-running -> backup -> upload -> install -> activate -> shot -> complete. Requires Tomer's handoff (game saved and
closed, HEBREW TRIAL OFF), recorded by init. Rollback: eboot.bin.before-r28b-* on the console + unlink mods/hebrew.
"""
from __future__ import annotations
import argparse,ftplib,hashlib,importlib.util,json,os,subprocess,sys,time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("install_r28b", ROOT / "port/r28b-dlc-dex/install-r28b.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
api, observer, queue = m.api, m.observer, m.queue

PACKAGE = ROOT / "artifacts/randomizer-r29-hebrew-rtl-20261031-r4"
WSL_IMAGE = r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\hebrew-rtl-ps5-20261031-r3\image\eboot.bin"
MODS_SOURCE = ROOT.parent / "hebrew-lab/build/hebrew-assistant-20261031-r6/mods"
BASE = "2883b72773f612f81e70e583da8d8f4e55e773303195a292dc4d9a1a4cf8a03d"   # installed: r28b+MUSIC+RTL without the FD fix (crashes with many mod files)
NEW = "2726483b67528b693969767bd48c582eecd91c6ccce96d8da40ab9a02d7f0520"    # r28b+MUSIC + FD fix (4b4d1b50) + Hebrew RTL; build-r29-hebrew.sh BASE_SPEC=r3/base-fd.json
AGENT = "claude-hebrew-rtl"
PAYLOAD_DIR = "/data/pldmgr/payloads/za_hebrew_rtl_20261031"
m.BASE, m.NEW, m.PACKAGE, m.AGENT = BASE, NEW, PACKAGE, AGENT
read, write, proof, emit, sha = m.read, m.write, m.proof, m.emit, m.sha


def manifest():
    files = sorted(p for p in (PACKAGE / "mods").rglob("*") if p.is_file())
    rows = [{"path": p.relative_to(PACKAGE / "mods").as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)} for p in files]
    digest = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    return rows, digest


def package_dir(digest):
    return "hebrew-rtl-r6-" + digest[:12]


def prepare_package():
    """Local package: the verified eboot and the PC-checked mods tree (new folder, never overwritten)."""
    if PACKAGE.exists():
        assert sha(PACKAGE / "PPSA91762/eboot.bin") == NEW
        return
    import shutil
    (PACKAGE / "PPSA91762").mkdir(parents=True)
    shutil.copyfile(WSL_IMAGE, PACKAGE / "PPSA91762/eboot.bin")
    assert sha(PACKAGE / "PPSA91762/eboot.bin") == NEW
    shutil.copytree(MODS_SOURCE, PACKAGE / "mods")
    rows, digest = manifest()
    write(PACKAGE / "PACKAGE.json", {"eboot_sha256": NEW, "base_sha256": BASE, "mods_files": len(rows),
          "mods_manifest_sha256": digest, "app0_folder": package_dir(digest), "mods": rows,
          "source_build": "port/hebrew-rtl/build-r29-hebrew.sh BASE_SPEC=hebrew-rtl-ps5-20261031-r3/base-fd.json (r28b+MUSIC+FD fix)", "pc_checked_run": "hebrew-lab/runs/hebrew-assistant-r6-20261031-r1",
          "hardware_tested": False})


def init(local, handoff):
    """Record the handoff, claim the queue, read the installed eboot twice. Writes nothing to the console."""
    prepare_package()
    local.mkdir(parents=True, exist_ok=True)
    out = Path(r"\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\hebrew-rtl") / ("install-" + api.stamp())
    out.mkdir(parents=True)
    write(local / "nas-location.json", {"evidence": str(out)})
    write(out / "external-handoff.json", {"at": api.utc_now(), "from": "Tomer", "statement": handoff,
          "game_saved_and_closed": False, "remote_close_authorized": True, "hebrew_trial_off": "unknown; activation refuses if ON"})
    board = queue.Board()
    job = {"console": api.HOST, "title_id": "PPSA91762", "name": "r29-hebrew: r28b+MUSIC with Hebrew RTL, plus mods/hebrew (replaces the models QA test eboot)",
           "artifacts": [{"path": str(PACKAGE / "PPSA91762/eboot.bin").replace("\\", "/"), "sha256": NEW,
                          "remote_path": m.EBOOT}],
           "expected_base": [{"remote_path": m.EBOOT, "sha256": BASE}],
           "requirements": ["external_console_handoff", "game_closed", "fresh_all_runs_save_backup_with_readback",
                            "current_base_readback_matches", "staged_readback_before_rename", "installed_readback_after_rename"],
           "notes": "Replace only eboot; add app0 folder + mods/hebrew link. Base r28b+MUSIC; the installed models-QA eboot is still in progress elsewhere (Tomer) and stays as a rollback file."}
    write(local / "job.json", job)
    ticket = board.enqueue(AGENT, "r29-hebrew-" + NEW[:8], local / "job.json")
    lease = board.claim(AGENT)
    write(local / ".lease.json", {"ticket": lease["ticket"], "token": lease["token"]})
    with m.Lease(local) as held:
        c = api.Console()
        try:
            first = m.bounded_file(c, m.EBOOT, out / "original/eboot.bin", held)
            second = c.sha256(m.EBOOT)
            if first["sha256"] != BASE or second != BASE:
                raise RuntimeError("Installed eboot is not the expected r28b+MUSIC base; stop and reconcile")
            write(out / "initial-probe.json", {"at": api.utc_now(), "base_sha256": BASE, "readback_path": first["path"],
                  "second_readback_verified": True, "ticket": ticket})
        finally:
            c.close()
    emit({"stage": "init", "evidence": str(out), "ticket": lease["ticket"]})


def rejob(local):
    """Replace this agent's queue ticket with one for the current NEW (the earlier ticket named another image)."""
    prepare_package()
    lease = read(local / ".lease.json"); board = queue.Board()
    why = "superseded: Tomer chose the r28b+MUSIC base, not the models QA test"
    board.release(AGENT, lease["ticket"], lease["token"], reason=why)       # back to the queue head ...
    board.release(AGENT, lease["ticket"], reason=why, cancel_queued=True)   # ... then cancelled, so claim takes the new job
    job = read(local / "job.json")
    job["artifacts"][0].update(path=str(PACKAGE / "PPSA91762/eboot.bin").replace("\\", "/"), sha256=NEW)
    job["name"] = "r29-hebrew: r28b+MUSIC with Hebrew RTL, plus mods/hebrew (replaces the models QA test eboot)"
    write(local / "job.json", job)
    board.enqueue(AGENT, "r29-hebrew-" + NEW[:8], local / "job.json")
    claimed = board.claim(AGENT)
    write(local / ".lease.json", {"ticket": claimed["ticket"], "token": claimed["token"]})
    emit({"stage": "rejob", "released": lease["ticket"], "ticket": claimed["ticket"], "new_sha256": NEW})


def close_running(c, lease, out):
    """Close the title Tomer left running (his recorded remote handoff). Only a single PPSA91762 eboot process is eligible."""
    handoff = read(out / "external-handoff.json")
    assert handoff.get("remote_close_authorized") or handoff.get("game_saved_and_closed")
    processes = api.eboot_processes()
    if not processes:
        emit({"stage": "close-running", "result": "nothing running"}); return
    if len(processes) != 1:
        raise RuntimeError("More than one game process; not closing anything: " + json.dumps(processes))
    mounted = [n for n in c.listing("/mnt/sandbox") if n.startswith("PPSA91762_") and c.listing("/mnt/sandbox/" + n)]
    titles = [json.loads(c.read("/mnt/sandbox/" + n + "/app0/sce_sys/param.json", 65536) or b"{}").get("titleId") for n in mounted]
    if titles != ["PPSA91762"]:
        raise RuntimeError("The running process is not identified as PPSA91762: " + json.dumps(titles))
    pid = api.process_pid(processes[0]); lease.heartbeat()
    result = api.http_json("/process_kill?pid=" + str(pid))
    deadline = time.monotonic() + 30
    while api.eboot_processes():
        if time.monotonic() > deadline: raise RuntimeError("PPSA91762 did not stop")
        time.sleep(.5)
    write(out / "closed-running.json", {"at": api.utc_now(), "pid": pid, "sandbox": mounted, "response": result,
          "authorized_by": "Tomer (remote handoff)"})
    emit({"stage": "closed-running", "pid": pid})


def upload(c, lease, out):
    m.idle()
    rows, digest = manifest()
    folder = m.APP + "/" + package_dir(digest)
    staged = folder + ".part"
    names = c.listing(m.APP)
    if folder.rsplit("/", 1)[1] in names:
        raise RuntimeError("Package folder already on the console; inspect it instead of overwriting")
    if staged.rsplit("/", 1)[1] in names:
        raise RuntimeError("A partial upload exists; inspect and remove it explicitly before retrying")
    made = set()
    def mkdirs(remote):
        parts = remote.split("/")
        for i in range(len(parts)):
            d = "/".join(parts[:i + 1])
            if d and d.startswith(staged) and d not in made:
                c.ftp.mkd(d); c.chmod(d, "777"); made.add(d)
    records = []
    for i, row in enumerate(rows):
        lease.check()
        remote = staged + "/" + row["path"]
        mkdirs(remote.rsplit("/", 1)[0])
        with (PACKAGE / "mods" / row["path"]).open("rb") as source:
            c.ftp.storbinary("STOR " + remote, source, 1 << 20)
        c.chmod(remote, "644")
        back = c.sha256(remote)
        if back != row["sha256"]:
            raise RuntimeError("Readback differs: " + row["path"])
        records.append({**row, "readback_sha256": back})
        if i % 50 == 0:
            lease.heartbeat(); emit({"stage": "upload", "done": i + 1, "files": len(rows)})
    marker = json.dumps({"mods_manifest_sha256": digest, "files": len(rows), "eboot_sha256": NEW}, indent=1).encode()
    c.store(staged + "/installation.json", marker)
    assert c.read(staged + "/installation.json", 4096) == marker
    m.idle(); lease.heartbeat()
    c.ftp.rename(staged, folder)
    for row in rows[:: max(1, len(rows) // 40)]:          # spot readback after publication
        assert c.sha256(folder + "/" + row["path"]) == row["sha256"]
    write(out / "upload.json", {"at": api.utc_now(), "folder": folder, "manifest_sha256": digest, "files": records})
    emit({"stage": "uploaded", "folder": folder, "files": len(rows)})


def activate(c, lease, out):
    transaction = read(out / "transaction.json")
    assert transaction["installed_readback_verified"]
    upload_record = read(out / "upload.json")
    digest = upload_record["manifest_sha256"]
    elf = out / "activate-hebrew.elf"
    if not elf.exists():
        sdk = "/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk"
        src = "/mnt/c" + str(HERE / "activate_hebrew.c")[2:].replace("\\", "/")
        tmp = "/home/tomer/ps5-za-native/hebrew-rtl-ps5-20261031-r2/activate-hebrew-" + digest[:12] + ".elf"
        subprocess.run(["wsl.exe", "-d", "Ubuntu", "-e", sdk + "/bin/prospero-clang", "-O2", "-Wall",
                        f'-DPACKAGE_DIR="{package_dir(digest)}"', f'-DPACKAGE_SHA="{digest}"', src, "-o", tmp], check=True)
        import shutil
        shutil.copyfile(r"\\wsl.localhost\Ubuntu" + tmp.replace("/", "\\"), elf)
    identity, capture = m.mount_at_menu(c, lease, out, NEW, "hebrew-activate")
    try:
        try: c.ftp.mkd(PAYLOAD_DIR)
        except ftplib.error_perm: pass
        remote = PAYLOAD_DIR + "/activate-hebrew.elf"
        raw = elf.read_bytes(); c.store(remote, raw); c.chmod(remote, "755"); assert c.read(remote, 8 << 20) == raw
        m.owned(c, identity); lease.heartbeat()
        emit({"stage": "activate", "payload": api.http_text(api.PAYLOAD_MANAGER + "/loadpayload:" + remote)})
        deadline = time.monotonic() + 60; log = b""
        while time.monotonic() < deadline:
            log = c.read("/data/hebrew-rtl-activate.log", 1 << 20) or b""
            if any(w in log for w in (b"COMPLETE", b"FAILED", b"REFUSED")): break
            time.sleep(1)
        (out / "activate.log").write_bytes(log)
        if b"COMPLETE" not in log:
            raise RuntimeError("Activation did not complete: " + log.decode("utf-8", "replace")[-400:])
        m.close_owned(c, identity, lease, out, "hebrew-activate")
        emit({"stage": "activated", "log": log.decode("utf-8", "replace").strip().splitlines()[-1]})
    finally:
        capture.stop()


def shot(c, lease, out):
    """Continue the active run (no saving), wait for the game, take verified observer screenshots, close."""
    saved = read(out / "save-backup-manifest.json")
    identity, capture = m.mount_at_menu(c, lease, out, NEW, "hebrew-shot")
    shots = out / "screenshots"; seq = 0
    def command(op, value=None, frames=None, wait=2.0):
        nonlocal seq
        seq += 1; m.owned(c, identity); lease.heartbeat()
        observer.issue(c.ftp, identity["session"], seq, op, value, frames)
        deadline = time.monotonic() + 60
        while True:
            time.sleep(wait)
            try:
                record = observer.collect(c.ftp, identity["session"], seq, shots)
                if record.get("result") != "settling" and record.get("ack", record).get("result") != "settling":
                    return record
            except ftplib.error_perm:
                pass
            if time.monotonic() > deadline:
                raise RuntimeError(f"No observer receipt for {op} seq {seq}")
    try:
        if identity["run"] != saved["active_run"]:
            raise RuntimeError("Active run changed since the backup; not continuing")
        command("continue", identity["run"], wait=3)
        # continue restarts the title into the run: a new PID and a new observer session. Re-identify before any command.
        old = (identity["pid"], identity["session"]); deadline = time.monotonic() + 120
        while True:
            lease.check()
            try:
                processes = api.eboot_processes(); status = observer.status(c.ftp)
                if len(processes) == 1 and (api.process_pid(processes[0]), status["session"]) != old and status["session"] != old[1]:
                    identity = {**identity, "pid": api.process_pid(processes[0]), "session": status["session"], "at": api.utc_now()}
                    m.owned(c, identity); break
            except (ftplib.error_perm, ValueError, KeyError, RuntimeError):
                pass
            if time.monotonic() > deadline: raise RuntimeError("The title did not come back after continue")
            time.sleep(1)
        seq = 0; write(out / "hebrew-shot-identity-after-continue.json", identity)
        log_path = out / "hebrew-shot.klog.log"
        deadline = time.monotonic() + 180
        while "[fs] mod: hebrew" not in log_path.read_text(encoding="utf-8", errors="replace"):
            if time.monotonic() > deadline: raise RuntimeError("mods/hebrew was not loaded by the game")
            time.sleep(2)
        time.sleep(45)                                       # title / load
        records = [command("snapshot")]
        command("input", "X", 4); time.sleep(3); records.append(command("snapshot"))
        command("input", "B", 4); time.sleep(2)
        # We never save; the game may autosave on load. Record it (same progress, nothing restored), then close.
        changed = [r["relative"] for r in saved["files"] if c.sha256(r["remote_path"]) != r["sha256"]]
        m.close_owned(c, identity, lease, out, "hebrew-shot")
        write(out / "shot-verification.json", {"at": api.utc_now(), "hebrew_mod_loaded": True,
              "save_files_changed_by_game": changed, "saves_restored": False,
              "screenshots": [f["name"] for r in records for f in r.get("files", [])], "game_closed": True})
        emit({"stage": "screenshots", "folder": str(shots)})
    finally:
        capture.stop()


def complete(c, lease, out):
    if not (out / "startup-verification.json").exists() and (out / "shot-verification.json").exists():
        write(out / "startup-verification.json", read(out / "shot-verification.json"))
    m.complete(c, lease, out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("init", "rejob", "close-running", "backup", "upload", "install", "activate", "shot", "complete"))
    parser.add_argument("--local", required=True, type=Path)
    parser.add_argument("--handoff", help="init: Tomer's handoff words (game saved and closed, HEBREW TRIAL OFF)")
    args = parser.parse_args()
    local = args.local.resolve()
    if args.operation == "rejob":
        rejob(local); sys.exit(0)
    if args.operation == "init":
        if not args.handoff: parser.error("init needs --handoff")
        init(local, args.handoff); sys.exit(0)
    out = Path(read(local / "nas-location.json")["evidence"])
    ops = {"close-running": close_running, "backup": m.backup, "install": m.install, "upload": upload, "activate": activate, "shot": shot, "complete": complete}
    with m.Lease(local) as lease:
        c = api.Console()
        try:
            ops[args.operation](c, lease, out)
        except Exception as error:
            write(out / ("error-" + args.operation + "-" + api.stamp() + ".json"),
                  {"at": api.utc_now(), "type": type(error).__name__, "error": str(error), "operation": args.operation})
            raise
        finally:
            c.close()
