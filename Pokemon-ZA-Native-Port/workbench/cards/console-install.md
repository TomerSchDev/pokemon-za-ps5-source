# Card: install a build on the console

**Only with Tomer coordinating.** Requires `--console-ok` for anything that contacts the console.
Read `cards/resource-queues.md`: export CONSOLE_INSTALL_AGENT/TICKET/TOKEN; first waiter means 10min including cleanup, restore/promote the baseline before handoff, and requeue unfinished work at the tail. Readiness/receipt schemas now include PC proof and baseline_handoff; old installers need those fields. Full protocol: `tools/console-install-queue/README-HE.md`.

## 1. Take a turn in the shared queue (local, never contacts the console)
**Before enqueue:** compiled/packaged candidate, tools/inputs, verified backups and final live checks ready; pinned hashes, ordered tests/expected results, evidence/time budget and bug/rollback plan written. Installation starts at the turn. See `cards/resource-queues.md`.
```powershell
zw queue status
zw queue enqueue --agent <you> --request-id <stable-id> --job C:/path/job.json
zw queue claim --agent <you>            # prints {ticket, token}; keep the token private
zw queue heartbeat --agent <you> --ticket <T> [--begin-install readiness.json]
zw queue complete ... --receipt r.json  |  zw queue release ... --reason X
```
(= `py -3 -I tools\console-install-queue\console_queue.py`. State: `PS5-13.60\console-install-state` — same folder from Windows and WSL.)
Job templates: `tools/console-install-queue/examples/`. Finish package/runner/test-plan preparation, verified backups and final live checks BEFORE enrollment, through earlier coordinated preparation access without disturbing an active owner/FPS session. Readiness must be < 5 min old and show handoff, game closed, save backup and base readbacks. Withdraw and refresh before re-enrollment if evidence becomes invalid while waiting.
Exit codes: 0 ok, 2 bad input, 3 lost lease, 4 busy, 5 recovery needed.

## 2. Install
- **Enforced path:** `zw install-bundle fingerprint|plan --job FILE` (offline); `zw install-bundle install --out NEW --readiness FILE --handoff FILE --console-ok`. The queued deployment must contain exact test proof for main_update, or isolated side_app metadata. See the queue README/examples. Offline console freezes the same turn; never release/requeue due to disconnection.
- Use opt-in `--defer-complete` when installation must be followed by tests in the same turn: it preserves ownership and writes an incomplete receipt. Keep heartbeats, test/close only the identified own app, then provide fresh readbacks and explicitly complete the handoff. Default unchanged; current installer `62fff384` passed three synthetic transaction tests/four scenarios; FS driver passed eight identity and ten single-POST transport tests (PC155, `evidence/save-fs-console-20261101-r3/executed/guard-verification.json`; no FS hardware claim).
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
- 2026-11-01: owned side91990/PID101 stopped before its observer with PRX load error; ordinary KillApp/SIGKILL could not clear its syscore tracing stop. Crash-bound `sceLncUtilForceKillApp(0x4018)` cleared it remotely; no eboot/PPSA sandbox remained, main36b3 unchanged (`evidence/hebrew-choice-console-20261101-runtime-websrv/final-safe-handoff`). Prebuild `zw hebrew-side-cleanup-prepare --dynamic-identity`; never close an unverified app/PID. Native PRX files require755; guarded installer regression passed22 tests (PC131).
