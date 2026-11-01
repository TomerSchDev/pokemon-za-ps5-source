"""ZA Vulkan probe (r3, r4 with pad and audio, r5 with the memory/import/thread probes): update the installed
eboot.bin, launch the title, collect evidence.

Subcommands:
  status   read-only: processes, installed eboot.bin hash, title folder, live sandbox file
  update   replace /data/homebrew/PPSA91760/eboot.bin with a verified readback (own PID closed only with --kill-own)
  run      launch through the existing launcher payload, capture klog, poll the live JSON, fetch results
  all      update, then run

--fat on update/run/all selects the r5 fat variant (vk-probe/dist-fat, build id ...-r5fat).
Only the fixed title PPSA91760 is touched. No other title is ever closed.
"""
from __future__ import annotations

import argparse
import ftplib
import hashlib
import importlib.util
import io
import json
import re
import socket
import sys
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent
EVIDENCE = ROOT / "evidence"
HOST = "192.168.1.135"
FTP_PORT = 2121
PAYLOAD_MANAGER = f"http://{HOST}:8084"
KLOG_PORT = 3232
TITLE = "PPSA91760"
TITLE_DIR = f"/data/homebrew/{TITLE}"
REMOTE_EBOOT = TITLE_DIR + "/eboot.bin"
REMOTE_EBOOT_NEW = TITLE_DIR + "/eboot.bin.new"
RUN_TAG = "r5"
LIVE_JSON = f"/mnt/sandbox/{TITLE}_000/download0/za-vk-probe.json"
LIVE_LOG = f"/mnt/sandbox/{TITLE}_000/download0/za-vk-probe.log"
R2_LIVE_JSON = f"/mnt/sandbox/{TITLE}_000/download0/za-native-probe.json"  # the r2 build's status file
# /app0 was read-only to the r3 title, so the keep copies live beside the live files, named after the run.
PERSISTENT_JSON = f"/mnt/sandbox/{TITLE}_000/download0/za-vk-probe-{RUN_TAG}.json"
PERSISTENT_LOG = f"/mnt/sandbox/{TITLE}_000/download0/za-vk-probe-{RUN_TAG}.log"
LAUNCHER_URL = (PAYLOAD_MANAGER
                + "/loadpayload:/data/pldmgr/payloads/za_native_probe_launch/za_native_probe_launch.elf")
LAUNCHER_LOG = "/data/za-native-probe-launch.log"
R2_EBOOT_SHA256 = "7ca2075915c0fb687e5ba4f57e98f020a3eb73c8da9391d599cc8588fb0f318f"
KNOWN_EBOOTS = {
    R2_EBOOT_SHA256: "r2",
    "4962b5e512bf2fb8f6b3f6f982c1195239744802d51965efb31d310a35b788f6": "r3",
    "135151946d6e81483f5934c52b3dc778df23f5443b97a143245c9d5770be6573": "r4",
    "5de2a972b169b81a816524908c30e9142726f4f9a4e51b26e97fd7a5b64e4de3": "r5",
    "a5ed980ad6f41e0184cb77771e8cce93cb139811f167de1ee1be7b15869bd62a": "r5fat",
}
DEFAULT_EBOOT = ROOT / "vk-probe/dist/PPSA91760/eboot.bin"
FAT_EBOOT = ROOT / "vk-probe/dist-fat/PPSA91760/eboot.bin"
DEFAULT_BUILD = "za-vk-probe-a0-20261027-r5"
FAT_BUILD = "za-vk-probe-a0-20261027-r5fat"
HTTP_TIMEOUT = 8.0
FTP_TIMEOUT = 30.0
KLOG_BACKLOG_SECONDS = 2.0
KLOG_PATTERNS = re.compile(r"fatal signal|GPU_FAULT|gpu fault|\[za-vk", re.I)


def stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", flush=True)


# ----------------------------------------------------------------- HTTP

def install_guard():
    spec = importlib.util.spec_from_file_location('za_install_guard', ROOT / 'tools/console-install-queue/install_guard.py')
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard

def http_json(path: str) -> dict:
    try:
        with urllib.request.urlopen(PAYLOAD_MANAGER + path, timeout=HTTP_TIMEOUT) as response:
            return json.load(response)
    except urllib.error.HTTPError:
        # An HTTP application rejection proves a response was received; it
        # must not freeze console ownership as a fictitious network outage.
        raise
    except OSError as exc:
        install_guard().observe_connection('offline', 'HTTP: ' + str(exc))
        raise


def http_text(url: str) -> str:
    try:
        with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError:
        raise
    except OSError as exc:
        install_guard().observe_connection('offline', 'HTTP: ' + str(exc))
        raise


def process_pid(process: dict) -> int | None:
    for key in ("pid", "id", "process_id"):
        value = process.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None


def eboot_processes() -> list[dict]:
    processes = http_json("/processes_list").get("processes", [])
    return [p for p in processes if p.get("name") == "eboot.bin"]


# ------------------------------------------------------------------ FTP

class Console:
    def __init__(self) -> None:
        guard = install_guard()
        raw = ftplib.FTP()
        try:
            raw.connect(HOST, FTP_PORT, timeout=FTP_TIMEOUT)
            raw.login()
            raw.sendcmd("SELF")  # stored SELF bytes, not a decrypted ELF
        except (OSError, EOFError, ftplib.error_temp) as exc:
            raw.close()
            guard.observe_connection('offline', type(exc).__name__ + ': ' + str(exc))
            raise
        guard.observe_connection('online', 'FTP connected, logged in and SELF succeeded')
        self.ftp = guard.GuardedFTP(raw)

    def close(self) -> None:
        try:
            self.ftp.quit()
        except Exception:  # noqa: BLE001
            self.ftp.close()

    def read(self, path: str, limit: int = 64 << 20) -> bytes | None:
        """Bytes of a remote file, or None when the console reports it missing."""
        data = bytearray()

        def append(chunk: bytes) -> None:
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError(f"{path} exceeded {limit} bytes")

        try:
            self.ftp.retrbinary("RETR " + path, append, 1 << 20)
        except ftplib.error_perm as exc:
            if str(exc).startswith(("550", "553", "450")):
                return None
            raise
        return bytes(data)

    def sha256(self, path: str) -> str | None:
        digest = hashlib.sha256()
        try:
            self.ftp.retrbinary("RETR " + path, digest.update, 1 << 20)
        except ftplib.error_perm as exc:
            if str(exc).startswith(("550", "553", "450")):
                return None
            raise
        return digest.hexdigest()

    def listing(self, path: str) -> list[str]:
        # The console's FTP service lists the current directory whatever path
        # MLSD is given, so change into the folder first (as deploy_probe.py does).
        self.ftp.cwd(path)
        try:
            return sorted(name for name, _ in self.ftp.mlsd() if name not in (".", ".."))
        finally:
            self.ftp.cwd("/")

    def store(self, remote: str, data: bytes) -> None:
        self.ftp.storbinary("STOR " + remote, io.BytesIO(data), 1 << 20)

    def chmod(self, remote: str, mode: str) -> None:
        self.ftp.sendcmd(f"SITE CHMOD {mode} {remote}")

    def delete_if_present(self, remote: str) -> bool:
        try:
            self.ftp.delete(remote)
            return True
        except ftplib.error_perm:
            return False


def read_live_json(console: Console, path: str = LIVE_JSON) -> dict | None:
    data = console.read(path, 1 << 16)
    if data is None:
        return None
    return json.loads(data.decode("utf-8", "replace"))


def read_any_live_json(console: Console) -> dict | None:
    """The live status of whichever probe build is running: r3's file, else r2's."""
    for path in (LIVE_JSON, R2_LIVE_JSON):
        live = read_live_json(console, path)
        if live is not None:
            return live
    return None


# ----------------------------------------------------------------- klog

class KlogCapture(threading.Thread):
    def __init__(self, output: Path, *, backlog_seconds: float = KLOG_BACKLOG_SECONDS) -> None:
        super().__init__(daemon=True)
        self.output = output
        self.backlog_seconds = backlog_seconds
        self.stop_event = threading.Event()
        self.error: str | None = None
        self.lines = 0
        self.backlog_lines = 0
        self.connected = False

    def run(self) -> None:
        try:
            with socket.create_connection((HOST, KLOG_PORT), timeout=5.0) as peer, \
                    self.output.open("w", encoding="utf-8", errors="replace") as stream:
                self.connected = True
                peer.settimeout(0.5)
                pending = b""
                started = time.monotonic()
                while not self.stop_event.is_set():
                    try:
                        chunk = peer.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        self.error = "connection closed by the console"
                        break
                    pending += chunk
                    *complete, pending = pending.split(b"\n")
                    for raw in complete:
                        line = raw.decode("utf-8", "replace").rstrip("\r")
                        # The service replays its buffer on connect: keep it out.
                        if time.monotonic() - started < self.backlog_seconds:
                            self.backlog_lines += 1
                            continue
                        stream.write(line + "\n")
                        self.lines += 1
                    stream.flush()
        except OSError as exc:
            self.error = str(exc)

    def stop(self) -> None:
        self.stop_event.set()
        self.join(timeout=5.0)


# ------------------------------------------------------------- commands

def cmd_status(args: argparse.Namespace) -> int:
    log("processes_list")
    try:
        running = eboot_processes()
        for process in running:
            print("  eboot.bin process:", json.dumps(process, ensure_ascii=False))
        if not running:
            print("  no eboot.bin process")
    except (OSError, ValueError) as exc:
        print("  processes_list failed:", exc)
    console = Console()
    try:
        log("installed eboot.bin sha256")
        digest = console.sha256(REMOTE_EBOOT)
        print("  ", digest, f"({KNOWN_EBOOTS.get(digest, 'not a known build')})")
        log(f"listing {TITLE_DIR}")
        for name in console.listing(TITLE_DIR):
            print("  ", name)
        log("persistent results")
        for path in (PERSISTENT_JSON, PERSISTENT_LOG):
            data = console.read(path, 1 << 20)
            print("  ", path, "absent" if data is None else f"{len(data)} bytes")
        log("live sandbox files")
        for path in (LIVE_JSON, R2_LIVE_JSON):
            live = console.read(path, 1 << 16)
            print("  ", path, "absent" if live is None else live.decode("utf-8", "replace").strip())
    finally:
        console.close()
    return 0


def close_own_title(console: Console, allow_kill: bool) -> dict:
    """Close the title only when its own live JSON identifies it. Returns what was done."""
    running = eboot_processes()
    if not running:
        return {"running": False}
    live = read_any_live_json(console)
    pid = live.get("pid") if live else None
    build = live.get("build", "") if live else ""
    pids = {process_pid(p) for p in running}
    if not (live and isinstance(pid, int) and build.startswith("za-") and pid in pids):
        raise RuntimeError(f"an eboot.bin process is running ({running}) and it is not identified as this probe; "
                           "close it yourself before updating")
    if not allow_kill:
        raise RuntimeError(f"the probe is running as PID {pid} ({build}); pass --kill-own to close it")
    log(f"closing own PID {pid} ({build})")
    response = http_json(f"/process_kill?pid={pid}")
    time.sleep(2.0)
    return {"running": True, "pid": pid, "build": build, "kill_response": response}


def cmd_update(args: argparse.Namespace) -> int:
    source = Path(args.eboot)
    if not source.is_file():
        raise SystemExit(f"missing {source}")
    new_bytes = source.read_bytes()
    new_sha = hashlib.sha256(new_bytes).hexdigest()
    record = {"utc": utc_now(), "source": str(source), "new_eboot_sha256": new_sha, "bytes": len(new_bytes)}
    console = Console()
    try:
        log("checking running titles")
        record["closed"] = close_own_title(console, args.kill_own)
        if eboot_processes():
            raise RuntimeError("an eboot.bin process is still running; not updating")
        log("installed eboot.bin before")
        # Fat image probes exceed the general 64 MiB log/file read limit.
        before = console.read(REMOTE_EBOOT, 768 << 20)
        if before is None:
            raise RuntimeError(f"{REMOTE_EBOOT} is missing; this script only updates an installed title")
        before_sha = hashlib.sha256(before).hexdigest()
        record["installed_sha256_before"] = before_sha
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        backup = EVIDENCE / f"backup-eboot-{before_sha[:16]}.bin"
        if not backup.exists():
            backup.write_bytes(before)
            log(f"backed up the installed eboot.bin to {backup.name}")
        record["backup"] = str(backup)
        if before_sha == new_sha:
            log("the installed eboot.bin already is this build")
        else:
            log(f"uploading {source.name} as eboot.bin.new")
            console.store(REMOTE_EBOOT_NEW, new_bytes)
            console.chmod(REMOTE_EBOOT_NEW, "755")
            readback = console.sha256(REMOTE_EBOOT_NEW)
            if readback != new_sha:
                raise RuntimeError(f"readback mismatch on eboot.bin.new: {readback}")
            log("readback verified, renaming to eboot.bin")
            console.ftp.rename(REMOTE_EBOOT_NEW, REMOTE_EBOOT)
            final = console.sha256(REMOTE_EBOOT)
            if final != new_sha:
                raise RuntimeError(f"readback mismatch on eboot.bin after rename: {final}")
            log("final readback verified")
        record["installed_sha256_after"] = console.sha256(REMOTE_EBOOT)
        record["readback_verified"] = record["installed_sha256_after"] == new_sha
        removed = [p for p in (PERSISTENT_JSON, PERSISTENT_LOG) if console.delete_if_present(p)]
        record["stale_results_removed"] = removed
        if removed:
            log("removed stale results: " + ", ".join(removed))
    finally:
        console.close()
    output = EVIDENCE / f"vk-{RUN_TAG}-update-{stamp()}.json"
    output.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"evidence {output}")
    return 0 if record.get("readback_verified") else 1


def cmd_run(args: argparse.Namespace) -> int:
    run_stamp = stamp()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    evidence_path = EVIDENCE / f"vk-{RUN_TAG}-{run_stamp}.json"
    klog_path = EVIDENCE / f"vk-{RUN_TAG}-{run_stamp}-klog.log"
    probe_log_path = EVIDENCE / f"vk-{RUN_TAG}-{run_stamp}-probe.log"
    record: dict = {"started_utc": utc_now(), "host": HOST, "expected_build": args.expected_build,
                    "samples": [], "live_heartbeat_verified": False, "visual_verified": False,
                    "klog": str(klog_path), "errors": []}
    if eboot_processes():
        raise SystemExit("an eboot.bin process is running; close it (or run `update --kill-own`) before launching")
    klog = KlogCapture(klog_path)
    klog.start()
    time.sleep(KLOG_BACKLOG_SECONDS + 0.5)
    record["klog_connected"] = klog.connected
    log(f"klog capture {'connected' if klog.connected else 'NOT connected: ' + str(klog.error)}")
    log("launching through the launcher payload")
    try:
        record["launch_response"] = http_text(LAUNCHER_URL)
    except OSError as exc:
        record["launch_response"] = None
        record["errors"].append(f"launch request failed: {exc}")
        log(f"launch request failed: {exc}")
    time.sleep(3.0)
    console = Console()
    seen_live = False
    final_live: dict | None = None
    exited = False
    try:
        launcher = console.read(LAUNCHER_LOG, 1 << 16)
        record["launcher_log"] = launcher.decode("utf-8", "replace") if launcher else None
        log("launcher log: " + (record["launcher_log"] or "absent").strip().replace("\n", " | "))
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            try:
                live = read_live_json(console)
            except (ValueError, ftplib.Error, OSError) as exc:
                record["errors"].append(f"live read: {exc}")
                live = None
            running = []
            try:
                running = eboot_processes()
            except (OSError, ValueError) as exc:
                record["errors"].append(f"processes_list: {exc}")
            if live is not None:
                # The expected build id may be a prefix: "...-r5" accepts "...-r5fat" too.
                if not str(live.get("build", "")).startswith(args.expected_build):
                    record["errors"].append(f"unexpected build in the live file: {live.get('build')}")
                    log(f"live file belongs to another build: {live.get('build')}; stopping")
                    break
                seen_live = True
                final_live = live
                record["samples"].append({"received_utc": utc_now(), "status": live,
                                          "eboot_processes": running})
                pad_live, audio_live = live.get("pad") or {}, live.get("audio") or {}
                dmem_live, extmem_live, thr_live = live.get("dmem") or {}, live.get("extmem") or {}, live.get("threads") or {}
                log(f"stage={live.get('stage')} heartbeat={live.get('heartbeat')} "
                    f"frames={(live.get('vulkan') or {}).get('frames_presented')} "
                    f"presses={pad_live.get('press_count')} tone={audio_live.get('tone_complete')} "
                    f"mapped={dmem_live.get('mapped_bytes')} import={extmem_live.get('imported_bytes')} "
                    f"gpu_read={extmem_live.get('read_ok')} stack={thr_live.get('stack_bytes')} "
                    f"passed={live.get('passed')} failed={live.get('failed')} exit={live.get('exit_reason')}")
                # The probe writes exit_reason "running" while its frame loop is alive.
                if live.get("exit_reason") not in (None, "", "running"):
                    exited = True
                    break
            elif seen_live and not running:
                log("live file gone and no eboot.bin process: the title exited")
                exited = True
                break
            else:
                log("live file not present yet" if not seen_live else "live file gone")
            time.sleep(5.0)
        else:
            log(f"timeout after {args.timeout} s")
        persistent = console.read(PERSISTENT_JSON, 1 << 16)
        record["final_json"] = json.loads(persistent.decode("utf-8", "replace")) if persistent else None
        probe_log = console.read(PERSISTENT_LOG, 4 << 20)
        if probe_log is None:
            probe_log = console.read(LIVE_LOG, 4 << 20)
        if probe_log is not None:
            probe_log_path.write_bytes(probe_log)
            record["probe_log"] = str(probe_log_path)
        # Finished probes keep their sandbox for ten seconds. Once evidence is
        # saved, close the identified test before CRT exit() takes the known
        # libkernel SIGSYS path. Record host closure, not a clean process exit.
        if args.kill_at_end and final_live and isinstance(final_live.get("pid"), int):
            pids = {process_pid(p) for p in eboot_processes()}
            if final_live["pid"] in pids:
                log(f"closing own PID {final_live['pid']} at the end")
                record["kill_response"] = http_json(f"/process_kill?pid={final_live['pid']}")
    finally:
        console.close()
        time.sleep(1.0)
        klog.stop()
    record["klog_lines"] = klog.lines
    record["klog_backlog_skipped"] = klog.backlog_lines
    if klog.error:
        record["errors"].append(f"klog: {klog.error}")
    if klog_path.exists():
        matches = [line for line in klog_path.read_text(encoding="utf-8", errors="replace").splitlines()
                   if KLOG_PATTERNS.search(line)]
        record["klog_matches"] = matches[:200]
        record["klog_crash_record"] = any(re.search(r"fatal signal|GPU_FAULT|gpu fault", m, re.I) for m in matches)
    samples = [s["status"] for s in record["samples"]]
    if len(samples) >= 2:
        first, last = samples[0], samples[-1]
        same_run = all((s.get("pid"), s.get("boot_monotonic_ns")) == (first.get("pid"), first.get("boot_monotonic_ns"))
                       for s in samples)
        record["live_heartbeat_verified"] = bool(same_run and last.get("heartbeat", 0) > first.get("heartbeat", 0)
                                                 and last.get("uptime_ms", 0) > first.get("uptime_ms", 0))
    final = record["final_json"] or final_live or {}
    record["passed"] = final.get("passed")
    record["failed"] = final.get("failed")
    record["exit_reason"] = final.get("exit_reason")
    record["failures"] = final.get("failures")
    record["ended_utc"] = utc_now()
    evidence_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"evidence {evidence_path}")
    ok = record["failed"] == 0 and record["exit_reason"] == "completed"
    log(f"result: passed={record['passed']} failed={record['failed']} exit_reason={record['exit_reason']} -> "
        + ("OK" if ok else "NOT OK"))
    return 0 if ok else 1


def cmd_all(args: argparse.Namespace) -> int:
    status = cmd_update(args)
    if status != 0:
        return status
    return cmd_run(args)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status", help="read-only console state").set_defaults(handler=cmd_status)
    update = commands.add_parser("update", help="replace the installed eboot.bin with a verified readback")
    run = commands.add_parser("run", help="launch, capture klog, poll the live JSON, fetch results")
    everything = commands.add_parser("all", help="update, then run")
    for sub in (update, everything):
        sub.add_argument("--eboot", default=str(DEFAULT_EBOOT))
        sub.add_argument("--kill-own", action="store_true",
                         help="close the probe's own PID (identified by its live JSON) before updating")
    for sub in (run, everything):
        sub.add_argument("--expected-build", default=DEFAULT_BUILD)
        sub.add_argument("--timeout", type=float, default=240.0)
        sub.add_argument("--kill-at-end", action="store_true",
                         help="close the probe's own PID if it is still running at the timeout")
    for sub in (update, run, everything):
        sub.add_argument("--fat", action="store_true",
                         help="the r5 fat variant: vk-probe/dist-fat and the ...-r5fat build id")
    update.set_defaults(handler=cmd_update)
    run.set_defaults(handler=cmd_run)
    everything.set_defaults(handler=cmd_all)
    args = parser.parse_args()
    if getattr(args, "fat", False):
        if getattr(args, "eboot", None) == str(DEFAULT_EBOOT):
            args.eboot = str(FAT_EBOOT)
        if getattr(args, "expected_build", None) == DEFAULT_BUILD:
            args.expected_build = FAT_BUILD
    try:
        return args.handler(args)
    except (RuntimeError, OSError, ftplib.Error, ValueError) as exc:
        log(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
