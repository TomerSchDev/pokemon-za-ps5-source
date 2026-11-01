# Card: install a build on the console

**Only with Tomer coordinating.** Requires `--console-ok` for anything that contacts the console.

## 1. Take a turn in the shared queue (local, never contacts the console)
```powershell
zw queue status
zw queue enqueue --agent <you> --request-id <stable-id> --job C:/path/job.json
zw queue claim --agent <you>            # prints {ticket, token}; keep the token private
zw queue heartbeat --agent <you> --ticket <T> [--begin-install readiness.json]
zw queue complete ... --receipt r.json  |  zw queue release ... --reason X
```
(= `py -3 -I tools\console-install-queue\console_queue.py`. State: `PS5-13.60\console-install-state` — same folder from Windows and WSL.)
Job templates: `tools/console-install-queue/examples/`. Readiness must be < 5 min old and show: handoff, game closed, save backup, base readbacks.
Exit codes: 0 ok, 2 bad input, 3 lost lease, 4 busy, 5 recovery needed.

## 2. Install
- Pattern (all installers): backup save → upload `eboot.bin.new` → readback SHA → rename → readback SHA. Keep the old eboot.
- Wired to the queue: `port/r28b-dlc-dex/install-r28b.py backup|install|smoke|complete --local DIR`.
- Older per-release installers (`port/perf-r28/install-r28.py init|install|ready|measure|complete|rollback --out ...`) hardcode their own SHA-256s. **Copy and re-pin** for a new build; don't reuse blindly.
- No installer exists yet for r29-ui / r29-music (only `port/rando-music/delivery/INSTALL-HE.md`).

## Facts
- App: `/data/homebrew/PPSA91762`. Data root: `/mnt/sandbox/PPSA91762_000/download0/zarecomp`.
- Launcher payload: `/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf` via `http://192.168.1.135:8084/loadpayload:<path>`.
- FTP reads return stored SELF bytes (the tools send `SITE`/`SELF`). Shared helpers: `run_r3.py` (`Console`, `KlogCapture`).
