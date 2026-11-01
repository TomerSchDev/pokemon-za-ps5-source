# Card: shared PC testing and console turns

Use the canonical checkout's `zw` even from a worktree. Read `AGENTS.md`'s verbatim resource rule.
State is shared outside checkouts: `PS5-13.60/pc-test-state` and existing `PS5-13.60/console-install-state`.
Never put production state in a task folder, NAS copy or private `--root`; never edit state.json by hand.

## FIFO and handoff
- BEFORE enqueue/submit (PC, console and structured tests): finish builds/link/package; stage artifacts, dependencies, runners/config/fixtures; pin paths/hashes and ordered tests with inputs, expected results, time/evidence budgets and a concrete bug/cleanup/rollback plan. No placeholder reservations or compilation/setup/planning while queued/owning, even without waiters.
- Backups and final live verification ALSO finish before enrollment; start installation immediately at your turn. Coordinate earlier access without disturbing an owner. Expired/changed evidence: withdraw, refresh outside the installation queue, then re-enroll ready. Bugs/rebuilds: preserve evidence, hand off safely under offline rules and prepare outside the queue. Never alter another agent's ticket.
- `zw pc-queue status|enqueue|claim|heartbeat|check|complete|release` for PC; `zw queue ...` for console.
- Enqueue with `--agent ID --request-id UNIQUE --job FILE`; claim your head ticket with `--agent ID --ticket T`.
- One owner per resource. With no waiter, continue indefinitely, heartbeating every <=30 s (lease is liveness only).
- First waiter sets `yield_by`: PC **300 s** (provisional), console **600 s**, including cleanup/rollback.
- Console offline: keep owner/ticket/FIFO; timers freeze, no complete/release/requeue. Guarded transport errors pause automatically; observed `zw queue connection --state offline|online --evidence FILE ...` pauses/resumes manually. Authenticated `zw doctor --console-ok` TCP probes work during the pause; all observer/install/write gates remain unchanged. Reconnect resumes remaining time; late-detected expired windows restart at 600s. PC is unchanged.
- Poll status/heartbeat every <=30 s while using OR waiting; do not block in a long unmonitored test.
- Heartbeat, cancellation and additional waiters never extend an existing deadline. Start only work fitting the remainder.
- At deadline, stop new work. Finish safe cleanup; the next agent waits for actual release, never steals or kills processes.
- `complete` finishes; `release --reason ...` ends the ticket. Unfinished work enqueues a NEW request at the tail.
- Do not hold one resource while waiting for the other. Read-only code/log analysis needs no turn; heavy tests do.
- Expired lease/mutex: no takeover. Reconcile the exact lease with concrete evidence that activity stopped and handoff is safe.

## Environment and proof
- PC commands need `PC_TEST_AGENT`, `PC_TEST_TICKET`, `PC_TEST_TOKEN` from the claim. `zw pc run` checks them.
- Console commands need `CONSOLE_INSTALL_AGENT`, `CONSOLE_INSTALL_TICKET`, `CONSOLE_INSTALL_TOKEN` AND coordinated `--console-ok`.
- Keep tokens private. Cleanup after yield_by uses `ZW_QUEUE_CLEANUP=1` only for cleanup; unset it immediately afterward.
- Keep operation/verification journals local during the turn; archive them to NAS afterward with SHA/content verification. Full candidate/readback checks remain mandatory.
- PC job: `{"name":"test purpose","notes":"what will run"}`. PC completion/release proof: ticket, own_processes_stopped=true, evidence {path,sha256}.
- Console readiness requires PC validation evidence; bypass only with Tomer's recorded urgent_fix/long_pc_queue approval.
- Console install/complete/release JSON examples: `tools/console-install-queue/examples/`; full protocol: its `README-HE.md`.
- Install with `zw install-bundle`; main_update requires an exact candidate test report, side_app requires a distinct title/param and confined files. Guarded FTP rejects unproved or undeclared writes. Read-only desktop monitor: `tools/console-install-queue/Open-Queue-Monitor.vbs`. Android: `zw queue-mobile` / `Open-Android-Connection.vbs`, paired Tailscale bridge; instructions in `tools/queue-android/README-HE.md`.

## Protect the console baseline
- Install every untested candidate as a separate side application with distinct title/install path and isolated writable data/saves/mods/config. Update/promote the main game only after recorded passed tests for that exact candidate; small/urgent fixes and PC-bypass approval do not waive this. Never use protected PPSA91761 without approval; keep the main game usable even if repair misses the deadline.
- Before any change, record current eboot, mods, assets, config, links and a verified rollback; preserve fresh saves separately.
- Before handoff: either restore the entry baseline, or promote the candidate and register its name, hashes, feature manifest and rebuild instructions.
- Read `status.baselines` again at your turn. A changed baseline means merge/rebuild and requeue; never repin old binaries just to bypass it.
- No registered baseline yet means **unknown**, not free to overwrite. Establish it from fresh observations before changing anything.
- Promotion is an agent's evidenced handoff, not proof of hardware correctness. Record failures/limits honestly and preserve features.
- Tools coordinate cooperating agents; direct scripts/old checkouts can bypass them. All agents must obey this card, including existing sessions.

Fact: one checksummed state/mkdir mutex per resource; fixed handoff deadlines and final baseline readbacks are tested offline.
