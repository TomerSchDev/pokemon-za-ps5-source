"""Watch an already-running r3 probe until it exits and save its final live JSON (read-only)."""
import json, sys, time
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
import run_r3 as r

deadline = time.monotonic() + (float(sys.argv[1]) if len(sys.argv) > 1 else 300.0)
samples, final = [], None
while time.monotonic() < deadline:
    console = r.Console()
    try:
        raw = console.read(r.LIVE_JSON, 1 << 16)
    finally:
        console.close()
    live = json.loads(raw.decode("utf-8", "replace")) if raw else None
    running = [r.process_pid(p) for p in r.eboot_processes()]
    if live:
        samples.append({"received_utc": r.utc_now(), "status": live, "eboot_pids": running})
        r.log(f"heartbeat={live.get('heartbeat')} frames={live.get('vulkan', {}).get('frames_presented')} "
              f"exit={live.get('exit_reason')} pids={running}")
        final = live
        if live.get("exit_reason") not in (None, "", "running"):
            break
    else:
        r.log(f"live file absent; pids={running}")
        if not running:
            break
    time.sleep(5.0)
out = r.EVIDENCE / f"vk-r3-watch-{r.stamp()}.json"
out.write_text(json.dumps({"samples": samples, "final": final}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
r.log(f"evidence {out}")
v = (final or {}).get("vulkan", {})
r.log(f"final: exit_reason={(final or {}).get('exit_reason')} passed={(final or {}).get('passed')} "
      f"failed={(final or {}).get('failed')} frames={v.get('frames_presented')}")
