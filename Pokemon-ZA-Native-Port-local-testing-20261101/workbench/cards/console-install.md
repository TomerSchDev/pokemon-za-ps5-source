# Card: install a build on the console

**Only with Tomer coordinating.** Requires `--console-ok` for anything that contacts the console.
Read `cards/resource-queues.md`: export CONSOLE_INSTALL_AGENT/TICKET/TOKEN; first waiter means 10min including cleanup, restore/promote the baseline before handoff, and requeue unfinished work at the tail. Readiness/receipt schemas now include PC proof and baseline_handoff; old installers need those fields. Full protocol: `tools/console-install-queue/README-HE.md`.

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
- **Enforced path:** `zw install-bundle fingerprint|plan --job FILE` (offline); `zw install-bundle install --out NEW --readiness FILE --handoff FILE --console-ok`. The queued deployment must contain exact test proof for main_update, or isolated side_app metadata. See the queue README/examples. Offline console freezes the same turn; never release/requeue due to disconnection.
- **Target rule:** use an isolated side application for untested candidates; update the main game only after the exact candidate passed relevant tests with evidence. Separate title/install path and writable data/saves/mods/config; PPSA91761 stays protected. Small/urgent fixes, PC bypass and baseline registration never waive this or depend on the agent fixing it before handoff.
- Pattern (all installers): backup save → upload `eboot.bin.new` → readback SHA → rename → readback SHA. Keep the old eboot.
- Historical queue transaction: `port/r28b-dlc-dex/install-r28b.py`; unproved/incomplete legacy jobs now fail closed. Use `zw install-bundle` for declared full-bundle installs.
- Older per-release installers (`port/perf-r28/install-r28.py init|install|ready|measure|complete|rollback --out ...`) hardcode their own SHA-256s. **Copy and re-pin** for a new build; don't reuse blindly.
- `port/main-install/install-main.py` handles the prior r29-ui gate; the dedicated JSON-fix adapter is reached through `zw newrun-install plan --local NEW`. Other operations require an explicit coordinated handoff and `--console-ok`.

## Facts
- App: `/data/homebrew/PPSA91762`. Data root: `/mnt/sandbox/PPSA91762_000/download0/zarecomp`.
- Launcher payload: `/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf` via `http://192.168.1.135:8084/loadpayload:<path>`.
- FTP reads return stored SELF bytes (the tools send `SITE`/`SELF`). Shared helpers: `run_r3.py` (`Console`, `KlogCapture`).
- Fact: shared FTP guards enforce declared bundle bytes and targets; failure/reconnection preserves the console ticket and pauses/resumes its timers. Verified with synthetic transports, not live hardware.
