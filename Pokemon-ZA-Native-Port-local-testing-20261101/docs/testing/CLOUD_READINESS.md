# Portability boundaries (local implementation)

There is no cloud execution, remote endpoint, upload, synchronization, paid dependency or
network listener. State/results/configuration are local files. The canonical PC FIFO and
Windows named mutex remain mandatory. No console is contacted by this framework.

| Responsibility | Local implementation | Optional future adapter |
|---|---|---|
| Specification | Versioned strict JSON contract | Same versioned job envelope/capability negotiation |
| Build references | Local paths + pinned EXE/module/dependencies | Locally provisioned licensed content-addressed catalogue |
| Scheduling/history | Standard-library SQLite journal + OS worker lock | Optional durable queue backend |
| Resource admission | Existing canonical PC Board, exclusive GPU/game | Measured CPU/commit/GPU/VRAM admission; no parallel mode before proof |
| Execution | Windows contained process-tree bridge to existing zw pc run | OS-specific contained process adapter |
| Monitoring | Windows process/system counters + runtime log metrics | Platform-specific supported counters with same null/measurement semantics |
| Results | Local atomic JSON, SHA-bound evidence | Explicitly authorized result storage transport |
| Agent interface | zw test CLI | Optional client preserving status/assertion semantics |

Configuration resolves relative paths against its own directory, then freezes normalized paths
in each job. Defaults derive from project layout, not a username or GPU model. Production code
does not embed this machine's absolute paths. `max_game_instances` exists but accepts only 1.
The execution adapter is Windows-only; this is a documented capability, not fake portability.
SQLite state must remain on one local filesystem, not a NAS WAL database or copied production queue.

The Windows Job Object controls process lifetime; it is not an OS filesystem/network sandbox.
V1 executes trusted local builds, uses isolated writable roots and checks protected inputs.
An untrusted remote-worker sandbox would require separate design and authorization.

Future work must account for executable import-name/ABI binding, provisioned game assets,
license restrictions, secret handling, save confidentiality and GPU/display/driver variation.
Paths alone do not supply assets, and metadata-only RomFS identity is not a complete reproducible
asset catalogue. This milestone does not authorize moving game binaries, assets, saves, keys
or screenshots to an external service. Any future transport remains optional and requires a
separate authorized implementation; no automatic remote synchronization is introduced.
