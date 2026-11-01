# TB1 / r22 immutable literal spans

This is a separate candidate, not applied to r21 and not enabled or measured on hardware. It changes only three call sites in `runtime/nvn/vulkan/exec.c`:

| Content kind | Preserved source bytes | Preserved requested alignment |
| --- | --- | ---: |
| Unbound UBO | `size` bytes from the existing static 64 KiB zero array | 256 |
| `ZERO_BINDING` | Existing float4 `{0,0,0,1}` | 16 |
| Unbound vertex buffer | Existing 256 zero bytes | 16 |

The UBO descriptor range still passes through the unchanged `ubo_span` clamp. Vertex binding data is identical. Vulkan buffer handles/offsets can intentionally repeat when cached, so raw descriptor structs and the number of redundant bind commands need not be byte-for-byte identical; the addressed bytes, required alignment, binding semantics and descriptor range are unchanged.

## Cache and lifetime

There are three separate content kinds, each with eight fixed slots. Keys contain exact requested size and alignment plus `vk_pending_seq()`. A valid bit prevents a false hit when the first observed sequence is zero. A change in logical sequence is a miss even when r20 batch4 groups both lists into the same physical queue call. `vk_exec_reset` explicitly invalidates entries, including when sequence numbers are reused. Toggling the reserved enabled flag also invalidates entries. Replacement only forgets a reference; it never frees a span or changes GPU resource lifetime.

These are immutable literal copies, not a cache for guest memory or arbitrary caller pointers. The generator verifies the original target declarations and statements before preparing a patch. The helper is private to the executor and must not be used with mutable data or a different literal for one of these content kinds.

Baseline is the default. `za_immutable_spans_set_enabled(bool)` is reserved for later integration by the executor owner under the existing execution lock. No observer command, preparation profile bit, control file, console state or r21 contract changes are included. A controlled future experiment can call this from the existing drained profile boundary.

Every baseline request, cache miss, unsupported size/alignment or unknown kind uses the original `vk_transient_copy`. This preserves allocation usage flags, memory placement, snapshot bytes and fatal allocation behavior. No allocation is enlarged, no usage is changed, and no resource is kept beyond the existing transient allocator lifetime. The largest original UBO zero source remains 64 KiB; a larger request is not newly supported or silently truncated by this change.

## Counters

The existing renderer stats boundary logs per-kind `requests`, `hits`, `misses`, `bypass`, `copied_bytes`, `avoided_bytes` and same-sequence slot `collisions`, plus resets. Counters reset after reporting. `bypass` includes baseline mode and requests ineligible for caching. Byte counters describe copy work, not GPU memory capacity or total allocated alignment padding.

Actual call frequency in the measured scene is unknown: r20b/r21 existing aggregate timers do not isolate these three sites. This candidate is gated on per-kind counters and an A/B test. No FPS gain is claimed.

## Reproduce without editing runtime

```text
python3 generate.py --source /home/tomer/ps5-za-native/preparation-r21-20261028/source --out /new/evidence/directory
bash test.sh
```

`generate.py` refuses to overwrite its output or write inside the input runtime tree. It produces a unified `candidate.patch`, a staged modified executor and include/header, exact baseline/patched call-site snippets, the original copy helper, and SHA-256 manifest. A missing or duplicated anchor fails closed. The script also accepts the preserved r20b source because these target statements are unchanged in r21.

`test.sh` creates a fresh directory under `evidence/immutable-spans-r22`, generates from the specified source (optional first argument), compiles only a host test with ASan/UBSan, and performs a dry-run patch applicability check. It does not build or modify the runtime. The test executes the actual candidate helper and source-extracted original/patched snippets, including the original `ubo_span` and `vk_transient_copy` functions.

Coverage includes normalized descriptor/bind data and range; all-zero versus default w=1; size/alignment variations; first sequence zero; logical versus physical submission identity; sequence changes/reset/reuse; bounded slot collisions; disabled baseline; fallback; per-kind counters; and allocator failure propagation in subprocesses. These are CPU correctness tests with a deterministic transient allocator stub. They do not validate Vulkan submission lifetime on hardware or establish performance.

Do not integrate or deploy the patch until the parent experiment selects this candidate after reviewing r21 outcomes. Review the source hash in each generated manifest; regenerate if the executor changes.
