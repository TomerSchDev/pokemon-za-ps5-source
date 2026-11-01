"""Scoped r21 console checks/input; never operates on an unidentified title.
All game inputs are bounded observer commands. Console closure requires the
same PID/session previously recorded by this tool and a verified save backup.
"""
import argparse
import importlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_r3 as r
H = ROOT / "evidence/preparation-r21-hardware"
APP = "/data/homebrew/PPSA91762"
SANDBOX = "/mnt/sandbox/PPSA91762_000"
DATA = SANDBOX + "/download0/zarecomp/rando"


def write(p, data):
    p.write_text(json.dumps(data, indent=2) + "\n")


def load_client(version):
    folder = {"r23c":"slot-depth-r23c-observer", "r23b":"slot-depth-r23b-observer", "r23":"slot-depth-r23-observer", "r22":"immutable-spans-r22-integration", "r21c":"preparation-r21c", "r21b":"preparation-r21b", "r21":"preparation-r21-observer", "r20b":"submission-r20b"}[version]
    sys.path.insert(0, str(ROOT / "port" / folder))
    return importlib.import_module("client")


def check(c, client, sid, pid):
    procs = r.eboot_processes()
    assert len(procs) == 1 and r.process_pid(procs[0]) == pid, procs
    param = json.loads(c.read(SANDBOX + "/app0/sce_sys/param.json", 65536))
    assert param["titleId"] == "PPSA91762"
    assert client.status(c.ftp)["session"] == sid
    active = json.loads(c.read(DATA + "/active.json", 4096))
    return active["id"]


def collect(c, client, sid, seq, out, expected, preparation=None):
    deadline = time.monotonic() + 15
    while True:
        try:
            kw = dict(expected_preparation=preparation) if preparation else {}
            rec = client.collect(c.ftp, sid, seq, out, **kw)
            ack = rec.get("ack", rec)
            if ack["result"] in expected:
                return rec
            if ack["result"] != "settling":
                raise RuntimeError("Unexpected acknowledgement: " + json.dumps(ack))
        except r.ftplib.error_perm as ex:
            if not str(ex).startswith("550"):
                raise
        if time.monotonic() >= deadline:
            raise TimeoutError("No matching completed acknowledgement")
        time.sleep(.5)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--client", choices=("r20b", "r21", "r21b", "r21c", "r22", "r23", "r23b", "r23c"), default="r20b")
    sub = p.add_subparsers(dest="op", required=True)
    sub.add_parser("inspect")
    log = sub.add_parser("log"); log.add_argument("--seconds", type=int, default=1800)
    for op in ("record", "snapshot", "continue", "input", "close", "preparation", "measure", "fps"):
        s = sub.add_parser(op)
        s.add_argument("--session", required=True)
        s.add_argument("--pid", type=int, required=True)
        if op == "record":
            s.add_argument("--sha256", required=True)
            s.add_argument("--backup", type=Path, required=True)
        elif op != "close":
            s.add_argument("--seq", type=int, required=True)
        if op == "input":
            s.add_argument("action"); s.add_argument("frames", type=int)
        if op == "preparation": s.add_argument("profile")
        if op == "fps": s.add_argument("mode", type=int, choices=(0, 1))
        if op == "measure": s.add_argument("seconds", type=int, choices=range(10, 41))
    a = p.parse_args(); H.mkdir(parents=True, exist_ok=True)
    if a.op == "log":
        assert 1 <= a.seconds <= 3600
        path = H / ("r21-" + r.stamp() + ".klog.log")
        cap = r.KlogCapture(path); cap.start(); print(str(path), flush=True)
        deadline = time.monotonic() + a.seconds
        try:
            while time.monotonic() < deadline and cap.is_alive(): time.sleep(.25)
        finally: cap.stop()
        print(json.dumps(dict(path=str(path), lines=cap.lines, error=cap.error)), flush=True)
        return
    client = load_client(a.client)
    c = r.Console()
    try:
        if a.op == "inspect":
            info = dict(processes=r.eboot_processes(), session=client.status(c.ftp))
            print(json.dumps(info), flush=True); return
        run = check(c, client, a.session, a.pid)
        out = H / ("session-" + a.session); out.mkdir(parents=True, exist_ok=True)
        identity = out / "identity.json"
        if a.op == "record":
            assert not identity.exists(), "Keep the original identity record"
            assert c.sha256(APP + "/eboot.bin") == a.sha256
            backup = json.loads((a.backup / "verification.json").read_text())
            assert backup["run"] == run and backup["double_read_verified"]
            for f in backup["files"]:
                local = a.backup / f["path"]
                assert r.hashlib.sha256(local.read_bytes()).hexdigest() == f["sha256"]
                assert c.sha256(DATA + "/" + run + "/" + f["path"]) == f["sha256"]
            record = dict(at=r.utc_now(), pid=a.pid, session=a.session, run=run,
                          eboot_sha256=a.sha256, backup=str(a.backup),
                          backup_verified=True, client=a.client)
            write(identity, record)
        else:
            owner = json.loads(identity.read_text())
            assert owner["pid"] == a.pid and owner["session"] == a.session and owner["run"] == run
            assert owner["backup_verified"]
            if a.op == "close":
                check(c, client, a.session, a.pid)
                record = dict(at=r.utc_now(), pid=a.pid, session=a.session,
                              response=r.http_json(f"/process_kill?pid={a.pid}"))
                deadline = time.monotonic() + 12
                while time.monotonic() < deadline and any(r.process_pid(x) == a.pid for x in r.eboot_processes()):
                    time.sleep(.5)
                record["owned_process_gone"] = not any(r.process_pid(x) == a.pid for x in r.eboot_processes())
                assert record["owned_process_gone"], record
                write(out / ("close-" + r.stamp() + ".json"), record)
            else:
                cmdout = out / (f"{a.seq:04d}-" + a.op); cmdout.mkdir(exist_ok=False)
                if a.op == "continue": arg, extra, expected = run, None, {"continue_requested"}
                elif a.op == "input": arg, extra, expected = a.action, a.frames, {"input_armed"}
                elif a.op == "snapshot": arg, extra, expected = None, None, {"saved"}
                elif a.op == "preparation": arg, extra, expected = a.profile, None, {"applied"}
                elif a.op == "fps": arg, extra, expected = a.mode, None, {"requested"}
                else: arg, extra, expected = a.seconds, None, {"complete"}
                client.issue(c.ftp, a.session, a.seq, a.op, arg, extra)
                if a.op == "measure":
                    print(json.dumps(dict(stage="measuring", seconds=a.seconds, seq=a.seq)), flush=True)
                    # No FTP/screenshots/input during settling and measurement.
                    time.sleep(a.seconds + 3)
                record = collect(c, client, a.session, a.seq, cmdout, expected,
                                 a.profile if a.op == "preparation" else None)
                check(c, client, a.session, a.pid)
        print(json.dumps(dict(path=str(out), result=record)), flush=True)
    finally:
        c.close()


if __name__ == "__main__": main()
