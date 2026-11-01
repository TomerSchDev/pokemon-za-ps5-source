# Three testing tiers

Status labels: **implemented** is code present; **verified** needs the execution evidence
listed in PERFORMANCE_BASELINE.md; **proposed**, **unsupported** and **blocked** are not passes.

| Tier | Current adapter | What a pass can establish | What it cannot establish |
|---|---|---|---|
| Logic L1 | Unsupported; returns UNSUPPORTED without launching | Nothing yet; use an explicitly submitted Full fallback for observable behavior | Generic log presence is not a typed internal gameplay assertion |
| Logic L2 | Unsupported, dependency investigation required | No claims | Safe render/present/audio omission or hidden/no-GPU execution |
| Logic L3 | Unsupported, deeper runtime work required | No claims | Independent deterministic ticks, virtual time or acceleration |
| Render | Real normal-runtime boot from new_game or pinned copied_save, scripted setup, requested present frames | Capture delivery; optional pinned reference comparison within supplied thresholds | Arbitrary checkpoint restore, fixed camera, deterministic image, semantic scene correctness |
| Full | Existing guarded Windows EXE + game DLL + SDL3/Vulkan via canonical zw pc run | Explicit observable log/frame/capture/FPS assertions for that exact build/input | Complete gameplay correctness or a number of simulation ticks inferred from FPS |

Render is a short normal-game workflow, not a standalone render API. A frame number refers
to backend presentations. First requested frame encodes warm-up; scripted input encodes setup.
`copied_save` takes a folder containing `save_0/main`, hashes every copied input file, and
lets the normal game load it. It is not a serialized running thread/heap/GPU snapshot.
An existing scenario is only a checkpoint when its setup and actual scene evidence are recorded.

The window width/height are passed as `LARECOMP_WINDOW`; the existing runner keeps internal
resolution 1x, dynamic resolution off, original aspect, SMAA/FSR1, volume 0 and a private INI.
Captured game-texture dimensions are measured and may differ from window dimensions.
No verified camera parameter is exposed. Hidden is opt-in and retains SDL video/Vulkan/audio
services; it must not be labeled headless. FPS 60 is measurement-only under the standing rules.

Capture-only returns `visual.status=NOT_EVALUATED` even if the test's explicit capture contract
passes. Reference comparison uses normalized RGB RMSE and fraction of pixels whose maximum
channel difference exceeds a threshold. Dimensions must match. Both configured tolerances
must pass; source baseline SHA must match. This does not implement SSIM, motion registration,
masking or perceptual correctness. Baselines are never updated by execution.

Full completion supports the existing duration budget or an observed final requested screenshot.
The supervisor can stop a few presents after a frame is written. A frame-target timeout fails
to complete; it is never converted into a duration success. Runtime nonzero exit/crash evidence
must fail independently of whether the legacy Python runner returns 0.

## Safe Logic progression (proposed)

1. Locate a narrow typed state probe using the atlas, annotate proven symbols and bind probe
   version/game build to output. Sample at a documented thread-safe point in normal runtime.
2. Add assertions with explicit missing-data/error behavior, then measure repeated normal-mode
   outcomes. Do not treat runtime startup logs as gameplay state.
3. For L2, audit render callbacks, present/input counters, GPU fences/queries/readbacks, pacing,
   SDL events, audio events and async I/O. Compare identical fixture/input/probe scenarios
   against normal mode; any mismatch blocks that scenario rather than loosening expectations.
4. For L3, coordinate virtual time, sleeps, guest scheduling and async effects, then test state
   equivalence and determinism. Report verified simulated ticks / wall second. Remove no
   synchronization just to increase an FPS counter. If independence cannot be proved, retain L1.

Interactive control is proposed: per-execution local commands with sequence IDs, input intervals,
acknowledged presented-frame/state version and snapshot requests. There is no global keyboard
or mouse injection, and this extension does not block the current runner.

## Verified scope of this milestone

Normal-runtime Render captured frames 60/120/180, and a second single-capture job stopped at
observed frame 120. Full passed a 30s new-game case and a 120s copied city-save route. All
15 positive-job captures decoded; their 1920x1080 texture dimensions differ from the 1280x720
window request. Input, explicit shots and periodic shots operated together. No hidden-window,
fixed-camera, arbitrary-state restore, L1/L2/L3 or approved game-reference comparison is claimed.
The reference comparator's synthetic positive/negative tests passed. Measurement details,
negative controls and original infrastructure failures are in PERFORMANCE_BASELINE.md.
