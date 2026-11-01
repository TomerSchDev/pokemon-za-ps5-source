# Local testing infrastructure audit

Audit date: 2026-11-01. Written before implementation. This file records source observations;
execution evidence and subsequent verification belong in PERFORMANCE_BASELINE.md.

## Scope and evidence discipline

**Verified** means inspected in the local source, not necessarily exercised with the installed binary.
**Hypothesis** needs an experiment. **Proposed** means not implemented at audit time.
The Windows runtime source is the sibling `pokeza-recomp-ps5`, commit
`d06e23f22dcde3f6827c3f953b4582d93b87824a`. The orchestration repository is
`Pokemon-ZA-Native-Port`, starting commit `64bbf2d`, with substantial pre-existing dirty/untracked work.
The shipped executable has not been proved byte-identical to a build of that source.
No generated `aot/main` code was read or game addresses newly inferred in this audit.

## 1. Existing architecture (verified)

* Canonical `zw pc run NAME` forwards to sibling `hebrew-lab/tools/run_poc.py`.
  It uses a fixed `hebrew-lab/runtime/lasrecomp.exe`, a read-only game directory,
  a new `hebrew-lab/runs/NAME` working/data directory, a copied `save_0`, a private
  INI, redirected stdout/stderr, and frame-indexed scripted input/screenshots.
* `workbench/zw.py:pc`, `require_turn`, and `tools/console-install-queue/console_queue.py:Board`
  enforce the **canonical PC resource FIFO**. Its state lives outside checkouts in
  `pc-test-state`; the console FIFO is separate. Claim tokens must stay private.
* `run_poc.py` holds the Windows named mutex `Local\Codex-ZA-PC-Isolated-Run`
  across preparation, all attempts and game cleanup. It serializes GPU/large commit use,
  protects the machine from overlapping bounded game runs, and complements the cooperative FIFO.
  Keep both. The mutex is Windows-session-local, not a guarantee against nonparticipating users/sessions.
* The queue uses a checksummed JSON state, atomic replacement and a mkdir metadata mutex;
  stale ownership is never stolen. Heartbeats are required within 30 seconds. The first
  waiter sets a fixed 300-second PC handoff window including cleanup.
* `run_poc` heartbeats every 20 seconds, stops at the 30-second cleanup margin,
  and requires 2 GiB disk / 18 GiB free commit. It terminates only its own child.
* Existing `port/ui-v2/pc/run-pc-game.py` supports custom EXE/DLL, copies a fixture,
  and hashes it before/after, but has less complete resource/mutex supervision.
  It is not a replacement for the guarded normal runner.

## 2. Builds, files and dependencies (verified)

* Runtime `Makefile`: `PLATFORM=windows`, MSYS2 UCRT64 clang/clang++, lld, SDL3,
  FFmpeg, shaderc, Vulkan and VMA; `runtime/*.c`, `hle`, `services`, NVN/Maxwell,
  Vulkan backend, Windows platform code, C++ UI/ImGui. Runtime flags include `-O2 -g`.
* The EXE exports runtime symbols and emits `lasrecomp.dll.a`. Generated main/SDK C
  and `tools/gamelib_entry.c` compile separately into ~1,400 objects and link into
  `lasgame.dll` against that import library. A generated build ID/ABI must match.
  `Makefile` targets `gen`, `gen-objs`, EXE and GAMELIB describe this distinction.
* `runtime/gamelib.c` loads with LoadLibrary/GetProcAddress and checks `lasgame_tables`
  ABI/ID. `LARECOMP_GAME_LIB` is an explicit module override. The DLL's import table
  also binds an executable module name; an arbitrary renamed EXE is not interchangeable.
* Project `port/ui-v2/pc/build-pc-runtime.sh`, `pc-runtime.mk`,
  `relink-game-dll.sh`, `README-pc-build.md` document the separate UI/hook variant,
  frozen AOT reuse and SDL 3.4 headers/import exports. `stockname` makes a copy under
  the executable name required by the stock DLL. No full runtime rebuild is needed here.
* Local reference module is 372,428,288 bytes; `romfs.bin` is 5,989,104,840 bytes.
  Reuse these read-only rather than copying them for each job.

## 3. Main loop, rendering and timing (verified)

* `runtime/main.c:main`: platform init, parse game/`--play`, `rt_paths_init`, boot,
  `ui_run`, then teardown/reboot loop. `boot` loads the game/NSOs, initializes kernel
  and dispatch, and starts the guest `nn::init::Start` thread through kernel services.
  There is no verified host `simulation_tick()` API.
* `runtime/dispatch.c`, `kernel.c`, `hle`, `services` bridge recompiled calls,
  guest SVCs, threads, waits and platform services. The guest game owns its updates.
* `runtime/nvn/vulkan/device.c:ui_window_init` loads settings, calls
  `SDL_Init(VIDEO|GAMEPAD)`, creates a Vulkan SDL window/surface, then instance,
  device, swapchain, executor and shaders. `backend_init` waits for UI readiness.
  `ui_run` pumps SDL events with a 16 ms wait. A hidden window still creates Vulkan.
* `runtime/nvn/objects.c:nvnQueuePresentTexture` applies present pacing then calls
  `backend_present`. The latter submits/draws/presents, increments presentation counts,
  injects input, runs diagnostic hooks and captures screenshots. These hooks depend on rendering.
* `platform/windows.c:plat_now_ns` uses QueryPerformanceCounter; pacing uses high-resolution
  waitable timers. `kernel.c` uses host-clock timed condition waits.
  `objects.c:present_pace` implements the game's interval (normally 2/60 seconds).
  `LARECOMP_PRESENT_INTERVAL=0` removes pacing and changes game speed; it is **not** verified logic acceleration.
* `vulkan/exec.c` has timeline semaphore waits, ring slots, GPU query results/readbacks,
  guest-visible counters and pacing heuristics. Skipping these could deadlock or change decisions.
* `services/audio.c` initializes SDL audio independently; queued/released buffers signal
  game threads. Muting volume does not remove audio timing. `LARECOMP_NO_AUDIO` is
  not proof that every audio service can be safely omitted. Async I/O, movie decoding,
  thread scheduling, SDL event pumping and GPU-produced data remain relevant dependencies.

## 4. Exact existing automation semantics (source verified)

| Interface | Supported syntax and behavior |
|---|---|
| `LARECOMP_INPUT` | `frame:NAME[:length],...`; default length 10; half-open interval `[start,start+length)`. Uppercase names A B X Y LSTICK RSTICK L R ZL ZR PLUS MINUS LEFT UP RIGHT DOWN; STICK_UP/DOWN/LEFT/RIGHT, RSTICK_UP/DOWN/LEFT/RIGHT, STICK_integerDegrees (0 right,90 up). Parsed each present using a 16,384-byte buffer. Malformed tokens may be silently ignored by the legacy parser. Intervals may overlap; digital buttons OR, sticks follow token assignment order. |
| Input clock | `input_frame(total_frames)` after present increments. Input frame 0 is not called during normal boot. Frame numbers are **presentations**, not independent simulation ticks. |
| Input isolation | `LARECOMP_NO_USER_INPUT=1` blocks host user input; scripted env defaults to blocking unless explicitly overridden. SDL events remain pumped. |
| `LARECOMP_SHOT_AT` | Ascending positive decimal frame numbers separated by commas. Writes game texture, not UI window, to `build/frames/frame_%05llu.png`. Captures exact equal frames; passed frames are skipped. This branch **does not** honor EXIT_AFTER_SHOT. |
| `LARECOMP_SCREENSHOT_EVERY` | Positive integer N; captures when total_frames % N == 0. Default path `build/frame_%05llu.png`; with SCREENSHOT_FROM nonzero: `build/frames/`, only at/after that frame. 0 disables. |
| `LARECOMP_EXIT_AFTER_SHOT` | Presence exits with `_exit(0)` after the EVERY branch when SCREENSHOT_FROM is zero, or after a requested window shot. It does not mean stop after the final SHOT_AT entry. |
| FPS | `LARECOMP_FPS_INTERVAL` float seconds, default 2; stderr `[vk] t=... frame N F fps max Mms level ...`. These are **interval** FPS averages/max gaps. They do not yield per-frame percentiles. |
| Frame-time tracing | `LARECOMP_LOG_PACE` presence logs `[pace] period P blocked B busy C ms`. Source excludes first, >100ms and loading gaps before logging. Percentiles from it must disclose this sampling bias. |
| Other | `LARECOMP_WINDOW=WIDTHxHEIGHT`, `LARECOMP_HIDDEN` (presence), FPS 30/60 and settings; no verified fixed camera for this game. |

`run_poc.py` SHA-256 at audit:
`a26444bc6464716e8ef18dd8dd3f691595aa7a48590d6dac6db68c8ffc6f70e3`.
Existing QA scripts include `hebrew-lab/tools/qa_translation.py` (game-tree guard and
menu_save/appearance scripted scenarios), species pilot scenarios, runtime shell tests,
resource-queue unit tests, and UI host tests. Prior `run.json` and PNGs are local evidence,
not automatically approved visual baselines or portable serialized runtime checkpoints.

## 5. Missing capabilities and risks

**Missing/unsupported until implemented and verified:** common versioned manifest/results,
durable execution queue, cancellation/recovery supervision, deterministic internal-state
assertion protocol, independent simulation clock/ticks, no-GPU execution, arbitrary state
serialization, approved baseline registry, interactive PC state/input channel.

Legacy runner exit status is not a game verdict: it may return zero after killing a crashed
or timed-out runtime. Four address-collision attempts overwrite the main logs (collision logs
are kept), and its seconds budget restarts for each attempt. A supervising hard deadline,
crash-log checks, explicit evidence and child-tree containment are necessary.
Runtime can re-exec for address collisions: checking/killing one recorded PID alone is insufficient.
Hidden mode, mute, warmed cache and stable save do not establish determinism.
Graphics initialization, screenshot readback and filesystem activity can dominate short runs.

## 6. Restrictions (binding, verified from AGENTS.md/cards)

No console access in this task. No game assets, game text, saves or keys in Git or external
uploads. No cloud/service/sync. Test data roots and copied saves must be isolated; canonical
development and original fixture paths must not be written. Do not kill unknown processes,
steal stale resource leases, alter the executable/game reference or duplicate large assets.
Retain all existing rules verbatim. Final source/docs package can go to the authorized NAS;
game content and secrets must be excluded from that package.

## 7. Safe implementation order / immediately feasible

1. Write this audit, architecture, strict versioned manifests and result contracts.
2. Add `zw test` forwarding to a small standard-library local queue CLI. Keep scheduling
   distinct from execution. Use the canonical Board and unchanged `zw pc run`.
3. Put the runner's descendants in a Windows kill-on-close Job Object **before** allowing
   the bridge to launch; retain the existing named game mutex. Supervise hard deadlines,
   explicit cancellation, evidence, queue handoff and recovery.
4. Add render capture via new-game or copied-save boot plus short setup/warmup inputs;
   optional pinned baseline comparison. State acquisition still runs the real game.
5. Reject independent Logic requests as UNSUPPORTED. Later introduce versioned, safe
   guest state probes under normal L1 execution; compare repeated equivalent scenarios
   before any L2/L3 work. Do not weaken assertions when modes diverge.
6. Execute negative controls and real sequential game scenarios, record measured metrics,
   then add concise binding agent rules. No runtime/core gameplay modifications planned.

## 8. Deeper changes (proposed, not initial milestone)

L1 needs typed state probes tied to verified game symbols and a sampling boundary.
L2 needs a dependency audit of NVN submits/fences, counters/readbacks, event and audio services.
L3 needs coordinated virtual clocks, thread/async scheduling and simulation/presentation separation,
plus repeated state equivalence tests. Runtime snapshots need thread/heap/GPU/I/O consistency.
Interactive control should be an authenticated per-execution local channel with command IDs,
acknowledged frame/state boundaries and no global keyboard/mouse injection.

## 9. Proposed commands / outputs (not yet implemented at audit time)

`zw test submit manifest.json` -> job_id + QUEUED; `zw test work --once` -> supervised
execution; `status JOB` -> phase, local queue position and canonical resource ticket;
`results JOB` -> explicit PASS/FAIL/ERROR/TIMEOUT/UNSUPPORTED/CANCELLED plus evidence;
`cancel JOB`, `list`, `recover` -> durable operations. Runtime failures are FAIL;
infrastructure/setup/recovery failures ERROR; missing assertions never imply success.
All paths/configuration remain local. See TEST_ARCHITECTURE.md for the design.

## 10. Evidence discovered after the initial audit

The shared `run_poc.py` was concurrently updated outside this task at local 00:32:35.
Its inspected newer SHA-256 is
`b648e83bd16a6e917d6c2960d19ff6756cb66f19c85954bdff30a0d541071ea8`.
It adds an evidenced automatic release after stopping its own child at the PC cleanup margin;
the input/capture grammar, 18GiB threshold and named mutex are unchanged. The new adapter
recognizes only its own exact job/ticket's checksummed release, verifies its contained tree is
also empty and preserves any next owner. A synthetic regression exercises this interleaving.
This task did not modify `run_poc.py` or restore an older copy.

A real waiting execution exposed Windows error 32 while the existing queue removed its own
metadata owner file. After proving that exact worker PID was gone and no game launched, its
own nonce-bound metadata directory was manually reconciled with SHA-bound evidence. The only
queue implementation change is a bounded sharing-error retry during owned metadata cleanup;
it never steals a stale/foreign lock. The new worker also polls waiting state read-only before
attempting claim. The existing queue regression suite passed after that change.

Current restrictions include foreign queued heads that are not claimed: the new runner can
show the blocking ticket and time out/cancel its own request, but cannot skip another agent's
FIFO position. Recovery does not grant authority to cancel those other agents' jobs.

Post-implementation real execution found that the legacy runner reuses its run record across
ASLR attempts. A partial new-attempt record can retain the previous attempt's exit_code and
terminated_by_harness fields. Only finished_utc plus exit_code seals a completed record.
The adapter now scopes native handle evidence to the current PID and creation time and keeps
prior-attempt exits separately. The historical false FAIL is retained, with a classification
review; regressions exercise stale partial fields and a still-failing current nonzero exit.

Actual isolated new-game and copied city-save workflows, explicit and periodic captures,
input injection, FPS/pace metrics, timeout, running cancellation and native exit-7 failure
were executed. All four positive game jobs passed their declared contracts. Standalone Logic
remains unsupported. See PERFORMANCE_BASELINE.md for IDs, measured values and retained errors;
these later executions do not retroactively turn source observations into deterministic proof.
Reference-comparison arithmetic has synthetic coverage; no approved game-baseline comparison
or hidden-window game run was executed in this milestone.
