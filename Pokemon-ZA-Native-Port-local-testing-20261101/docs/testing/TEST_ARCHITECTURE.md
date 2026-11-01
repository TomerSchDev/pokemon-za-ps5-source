# Local test architecture

Design written after the audit and before implementation. Final verification status is in
PERFORMANCE_BASELINE.md. No SDL3/Vulkan or game code is changed by this milestone.

## Components and boundaries

`zw test` -> strict versioned manifest -> SQLite job journal -> one local worker ->
canonical PC resource FIFO -> contained bridge -> unchanged canonical `zw pc run` ->
existing Windows game-run mutex -> real EXE/DLL/SDL3/Vulkan.

SQLite is Python's built-in transactional file storage, not a service/database deployment.
It gives concurrent submissions, stable FIFO sequence numbers, atomic claim/cancellation,
execution history and crash-safe updates. A worker file lock is OS-owned and automatically
released on process exit. A transaction only covers short journal updates, never game execution.
Default state and results are outside Git, shared by all checkouts through canonical configuration.
Do not create private production resource queues.

The manifest names the fixed EXE supported by the existing runner, explicit game module,
game directory, scene/fixture and declared assertions. Hashes pin runtime/module/config,
fixture files, baseline and supervision tools. Large RomFS remains read-only in place;
record its path/size/mtime, explicitly not a content hash. A future signed content catalogue
can provide full asset identity without rehashing 6GB every job. No binary copying is needed.

## Supervision and safety

All game jobs are exclusive (GPU=1, game_instances=1); future `max_game_instances` is
configured but only 1 is accepted until resource isolation is proven. Preparation/submission
can be concurrent; no game launches during submit. Runtime execution keeps canonical resource
ownership and existing mutex semantics. An inherited queue token supplied by a caller is not
authority for this worker: it obtains its own declared turn.

The parent creates a Windows Job Object with KILL_ON_JOB_CLOSE. A lightweight child waits
for a stdin handshake; the parent assigns it to the Job Object before sending GO. Descendants,
including `zw`, py launcher, runner and runtime re-execs remain contained. No global input,
image-name kill, breakaway or arbitrary PID cleanup. If containment fails, no game starts.
The worker polls cancellation/deadlines, runtime evidence and process counters; it closes the
job and verifies ActiveProcesses=0 before releasing its PC turn. On interrupted runs, recovery
verifies worker identity and containment or stops with ERROR/manual reconciliation.

Retained native process handles identify exits even after a PID is gone. Sampling failures
are recorded separately and cannot prevent mandatory tree shutdown. A partial legacy progress
record is not an exit verdict: finished_utc seals completion, and native evidence is scoped to
the current PID/creation time rather than old ASLR attempts. No global collision-count exception
can hide a current nonzero exit. Recovery versions the previous result before rewriting it.

Queue waiting has its own bounded timeout, separate from execution's hard timeout. A resource
handoff cancels unfinished work, which must submit a new job/ticket at the tail. Stale canonical
metadata locks are never removed. Recovery releases only this runner's exact ticket with concrete
no-process evidence; no other agent's lease/process can be reclaimed.

## Results and evidence

Scheduling phases: QUEUED, WAITING_RESOURCE, PREPARING, RUNNING, FINALIZING, FINISHED.
Terminal verdicts: PASS, FAIL, ERROR, TIMEOUT, UNSUPPORTED, CANCELLED.
Finalization writes `result.json` atomically before committing the verdict in the journal;
recovery must never turn an interrupted execution into PASS. Logs/captures/metrics have
execution IDs, hashes and relative paths. Saves remain in the private legacy run directory.
Queue tokens are stored only in a private recovery record, never in result manifests/packages.

PASS requires every declared assertion plus mandatory checks (runtime evidence, absence of
crash markers, protected input identity, requested captures and planned completion).
Capture-only may PASS its explicit capture-delivery contract; visual correctness remains
NOT_EVALUATED. Baseline comparison reports RMSE/changed-pixel fraction and pinned tolerances;
it cannot approve/replace baselines. Missing or corrupt evidence cannot pass.
Any observed crash/nonzero runtime exit before a planned stop is FAIL even if captures exist.
Setup/resource/containment errors are ERROR. Hard execution deadline is TIMEOUT. Cancellation
or resource handoff is CANCELLED. Unsupported tier/capability returns UNSUPPORTED without launch.

Frame-bound completion is an observed screenshot boundary using the existing interface;
the supervisor may stop a few presentations later. It is not an exact simulation-tick stop.
FPS interval averages and selectively sampled pace percentiles are explicitly labeled.
Unknown simulation ticks/duration, GPU counters and screenshot overhead remain null with reasons.

Final verification: four real Full/Render positive jobs passed; timeout, cancellation, negative
assertion and native exit-7 controls produced their explicit non-PASS verdicts. All 17 job
histories, including development errors, remain intact. See PERFORMANCE_BASELINE.md.
Image decoding verifies the complete PNG before it can satisfy a frame stop. Periodic capture
coverage is checked through the highest known logged/captured present; frames after that
observation are not invented. Reference arithmetic is synthetically verified, not an approved
visual baseline for the game.

The hard deadline supervises contained game processes and their retries. Preparation hashing
and local I/O use cooperative deadline checkpoints; a blocked OS file read has no independent
watchdog in v1. Job containment is process-lifetime control, not a filesystem/network sandbox.
Use trusted local builds; full RomFS content hashing and stronger worker isolation remain future work.

## Future adapters (proposed)

Keep specification, artifact references, Store, canonical resource adapter, Windows process
adapter, measurement and evidence evaluation separable. Future remote workers can consume the
same contracts through an optional transport/storage adapter after licensing and isolation review.
There is no upload, sync, network API or remote dependency here. Interactive per-job command/ack
transport is reserved for a future runtime-supported channel, not implemented by host input injection.
