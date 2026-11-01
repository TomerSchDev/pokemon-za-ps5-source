# Independent r23 slot-depth observer/client

This directory extends the finalized r22 observer with one scoped command, `slot_depth 8` or `slot_depth 16`. Runtime integration, resource allocation and GPU lifetime policy are owned separately by `port/slot-depth-r23`; this directory contains no runtime implementation or console operations.

The observer permits a switch only after a successful non-represented present with a positive frame. Menu, failed-present, represented and frame-zero calls are rejected without invoking the runtime. While settling or recording, neither commands nor slot status are polled. Existing preparation, immutable-span, submission, capture, retirement, FPS, input and continue paths remain available. The native retirement helper and its tests are byte-identical to finalized r21c via r22.

`slot-depth-control.h` is the shared ABI1 contract. `za_slot_depth_switch` returns 8 or 16 only when that depth is applied; -1 invalid input, -3 unsafe boundary/drain, -4 memory gate, -5 incompatible other experiment, and -6 resource preflight failure. The runtime owns serialization, the checked drain, baseline8/capacity16, and the batch4/preparation-baseline/immutable-off restriction. The status getter copies one coherent executor-locked snapshot, with actual active depth, and performs no allocation, memory query or drain.

Receipts distinguish this request's `requested_slots`, `runtime_result`, and `frame` from the last runtime snapshot's `status_requested_slots`, `status_result`, and `status_frame`. That distinction preserves truthful diagnostics for a menu or boundary rejection, where no new runtime call occurred. Applied status requires matching request/result/frame/actual depth and completed sequence at least the drained sequence. Rejected runtime changes must retain the prior active depth.

Sixteen-slot application additionally requires `budget_valid=1`, a nonzero pool no larger than 64 GiB, `0 < largest_free_extent <= pool_bytes`, `driver_bytes <= pool_bytes`, at least 1 GiB of required headroom and a largest free contiguous extent meeting that requirement. `largest_free_extent` is not total free RAM. Eight-slot application may succeed when the budget query is unavailable. All memory/resource diagnostics are reported as their actual fields, with strict integer bounds in the client; no synthetic total is calculated.

```text
python client.py slot_depth --session SID --seq N 16
python client.py collect --session SID --seq N --slot-depth 16 --out EVIDENCE
```

Programmatic collection requires `expected_slot_depth=16` or `8` (canonical strings also accepted). The expected target is independent of the acknowledgement's echoed request. A queued, stale, malformed, incoherent or mismatched result cannot be saved as an applied result. Earlier collection arguments remain unchanged.

Reproduce with `python extend.py`, then run `bash test.sh` under WSL Ubuntu. The generator reads pinned r22 source and writes only this separate observer/client and its evidence. Host tests execute the actual observer parser and receipt writer with runtime status stubs under ASan/UBSan, plus the actual offline client. They cover both depths, negative statuses, memory/ABI/frame/return mismatches, replay, safe-present rejection, measurement deferral, old snapshot diagnostics, malformed acknowledgements and prior protocol regressions. The test input hashes are captured before compilation and checked again afterward. These tests do not establish runtime memory behavior or GPU correctness; the separate runtime and hardware reviews are required for those conclusions.
