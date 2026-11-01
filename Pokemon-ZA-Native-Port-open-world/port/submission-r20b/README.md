# r20b bounded submission comparison

Candidate title: `randomizer-r20b-batch`, app ID `PPSA91762`.
Artifact: `artifacts/randomizer-r20b-batch/PPSA91762/eboot.bin`.
SHA-256: `9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852`.
Size: 401,934,578 bytes.

This keeps r20's separate per-list command-buffer recording and ordered upload/main buffers, while making the maximum submission group selectable: `each` (1), `batch2`, `batch4`, or `batch8`. The eight retirement slots remain unchanged. Shader compilation, game logic, frame pacing, resolution policy and saves are untouched. This is a measurement candidate, with no claim of a proven FPS increase.

## Why the smaller groups

r20 cut Vulkan submit overhead, but an eight-list batch can occupy all eight retirement slots. One final timeline signal then retires those slots together, so CPU recording may wait for the whole batch. Four/two-list groups leave more room for overlap. This is a hypothesis to measure. The earlier each/batch captures had different camera positions and do not establish a matched performance regression.

The PS5 driver does not chain these command buffers via `radv_ps5_cs_chain`. It concatenates their streams for AGC submission, splitting at the driver's DWORD cap if necessary. The r20 counters count Vulkan calls and the driver's winsys calls, not each possible split AGC submission. CPU ring wait time is real elapsed time; summed per-command-buffer GPU queries can overlap and are not GPU frame duration.

## Startup and live switching

Packaged `submission-options.txt` is `each`. Missing or malformed configuration also selects `each`. Accepted startup values are exactly the four profile names (surrounding whitespace is allowed). Existing `LARECOMP_VK_SUBMIT_EACH` or `LARECOMP_SYNC_SUBMIT` overrides force `each` and reject live batching requests.

Use the private `client.py` with the existing observer session token and monotonically increasing command sequence:

```text
python port/submission-r20b/client.py status
python port/submission-r20b/client.py submission --session SESSION --seq 10 batch4
python port/submission-r20b/client.py collect --session SESSION --seq 10 --out EVIDENCE_DIRECTORY
```

Issuing a command only queues it. An `applied` receipt confirms the GPU drain and profile change completed. It includes `requested_profile`, actual `profile`, `max_lists`, `frame`, and `cost_ns`. The client validates profile/cap agreement. A kernel-log transition also records the old/new profile, frame and drained timeline sequence. Negative results are `rejected_boundary`, `rejected_override`, or `drain_failed`; none report an applied cap. Menu commands are rejected by the existing observer menu path.

The switch runs at the existing observer callback after a successful, non-represented present, under the renderer's recursive execution lock. It flushes and waits for all earlier submitted work, confirms the timeline completed, then changes the cap with the pending queue empty. A represented/failed present rejects the command; retry with a new sequence once a real frame presents. The transition can pause for the GPU drain and must be outside the measured interval.

The observer does not poll commands or perform command-file I/O while a measurement is active, including its settling interval. A command already queued waits until that measurement finishes. The usual completed-measure CSV/ack writes remain. Allow a fresh settling interval after a successful profile receipt, then measure. Keep camera, character, FPS mode and scene unchanged across each → batch4 → batch2 → each repeats. Counters are cumulative across switches; use interval differences or subsequent complete log windows.

## Safety retained from r20

- One final timeline signal at the maximum logical sequence; retirement can be delayed but never advanced.
- Per-list XFB copyback, command buffers, upload-before-main order, ring rotation and command pool lifetime remain unchanged.
- Required fence, empty fence/end, CPU wait/readback, binary presentation and NVN call-end flushes remain.
- Maximum eight stored lists/sixteen command buffers; the active profile lowers the list cap to two/four/one. Other caps remain 400 draws, 32,768 commands and 2 ms.
- The 2 ms threshold is checked at completed-list boundaries; it cannot preempt a single long list. The profile transition runs only after that work completes.
- No removal of `sceAgcSuspendPoint` and no driver/SDK edits.

## Validation

`test.sh` compiles the actual shared queue/executor/switch includes and copied observer with Clang 21, ASan/UBSan, `-Wall -Wextra -Werror`. Cases include copied descriptor lifetime, exact command-buffer order, one timeline signal, eight-slot reuse, list/draw/command/age bounds, empty fence/end, readback, binary/standalone-signal boundaries, each/2/4/8 profiles, force overrides, timeout rejection, and the observer's applied receipts and measurement exclusion. `test-client.py` tests the actual offline command/collect paths and rejects inconsistent receipts.

These host traces validate scheduling and observable order. They do not prove hardware rendering or the complete nested `CMD_CALL` parser, which the mock models through its resulting fence flag. Hardware comparison remains required.

The PS5 title entry and private observer compile with `-Werror`. The full runtime compiles and links, retaining existing SDK/VMA warnings. Packaging and registration checks pass. `audit.py` records unchanged imports (325), all extra objects except the intended title-entry/observer changes, 134 unchanged runtime source files, and 61/64 runtime objects identical after stripping debug metadata. `objects.o` and `exec.o` contain intentional changes. The remaining VMA difference is its assertion source path: instructions/relocations are identical and all allocated sections match after path normalization. Game and driver archive hashes match the prior r20 audit.

Evidence is in `evidence/submission-r20b`. The isolated build is `/home/tomer/ps5-za-native/batch-r20b-20261028`; r20/r19 source and artifacts were preserved. No console access, deployment, save operations or NAS copy were performed by this code agent.
