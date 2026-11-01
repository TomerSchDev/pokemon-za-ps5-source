Z-A native randomizer r19a: local shader compiler integration

Status: built and host-validated; integrated PS5 validation is recorded in the
versioned deliverable hardware-verification.json. Read its scope and limits.
The earlier r18b standalone PS5 test validated the glslang compiler adapter;
that is not evidence of this integrated game's behavior under load.

Base: r17a observer, PPSA91762. The generated cheat-enabled game archive,
menu/randomizer objects, SDL shim, performance hooks and Vulkan driver are
reused. Changed objects: title_entry.o, shaderc_cache.o and runtime shaders.o;
added objects: compiler_adapter.o and worker.o. observer.o also fixes input
that was accidentally disarmed before its scheduled first frame, with a mutex
protecting command/input state and a host regression check. Registration section sizes
and all 230332 main / 40069 SDK function-table entries survive conversion.

Behavior:
- Read the existing runtime and packaged SPIR-V caches first.
- Compile missing vertex/fragment/compute sources on ONE dedicated 8MiB-stack
  worker. Its warm-up starts while the randomizer launcher is open.
- At most eight admitted jobs, each with at most 2MiB copied source. Outputs
  have a 16MiB per-job ceiling. The count includes active/done-but-unconsumed
  jobs. Caller-owned outputs are outside that queue bound.
- Existing shader/pipeline workers wait for their result. This does not make
  every game call nonblocking: startup built-ins and the current compute
  path can still wait, and a draw requiring a new pipeline can still stall.
- Vulkan 1.3 uses SPIR-V 1.6; Vulkan 1.2 uses SPIR-V 1.5. Runtime compute
  stage 5 maps to the compiler adapter's stage 2.
- Keep runtime NoContraction postprocessing for vertex shaders. Cache ONLY
  that final result, with checked flush/fsync/close and atomic rename.
- A missing/invalid disk cache is rebuilt. Cache readers reject files larger
  than 16MiB. Directory/config initialization is synchronized.
- A 30-second request deadline does not cancel glslang or free its input.
  The worker retains ownership and drains abandoned jobs. A timed-out request
  disables new local work for this session. The bound is on caller wait;
  a stuck compiler thread cannot safely be forcibly canceled in-process.

Configuration: /app0/local-shader-options.txt (read before first shader use)
  local       default; local compiler, no wait for a PC
  host        previous development bridge, up to 120 seconds for the PC
  cache-only  no local compilation or host wait
Changing it requires a fresh title launch. Disk-cache format/hash version is
unchanged. Do not delete the existing game or driver pipeline caches.

Checks completed:
- 24 concurrent mock callers, bounded queue high-water 8; invalid input,
  error recovery, timeout and abandoned-source ownership. ASan+UBSan and
  ThreadSanitizer passed (separate runs).
- 36 real concurrent captured-shader compilations match prior host SHA-256.
  37 raw modules pass spirv-val, including Vulkan 1.2 compute recovery.
- The ACTUAL runtime cache/postprocessing functions compiled in a host test:
  12 cold compiles; 0 after process restart; 1 after corrupting one cache
  file. All final cache hashes restored, 12 postprocessed SPIR-V validations,
  no temporary files left. ASan+UBSan enabled.
- PS5 C sources compiled with -Werror. Full game link, symbol/import audit,
  registration-count check, ELF conversion-preservation check and SELF
  packaging passed. See the hardware report for measured scenes and limits.

Build:
  prepare.py creates an isolated /home/tomer/ps5-za-native/compiler-r19-20261028
  tree from the preserved r17a tree. It refuses to overwrite an existing tree.
  build.sh compiles only changed runtime/compiler objects and links the
  immutable generated game archive. It does not regenerate game units.
  test.sh runs the worker and real shader API tests. test-cache.py takes the
  HOST_TEST_WORK directory printed by test.sh and checks runtime persistence.
  Dependencies (SDK, pinned glslang f0bd0257c308b9a26562c1a30c4748a0219cc951,
  driver archives, original game/code inputs) are deliberately not included.

Hardware procedure:
  Wait for the user to save and close the current game.
  hardware.py deploy checks idle state and a known installed executable hash,
  keeps local and remote rollback binaries, verifies staging by readback,
  and installs only eboot.bin, local-shader-options.txt and the observer
  enable flag. It does not alter saves, randomizer assets, performance settings
  or caches. Use launch/log explicitly; never kill an unidentified title.
  On the launcher, back up the active save before autonomous gameplay tests.
  The optional local-shader-test.txt contains up to four exact lowercase
  16-digit shader hashes to force recompilation without deleting disk caches.
  It is only a diagnostic: remove before normal play/restart. Not shipped
  in the update. The tested fragment compiled in 1.438 ms and matched the
  same pinned host compiler; the second requested vertex was not reached
  in this scene and is not counted as an integrated test.

Known independent limitation: the standalone probe's normal SDK exit path
received SIGSYS. Its validated r18b harness used controlled host termination.
This integration has not changed the game's exit handling.

Observer regression: test-observer.sh checks same-frame polling preserves a
future input, frame-limited release, session scoping and capture exclusion.
The r17 client protocol is unchanged. Input support was verified in-game.
