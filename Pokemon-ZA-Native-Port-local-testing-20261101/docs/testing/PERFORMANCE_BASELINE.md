# Performance and validation baseline

Date: 2026-11-01. **The first local-runner milestone is implemented and verified.**
This is a measured validation ledger, not evidence of simulation acceleration or visual approval.
All game jobs ran sequentially through the existing canonical PC FIFO and Windows mutex.

## Measured benchmark cases

The job IDs below select the original local manifests, result.json, logs, samples and SHA inventories.
Times are seconds. Execution wall time includes supervised preparation and shutdown; total time
also includes queue waiting and finalization. Each row is one observation, not a repeated-run mean.

| Scenario / job | Actual recipe | Verdict | Execution wall | Queue wait | Total wall |
|---|---|---|---:|---:|---:|
| Short Logic / job-3ef316981ad7441186afee3b64e83e1e | Proposed 300 ticks; no safe state/tick adapter | UNSUPPORTED, no game | — | — | — |
| Long Logic / job-62316eb73c8e47a8ab5c7d9361575433 | Proposed 3,000 ticks; no safe state/tick adapter | UNSUPPORTED, no game | — | — | — |
| Single Render / job-6f95aad527b44fb88c38b33719ad1395 | New game, frame 120, observed capture stop | PASS, visual NOT_EVALUATED | 17.301 | 634.927 | 653.488 |
| Multi Render / job-4946c184d0a443efa702e795e6befecb | New game, frames 60/120/180, observed capture stop | PASS, visual NOT_EVALUATED | 19.363 | 1246.568 | 1267.274 |
| Short Full / job-39864697a6ac4c25bd7a18eb805a3491 | 30s budget; 30:A:8,90:A:8; SHOT_AT 60/120, EVERY 90 | PASS | 33.081 | 768.664 | 803.241 |
| Long Full / job-bc84dbb04c974ba786740557a603a387 | 120s budget; copied city-orig save; 240:A:8,420:A:8,750:STICK_UP:60; shots 300/900/1200 | PASS | 123.325 | 1112.637 | 1237.582 |

The startup captures show the language-selection screen; the long fixture run reached the 3D
city, inspected at frame 1200. No assertion automatically establishes the semantic correctness
of those scenes. Window request was 1280x720; all 15 PNGs from these four PASS jobs decode as
1920x1080 game textures. The short Full run delivered all six periodic captures through present
540 as well as the two explicit captures. Existing input, SHOT_AT and EVERY worked together.

| Scenario | Mean logged interval FPS | Pace p50 / p95 / p99 (ms) | Pace samples | Worst logged gap (ms) | Peak sampled private / working set (bytes) | CPU seconds / % of one logical CPU | Peak system memory load |
|---|---:|---|---:|---:|---|---|---:|
| Single Render | 25.225 | 33.400 / 34.446 / 57.077 | 120 | 170 | 16,154,308,608 / 4,319,129,600 | 25.250 / 145.946% | 63% |
| Multi Render | 26.050 | 33.350 / 34.212 / 98.264 | 180 | 179 | 16,171,716,608 / 4,320,530,432 | 26.625 / 137.508% | 61% |
| Short Full | 27.516 | 33.340 / 34.027 / 34.797 | 534 | 233 | 16,168,079,360 / 4,320,665,600 | 35.766 / 108.116% | 64% |
| Long Full | 27.976 | 33.330 / 34.050 / 39.593 | 2906 | 3047 | 17,711,173,632 / 5,289,865,216 | 240.484 / 195.001% | 67% |

## Instrumentation and limits

Measured: submission/queue/acquisition/execution/finalization timestamps, interval presentation
FPS, filtered present-thread pace periods, sampled cumulative runtime CPU, private bytes,
working set, system memory load/free commit and local hardware identification. Rounded-counter
FPS estimates are separately labeled in JSON and are not substituted for logged FPS here.

Pace percentiles interpolate logged periods. The runtime excludes first-frame, loading and
>100ms periods: these are not complete frame-time percentiles. The separate max-gap log exposes
a 3047ms gap in the long run despite its much lower pace p99. Memory/CPU samples have nominal
1-second spacing; peaks and the final exit interval may be missed. CPU percentage is relative
to one logical CPU and uses execution wall time including preparation.

Unavailable (null with reasons): actual simulation duration/ticks/ticks per wall second,
isolated runtime initialization, GPU utilization, dedicated GPU allocation and screenshot-only
overhead. No speedup, headless operation, deterministic state/image or screenshot overhead is
claimed. Queue waits include this runner's earlier jobs and other agents' canonical turns.
A queue wait is not runtime slowness.

## Final verification and negative controls

* Final installed canonical `zw test selftest --existing-queues`: **28/28 new tests passed
  in 2.547s**, **41/41 existing queue tests passed in 13.013s**. Includes concurrent submitting
  threads/processes, persistence, rejection of empty PASS, PNG/reference negative controls,
  OS worker exclusion, retained exit identity, process descendants on supervisor death,
  cleanup despite diagnostic failure, exact-ticket recovery, subsequent-owner preservation
  and partial legacy/ASLR-attempt exit classification.
* Existing `workbench/test_zw.py`: **9/10 passed in 0.355s**. The combined command exits 1:
  `test_brief_starts_with_rules_and_stays_small` reports species brief 17,141 >= 16,000.
  An earlier check already failed at 16,662. This task does not change that brief or its
  existing cards; the assertion is unchanged. The unrelated failure is retained, not suppressed.
* Hard game timeout: job-d6c0398eed03404ca44aee1de84b6e6d requested an unreachable frame,
  returned **TIMEOUT at 8.153s** for an 8s execution deadline, with zero contained processes.
* Missing-log assertion despite a valid capture: job-609c303bf2cf426b9fee9f3da2693bb5
  returned **FAIL** at 17.038s. Missing evidence did not become success.
* Actual running game cancellation: job-6989eabf4228463abe05f0b3ef4625c0 returned
  **CANCELLED** at 6.119s; the monitor confirmed the runtime existed before cancellation.
  Waiting cancellation (job-8be64d4f930d476191de8cc06bb4780d) also completed correctly.
* Native runtime exit 7 was deliberately injected only into the verified process in its
  execution Job Object. Both job-dd993844404d42c9afdb445f4907ca24 and the final-classifier
  retest job-3f3dfa564c674a8aae360c94ed7650c3 returned **FAIL**, retaining native exit 7.
  These are failure-path tests, not spontaneous game-crash observations.
* Real waiting worker interruption: job-3ed786bb1e3d451bbe8f12a5180f04d2 recovered as
  **ERROR**, cancelled only its own queued ticket, and preserved the other agent's owner.
  Supervisor death with a live descendant is additionally covered by native synthetic tests.
* Independent final read-only verification: **17/17 jobs terminal**, **163 inventoried
  artifact files matched SHA-256/size**, **15 PASS PNGs fully decoded**, all four PASS jobs'
  mandatory/declared checks true, all execution trees empty, worker OS lock available, no private
  execution receipts left. EXE/DLL pins still match; original complete AGENTS byte prefix matches.
  Machine-readable sanitized evidence is included in the source package's validation directory.

## Development failures retained in history

The 17 jobs retain their original verdicts: 4 PASS, 4 FAIL, 4 ERROR, 2 CANCELLED,
2 UNSUPPORTED, 1 TIMEOUT. This is not a game pass-rate calculation: it includes deliberate
negative tests and infrastructure development failures. No old failure was promoted to PASS.

* job-8a8792ca6a224faf97ef43922132159e: Windows sharing error in owned metadata cleanup,
  before game launch. Its exact stopped owner was reconciled with evidence. Added only bounded
  error-32/33 retry; no stale/foreign lock stealing.
* job-cb87e24325b546488ffe674f5de0e71c: existing capacity gate returned ERROR after
  527.379s wait; no game. Free commit was 17.30GiB, below the unchanged 18GiB threshold.
  Testing resumed when 22.53GiB became available; the threshold was never reduced.
* job-0e1afbdb63ca46988c5c684877f5c307: real process-diagnostic access race caused ERROR.
  Native Job containment stopped the tree; recovery completed only its own ticket. The original
  partial result is retained as pre-recovery history. Sampling now skips already retained PIDs;
  diagnostic errors cannot prevent mandatory stop/close. Subsequent long/short Full runs passed.
* job-fb07c30679574299b902c3811cf6c7ed: historical false FAIL after two ASLR collisions,
  because a partial legacy record retained a previous attempt's exit 1. The current attempt
  was still alive and its frame 120 existed. Fixed classification requires a completed record
  or native evidence bound to current PID/creation time; prior exits remain separate. Original
  FAIL and classification-review.json remain unchanged. The later normal capture passed;
  retained real collision evidence and synthetic regressions cover the collision classification,
  rather than claiming the later run reproduced an ASLR collision.

## Machine and exact build observation

Local CIM at 2026-10-31T22:42:42Z (2026-11-01 local): Windows 11 Home 10.0.26200,
i7-12700F, 12 cores/20 logical processors, 34,163,838,976 physical-memory bytes,
NVIDIA GeForce RTX 3050 driver 32.0.16.1088; Meta Virtual Monitor also present.
This does not measure GPU utilization/VRAM. Runtime logs identify v0.1.4-local202.

Pinned EXE SHA-256:
`c74c94359182e6749b92eab82c066b6963dd33c25b0d0314e2a3667e1623e7fc`.
Pinned game module SHA-256:
`a3e0da9a4f07e82c5db23f7eec90982b25edc0e7f240e73503a65e5f510b78fe`.
Original files and copied-save sources were unchanged. No PS5 hardware was tested.

## Comparison method for future optimization

Repeat control/candidate scenarios on the same pinned machine/build/fixture/driver/settings
and explicit cache condition. Compare queue time separately from acquired-resource time; show
spread, outliers and failed runs. Compare screenshot overhead only with paired equivalent runs.
For Logic, first prove state equivalence then measure actual ticks / wall seconds. The current
runner improves supervision and evidence; no end-to-end performance improvement is established.
