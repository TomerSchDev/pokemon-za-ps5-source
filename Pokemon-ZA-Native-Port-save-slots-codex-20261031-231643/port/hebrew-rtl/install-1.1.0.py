"""Console gate for release 1.1.0 (main-1.0.1 + Hebrew RTL + mods/0-hebrew) on PPSA91762, through the shared queue.

PREPARED, NOT RUN. Only the coordinator runs it with Tomer (game saved and closed). Starting point: the console as the
main-1.0.0 gate left it (eboot 51b7e65b, side-branch mods renamed _NAME, mods/_hebrew -> app0 hebrew-rtl-r6-e787deb75759).

Reuses port/main-install/install-main.py (and through it port/r28b-dlc-dex/install-r28b.py): lease, all-runs save
backup (double read), staged .new -> readback -> rename eboot swap keeping eboot.bin.before-r28b-<tag>, r29-ui launcher
mount, observer screenshots, owned close. Adds:
  isolate   the side-branch mods must stay disabled (_NAME); the payload only renames, logs ALREADY when done
  verify    the app0 Hebrew package (same r6 tree as the 31.10 install) is read back file by file; uploaded if absent
  activate  payload links mods/0-hebrew -> ../../../app0/<package>/hebrew; REFUSES if an enabled mod sorts before it
  shot      launcher, continue the active run, in-game + menu (X) screenshots; crash/save checks
Order: init -> backup -> isolate -> verify -> install -> activate -> shot -> complete.
Rollback: eboot.bin.before-r28b-<tag> (= main-1.0.0 51b7e65b) back to eboot.bin; `deactivate` renames 0-hebrew -> _0-hebrew.
"""
from __future__ import annotations
import argparse, ftplib, hashlib, importlib.util, json, os, shutil, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("install_main", ROOT / "port/main-install/install-main.py")
mm = importlib.util.module_from_spec(spec); spec.loader.exec_module(mm)
m, api, queue = mm.m, mm.api, mm.queue
read, write, emit, sha = m.read, m.write, m.emit, m.sha

RELEASE = "main-1.1.0"
ARTIFACTS = Path(os.environ.get("ZA_ARTIFACTS", r"C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port\artifacts"))
PACKAGE = ARTIFACTS / "main-1.1.0-candidate-20261031-r1"
WSL_IMAGE = r"\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\hebrew-1.1.0-candidate-20261031-r1\image\eboot.bin"
MODS_SOURCE = ROOT.parent / "hebrew-lab/build/hebrew-assistant-20261031-r6/mods"     # holds hebrew/ (564 files)
BASE = "51b7e65b0bd930bfe7ede0127d56736ee43d8487310ebff6337c92e11b3e1ab1"   # main-1.0.0, installed by its gate
NEW = os.environ.get("ZA_110_EBOOT", "")                                  # pinned below from PACKAGE.json
LINK_NAME = "0-hebrew"                                                    # mod-order rule: text layer sorts first
SIDE_MODS = list(mm.SIDE_MODS)                                            # hebrew + console-fifty x2 + rowlet: stay _NAME
AGENT = "claude-main-1.1.0"
PAYLOAD_DIR = "/data/pldmgr/payloads/za_main_release"


def manifest():
    rows = [{"path": p.relative_to(PACKAGE / "mods").as_posix(), "bytes": p.stat().st_size, "sha256": sha(p)}
            for p in sorted((PACKAGE / "mods").rglob("*")) if p.is_file()]
    return rows, hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()


def package_dir(digest):
    return "hebrew-rtl-r6-" + digest[:12]


def prepare_package():
    global NEW
    if not PACKAGE.exists():
        (PACKAGE / "PPSA91762").mkdir(parents=True)
        shutil.copyfile(WSL_IMAGE, PACKAGE / "PPSA91762/eboot.bin")
        shutil.copytree(MODS_SOURCE, PACKAGE / "mods")
        rows, digest = manifest()
        write(PACKAGE / "PACKAGE.json", {"release": RELEASE, "eboot_sha256": sha(PACKAGE / "PPSA91762/eboot.bin"),
              "base_sha256": BASE, "mods_files": len(rows), "mods_manifest_sha256": digest,
              "app0_folder": package_dir(digest), "mods_link": LINK_NAME, "mods": rows, "hardware_tested": False})
    info = read(PACKAGE / "PACKAGE.json")
    NEW = info["eboot_sha256"]
    assert sha(PACKAGE / "PPSA91762/eboot.bin") == NEW
    rows, digest = manifest()
    assert digest == info["mods_manifest_sha256"] and rows == info["mods"], "package mods changed"
    m.BASE, m.NEW, m.PACKAGE, m.AGENT = BASE, NEW, PACKAGE, AGENT
    mm.BASE, mm.NEW, mm.PACKAGE, mm.AGENT, mm.RELEASE = BASE, NEW, PACKAGE, AGENT, RELEASE
    return rows, digest


def init(local, handoff):
    prepare_package()
    local.mkdir(parents=True, exist_ok=True)
    out = Path(r"\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\main-releases") / (RELEASE + "-gate-" + api.stamp())
    out.mkdir(parents=True)
    write(local / "nas-location.json", {"evidence": str(out)})
    write(out / "external-handoff.json", {"at": api.utc_now(), "from": "Tomer", "statement": handoff,
          "remote_close_authorized": True, "game_saved_and_closed": False})
    job = {"console": api.HOST, "title_id": "PPSA91762", "name": RELEASE + " console gate (1.0.1 + Hebrew RTL + mods/0-hebrew)",
           "artifacts": [{"path": str(PACKAGE / "PPSA91762/eboot.bin").replace("\\", "/"), "sha256": NEW, "remote_path": m.EBOOT}],
           "expected_base": [{"remote_path": m.EBOOT, "sha256": BASE}],
           "notes": "eboot swap (old kept); app0 Hebrew package verified; link mods/0-hebrew; side-branch mods stay disabled."}
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
                raise RuntimeError("Installed eboot is not main-1.0.0")
            write(out / "initial-probe.json", {"at": api.utc_now(), "base_sha256": BASE, "second_readback_verified": True})
        finally:
            c.close()
    emit({"stage": "init", "evidence": str(out), "ticket": lease["ticket"]})


def verify(c, lease, out):
    """The Hebrew package on app0: read back every file; upload (staged .part, then rename) only if absent."""
    m.idle()
    rows, digest = prepare_package()
    folder = m.APP + "/" + package_dir(digest)
    names = c.listing(m.APP)
    if folder.rsplit("/", 1)[1] not in names:
        staged = folder + ".part"
        if staged.rsplit("/", 1)[1] in names:
            raise RuntimeError("A partial upload exists; inspect it before retrying")
        made = set()
        for i, row in enumerate(rows):
            lease.check()
            remote = staged + "/" + row["path"]; parts = remote.rsplit("/", 1)[0].split("/")
            for j in range(len(parts)):
                d = "/".join(parts[:j + 1])
                if d.startswith(staged) and d not in made:
                    c.ftp.mkd(d); c.chmod(d, "777"); made.add(d)
            with (PACKAGE / "mods" / row["path"]).open("rb") as source:
                c.ftp.storbinary("STOR " + remote, source, 1 << 20)
            c.chmod(remote, "644")
            if i % 50 == 0: lease.heartbeat(); emit({"stage": "upload", "done": i + 1, "files": len(rows)})
        marker = json.dumps({"mods_manifest_sha256": digest, "files": len(rows), "eboot_sha256": NEW}, indent=1).encode()
        c.store(staged + "/installation.json", marker)
        c.ftp.rename(staged, folder)
    marker = c.read(folder + "/installation.json", 4096) or b""
    if digest.encode() not in marker:
        raise RuntimeError("app0 package marker does not name manifest " + digest)
    bad = []
    for i, row in enumerate(rows):
        if c.sha256(folder + "/" + row["path"]) != row["sha256"]: bad.append(row["path"])
        if i % 100 == 0: lease.heartbeat()
    if bad:
        raise RuntimeError("app0 package differs: %d files, e.g. %s" % (len(bad), bad[:3]))
    write(out / "upload.json", {"at": api.utc_now(), "folder": folder, "manifest_sha256": digest, "files": len(rows),
          "every_file_read_back": True})
    emit({"stage": "verified", "folder": folder, "files": len(rows)})


def payload_elf(out, name, defines, source):
    elf = out / name
    if not elf.exists():
        sdk = "/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk"
        tmp = "/tmp/" + name
        subprocess.run(["wsl.exe", "-d", "Ubuntu", "-e", sdk + "/bin/prospero-clang", "-O2", "-Wall", *defines,
                        "/mnt/c" + str(source)[2:].replace("\\", "/"), "-o", tmp], check=True)
        shutil.copyfile(r"\\wsl.localhost\Ubuntu" + tmp.replace("/", "\\"), elf)
    return elf


def run_payload(c, lease, out, elf, log_path, label, expected=None):
    identity, capture = mm.mount(c, lease, out, expected or NEW, label)   # r29-ui launcher before and after
    try:
        try: c.ftp.mkd(PAYLOAD_DIR)
        except ftplib.error_perm: pass
        remote = PAYLOAD_DIR + "/" + elf.name
        raw = elf.read_bytes(); c.store(remote, raw); c.chmod(remote, "755"); assert c.read(remote, 8 << 20) == raw
        m.owned(c, identity); lease.heartbeat()
        emit({"stage": label, "payload": api.http_text(api.PAYLOAD_MANAGER + "/loadpayload:" + remote)})
        deadline = time.monotonic() + 60; log = b""
        while time.monotonic() < deadline:
            log = c.read(log_path, 1 << 20) or b""
            if any(w in log for w in (b"COMPLETE", b"FAILED", b"REFUSED")): break
            time.sleep(1)
        (out / (label + ".log")).write_bytes(log)
        m.close_owned(c, identity, lease, out, label)
        if b"COMPLETE" not in log:
            raise RuntimeError(label + " did not complete: " + log.decode("utf-8", "replace")[-400:])
        return log
    finally:
        capture.stop()


def activate(c, lease, out):
    assert read(out / "transaction.json")["installed_readback_verified"]
    digest = read(out / "upload.json")["manifest_sha256"]
    elf = payload_elf(out, "activate-0-hebrew-%s.elf" % digest[:12],
                      [f'-DPACKAGE_DIR="{package_dir(digest)}"', f'-DPACKAGE_SHA="{digest}"', f'-DLINK_NAME="{LINK_NAME}"'],
                      HERE / "activate_hebrew.c")
    log = run_payload(c, lease, out, elf, "/data/hebrew-rtl-activate.log", "hebrew-activate")
    emit({"stage": "activated", "log": log.decode("utf-8", "replace").strip().splitlines()[-1]})


def isolate(c, lease, out):
    """Before the swap (eboot = main-1.0.0): side-branch mods must be _NAME; a renamed one logs ALREADY."""
    assert c.sha256(m.EBOOT) == BASE
    names = "{" + ",".join('"' + n + '"' for n in SIDE_MODS) + "}"
    elf = payload_elf(out, "isolate-disable.elf", ["-DMOD_NAMES=" + names, "-DRESTORE=0"], ROOT / "port/main-install/isolate_mods.c")
    log = run_payload(c, lease, out, elf, "/data/main-isolate-mods.log", "isolate", expected=BASE)
    emit({"stage": "isolated", "log": log.decode("utf-8", "replace").strip().splitlines()})


def deactivate(c, lease, out):
    elf = payload_elf(out, "deactivate-0-hebrew.elf", ['-DMOD_NAMES={"%s"}' % LINK_NAME, "-DRESTORE=0"],
                      ROOT / "port/main-install/isolate_mods.c")
    log = run_payload(c, lease, out, elf, "/data/main-isolate-mods.log", "hebrew-deactivate")
    emit({"stage": "deactivated", "log": log.decode("utf-8", "replace").strip().splitlines()})


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("operation", choices=("init", "backup", "isolate", "verify", "install", "activate", "shot",
                                         "complete", "deactivate"))
    p.add_argument("--local", required=True, type=Path)
    p.add_argument("--handoff")
    a = p.parse_args(); local = a.local.resolve()
    prepare_package()
    if a.operation == "init":
        if not a.handoff: p.error("init needs --handoff (Tomer: game saved and closed)")
        init(local, a.handoff); sys.exit(0)
    out = Path(read(local / "nas-location.json")["evidence"])
    ops = {"backup": m.backup, "isolate": isolate, "verify": verify,
           "install": m.install, "activate": activate, "shot": mm.shot, "complete": m.complete, "deactivate": deactivate}
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
