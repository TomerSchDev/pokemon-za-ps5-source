"""Finish the known r20b session without restarting or writing any save.

The renderer reads submission-options.txt only once at startup. Its live state
is changed through the drained observer command; the atomic file update only
selects the next launch's profile.
"""
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "port/submission-r20b"))
import run_r3 as r
import client
from sample import collect, write

SID = "0000066a30a19292"
PID = 113
RUN = "r000000006ae24814-71b51a27"
APP = "/data/homebrew/PPSA91762"
DATA = "/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando"
PROFILE = "batch4"
EXPECTED_SHA = "9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852"


def main():
    out = ROOT / "evidence/submission-r20b-hardware" / ("finish-" + r.stamp())
    out.mkdir(parents=True, exist_ok=False)
    c = r.Console()
    try:
        procs = r.eboot_processes()
        assert not procs or (len(procs) == 1 and int(procs[0]["pid"]) == PID), procs
        active_at_finish = bool(procs)
        if not active_at_finish:
            assert c.sha256(APP + "/eboot.bin") == EXPECTED_SHA
        assert json.loads(c.read(APP + "/sce_sys/param.json"))["titleId"] == "PPSA91762"
        assert c.read("/user/app/PPSA91762/mount.lnk") == APP.encode()
        if active_at_finish:
            assert client.status(c.ftp)["session"] == SID
            assert json.loads(c.read(DATA + "/active.json", 4096))["id"] == RUN
            applied = collect(c.ftp, SID, 60, out, "applied")
            assert applied["ack"]["profile"] == PROFILE
            live_proof = dict(kind="observer_ack", data=applied["ack"])
        else:
            # The user has since closed the title: its sandbox is unmounted.
            # Preserve the actual runtime log evidence instead of fabricating
            # an unavailable acknowledgement or reopening the game.
            log = ROOT / "evidence/submission-r20b-hardware/r20-20261028-194219Z.klog.log"
            lines = log.read_text(errors="replace").splitlines()
            proof = [s for s in lines if re.search(r"\[za-r20b-submit\] applied frame=12357 profile=batch4 max_lists=4 previous=each drained_seq=952143", s)]
            assert len(proof) == 1
            live_proof = dict(kind="runtime_log", log=log.name, line=proof[0],
                              note="Final command 60 ack unavailable after sandbox unmounted; prior measured batch4 command 20 has its matching ack.")
        dest = APP + "/submission-options.txt"
        old = c.read(dest, 1024)
        assert old == b"each\n", repr(old)
        (out / "previous-submission-options.txt").write_bytes(old)
        backup = dest + ".before-r20b-" + r.stamp()
        assert c.read(backup, 1024) is None
        c.store(backup, old)
        assert c.read(backup, 1024) == old
        staged = dest + ".r20b-stage-" + r.stamp()
        new = (PROFILE + "\n").encode()
        c.store(staged, new)
        assert c.read(staged, 1024) == new
        assert c.read(dest, 1024) == old
        if active_at_finish:
            assert client.status(c.ftp)["session"] == SID
        else:
            assert not r.eboot_processes(), "Title started during configuration staging"
        c.ftp.rename(staged, dest)
        assert c.read(dest, 1024) == new
        save_path = DATA + "/" + RUN + "/save/save_0/main"
        # Bounded, read-only observation. Gameplay may legitimately save again.
        save_a = c.read(save_path, 16 << 20) if active_at_finish else None
        save_b = c.read(save_path, 16 << 20) if active_at_finish else None
        if active_at_finish:
            assert save_a is not None and save_b is not None
        record = dict(at=r.utc_now(), session=SID, pid=PID, run=RUN,
                      active_at_finish=active_at_finish,
                      last_live_profile=PROFILE, live_proof=live_proof,
                      startup_profile=PROFILE, startup_readback_verified=True,
                      previous_startup="each", remote_config_backup=backup,
                      save_path=save_path, save_read_stable=save_a == save_b if save_a else None,
                      save_sha256=hashlib.sha256(save_b).hexdigest() if save_b else None,
                      save_verification_note="Not re-read after close; sandbox unmounted" if not active_at_finish else "Read only",
                      save_written_by_tool=False,
                      caveat="Selected for further play after one stationary scene; no global performance or long-session stability claim.")
        write(out / "receipt.json", record)
        print(json.dumps(dict(path=str(out), **record)), flush=True)
    finally:
        c.close()


if __name__ == "__main__":
    main()
