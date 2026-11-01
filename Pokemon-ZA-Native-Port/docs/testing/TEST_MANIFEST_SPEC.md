# Manifest and result specification (version 1)

The executable validator is `tools/local-testing/contracts.py`; unknown fields, duplicate JSON
keys, nonfinite numbers, invalid types, unknown assertions and malformed scripts are rejected.
`manifest.schema.json` documents the same public fields for editors. Runtime capability checks
can additionally return UNSUPPORTED/ERROR after a valid submission. No shell commands are accepted.

`manifest.example.json` is a complete local reference-build capture example, with relative
paths and pinned hashes. Prefer `prepare` for another build; the example does not provision assets
or establish visual correctness. Paths are relative to the example's own directory.

## Manifest fields

| Field | Contract |
|---|---|
| schema_version | Integer 1 (boolean is not an integer) |
| test_id, agent_id, build_id, result_directory | 1..100 characters, ASCII letters/numbers/dot/underscore/hyphen, no `.`/`..`; result_directory is a label under the configured result root, never an arbitrary path |
| type | logic / render / full |
| logic_level | Optional L1/L2/L3 for logic. Currently all return UNSUPPORTED |
| runtime | executable and game_module objects `{path,sha256}` plus game_directory. Paths resolve relative to the manifest, then freeze as absolute local paths. SHA is lowercase 64 hex. Fixed executable restriction is enforced at execution |
| input | script and checkpoint. Script is the exact legacy grammar in the audit, restricted to valid positive frame/length and angles 0..359; <16,384 ASCII bytes. Empty script is allowed and still blocks host input. checkpoint is `{kind:"new_game"}` or `{kind:"copied_save",path,files:{"save_0/main":"SHA",...}}` |
| execution | seconds (1..600), optional stop_after_frame (1..1,000,000). Frame stop must be the final explicit screenshot. It is an observed boundary, not an exact tick limit |
| timeout_seconds | Execution deadline, 1..900 seconds, starting with preparation. Contained game processes/retries have a hard monitored deadline; preparation hashing/I/O has cooperative checkpoints, not a separate blocked-I/O watchdog. Monitored shutdown/final evidence cleanup adds cleanup time |
| queue_timeout_seconds | 1..86,400, counted from submission to canonical resource acquisition, including local FIFO wait |
| graphics | width 64..7680, height 64..4320 (SDL window); hidden boolean; fps 30/60; pace_trace boolean. Internal graphics settings remain those of the existing isolated runner |
| screenshots | frames sorted unique positive integers (at most 100), every >=0 (0 disables), mode capture_only/reference. No SCREENSHOT_FROM/EXIT_AFTER_SHOT override; existing meanings are untouched |
| screenshots.baseline | For reference only: path,sha256,frame,rmse_max (0..1),changed_fraction_max (0..1),pixel_threshold (0..255). Baseline frame must be requested; identity is immutable |
| assertions | Nonempty array of objects defined below |
| resources | `{game_instances:1,gpu:1}`. No parallel game mode enabled |
| artifacts | logs and metrics must be true; screenshots boolean must be true if captures requested |

Assertions: `{"kind":"log_contains","text":"literal"}` searches runtime stderr;
`{"kind":"screenshot_exists","frame":120}` requires a decoded requested PNG;
`{"kind":"min_presented_frame","frame":120}` needs a capture or logged present counter;
`{"kind":"fps_at_least","value":25}` requires measured interval FPS, not simulated ticks.
There are no arbitrary memory reads, Python expressions, regex execution or custom shell assertions.

Submission freezes the normalized manifest and its canonical JSON SHA-256. EXE/module hashes,
all shipped DLL hashes, exefs main/SDK hashes, supervision source hashes and fixture hashes
are recorded at execution. Game-tree sizes/mtimes are guarded; RomFS content identity remains
metadata-only (explicit limitation). All protected inputs are checked after execution.

## Results

Each executed job has a unique job ID and execution ID, an atomic result.json and journal verdict.
Result schema fields include version, test/build/agent/job/execution IDs, manifest SHA, explicit
status/reason, timestamps, runtime record, reproducibility metadata, mandatory/declared checks,
separate visual verdict, metrics with unavailable values null, process cleanup proof, resource
receipt and an artifact inventory with relative paths/bytes/SHA-256. A recovered interrupted job
is ERROR and preserves available evidence; no automatic retry or PASS promotion.

| Verdict | Meaning |
|---|---|
| PASS | Planned completion plus every mandatory/declared assertion passed; visual status remains separate |
| FAIL | Runtime crash/nonzero exit or observed assertion/visual regression |
| ERROR | Setup, build identity, infrastructure, evidence or cleanup/recovery failure |
| TIMEOUT | Resource-wait or hard execution deadline exceeded; reason identifies which |
| UNSUPPORTED | Valid but unimplemented tier/adapter capability, no simulated success |
| CANCELLED | Explicit cancellation or canonical handoff; unfinished work needs new submission. An unexpectedly interrupted worker recovers as ERROR |

Queued jobs have no result yet (`status:null`), never an implicit PASS. An invalid submission
returns CLI ERROR/nonzero and does not create a job. `cancel` records intent immediately;
the worker produces the terminal result and verifies cleanup. Start a worker to process queued jobs.

Exit codes: 0 successful command (or PASS for results / work --once), 1 completed non-PASS,
2 CLI/config/infrastructure command failure, 3 results requested while pending. A draining
worker prints each job's own verdict; its eventual 0 exit does not summarize every job as passed.

Exit evidence distinguishes the legacy completed record from a progress record: finished_utc
and exit_code are required for completion. Native retained handles identify the current runtime
by PID/creation time. Stale nonzero fields or handles from earlier ASLR attempts cannot alone
fail the current attempt; a current unexpected nonzero exit always fails. PNGs must fully decode.
Periodic captures must cover all intervals through the highest known logged/captured present.
