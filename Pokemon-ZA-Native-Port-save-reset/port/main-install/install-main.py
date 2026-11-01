"""Install a main release (1.0.0 = r29-ui) on PPSA91762 for its console gate, through the shared queue.

Reuses port/r28b-dlc-dex/install-r28b.py (lease, all-runs save backup, staged/readback/rename eboot swap, owned close).
Adds: isolate (side-branch mod links NAME -> _NAME by payload, reversible with --restore), assets (randomizer-assets
staged + read back, the old folder kept as randomizer-assets.before-<release>-<tag>), shot (launcher + in-game).
Order: init -> backup -> isolate -> assets -> install -> shot -> complete. No save is ever restored or written.
Rollback: eboot.bin.before-r28b-<tag>, randomizer-assets.before-<release>-<tag>, isolate --restore.
"""
from __future__ import annotations
import argparse,ftplib,hashlib,importlib.util,json,shutil,subprocess,sys,time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("install_r28b", ROOT / "port/r28b-dlc-dex/install-r28b.py")
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
api, observer, queue = m.api, m.observer, m.queue
read, write, proof, emit, sha = m.read, m.write, m.proof, m.emit, m.sha

RELEASE = "main-1.0.0"
SOURCE = ROOT / "artifacts/randomizer-r29-ui-codex-20261031-01"          # r29-ui as delivered (= za build main)
PACKAGE = ROOT / "artifacts/main-1.0.0-install-r1"
BASE = "2726483b67528b693969767bd48c582eecd91c6ccce96d8da40ab9a02d7f0520"   # installed: heb-trans state
NEW = "51b7e65b0bd930bfe7ede0127d56736ee43d8487310ebff6337c92e11b3e1ab1"    # r29-ui = main-1.0.0
SIDE_MODS = ["hebrew", "00-console-fifty-20261031-r1", "00-0-console-fifty-20261031-r1", "000-rowlet-pilot-r1"]
AGENT = "claude-main-release"
ASSETS = m.APP + "/randomizer-assets"
READY = ("[za-randomizer] music plan", "run storage ready")                 # r29-ui launcher klog lines
m.BASE, m.NEW, m.PACKAGE, m.AGENT = BASE, NEW, PACKAGE, AGENT


def prepare_package():
    sums = read(SOURCE / "SHA256SUMS.json")
    for rel, digest in sums.items():
        assert sha(SOURCE / rel) == digest, "package file changed: " + rel
    assert sums["eboot.bin"] == NEW
    if not PACKAGE.exists():
        (PACKAGE / "PPSA91762").mkdir(parents=True)
        shutil.copyfile(SOURCE / "eboot.bin", PACKAGE / "PPSA91762/eboot.bin")
        shutil.copytree(SOURCE / "randomizer-assets", PACKAGE / "randomizer-assets")
    assert sha(PACKAGE / "PPSA91762/eboot.bin") == NEW
    rows = [{"path": p.relative_to(PACKAGE / "randomizer-assets").as_posix(), "sha256": sha(p)}
            for p in sorted((PACKAGE / "randomizer-assets").rglob("*")) if p.is_file()]
    for r in rows:
        assert sums["randomizer-assets/" + r["path"]] == r["sha256"], r["path"]
    return rows


def init(local, handoff):
    prepare_package()
    local.mkdir(parents=True, exist_ok=True)
    out = Path(r"\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\main-releases") / (RELEASE + "-gate-" + api.stamp())
    out.mkdir(parents=True)
    write(local / "nas-location.json", {"evidence": str(out)})
    write(out / "external-handoff.json", {"at": api.utc_now(), "from": "Tomer", "statement": handoff,
          "remote_close_authorized": True, "game_saved_and_closed": False})
    job = {"console": api.HOST, "title_id": "PPSA91762", "name": RELEASE + " console gate (r29-ui); side-branch mods disabled reversibly",
           "artifacts": [{"path": str(PACKAGE / "PPSA91762/eboot.bin").replace("\\", "/"), "sha256": NEW, "remote_path": m.EBOOT}],
           "expected_base": [{"remote_path": m.EBOOT, "sha256": BASE}],
           "notes": "eboot + full randomizer-assets (old kept); mods hebrew/console-fifty/rowlet renamed with _ (restorable)."}
    write(local / "job.json", job)
    board = queue.Board()
    board.enqueue(AGENT, RELEASE + "-" + NEW[:8], local / "job.json")
    lease = board.claim(AGENT)
    write(local / ".lease.json", {"ticket": lease["ticket"], "token": lease["token"]})
    with m.Lease(local) as held:
        c = api.Console()
        try:
            first = m.bounded_file(c, m.EBOOT, out / "original/eboot.bin", held)
            if first["sha256"] != BASE or c.sha256(m.EBOOT) != BASE:
                raise RuntimeError("Installed eboot is not the expected base")
            write(out / "initial-probe.json", {"at": api.utc_now(), "base_sha256": BASE, "readback_path": first["path"],
                  "second_readback_verified": True})
        finally:
            c.close()
    emit({"stage": "init", "evidence": str(out), "ticket": lease["ticket"]})


def payload(out, restore):
    names = "{" + ",".join('"' + n + '"' for n in SIDE_MODS) + "}"
    elf = out / ("isolate-%s.elf" % ("restore" if restore else "disable"))
    if not elf.exists():
        sdk = "/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk"
        src = "/mnt/c" + str(HERE / "isolate_mods.c")[2:].replace("\\", "/")
        tmp = "/tmp/" + elf.name
        subprocess.run(["wsl.exe", "-d", "Ubuntu", "-e", sdk + "/bin/prospero-clang", "-O2", "-Wall",
                        "-DMOD_NAMES=" + names, "-DRESTORE=%d" % restore, src, "-o", tmp], check=True)
        shutil.copyfile(r"\\wsl.localhost\Ubuntu" + tmp.replace("/", "\\"), elf)
    return elf


def isolate(c, lease, out, restore=False):
    """Mount at the menu with the CURRENT eboot, rename the side-branch links, close."""
    current = c.sha256(m.EBOOT)
    expected = BASE if current == BASE else NEW
    elf = payload(out, restore)
    identity, capture = (m.mount_at_menu(c, lease, out, expected, "isolate") if expected == BASE
                         else mount(c, lease, out, expected, "isolate"))
    try:
        folder = "/data/pldmgr/payloads/za_main_release"
        try: c.ftp.mkd(folder)
        except ftplib.error_perm: pass
        remote = folder + "/" + elf.name
        raw = elf.read_bytes(); c.store(remote, raw); c.chmod(remote, "755"); assert c.read(remote, 8 << 20) == raw
        m.owned(c, identity); lease.heartbeat()
        emit({"stage": "isolate", "payload": api.http_text(api.PAYLOAD_MANAGER + "/loadpayload:" + remote)})
        deadline = time.monotonic() + 60; log = b""
        while time.monotonic() < deadline:
            log = c.read("/data/main-isolate-mods.log", 1 << 20) or b""
            if b"COMPLETE" in log or b"FAILED" in log: break
            time.sleep(1)
        (out / ("isolate-%s.log" % ("restore" if restore else "disable"))).write_bytes(log)
        m.close_owned(c, identity, lease, out, "isolate")
        if b"COMPLETE" not in log:
            raise RuntimeError("Mod isolation failed: " + log.decode("utf-8", "replace")[-400:])
        emit({"stage": "isolated", "log": log.decode("utf-8", "replace").strip().splitlines()})
    finally:
        capture.stop()


def assets(c, lease, out):
    m.idle()
    rows = prepare_package()
    tag = api.stamp()
    staged = ASSETS + "." + RELEASE + ".part"
    old = ASSETS + ".before-" + RELEASE + "-" + tag
    names = c.listing(m.APP)
    if staged.rsplit("/", 1)[1] in names:
        raise RuntimeError("A partial assets upload exists; inspect it before retrying")
    made = set()
    for i, row in enumerate(rows):
        lease.check()
        remote = staged + "/" + row["path"]
        parts = remote.rsplit("/", 1)[0].split("/")
        for j in range(len(parts)):
            d = "/".join(parts[:j + 1])
            if d.startswith(staged) and d not in made:
                c.ftp.mkd(d); c.chmod(d, "777"); made.add(d)
        with (PACKAGE / "randomizer-assets" / row["path"]).open("rb") as source:
            c.ftp.storbinary("STOR " + remote, source, 1 << 20)
        c.chmod(remote, "644")
        if c.sha256(remote) != row["sha256"]:
            raise RuntimeError("Assets readback differs: " + row["path"])
        if i % 40 == 0: lease.heartbeat(); emit({"stage": "assets", "done": i + 1, "files": len(rows)})
    m.idle(); lease.heartbeat()
    c.ftp.rename(ASSETS, old)
    try:
        c.ftp.rename(staged, ASSETS)
    except Exception:
        c.ftp.rename(old, ASSETS); raise
    for row in rows:
        assert c.sha256(ASSETS + "/" + row["path"]) == row["sha256"], row["path"]
    write(out / "assets.json", {"at": api.utc_now(), "installed": ASSETS, "previous_kept_as": old, "files": len(rows)})
    emit({"stage": "assets-installed", "files": len(rows), "previous": old})


RUN_SOURCE = r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\v3-run-gen-20261031\flow-root"   # ui-v2 launcher-flow run


def pushrun(c, lease, out):
    """Publish a v3 run generated off-console by the r29-ui launcher code (same assets) and make it active."""
    src = Path(RUN_SOURCE)
    run_id = read(src / "active.json")["id"]
    local = PACKAGE / "gate-run" / run_id
    if not local.exists():
        shutil.copytree(src / run_id, local)
    rows = [{"path": p.relative_to(local).as_posix(), "sha256": sha(p)} for p in sorted(local.rglob("*")) if p.is_file()]
    folder = m.APP + "/main-gate-run-" + run_id
    if folder.rsplit("/", 1)[1] not in c.listing(m.APP):
        made = set()
        for row in rows:
            remote = folder + "/" + row["path"]; parts = remote.rsplit("/", 1)[0].split("/")
            for j in range(len(parts)):
                d = "/".join(parts[:j + 1])
                if d.startswith(folder) and d not in made:
                    try: c.ftp.mkd(d)
                    except ftplib.error_perm: pass
                    c.chmod(d, "777"); made.add(d)
            with (local / row["path"]).open("rb") as source:
                c.ftp.storbinary("STOR " + remote, source, 1 << 20)
            c.chmod(remote, "644")
            if c.sha256(remote) != row["sha256"]: raise RuntimeError("Run file readback differs: " + row["path"])
    elf = out / ("push-run-" + run_id + ".elf")
    if not elf.exists():
        sdk = "/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk"
        files = "{" + ",".join('"' + r["path"] + '"' for r in rows) + "}"
        tmp = "/tmp/" + elf.name
        subprocess.run(["wsl.exe", "-d", "Ubuntu", "-e", sdk + "/bin/prospero-clang", "-O2", "-Wall",
                        f'-DRUN_ID="{run_id}"', f'-DSRC_DIR="main-gate-run-{run_id}"', "-DRUN_FILES=" + files,
                        "/mnt/c" + str(HERE / "push_run.c")[2:].replace("\\", "/"), "-o", tmp], check=True)
        shutil.copyfile(r"\\wsl.localhost\Ubuntu" + tmp.replace("/", "\\"), elf)
    identity, capture = mount(c, lease, out, NEW, "pushrun")
    try:
        remote = "/data/pldmgr/payloads/za_main_release/" + elf.name
        raw = elf.read_bytes(); c.store(remote, raw); c.chmod(remote, "755"); assert c.read(remote, 8 << 20) == raw
        m.owned(c, identity); lease.heartbeat()
        emit({"stage": "pushrun", "payload": api.http_text(api.PAYLOAD_MANAGER + "/loadpayload:" + remote)})
        deadline = time.monotonic() + 60; log = b""
        while time.monotonic() < deadline:
            log = c.read("/data/main-push-run.log", 1 << 20) or b""
            if b"COMPLETE" in log or b"FAILED" in log or b"REFUSED" in log: break
            time.sleep(1)
        (out / "push-run.log").write_bytes(log)
        # the active run changed on purpose, so close_owned's run check would refuse; close the same PID directly
        processes = api.eboot_processes()
        assert len(processes) == 1 and api.process_pid(processes[0]) == identity["pid"], "not the launched process"
        api.http_json("/process_kill?pid=" + str(identity["pid"]))
        deadline = time.monotonic() + 20
        while api.eboot_processes():
            if time.monotonic() > deadline: raise RuntimeError("Launched process did not stop")
            time.sleep(.5)
        if b"COMPLETE" not in log: raise RuntimeError("Run push failed: " + log.decode("utf-8", "replace")[-400:])
        write(out / "push-run.json", {"at": api.utc_now(), "run": run_id, "files": rows, "previous_active": identity["run"]})
        emit({"stage": "run-active", "run": run_id, "previous": identity["run"]})
    finally:
        capture.stop()


def mount(c, lease, out, expected, label):
    """install-r28b.mount_at_menu with the r29-ui launcher's ready lines instead of the old native menu marker."""
    source = Path(m.__file__).read_text(encoding="utf-8")
    assert '"native controller menu opened" in log' in source
    patched = source.replace('and "native controller menu opened" in log)', 'and all(r in log for r in READY))')
    namespace = dict(vars(m)); namespace["READY"] = READY
    exec(compile(patched, m.__file__, "exec"), namespace)
    return namespace["mount_at_menu"](c, lease, out, expected, label)


def shot(c, lease, out):
    saved = read(out / "save-backup-manifest.json")
    identity, capture = mount(c, lease, out, NEW, "main-shot")
    shots = out / "screenshots"; seq = [0]
    def command(op, value=None, frames=None, wait=2.0):
        seq[0] += 1; m.owned(c, identity); lease.heartbeat()
        observer.issue(c.ftp, identity["session"], seq[0], op, value, frames)
        deadline = time.monotonic() + 90
        while True:
            time.sleep(wait)
            try:
                r = observer.collect(c.ftp, identity["session"], seq[0], shots)
                if r.get("result") != "settling" and r.get("ack", r).get("result") != "settling": return r
            except ftplib.error_perm: pass
            if time.monotonic() > deadline: raise RuntimeError(f"No observer receipt for {op} {seq[0]}")
    try:
        records = [command("snapshot")]                                   # the new launcher
        command("continue", identity["run"], wait=3); time.sleep(50)
        command("input", "A", 6); time.sleep(45); records.append(command("snapshot"))
        command("input", "X", 6); time.sleep(5); records.append(command("snapshot"))
        command("input", "B", 6); time.sleep(3)
        log = (out / "main-shot.klog.log").read_text(encoding="utf-8", errors="replace")
        crashed = "za-native-fault" in log or "signal 11" in log
        changed = [r["relative"] for r in saved["files"] if c.sha256(r["remote_path"]) != r["sha256"]]
        m.close_owned(c, identity, lease, out, "main-shot")
        result = {"at": api.utc_now(), "crash": crashed, "save_files_changed_by_game": changed, "saves_restored": False,
                  "screenshots": [f["name"] for r in records for f in r.get("files", [])], "game_closed": True}
        write(out / "shot-verification.json", result)
        if not crashed: write(out / "startup-verification.json", result)
        emit({"stage": "screenshots", **result})
    finally:
        capture.stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("operation", choices=("init", "backup", "isolate", "assets", "install", "pushrun", "shot", "complete"))
    p.add_argument("--local", required=True, type=Path)
    p.add_argument("--handoff"); p.add_argument("--restore", action="store_true", help="isolate: rename _NAME back to NAME")
    a = p.parse_args(); local = a.local.resolve()
    if a.operation == "init":
        if not a.handoff: p.error("init needs --handoff")
        init(local, a.handoff); sys.exit(0)
    out = Path(read(local / "nas-location.json")["evidence"])
    ops = {"backup": m.backup, "isolate": lambda c, l, o: isolate(c, l, o, a.restore), "assets": assets,
           "install": m.install, "pushrun": pushrun, "shot": shot, "complete": m.complete}
    with m.Lease(local) as lease:
        c = api.Console()
        try:
            ops[a.operation](c, lease, out)
        except Exception as error:
            write(out / ("error-" + a.operation + "-" + api.stamp() + ".json"),
                  {"at": api.utc_now(), "type": type(error).__name__, "error": str(error), "operation": a.operation})
            raise
        finally:
            c.close()
