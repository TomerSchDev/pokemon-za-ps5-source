# Runtime registrations and crash decoding

`index_runtime.py` reads the local runtime C registrations and P2's defined-symbol output. It writes `hle.jsonl` and a registration-evidence sidecar to the external data directory. Pass `--agent ID` while producing package data so ownership is checked before publication.

```powershell
py -3 -I tools/za-atlas/P4/index_runtime.py --agent ID
py -3 -I tools/za-atlas/P4/test_crash.py
py -3 -I tools/za-atlas/P4/crash.py PATH_TO_KLOG --elf /home/tomer/PATH_TO_MATCHING_BUILD/llvm-pie.elf
```

The crash decoder reads a saved local log and the exact matching ELF. It makes no console connections. It selects the last original native fault PC, subtracts the explicit image base (`--base`, default `0x400000`), symbolizes eligible executable frames, and disassembles the faulting instruction. `--all` retains runtime wrappers, `--json` emits a structured report, and `--db` enriches guest addresses from an existing Atlas database.

Windows calls into WSL go through `llvm_bridge.sh`; both LLVM tools run under `nice`. The first decode requires LLVM work. Subsequent identical queries use a cache validated against ELF size/nanosecond modification time, input addresses, and decoder source hashes. Use `--refresh` to force a new decode, or after unusual same-size/same-mtime ELF replacement. Choose `--work-dir` to control the cache location. Cache and reports contain derived data and must remain outside git and source archives.

`guest_addr` in `hle.jsonl` means an original defined guest function symbol. Dynamic NVN and IPC registrations may have `null` addresses. The actual HLE stub addresses are allocated by runtime registration order and cannot be determined from source names alone.

The runtime index records registrations, including conditional source registrations, rather than asserting that every entry is active in a particular binary. The crash decoder labels source-derived inline hints explicitly; it does not pretend that an ELF without inline debug information supplied those source locations.
