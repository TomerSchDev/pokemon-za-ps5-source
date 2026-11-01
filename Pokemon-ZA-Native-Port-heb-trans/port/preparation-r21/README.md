# r21 preparation experiment

Isolated snapshot: `/home/tomer/ps5-za-native/preparation-r21-20261028`.
Baseline source: untouched `batch-r20b-20261028`.

This experiment changes only repeated CPU descriptor preparation. It creates immutable ordered binding recipes per `Prog` after reflection and before the existing atomic ready publication. The optional lazy path initializes the 1,120-byte `rscale` table only when the current stage has binding 18. All normal texture/cbuf resolution, transient copies, descriptor allocation/update and descriptor binds remain in place. No descriptor cache or resource lifetime change is introduced.

Profiles in the same binary:

| Profile | Flags | Binding traversal | rscale |
| --- | ---: | --- | --- |
| baseline | 0 | r20b body | unconditional |
| plan-only | 1 | immutable recipe | unconditional |
| lazy-only | 2 | reflection scan | only if binding 18 |
| optimized | 3 | immutable recipe | only if binding 18 |

Startup is always preparation `baseline`. The package retains the previously selected submission `batch4` and local shader mode. Preparation profiles are not persisted by this runtime.

`za_preparation_switch_profile(name, frame)` holds the existing execution lock, rejects an active list/render pass, drains pending work and verifies both timeline completion and an empty pending queue before changing flags. It returns flags + 1 on success and a negative code otherwise; failure leaves the old profile. The observer invokes it only at its accepted post-present boundary. `za_preparation_profile_name()` and `za_preparation_profile_flags()` provide the applied state. Observer/client sources and tests live in `../preparation-r21-observer`.

`[za-r21-prep]` periodic lines contain cumulative counters independently for the currently selected profile: calls and VS/FS/CS counts; ordinary/special reflection visits or recipe items visited; rscale builds/skips; actual set allocation/update/write counts. No per-binding clock calls are added. Delta counters only within the same profile. Existing profiler `sets` time includes more than allocation/update; totals overlap and gains must not be added together.

The baseline body is extracted directly from r20b, with only the shared update/write counters added. The wrapper adds the same small accounting to all profiles. Thus same-binary comparisons are controlled but this binary's baseline still has instrumentation and extra recipe metadata compared with the installed r20b binary.

## Reproduction and gates

Run `python3 prepare.py` once to create the new snapshot. It pins the three changed source inputs and saves every baseline runtime hash. `prepare.apply()` deliberately regenerates only candidate files from the untouched baseline when revising this experiment; it does not recreate the snapshot.

`python3 test.py` extracts actual r20b and candidate stage functions into the host harness. It compares normalized descriptor writes, precise buffer handles/offsets/ranges, image descriptors, full rscale/tint/gmap copied bytes, resolver call order and `tex_sc`/`tex_wh` effects across all profiles. Empty/maximal/mixed/unsupported/duplicate bindings and vertex/fragment/compute cases are included. The real switch boundary is tested against successful and failed drains. Clang ASan/UBSan plus `-Wall -Wextra -Werror` are required.

`bash build.sh` gates on these tests and independent observer protocol tests, rebuilds the isolated runtime and observer/title entry, reuses the original game/compiler/driver archives, links and packages. Registration, dynamic imports, unchanged runtime sources, unchanged helper objects and stripped runtime objects are audited. VMA's embedded source directory is normalized only for its preservation comparison; its disassembly/relocations must match.

`ready.json` is written only after these gates succeed. Hardware validation is separate and remains pending at build time. This implementation performs no console access or save operations.
