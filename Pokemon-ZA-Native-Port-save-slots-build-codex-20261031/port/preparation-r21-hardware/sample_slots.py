"""One scoped live-profile sample: capture outside a 20s recorder window.
Requires a known launch PID/session/run, and never launches, kills or moves.
"""
import argparse, ftplib, hashlib, json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "port/slot-depth-r23-observer"))
import run_r3 as r
import client

def write(path, data):
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

def retire_snapshot(console, session, seq, receipt, out):
    assert receipt["ack"]["result"] == "saved"
    for f in receipt["files"]:
        name=f["name"]
        assert name.startswith("frame_") and name.endswith(".png") and "/" not in name
        assert f["readback_verified"]
        assert hashlib.sha256((out/name).read_bytes()).hexdigest()==f["sha256"]
        remote=client.BASE+"/session_"+session+"/"+name
        assert console.sha256(remote)==f["sha256"]
        target=f"{session}:{receipt['ack']['seq']}"
        client.issue(console.ftp,session,seq,"retire_capture",target)
        deadline=time.monotonic()+12
        while True:
            try:
                retired=client.collect(console.ftp,session,seq,out,expected_retire_capture=target)
                break
            except ftplib.error_perm as ex:
                if not str(ex).startswith("550") or time.monotonic()>=deadline:raise
                time.sleep(.3)
        assert retired["ack"]["result"]=="retired",retired
        assert console.sha256(remote) is None
        write(out/(name+".retired.json"),dict(remote=remote,local=str(out/name),sha256=f["sha256"],receipt=retired))

def collect(ftp, session, seq, out, expected, preparation=None):
    deadline = time.monotonic() + 12
    while True:
        try:
            value = client.collect(ftp, session, seq, out, expected_slot_depth=preparation)
            ack = value.get("ack", value)
            if ack.get("result") == expected:
                return value
            if preparation is not None and ack.get("result") in {
                    "memory_gate", "preflight_failed", "drain_failed", "incompatible_profile"}:
                return value
            if ack.get("result") != "settling":
                raise RuntimeError("Unexpected acknowledgement: " + json.dumps(ack))
        except ftplib.error_perm as ex:
            if not str(ex).startswith("550"): raise
        if time.monotonic() >= deadline:
            raise TimeoutError("Observer acknowledgement did not complete")
        time.sleep(.5)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--session", required=True)
    p.add_argument("--seq", type=int, required=True)
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--seconds", type=int, default=20, choices=range(10, 41))
    p.add_argument("--label", required=True)
    p.add_argument("--fps-mode", type=int, choices=(0, 1), default=0,
                   help="Expected existing FPS mode; this sampler does not change it")
    p.add_argument("profile", type=int, choices=(8, 16))
    a = p.parse_args()
    if not all(ch.isalnum() or ch in "-_" for ch in a.label):
        raise ValueError("Invalid label")
    out = ROOT / "evidence/preparation-r21-hardware" / ("session-" + a.session) / a.label
    out.mkdir(parents=True, exist_ok=False)
    console = r.Console()
    try:
        processes = r.eboot_processes()
        assert len(processes) == 1 and int(processes[0]["pid"]) == a.pid, processes
        info = client.status(console.ftp)
        assert info["session"] == a.session
        active_path = "/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando/active.json"
        active = json.loads(console.read(active_path, 4096))
        assert active["id"] == a.run, active
        identity = json.loads((out.parent / "identity.json").read_text())
        assert identity["client"] == "r23" and identity["backup_verified"]
        assert identity["pid"] == a.pid and identity["session"] == a.session and identity["run"] == a.run
        record = dict(at=r.utc_now(), session=a.session, pid=a.pid, run=a.run,
                      profile=a.profile, control="slot_depth", preparation="baseline", immutable_spans="off", fps_mode=a.fps_mode, seconds=a.seconds, sequence_start=a.seq, completed=False)
        write(out / "phase.json", record)
        client.issue(console.ftp, a.session, a.seq, "slot_depth", a.profile)
        applied = collect(console.ftp, a.session, a.seq, out, "applied", a.profile)
        if applied["ack"]["result"] != "applied":
            record["transition"] = applied["ack"]
            record["status"] = "not_measured_" + applied["ack"]["result"]
            write(out / "phase.json", record)
            print(json.dumps(record), flush=True)
            return
        assert applied["ack"]["active_slots"] == a.profile
        record["transition"] = applied["ack"]
        client.issue(console.ftp, a.session, a.seq+1, "snapshot")
        record["before"] = collect(console.ftp, a.session, a.seq+1, out, "saved")
        client.issue(console.ftp, a.session, a.seq+2, "measure", a.seconds)
        record["settling"] = collect(console.ftp, a.session, a.seq+2, out, "settling")
        print(json.dumps(dict(stage="measuring", profile=a.profile, control="slot_depth", preparation="baseline", immutable_spans="off", seconds=a.seconds,
                              session=a.session, seq=a.seq+2)), flush=True)
        # No FTP, screenshots, input or mode switches during recorder window.
        time.sleep(a.seconds + 3)
        record["measurement"] = collect(console.ftp, a.session, a.seq+2, out, "complete")
        client.issue(console.ftp, a.session, a.seq+3, "snapshot")
        record["after"] = collect(console.ftp, a.session, a.seq+3, out, "saved")
        retire_snapshot(console, a.session, a.seq+4, record["before"], out)
        retire_snapshot(console, a.session, a.seq+5, record["after"], out)
        assert json.loads(console.read(active_path, 4096))["id"] == a.run
        analysis = json.loads((out / f"measure_{a.seq+2}-analysis.json").read_text())
        assert analysis["all_intervals"]["intervals"] > 0
        assert analysis["all_intervals"]["duration_s"] >= a.seconds - .15
        assert analysis["fps_modes"] == [a.fps_mode]
        assert not analysis["capture_inside_window"]
        assert client.status(console.ftp)["session"] == a.session
        final_procs = r.eboot_processes()
        assert len(final_procs) == 1 and r.process_pid(final_procs[0]) == a.pid
        record["completed"] = True
        record["completed_at"] = r.utc_now()
        write(out / "phase.json", record)
        print(json.dumps(dict(path=str(out), profile=a.profile,
                              timing=analysis["all_intervals"],
                              shader_affected=analysis["shader_affected_intervals"],
                              fps_modes=analysis["fps_modes"])), flush=True)
    finally:
        console.close()

if __name__ == "__main__":
    main()


