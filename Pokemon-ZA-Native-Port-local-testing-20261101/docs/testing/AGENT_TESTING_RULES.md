# Binding workflow for agents

The canonical AGENTS.md and resource-queues card remain binding in full. This workflow adds
test evidence requirements and does not authorize console use, uploads, stale lease takeover,
asset distribution or changes to another agent's checkout. All game tests remain sequential.

1. Read the canonical rules and task card. Develop/build in an isolated branch/worktree and
   new output directories. Do not commit unless Tomer asks. Prepare jobs without holding PC
   resources; obtain a canonical turn for heavy builds/tests under the existing policy.
2. Select the cheapest tier that can validate the actual change. Logic changes prefer Logic
   when a typed probe exists; currently submit an explicit Full fallback. Rendering changes
   start with Render. Timing/input/integration/gameplay flow use Full when needed.
3. Pin the exact supported EXE/DLL and copied-save fixture. Prepare and inspect a manifest.
   Use literal assertions that establish the intended behavior, not just startup success.
4. Submit via `zw test submit`. Run one `zw test work` worker for the shared journal, or
   leave it to the already running worker. It obtains its own canonical PC turn and preserves
   the existing game mutex. Never launch another instance or private production PC queue.
5. Query `status` and `results`; continue independent work while waiting. Work touching the
   leased resource still follows the heartbeat/handoff policy. Never hold the console while
   waiting for the PC. The worker polls its waiting ticket and heartbeats its owned lease.
6. Inspect all assertions, runtime/crash logs, screenshots and metric limitations. Capture-only
   visual status is NOT_EVALUATED. Only an approved pinned reference can provide a visual verdict.
   Baselines must be reviewed/approved separately and never replaced to hide a regression.
7. A failed low tier blocks unnecessary expensive escalation. A pass covers only that contract;
   escalate when the changed subsystem needs broader integration. UNSUPPORTED requires a
   supported fallback or explicit further investigation, not a claim that it passed.
8. Cancel via the job ID; wait for FINISHED and cleanup evidence. Interrupted worker: `recover`.
   A cleanup/recovery ERROR requires inspecting evidence before more resource work. Never
   remove canonical queue metadata mutexes or terminate processes owned by another agent.
9. Report actual verdict, build/manifest/job IDs, artifact paths and remaining unknowns. Do not
   describe preparation, synthetic selftests or an unexecuted scenario as a game pass.

## Local commands

From the canonical checkout after installation (same configuration for every worktree):

```powershell
.\zw test init                         # once, writes ../local-test-config.json
.\zw test capacity                     # cheap disk/commit preflight; no game/turn
.\zw test prepare --test-id menu-001 --agent my-agent --build my-build `
  --type render --frames 120 --stop-after-frame 120 --seconds 45 --timeout 60 `
  --out ..\menu-001.json
.\zw test submit ..\menu-001.json      # returns job ID
.\zw test work --once                  # takes its own FIFO turn; no inherited token needed
.\zw test status job-EXACT_ID
.\zw test results job-EXACT_ID
.\zw test cancel job-EXACT_ID
.\zw test list
.\zw test recover
.\zw test selftest                     # synthetic, lightweight, no game or console
.\zw test selftest --existing-queues   # also existing queues and zw regression suites
```

`prepare --dll ... --game ... --save-src ... --input "240:A:8,420:A:8"` customizes the
supported existing adapter. The EXE must still match the fixed guarded runner executable.
`--config FILE` belongs before the subcommand; `ZA_TEST_CONFIG` can select the shared local file.
Do not confuse test ID (scenario label) with unique generated job ID.

Use one foreground worker, or start it hidden with redirected output using PowerShell
`Start-Process -WindowStyle Hidden`; retain its PID/output paths. No daemon/service install is needed.
Default worker drains until idle for 30 seconds. Per-job canonical turns retain FIFO fairness
with other tools. There is no automatic retry or cloud sync.

Prerequisites are the project's existing Python 3.12+ and Pillow (capture decoding/comparison),
plus the provisioned game/runtime. The runner installs/downloads nothing. On Windows through
`zw.cmd`, use `--frames=` to request no frames; an empty separately quoted argument can be
discarded by the cmd wrapper. The underlying runtime input environment still supports empty strings.

## Recovery boundaries

The journal uses atomic transactions and an OS file lock. The worker's PID plus creation time
must be dead before another worker recovers its execution. Armed Windows containment is
terminated/checked for zero descendants, then only that exact PC ticket is reconciled using
checksummed evidence. Missing saved token in the tiny claim-to-journal window requires the
exact lease to expire before evidenced reconciliation. Other agents' stale mutex/lease blocks
are reported and never stolen. If that blocks a test, report it; do not bypass the queue.

Results, original private run directories and saves stay local. Keep generated artifacts out
of Git. Final source/docs packages exclude game files, captures containing game content,
saves, token records and secrets; copy authorized final deliverables to the NAS with SHA verification.

## Existing specialized workflows remain available

V1 does not expose arbitrary EXE bundles, mods, font or cache-seeding options. For those
unsupported scenarios, use the already documented guarded legacy workflow with the canonical
PC turn, existing lock rules, copied fixture/private data root, timeout and concrete evidence.
Identify this explicitly as a legacy fallback, not an execution of an unsupported manifest.
Do not interpret a legacy Python exit code as a game verdict or label it a Logic pass. Report
the actual observed assertions/status and artifacts. This preserves existing capabilities while
the common adapter gains separately validated options; it does not permit bypassing the queue.

Negative controls deliberately return non-PASS; report that the failure path behaved correctly
without relabeling that game job PASS. Preserve development failures and pre-recovery results.
Do not treat an unsealed legacy progress record as the current runtime's exit verdict; inspect
the structured current-attempt native evidence and the source-classification limitations.
