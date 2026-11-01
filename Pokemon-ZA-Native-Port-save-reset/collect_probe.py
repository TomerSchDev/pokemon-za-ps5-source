"""Collect fresh read-only telemetry from the native PS5 probe (no remote actions)."""
from __future__ import annotations

import argparse
import ftplib
import io
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import time
import sys

sys.stdout.reconfigure(encoding="utf-8")


def read_sample(host: str, port: int, transport: str, expected_build: str, timeout: float = 4.0) -> dict:
    data = bytearray()
    if transport == "ftp":
        ftp = ftplib.FTP()
        ftp.connect(host, 2121, timeout=timeout)
        try:
            ftp.login()
            path = "/mnt/sandbox/PPSA91760_000/download0/za-native-probe.json"
            def append(chunk):
                data.extend(chunk)
                if len(data) > 16_384:
                    raise ValueError("Status file exceeded 16 KiB")
            ftp.retrbinary("RETR " + path, append)
        finally:
            ftp.close()
    else:
        with socket.create_connection((host, port), timeout=timeout) as peer:
            peer.settimeout(timeout)
            while b"\n" not in data:
                chunk = peer.recv(4096)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > 16_384:
                    raise ValueError("Status response exceeded 16 KiB")
    status = json.loads(bytes(data).decode("utf-8"))
    if status.get("build") != expected_build:
        raise ValueError("Unexpected build: do not attribute another application's response to this test")
    for field in ("pid", "boot_monotonic_ns", "uptime_ms", "heartbeat"):
        if type(status.get(field)) is not int or status[field] < 0:
            raise ValueError(f"Invalid telemetry field: {field}")
    return status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.135")
    parser.add_argument("--port", type=int, default=18760)
    parser.add_argument("--transport", choices=("ftp", "tcp"), default="ftp")
    parser.add_argument("--expected-build", default="za-native-probe-a0-20261026-r2")
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--interval", type=float, default=11.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 2 <= args.samples <= 30 or not 1 <= args.interval <= 15:
        parser.error("Use 2..30 samples and a 1..15 second interval")
    started = datetime.now(timezone.utc)
    output = args.output or Path(__file__).parent / "evidence" / ("hardware-" + started.strftime("%Y%m%d-%H%M%SZ") + ".json")
    if output.exists():
        parser.error("Output already exists; choose a new filename")
    result = {"started_utc": started.isoformat(), "host": args.host, "port": 2121 if args.transport == "ftp" else args.port,
              "transport": args.transport,
              "samples": [], "live_heartbeat_verified": False, "visual_verified": False,
              "vulkan_tested": False, "game_code_executed": False}
    try:
        for i in range(args.samples):
            sample = read_sample(args.host, args.port, args.transport, args.expected_build)
            result["samples"].append({"received_utc": datetime.now(timezone.utc).isoformat(), "status": sample})
            print(json.dumps(sample, ensure_ascii=False), flush=True)
            if i + 1 < args.samples:
                time.sleep(args.interval)
        first = result["samples"][0]["status"]
        last = result["samples"][-1]["status"]
        same_run = all((s["status"]["pid"], s["status"]["boot_monotonic_ns"]) ==
                       (first["pid"], first["boot_monotonic_ns"]) for s in result["samples"])
        result["live_heartbeat_verified"] = same_run and last["heartbeat"] > first["heartbeat"] and last["uptime_ms"] > first["uptime_ms"]
    except (OSError, ValueError, ftplib.Error) as exc:
        result["error"] = str(exc)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Evidence:", output)
    return 0 if result["live_heartbeat_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
