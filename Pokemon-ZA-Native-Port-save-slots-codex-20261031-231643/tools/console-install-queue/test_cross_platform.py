#!/usr/bin/env python3
"""Exercise real Windows and WSL processes against one temporary NTFS queue."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).with_name("console_queue.py").resolve()


def wsl_path(path):
    text = str(Path(path).resolve()).replace("\\", "/")
    if len(text) < 3 or text[1] != ":":
        raise ValueError("test requires a Windows drive path")
    return "/mnt/" + text[0].lower() + "/" + text[3:]


def main():
    if os.name != "nt":
        raise SystemExit("Run this interoperability test from Windows")
    with tempfile.TemporaryDirectory(prefix="console-queue-cross-") as temporary:
        base = Path(temporary)
        state = base / "state"
        artifact = base / "synthetic.bin"
        artifact.write_bytes(b"synthetic cross-platform test artifact")
        sha = hashlib.sha256(artifact.read_bytes()).hexdigest()
        job = base / "job.json"
        job.write_text(json.dumps({"console": "192.168.1.135", "title_id": "PPSA91762", "name": "host test only",
            "artifacts": [{"path": str(artifact), "sha256": sha, "remote_path": "/data/homebrew/PPSA91762/eboot.bin"}],
            "expected_base": [{"remote_path": "/data/homebrew/PPSA91762/eboot.bin", "sha256": "0" * 64}]}))
        script = base / "queue-call.sh"
        script.write_text("#!/bin/bash\nset -euo pipefail\nexec python3 -I " + shlex.quote(wsl_path(SCRIPT)) + " --root " + shlex.quote(wsl_path(state)) + ' "$@"\n', encoding="utf-8", newline="\n")
        def call(kind, *args):
            command = ([sys.executable, "-I", str(SCRIPT), "--root", str(state)] if kind == "windows" else
                       ["wsl", "-d", "Ubuntu", "--", "bash", wsl_path(script)]) + list(args)
            result = subprocess.run(command, capture_output=True, text=True, timeout=60)
            if not result.stdout.strip():
                raise RuntimeError((command, result.returncode, result.stderr))
            return result.returncode, json.loads(result.stdout)
        assert call("wsl", "status")[1]["initialized"] is False
        jobs = [("windows" if i % 2 == 0 else "wsl", i) for i in range(8)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = list(pool.map(lambda row: call(row[0], "enqueue", "--agent", "shared-worker", "--request-id", f"cross-{row[1]}", "--job", job.as_posix()), jobs))
        assert all(code == 0 for code, _ in results), results
        assert sorted(row["ticket"] for _, row in results) == [f"{i:08d}" for i in range(1, 9)]
        repeat = call("wsl", "enqueue", "--agent", "shared-worker", "--request-id", "cross-0", "--job", job.as_posix())
        snapshot = call("windows", "status")[1]
        variants = {row["job_sha256"]: row["job"] for row in snapshot["jobs"]}
        assert repeat[0] == 0 and repeat[1].get("already_enqueued"), {"repeat": repeat, "variants": variants}
        contenders = [("windows" if i % 2 == 0 else "wsl", f"cross-owner-{i}") for i in range(6)]
        with ThreadPoolExecutor(max_workers=6) as pool:
            claims = list(pool.map(lambda row: call(row[0], "claim", "--agent", row[1]), contenders))
        winners = [(contenders[i], result) for i, result in enumerate(claims) if result[0] == 0]
        assert len(winners) == 1 and all(code in (0, 4) for code, _ in claims), claims
        (winner_platform, winner_agent), (_, lease) = winners[0]
        other = "wsl" if winner_platform == "windows" else "windows"
        assert call(other, "heartbeat", "--agent", winner_agent, "--ticket", lease["ticket"], "--token", lease["token"])[0] == 0
        assert call(other, "release", "--agent", winner_agent, "--ticket", lease["ticket"], "--token", lease["token"], "--reason", "cross-platform reservation test complete")[0] == 0
        final = call("windows", "status")[1]
        assert final["active"] is None and len(final["jobs"]) == 8
        print(json.dumps({"passed": True, "mixed_enqueues": 8, "unique_fifo_tickets": 8,
                          "mixed_claims": 6, "exclusive_winners": 1,
                          "cross_platform_idempotency": True, "cross_platform_heartbeat_release": True,
                          "hardware_access": False, "state": "temporary directory removed after test"}))


if __name__ == "__main__":
    main()
