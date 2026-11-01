# r22 independent immutable-span A/B candidate

This directory integrates the separately reviewed TB1 candidate into a private clone of finalized r21c. It is built for a possible future same-scene A/B experiment. It has not been deployed or measured on a PS5 by this agent.

Only the existing unbound UBO zero literal, `ZERO_BINDING` float4 `{0,0,0,1}`, and unbound vertex 256-byte zero literal use the new cache. The reviewed helper and header are copied byte for byte from `port/immutable-spans-r22`. Three content kinds each have eight bounded slots, keyed by exact size, requested alignment and `vk_pending_seq()`. A valid bit, logical-sequence check, executor reset and toggle invalidation prevent stale reuse. Physical batch4 grouping does not extend cache validity. The original transient allocator still owns all storage and retirement; this change extends no GPU allocation lifetime.

Startup defaults are immutable spans **off**, r21 preparation **baseline**, submission **batch4**, local shader compiler **local**. Existing preparation profiles remain available: `baseline`, `plan-only`, `lazy-only`, `optimized`. No immutable-span profile file is added, and the runtime never polls for this setting during normal draws.

## Scoped live control

The separate observer command is `immutable_spans off` or `immutable_spans on`, within the existing session/sequence protocol. The command is consumed only outside settling/measurement. It is rejected in the menu, at frame zero, after a failed present or on a represented frame.

`za_immutable_spans_switch(mode, frame)` takes the existing recursive `exec_lock`. The backend rejects deferred submission or an active render pass, flushes through the existing submission path, checks the completed fence sequence and that the submission queue is empty, and only then toggles the owner-controlled flag. Failure leaves the previous state intact. An explicit switch reports and closes the preceding counter interval; normal gameplay adds no control-file I/O, control lock, or drain. Status reads use the same executor lock.

The return contract is `flags + 1` after application: off returns 1, on returns 2. Invalid mode returns -1; unsafe boundary/drain failure returns -3. The observer checks the return against actual runtime status and the requested mode before reporting `applied`. The receipt includes `requested_mode`, actual `mode` and `flags`, `frame`, `cost_ns`, and `runtime_result`. The client requires the intended mode as a separate argument and rejects internally inconsistent or mismatched acknowledgements before saving a successful record.

```text
python client.py immutable_spans --session SID --seq N on
python client.py collect --session SID --seq N --immutable-spans on --out EVIDENCE
```

Programmatic collection uses `expected_immutable_spans='on'` (or `'off'`). Existing preparation and capture-retirement collection arguments are unchanged. `retire-capture.inc`, its tests, `observer.h`, `analyze.py`, and the preparation API header are exact copies of finalized r21c.

## Reproduce and verify

```text
wsl -d Ubuntu -- python3 /mnt/c/.../port/immutable-spans-r22-integration/prepare.py
wsl -d Ubuntu -- bash /mnt/c/.../port/immutable-spans-r22-integration/test.sh
wsl -d Ubuntu -- bash /mnt/c/.../port/immutable-spans-r22-integration/build.sh
```

Preparation refuses an existing clone or manifest. It checks finalized r21c source pins, clones into `/home/tomer/ps5-za-native/immutable-spans-r22-20261028`, generates the exact three-site TB1 patch, adds control wrappers, and preserves the original snapshot. The complete runtime patch and source manifests are in `evidence/immutable-spans-r22-integration`.

Tests execute source-extracted original/patched literal sites with a deterministic host allocator, the actual integrated helper, actual backend boundary, source-extracted objects wrappers, real observer parser/receipt paths, and real client validation. AddressSanitizer and UndefinedBehaviorSanitizer cover the C paths. Coverage includes logical sequence versus physical batch, reset/sequence zero/reuse, exact addressed bytes/range/alignment, all-zero versus w=1, collisions/fallback/allocation failure, drained-boundary failure retention, recursive/concurrent executor locking, menu/present/replay rejection, no measurement polling, and forged receipt rejection. The r21c symlink/FIFO/descriptor/read-failure retirement tests remain intact; their fixture uses Linux `/tmp` because NTFS does not support that FIFO case.

Build compiles only `nvn/objects.o` and `nvn/vulkan/exec.o`, plus the private observer and revision-bearing title entry. The other 62 runtime objects and existing extra objects must remain byte identical. The audit verifies unchanged game archive and driver hashes, unchanged dynamic imports and selected allocator/submission functions, the r21c retirement helper, exact TB1 helper, and source/test bindings. Output is `artifacts/randomizer-r22-immutable-spans/PPSA91762/eboot.bin`; `ready.json` is emitted only after all gates pass.

## Performance interpretation

Per-kind logs record requests, hits, misses, bypass, copied and avoided bytes, collisions, and resets. Their actual scene frequency and performance benefit remain unknown until hardware A/B measurements. A CPU host test is not a Vulkan lifetime validation or an FPS result. Keep the experiment narrow and compare off/on with the same preparation/submission settings and scene; settle after the applied receipt and do not transfer files during the measurement window.
