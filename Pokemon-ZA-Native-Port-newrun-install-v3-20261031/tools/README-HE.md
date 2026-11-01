# אינדקס הכלים של הפרויקט (נוצר אוטומטית 31.10.2026; `tools/README-HE.md`)

סה"כ 608 קובצי כלים/מקור (ללא בדיקות): python 418, shell 81, c 63, c++ 40, c# 4, powershell 2.
הכללים: קוד הכלים חי ב-git; נתוני משחק לעולם לא. סקריפטים חיצוניים מועתקים ל-`tools/labs/*` עם `SOURCE.txt`.

## . (5)
- `collect_probe.py` — Collect fresh read-only telemetry from the native PS5 probe (no remote actions).
- `deploy_probe.py` — Install a NEW native probe title with SHA-256 readback; never overwrite a title.
- `probe_launch.c` — SPDX-License-Identifier: GPL-3.0-or-later
- `run_r3.py` — ZA Vulkan probe (r3, r4 with pad and audio, r5 with the memory/import/thread probes): update the installed
- `watch_r3.py` — Watch an already-running r3 probe until it exits and save its final live JSON (read-only).

## evidence (1)
- `evidence/probe-a0-r1.cpp` — SPDX-License-Identifier: GPL-3.0-or-later

## port/cheats-r27 (2)
- `port/cheats-r27/prepare-money-hooks.py` — Audit and patch five isolated 2.0.2 translated units; never edits its inputs.
- `port/cheats-r27/za_money.cpp`

## port/cheats-r28 (7)
- `port/cheats-r28/prepare-items-hooks.py` — Hash-pinned additive hooks, in fresh copies; retain all r27 money hooks.
- `port/cheats-r28/research/alpha-candidates.py` — Flatbuffers field 11 (vtable +0x1a), with a float read/comparison.
- `port/cheats-r28/research/alpha-windows.py`
- `port/cheats-r28/research/aot.py` — Read-only targeted inspection of the user's translated 2.0.2 game code.
- `port/cheats-r28/research/catalog.py` — Build the requested allowlist from local PKHeX and audit actual game data.
- `port/cheats-r28/research/pin-bag.py`
- `port/cheats-r28/za_items.c`

## port/dlc-dex-unlock (2)
- `port/dlc-dex-unlock/prepare_dlc_dex_hook.py` — Prepare the one audited 2.0.2 DLC Dex hook. Inputs are never edited.
- `port/dlc-dex-unlock/za_dlc_dex_unlock.c`

## port/dynamic-timing (5)
- `port/dynamic-timing/audit_nso.py` — Read-only audit of the 2.0.2 main NSO behind the static findings in analysis/dynamic-timing-design-HE.md.
- `port/dynamic-timing/prepare-dynamic-hooks.py` — Verify (and optionally prepare) the five translated-C hook sites of the dynamic frame timing for Z-A 2.0.2.
- `port/dynamic-timing/za_dyn_glue.c`
- `port/dynamic-timing/za_dyn_timing.c`
- `port/dynamic-timing/za_rc3_reference.c`

## port/ffmpeg-stubs (2)
- `port/ffmpeg-stubs/build-check.sh` — ffmpeg-stubs for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
- `port/ffmpeg-stubs/ffmpeg_stubs.c`

## port/immutable-spans-r22-integration (6)
- `port/immutable-spans-r22-integration/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/immutable-spans-r22-integration/build.sh` — Independent future A/B build only. No console or NAS access.
- `port/immutable-spans-r22-integration/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/immutable-spans-r22-integration/observer-r22.c`
- `port/immutable-spans-r22-integration/prepare.py` — Create an independent r22 clone from finalized r21c; never modify its inputs.
- `port/immutable-spans-r22-integration/receipt.py` — Fail-closed preservation and source/test/hash gates for independent r22.

## port/immutable-spans-r22 (1)
- `port/immutable-spans-r22/generate.py` — Create a reviewable r22 patch and exact target snippets; never edit --source.

## port/local-shader-r19 (11)
- `port/local-shader-r19/build.sh` — Incremental game build only. No network access or console actions.
- `port/local-shader-r19/compiler_adapter.c`
- `port/local-shader-r19/hardware.py` — Explicit, idle-only r19 install/launch. No implicit game close or save edits.
- `port/local-shader-r19/observer-r19.c`
- `port/local-shader-r19/package-result.py` — Package this validated local update and copy final files to the user's NAS.
- `port/local-shader-r19/prepare.py` — Prepare an isolated r19a tree; packaged source files are authoritative.
- `port/local-shader-r19/shaderc_cache.c`
- `port/local-shader-r19/shaders-r19.c` — GLSL -> SPIR-V (shaderc), descriptor layouts from the SPIR-V itself, translated NVN programs, built-in shaders
- `port/local-shader-r19/title_entry-r19.c`
- `port/local-shader-r19/verify-registration.py` — Do not accept a --gc-sections title that lost runtime registrations.
- `port/local-shader-r19/worker.c`

## port/observer-r17 (8)
- `port/observer-r17/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/observer-r17/build.sh`
- `port/observer-r17/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/observer-r17/hardware.py` — Scoped r17 hardware validation. Explicit commands; never closes another title.
- `port/observer-r17/observer.c`
- `port/observer-r17/package.py` — Package reviewed outputs only and verify versioned NAS copies.
- `port/observer-r17/prepare.py` — Patch a private copy of the validated r16 build. Never edit shared runtime.
- `port/observer-r17/title_png.c`

## port/perf-r24-hardware (5)
- `port/perf-r24-hardware/analyze_external_run.py` — Offline adapter for another operator's hardware_run.py evidence.
- `port/perf-r24-hardware/analyze_verified.py` — Fail-closed, offline analysis of r24 / r23c observer measurements.
- `port/perf-r24-hardware/hardware.py` — Pinned r24 experiments: idle-only title update, reversible config, save backup.
- `port/perf-r24-hardware/publish_review.py` — Package this thread's independent r24 review, never a console deployment.
- `port/perf-r24-hardware/sample_fixed.py` — One 20-second stationary sample on recorded r23c/r24, captures outside it.

## port/perf-r24 (15)
- `port/perf-r24/analyze_r24.py` — Offline r24-perf counters for one observer measurement; never accesses the console.
- `port/perf-r24/build-perf-r24.sh` — r24-perf: the installed r23c (randomizer PPSA91762) plus switchable performance instrumentation and options.
- `port/perf-r24/console.py` — console.py with --client r24: port/preparation-r21-hardware/console.py, unchanged, plus the r24 observer clien
- `port/perf-r24/hardware_run.py` — Scoped hardware measurements requested by HANDOFF-r24-perf-HE.md.
- `port/perf-r24/observer/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/perf-r24/observer/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/perf-r24/observer/observer-r24.c`
- `port/perf-r24/package_60_hardware.py` — Package measurements and a Hebrew JSON summary, excluding game/save contents.
- `port/perf-r24/package_hardware_results.py` — Package only measurement evidence; no game binaries, save contents or credentials.
- `port/perf-r24/repro-r23c.sh` — Reproduce the installed r23c image from the perf-r24 copy BEFORE any r24 change, to prove the recipe:
- `port/perf-r24/results_60_hardware.py` — Summarize the 60 FPS trials by recorded FPS mode, retaining every interval.
- `port/perf-r24/run_60_hardware.py` — Execute TEST-60FPS-4K-r24-HE.md using the existing scoped observer.
- `port/perf-r24/sample_slots_r24.py` — r24 copy of port/preparation-r21-hardware/sample_slots.py: r24 client, depths 8/16/32/64, identity client r24.
- `port/perf-r24/summarize_hardware.py` — Build a portable JSON record from the requested hardware measurements.
- `port/perf-r24/title_entry-r24.c`

## port/perf-r24clock (9)
- `port/perf-r24clock/analyze_r24clock.py` — Offline r24-clock counters for one observer measurement; never accesses the console.
- `port/perf-r24clock/apply-runtime-r24clock.py` — Apply r24-clock's edits to an r24-prof work copy (r24-prof's own edits are already in it).
- `port/perf-r24clock/build-perf-r24clock.sh` — r24-clock: r24-prof (port/perf-r24prof/build-perf-r24prof.sh, eboot 64acf8fa...4fb3) plus vkprof / ticks / tsc
- `port/perf-r24clock/hardware_clock.py` — Scoped hardware execution of TEST-CLOCK-r24clock-HE.md, preserving raw intervals.
- `port/perf-r24clock/hardware_stress_play.py` — Scoped NEXT-stress-and-play hardware protocol; no save writes or interaction inputs.
- `port/perf-r24clock/package_clock_results.py` — Recompute full-window clock counters and package the scoped hardware evidence.
- `port/perf-r24clock/package_stress_play.py` — Compile NEXT-stress-and-play results and verified, save-free deliverables.
- `port/perf-r24clock/title_entry-r24clock.c`
- `port/perf-r24clock/za_clock.c`

## port/perf-r24prof (9)
- `port/perf-r24prof/analyze_hardware_samples.py` — Extended offline analysis: self functions, runtime files, external callers and sampling bias.
- `port/perf-r24prof/apply-runtime-r24prof.py` — Apply r24-prof's runtime hooks to an r24-perf source tree (kernel.c, nvn/objects.c, nvn/vulkan/device.c).
- `port/perf-r24prof/build-perf-r24prof.sh` — r24-prof: r24-perf (port/perf-r24/build-perf-r24.sh, eboot a7890eca...6a5610) plus scale / force60 / a samplin
- `port/perf-r24prof/hardware_profile.py` — Scoped execution of TEST-PROFILE-r24prof-HE.md; PIE stays on the host.
- `port/perf-r24prof/package_profile_results.py` — Finalize measurement counters and package r24-prof evidence without executable/game/save files.
- `port/perf-r24prof/run_reference_symbolizer.py` — Run the provided symbolizer for each measurement on the verified stable-scene files.
- `port/perf-r24prof/symbolize_samples.py` — Symbolize r24-prof sample files (za_prof.c / za_prof_core.h layout) against the EXACT PIE of the build.
- `port/perf-r24prof/title_entry-r24prof.c`
- `port/perf-r24prof/za_prof.c`

## port/perf-r25 (7)
- `port/perf-r25/analyze_r25.py` — Offline r25 counters for one observer measurement; never accesses the console.
- `port/perf-r25/apply-runtime-r25.py` — Apply r25's edits to an r24-clock work copy (r24-prof's and r24-clock's own edits are already in it).
- `port/perf-r25/build-perf-r25.sh` — r25-perf: r24-clock (port/perf-r24clock/build-perf-r24clock.sh, eboot 35ee54da...573e) plus submit=thread (a s
- `port/perf-r25/hardware_r25.py` — Scoped r25 hardware runner. Only PPSA91762; raw evidence and exact restoration.
- `port/perf-r25/package_hardware_r25.py` — Offline, save-free r25 evidence report and verified NAS delivery.
- `port/perf-r25/title_entry-r25.c`
- `port/perf-r25/za_clock_r25.c`

## port/perf-r26 (12)
- `port/perf-r26/analyze_r26.py` — Offline r26 counters for one observer measurement; never accesses the console.
- `port/perf-r26/apply-runtime-r26.py` — Apply r26's one runtime edit to an r25 work copy (r24-prof's, r24-clock's and r25's edits are already in it).
- `port/perf-r26/build-perf-r26.sh` — r26-perf: r25-perf (port/perf-r25/build-perf-r25.sh, eboot 804205b7...b2d6) plus the dynamic frame timing
- `port/perf-r26/build-perf-r26p.sh` — r26p-play: r26-perf (port/perf-r26/build-perf-r26.sh, eboot 1685430c...d88c) with the overlay's live FPS count
- `port/perf-r26/build-perf-r26p1.sh` — Restore the missing FPS TRIAL row. Only cheats.o changes from the verified r26p image.
- `port/perf-r26/cheats-r26.cpp` — r26p: port/randomizer/cheats.cpp (the L3+R3 overlay: SHINY / CAPTURE / RESET) plus
- `port/perf-r26/install_r26p.py` — Transactional PPSA91762 r26p install. Never writes game saves or PPSA91761.
- `port/perf-r26/install_r26p1.py` — Restore the missing FPS TRIAL control, updating only PPSA91762/eboot.bin while idle.
- `port/perf-r26/package_r26p1.py` — Package only the binary update, requested-use guide, verification and explicit source changes.
- `port/perf-r26/title_entry-r26.c`
- `port/perf-r26/title_entry-r26p.c`
- `port/perf-r26/za_dyn_glue_r26.c`

## port/perf-r27 (9)
- `port/perf-r27/build-r27-play.sh` — r27-play = exact r26p1 runtime/options + trainer name + PC-proven MONEY hooks.
- `port/perf-r27/build-r27b-play.sh` — r27b fixes the launcher's missing r17 observer integration. No console access.
- `port/perf-r27/cheats-r27.cpp` — r27: r26p1 L3+R3 overlay, preserving SHINY / CAPTURE / FPS COUNTER / FPS TRIAL / RESET.
- `port/perf-r27/install_r27.py` — Install the validated r27 package over r26p1, changing only PPSA91762/eboot.bin.
- `port/perf-r27/prepare-delivery.py` — Versioned r27 update/source/evidence delivery; excludes game assets and saves.
- `port/perf-r27/prepare-r27b-delivery.py` — Package a completed r27b installation; never contacts the console or reads saves.
- `port/perf-r27/remove-old-probe.py` — Remove only the obsolete ZA Native Probe A0, with verified off-console backup.
- `port/perf-r27/verify-r27-build.py` — Fail-closed structural checks and source-bound PC-proof gate for build-r27-play.sh.
- `port/perf-r27/verify-r27b-build.py` — r27b: retain the pinned r27 verifier and require an isolated two-object fix.

## port/perf-r28 (8)
- `port/perf-r28/build-r28-play.sh`
- `port/perf-r28/deliver-r28.py` — Assemble verified offline binaries, user instructions and authored sources.
- `port/perf-r28/final-audit.py`
- `port/perf-r28/install-r28.py` — Scoped r28 installer over the exact r27b Hebrew-trial baseline.
- `port/perf-r28/observe-installed.py` — Read-only completion evidence when play changes the run during installation.
- `port/perf-r28/prepare-menu.py` — Retain the installed Hebrew-trial overlay; add a second cheat page.
- `port/perf-r28/src/cheats-r28.cpp` — r27: r26p1 L3+R3 overlay, preserving SHINY / CAPTURE / FPS COUNTER / FPS TRIAL / RESET.
- `port/perf-r28/verify-r28.py`

## port/performance-r16 (5)
- `port/performance-r16/apply.py` — Build guarded r16 experiments in an isolated snapshot, never in r15.
- `port/performance-r16/package.py` — Package the verified local candidate and copy final deliverables to the NAS.
- `port/performance-r16/performance.c`
- `port/performance-r16/prepare.sh`
- `port/performance-r16/relink.sh`

## port/preparation-r21-hardware (20)
- `port/preparation-r21-hardware/analyze_slots.py` — Offline r23 slot-depth phase/CSV/profiler validation; never accesses console.
- `port/preparation-r21-hardware/analyze_spans.py` — Offline r22 phase/CSV/log analyzer. No console or network access.
- `port/preparation-r21-hardware/analyze_suite.py` — Offline r21 same-binary comparison evidence; never accesses the console.
- `port/preparation-r21-hardware/cleanup_captures.py` — Retire only locally preserved, exact-hash-matching observer PNG captures.
- `port/preparation-r21-hardware/cleanup_captures_c.py` — Retire only locally preserved, exact-hash-matching observer PNG captures.
- `port/preparation-r21-hardware/console.py` — Scoped r21 console checks/input; never operates on an unidentified title.
- `port/preparation-r21-hardware/deploy.py` — Idle-only r21 deployment; preserve all installed settings including batch4.
- `port/preparation-r21-hardware/deploy_b.py` — Idle-only r21b observer-maintenance update; rendering runtime remains r21.
- `port/preparation-r21-hardware/deploy_c.py` — Idle-only r21c native filesystem adapter; rendering runtime remains r21.
- `port/preparation-r21-hardware/deploy_r22.py` — Idle-only r22 immutable span experiment; restore exact r21c if needed.
- `port/preparation-r21-hardware/deploy_r23.py` — Idle-only r23 slot-depth experiment; restore exact r22 if needed.
- `port/preparation-r21-hardware/deploy_r23b.py` — Idle-only r23b deployment with explicit gated startup16 configuration.
- `port/preparation-r21-hardware/deploy_r23c.py` — Use the reviewed idle-only startup-config transport for the native read fix.
- `port/preparation-r21-hardware/package_result.py` — Prepare/validate a scoped performance release; only --publish writes ZIPs/NAS.
- `port/preparation-r21-hardware/retire_navigation.py` — Free current test-session navigation captures; exact local/remote hash gate.
- `port/preparation-r21-hardware/sample.py` — One scoped live-profile sample: capture outside a 20s recorder window.
- `port/preparation-r21-hardware/sample_b.py` — One scoped live-profile sample: capture outside a 20s recorder window.
- `port/preparation-r21-hardware/sample_c.py` — One scoped live-profile sample: capture outside a 20s recorder window.
- `port/preparation-r21-hardware/sample_slots.py` — One scoped live-profile sample: capture outside a 20s recorder window.
- `port/preparation-r21-hardware/sample_spans.py` — One scoped live-profile sample: capture outside a 20s recorder window.

## port/preparation-r21-observer (3)
- `port/preparation-r21-observer/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/preparation-r21-observer/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/preparation-r21-observer/observer-r21.c`

## port/preparation-r21 (4)
- `port/preparation-r21/audit.py` — Read-only source/object preservation audit of the isolated candidate.
- `port/preparation-r21/build.sh` — Isolated incremental runtime build. No game-code generation or console access.
- `port/preparation-r21/prepare.py` — Reproducible isolated r21 preparation; never edits the installed r20b snapshot.
- `port/preparation-r21/receipt.py` — Gate ready.json on tests, preservation and final artifact identity. No network.

## port/preparation-r21b (6)
- `port/preparation-r21b/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/preparation-r21b/build.sh` — Isolated incremental runtime build. No game-code generation or console access.
- `port/preparation-r21b/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/preparation-r21b/observer-r21b.c`
- `port/preparation-r21b/prepare.py` — Copy the ready r21 snapshot; runtime sources and objects stay byte identical.
- `port/preparation-r21b/receipt.py` — Preservation/import/test/packaging gate for observer-only r21b.

## port/preparation-r21c (6)
- `port/preparation-r21c/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/preparation-r21c/build.sh` — Isolated incremental runtime build. No game-code generation or console access.
- `port/preparation-r21c/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/preparation-r21c/observer-r21c.c`
- `port/preparation-r21c/prepare.py` — Copy the ready r21 snapshot; runtime sources and objects stay byte identical.
- `port/preparation-r21c/receipt.py` — Preservation/import/test/packaging gate for observer-only r21c.

## port/r28b-dlc-dex (14)
- `port/r28b-dlc-dex/audit-base.sh`
- `port/r28b-dlc-dex/build-feature.sh` — Add the early DLC dex flag hook to a copied and byte-identically relinked r28a tree.
- `port/r28b-dlc-dex/build-music-variant.sh` — Reuse the five pinned r29 music objects only after proving their three base
- `port/r28b-dlc-dex/check-merge-kit.sh`
- `port/r28b-dlc-dex/check-space-and-title.sh`
- `port/r28b-dlc-dex/delivery/create_delivery.py` — Package the two pinned, offline-tested PS5 candidates. Never contacts hardware.
- `port/r28b-dlc-dex/final-audit.sh`
- `port/r28b-dlc-dex/finish-image.sh`
- `port/r28b-dlc-dex/install-r28b.py` — Scoped r28b full-image installation, backed by the shared console queue.
- `port/r28b-dlc-dex/prepare-control.sh`
- `port/r28b-dlc-dex/prepare-merge-tree.py` — Copy all explicit linked inputs of a pinned existing build into a fresh merge tree.
- `port/r28b-dlc-dex/prepare-merge.sh` — Usage: prepare-merge.sh --runtime-tree TREE --base-out OUT --archive FILE --work NEW_TREE
- `port/r28b-dlc-dex/summarize-build.py` — Write compact evidence manifests for the two completed offline build variants.
- `port/r28b-dlc-dex/verify-feature-image.py` — Verify linked early-DLC-Dex hook and preserve the supplied base's globals/imports.

## port/rando-dexcount (5)
- `port/rando-dexcount/prepare-dexcount-hooks.py` — Audit and patch TWO translated 2.0.2 units for rando-dexcount; never edits its inputs.
- `port/rando-dexcount/ps5/apply-r28a.sh` — rando-dexcount for r28a: prepare the PS5 objects to layer on the r28-play work tree. Builds NO package.
- `port/rando-dexcount/ps5/compare_ar.py` — Compare two System V/GNU ar archives member by member (name order and SHA-256 of every member).
- `port/rando-dexcount/research/find-dex-missions.py` — Read-only inventory of every Pokedex-count condition in Z-A 2.0.2 (+DLC) and of the two Pokedex lists.
- `port/rando-dexcount/za_dexcount.c`

## port/rando-dexopen (12)
- `port/rando-dexopen/build-r28b.sh` — r28b-play = r28a-play FINAL (eboot 5c6777ec...) + rando-dexopen (ps5/apply-r28b.sh: main_287.o and main_115.o 
- `port/rando-dexopen/deliver-r28b.py` — Assemble artifacts/randomizer-r28b-play from a finished r28b build.
- `port/rando-dexopen/make-build-info.py` — BUILD-INFO.json for r28b-play, from the build's evidence (no guessing: every number is read from a file).
- `port/rando-dexopen/prepare-dexopen-hooks.py` — Audit and patch TWO translated 2.0.2 units for rando-dexopen; never edits its inputs.
- `port/rando-dexopen/ps5/apply-r28b.sh` — rando-dexopen for r28b: prepare the PS5 objects to layer on the r28a-play FINAL tree. Builds NO package.
- `port/rando-dexopen/ps5/compare_ar.py` — Compare two System V/GNU ar archives member by member (name order and SHA-256 of every member).
- `port/rando-dexopen/research/dlc_conditions.py` — Derived facts: every *_condition entry of the two data files that mention FLAG_DLC_DEX_ENABLE, with the enclos
- `port/rando-dexopen/research/dlc_setters.py` — Derived facts: in the DLC event table that mentions FLAG_DLC_DEX_ENABLE, print every flatbuffer table whose st
- `port/rando-dexopen/research/hit_context.py` — Derived facts about the two data files that mention FLAG_DLC_DEX_ENABLE: their game paths (if a candidate path
- `port/rando-dexopen/research/scan_flag_refs.py` — Data-side check for rando-dexopen (informational): which game DATA tables mention FLAG_DLC_DEX_ENABLE, by name
- `port/rando-dexopen/verify-r28b.py` — r28b-play checks against r28a-play's final tree (build-r28b.sh calls each mode at its step).
- `port/rando-dexopen/za_dexopen.c`

## port/rando-music (30)
- `port/rando-music/build-r29-music.sh` — r29-music: the MUSIC row (new-run music shuffle) on top of an existing verified build. No console access.
- `port/rando-music/host/build-host-cli.sh` — Build the r29-music host CLI (same sources as the title's generation path) with ASan/UBSan.
- `port/rando-music/host/za_music_host.cpp` — Host CLI: create a COMPLETE randomizer run folder exactly as the r29-music title's New Run does (same core,
- `port/rando-music/native_menu_music.cpp`
- `port/rando-music/pc/analyze_proof.py` — Summarise the r29-music PC proof runs (read-only on game data; writes one JSON summary).
- `port/rando-music/pc/audio_level.py` — RMS level of a run's raw audout capture (LARECOMP_AUDOUT_WAV: s16 stereo 48 kHz, no header) per window.
- `port/rando-music/pc/make_pc_proof.py` — pc-proof.json for r29-music from the four final PC runs plus static checks of each run's actual music bank.
- `port/rando-music/pc/run_music_pc.py` — One bounded PC run of Pokemon Legends Z-A for the music-randomizer proof (no console, no real save).
- `port/rando-music/prepare-r29-delivery.py` — Assemble an r29-music package from a verified WSL build, the host tests and the PC proof.
- `port/rando-music/research/akpk.py` — Read-only Wwise file package (AKPK, Stream.pck) index: media id -> (offset, size). Reads only the header.
- `port/rando-music/research/bgm_events.py` — Read-only: list BGM.bnk events (named via bgm_command strings) with their actions.
- `port/rando-music/research/bgm_switches.py` — Read-only: dump BGM.bnk music switch containers (decision trees) and which events Play them.
- `port/rando-music/research/bnk_overview.py` — Read-only: overview of a Wwise bank's sections and HIRC object types; match event names from bgm_command strin
- `port/rando-music/research/candidates.py` — Read-only: list candidate songs (switch leaves -> non-silent, infinitely looping playlists) with switch and fo
- `port/rando-music/research/dump_files.py` — Read-only: copy named Z-A game files (RomFS or packed) into a private, git-ignored output directory for analys
- `port/rando-music/research/exp_retarget.py` — Experiment (writes only a COPY into music-lab): retarget every non-silent leaf of the given music switches to 
- `port/rando-music/research/label_paths.py` — Read-only: print a music switch's decision-tree leaves with state keys labelled by the SET_STATE events that s
- `port/rando-music/research/list_audio.py` — Read-only: list Z-A RomFS audio files and pack/file names that look music-related. Prints to stdout only.
- `port/rando-music/research/music_graph.py` — Read-only BGM.bnk music graph: events -> containers -> playlists -> segments -> tracks -> media.
- `port/rando-music/research/stream_reads.py` — Read-only: which streamed media a PC run read (LARECOMP_LOG_READS), mapped to BGM.bnk songs (playlists).
- `port/rando-music/research/strs.py`
- `port/rando-music/research/validate_music.py` — Read-only: parse every music object in a v145 bank with wwise_music and report failures (layout self-check).
- `port/rando-music/research/wwise_music.py` — Read-only forward parser for Wwise v145 music objects (segment/track/switch/playlist) in memory.
- `port/rando-music/research/wwise_v145.py` — Read-only Wwise v145 (2022.1) bank helpers for BGM research. Parses sections, HIRC objects, events, actions,
- `port/rando-music/run_store_music.cpp` — r29-music copy of port/randomizer/run_store.cpp (SHA-256 3912a1e973a1e43d2050a0c184605b1eb9a834ca2ae5235b708d8
- `port/rando-music/tools/embed_plan.py` — Generate za_music_plan.cpp (the plan text as a byte array plus its SHA-256) for the title build.
- `port/rando-music/tools/make_music_plan.py` — Build the music-shuffle plan for Pokemon Legends: Z-A 2.0.2 from the game's own data (read-only).
- `port/rando-music/tools/za_bgm.py` — Wwise v145 (2022.1) sound bank reader for Pokemon Legends: Z-A 2.0.2 BGM.bnk. Read-only, in memory.
- `port/rando-music/verify-r29.py` — r29-music build checks (no console access).
- `port/rando-music/za_music.cpp`

## port/rando-v2 (10)
- `port/rando-v2/build-check-ps5.sh` — Cross-compiles the rando-v2 sources for the PS5 title exactly as port/randomizer/build-randomizer.sh compiles 
- `port/rando-v2/name_keyboard.cpp` — Same bit values as menu_display.hpp (kept local so the keyboard builds without the display code).
- `port/rando-v2/native_menu.cpp`
- `port/rando-v2/research/aot_xref.py` — Cross-references in the translated 2.0.2 game code (read-only).
- `port/rando-v2/research/scan_block_keys.py` — Find where the translated 2.0.2 game code builds PKHeX save-block keys (MOVZ lo16 + MOVK hi16, or one 32-bit
- `port/rando-v2/research/scan_demo_refs.py` — Read-only (py -3 scan_demo_refs.py OUT.json): which table identifiers (NPC Pokemon records, boss encounters, s
- `port/rando-v2/research/scan_demo_species.py` — Read-only (py -3 scan_demo_species.py OUT.json): unpack every file of the cutscene (demo) packs of the 2.0.2 r
- `port/rando-v2/run_name.cpp`
- `port/rando-v2/verify/Program.cs` — Offline verification for the randomizer player-name writer (port/rando-v2/za_player_name.cpp).
- `port/rando-v2/za_player_name.cpp` — ---- SwishCrypto (PKHeX Saves/Encryption/SwishCrypto/SwishCrypto.cs)

## port/rando-v3 (6)
- `port/rando-v3/core/randomizer.cpp`
- `port/rando-v3/src/legacy_progression.cpp`
- `port/rando-v3/src/legacy_research_rewards.cpp`
- `port/rando-v3/src/rando_v3.cpp`
- `port/rando-v3/tools/build-host.sh` — rando-v3 host build + tests (WSL, clang-21, ASan/UBSan). No console, no game data in git.
- `port/rando-v3/tools/prepare-v3-assets.py` — Build the rando-v3 asset set from the existing prepared randomizer assets plus raw game tables.

## port/randomizer (36)
- `port/randomizer/apply-gwin-guard.py` — Bound XFB copies to the imported allocation, including an import at offset 0.
- `port/randomizer/audit-field-moves.py` — Read-only discovery of field-move obstacle rules in the pinned 2.0.2 data.
- `port/randomizer/audit-randomization-expansion.py` — Inventory potential extensions without modifying any game data.
- `port/randomizer/build-cheat-hooks.sh`
- `port/randomizer/build-copy-payload.sh`
- `port/randomizer/build-launcher.sh`
- `port/randomizer/build-randomizer.sh`
- `port/randomizer/cheats.cpp`
- `port/randomizer/copy_game_payload.c`
- `port/randomizer/core/randomizer.cpp`
- `port/randomizer/deploy-randomizer.py` — Stage and, separately, publish NEW PPSA91762. Never replaces PPSA91761.
- `port/randomizer/import_repair.cpp`
- `port/randomizer/inspect-rewards.py` — Read-only reward-table discovery in the user's pinned local 2.0.2 game.
- `port/randomizer/inspect-story-links.py` — Read-only current-build boss/event/cinematic inventory. Does not patch ROMFS.
- `port/randomizer/menu_display.cpp` — VideoOut tiling/presentation follows PS5_Vulkan's GPL-3.0-or-later demo_renderer.cpp.
- `port/randomizer/native_menu.cpp`
- `port/randomizer/package-deliverables.py` — Versioned randomizer overlay and curated source/evidence; no full game assets.
- `port/randomizer/plan-logic-providers.py` — Read-only feasibility of small, seeded progression-provider teams.
- `port/randomizer/prepare-assets.py`
- `port/randomizer/prepare-cheat-hooks.py` — Two isolated translated units; baseline game archive and generated C untouched.
- `port/randomizer/prepare-progression.py` — Audit all TMs; prepare targeted, seeded early-rock routes and authored moves.
- `port/randomizer/prepare-research-rewards.py` — Prepare a pinned, bounded research-reward table; does not modify a console.
- `port/randomizer/progression.cpp`
- `port/randomizer/refresh-release-shaders.py` — Add this title's verified helper outputs to a local release, never to the console.
- `port/randomizer/repair-existing-run.py` — Repair the r11 wild table by publishing a NEW run, retaining the entire old run.
- `port/randomizer/research_rewards.cpp`
- `port/randomizer/rock-route-oracle.py` — Independent seeded route oracle and raw-game capability checks.
- `port/randomizer/run_oracle.py` — Read-only replay of the targeted wild-table postprocessor.
- `port/randomizer/run_store.cpp`
- `port/randomizer/snapshot-prior-runs.py` — Read-only integrity check and save backup for the two pre-r8 test runs.
- `port/randomizer/stage-reward-assets.py` — Stage two pinned reward assets for the owned title while no game is running.
- `port/randomizer/summarize-progression.py` — Inspect exact ZA 2.0.2 moves and spawn data without changing the game.
- `port/randomizer/update-assets.py` — Versioned asset update for PPSA91762 only, while no title is running.
- `port/randomizer/verify-console-run.py` — Read-only evidence for this title's active run; compare PS5 tables with host core.
- `port/randomizer/verify-progression.py` — Validate every allowed replacement against raw personal tables, then outputs.
- `port/randomizer/verify-research-rewards.py` — Independent Python oracle and binary-offset invariant checks for C++ outputs.

## port/runtime-texfix (11)
- `port/runtime-texfix/apply-runtime-texfix.py` — r28a texfix: apply the texture-lifetime fix to a runtime tree (a copy - never a reference tree).
- `port/runtime-texfix/build-r28a-candidate.sh` — r28a-play (texfix CANDIDATE) = r28-play (eboot 65f6745f...) + the texture-lifetime fix (port/runtime-texfix) i
- `port/runtime-texfix/build-r28a-final.sh` — r28a-play FINAL = the r28a texfix candidate (build-r28a-candidate.sh: r28-play + the texture-lifetime fix in f
- `port/runtime-texfix/collect-candidate-evidence.sh` — Copies a texfix build's small evidence files (no binaries) from its WSL work tree into the repository's eviden
- `port/runtime-texfix/collect-final-evidence.sh` — Copies the FINAL r28a build's small evidence files (no binaries) from its WSL work tree into evidence/r28a-tex
- `port/runtime-texfix/deliver-r28a.py` — Assemble artifacts/randomizer-r28a-play from a finished r28a build (FINAL step - after the dexcount layer).
- `port/runtime-texfix/make-build-info.py` — BUILD-INFO.json for r28a-play, from the final build's evidence (no guessing: every number is read from a file)
- `port/runtime-texfix/pc/build-pc-texfix.sh` — PC runtime (lasrecomp.exe) with the texfix - for a scripted PC session only, never shipped. MSYS2 UCRT64 shell
- `port/runtime-texfix/pc/run_pc_texfix.py` — One bounded scripted PC session for the r28a texfix (hebrew-lab/tools/run_poc.py's pattern, another runtime co
- `port/runtime-texfix/pc/session_inputs.py` — The scripted PC sessions for the r28a texfix: many scene transitions, as LARECOMP_INPUT and capture frames.
- `port/runtime-texfix/verify-r28a.py` — r28a-play (texfix candidate) checks against r28-play.

## port/shader-prewarm (24)
- `port/shader-prewarm/audit_generate_extra.py` — Exact runtime helper and control-defined XFB source generation (no game execution).
- `port/shader-prewarm/audit_inventory.py` — Independent inventory reconciliation; read-only inputs, audit-prefixed outputs.
- `port/shader-prewarm/audit_raw_sph.py` — Read-only raw NVN shader-header scan outside recognized BNSH byte ranges.
- `port/shader-prewarm/audit_report.py` — Finalize independent, bounded shader-coverage audit from saved evidence.
- `port/shader-prewarm/build-offline.sh`
- `port/shader-prewarm/build-research.sh` — Does not clone automatically, mutate the installed runtime, or contact PS5.
- `port/shader-prewarm/compile_all.py` — Bounded four-worker offline GLSL compile/validation, resumable by content hash.
- `port/shader-prewarm/compiler.c`
- `port/shader-prewarm/compiler_probe.c`
- `port/shader-prewarm/compiler_worker.c`
- `port/shader-prewarm/extract_bnsh.py` — Read-only scan of local 2.0.2 RomFS for validated BNSH containers.
- `port/shader-prewarm/extract_exefs.py` — Read-only scan of decompressed NSOs for embedded BNSH archives.
- `port/shader-prewarm/finalize_offline_delivery.py` — Finalize the user report from measured compile/install receipts, then hash files.
- `port/shader-prewarm/forecast.py` — Read-only encounter forecast for shader-prewarm research; never writes game data.
- `port/shader-prewarm/inspect_assets.py` — Bounded, read-only model/shader catalogue audit. Names are candidates, not proven bindings.
- `port/shader-prewarm/install_offline_cache.py` — Validate a ZA r15 shader pack; --install adds absent files over local PS5 FTP.
- `port/shader-prewarm/link-check.sh` — Research-only link check. No package signing, deployment or console commands.
- `port/shader-prewarm/merge_audit_sources.py` — Merge independently audited exact source variants into the offline compile queue.
- `port/shader-prewarm/package_offline_cache.py` — Package only validated absent SPIR-V keys and our reproducible tooling.
- `port/shader-prewarm/package_research.py` — Package only final research source/metadata; no SDK, game content or build cache.
- `port/shader-prewarm/parse_bnsh.py` — Bounded BNSH 2.4 binary-program extraction; no executable guest code runs.
- `port/shader-prewarm/translate_all.py` — WSL offline translation with the installed runtime's exact Maxwell translator.
- `port/shader-prewarm/translate_bridge.c`
- `port/shader-prewarm/verify_offline_tools.py` — WSL checks: malformed BNSH rejection and persistent compiler recovery/parity.

## port/shader-probe-r18 (5)
- `port/shader-probe-r18/analyze.py` — Offline verification of the bounded PS5 compiler test; run under WSL.
- `port/shader-probe-r18/build.sh`
- `port/shader-probe-r18/hardware.py` — Bounded compiler test in PPSA91760. Closes only its nonce/PID-verified probe.
- `port/shader-probe-r18/probe.c`
- `port/shader-probe-r18/verify-image.py` — Verify constructor, constant and code bytes survive native title conversion.

## port/shaderc-cache (3)
- `port/shaderc-cache/build-check.sh` — shaderc-cache for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
- `port/shaderc-cache/shaderc_cache.c`
- `port/shaderc-cache/tools/compile-missing.sh` — shaderc-cache: compile the GLSL files a console run left in its missing-shader directory into cache/spirv/<has

## port/slot-depth-r23-observer (4)
- `port/slot-depth-r23-observer/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/slot-depth-r23-observer/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/slot-depth-r23-observer/extend.py` — Reproduce only the separate r23 observer/client from finalized r22 sources.
- `port/slot-depth-r23-observer/observer-r23.c`

## port/slot-depth-r23 (3)
- `port/slot-depth-r23/build.sh` — Independent future A/B build only. No console or NAS access.
- `port/slot-depth-r23/prepare.py` — Isolated r23 clone and exact-anchor patch of finalized r22; no console I/O.
- `port/slot-depth-r23/receipt.py` — Pin the r23 build, exact runtime preservation, tests and observer contract.

## port/slot-depth-r23b-observer (3)
- `port/slot-depth-r23b-observer/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/slot-depth-r23b-observer/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/slot-depth-r23b-observer/observer-r23b.c`

## port/slot-depth-r23b (3)
- `port/slot-depth-r23b/build.sh` — Observer-only persisted startup request. No console or NAS access.
- `port/slot-depth-r23b/prepare.py` — Prepare an isolated observer-only r23b snapshot; never modify r23.
- `port/slot-depth-r23b/receipt.py` — Pin observer-only startup option, unchanged runtime and reviewed driver.

## port/slot-depth-r23c-observer (3)
- `port/slot-depth-r23c-observer/analyze.py` — Analyze render-thread present submission intervals, not GPU scanout FPS.
- `port/slot-depth-r23c-observer/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/slot-depth-r23c-observer/observer-r23c.c`

## port/slot-depth-r23c (3)
- `port/slot-depth-r23c/build.sh` — Observer-only persisted startup request. No console or NAS access.
- `port/slot-depth-r23c/prepare.py` — Prepare an isolated observer-only r23c snapshot; never modify r23.
- `port/slot-depth-r23c/receipt.py` — Pin observer-only startup option, unchanged runtime and reviewed driver.

## port/submission-r20-hardware (2)
- `port/submission-r20-hardware/hardware.py` — Parent-owned r20 deployment. Explicit idle-only changes; never kills a title.
- `port/submission-r20-hardware/package.py` — Versioned r20 candidate delivery and SHA-256-verified NAS copy.

## port/submission-r20 (3)
- `port/submission-r20/audit.py` — Read-only source/object preservation audit of the isolated candidate.
- `port/submission-r20/build.sh` — Isolated incremental runtime build. No game-code generation or console access.
- `port/submission-r20/prepare.py` — Create r20 in a new WSL tree. Baseline and generated game archive are inputs.

## port/submission-r20b-hardware (6)
- `port/submission-r20b-hardware/analyze_windows.py` — Normalize complete 2s game-profiler windows inside an observer CSV.
- `port/submission-r20b-hardware/finish.py` — Finish the known r20b session without restarting or writing any save.
- `port/submission-r20b-hardware/hardware.py` — Parent-owned r20b deployment using the audited idle-only r20 transport.
- `port/submission-r20b-hardware/package.py` — Create a versioned r20b candidate/result bundle and verify its NAS copy.
- `port/submission-r20b-hardware/sample.py` — One scoped live-profile sample: capture outside a 20s recorder window.
- `port/submission-r20b-hardware/summarize.py` — Summarize the completed matched-scene r20b experiment from saved evidence.

## port/submission-r20b (8)
- `port/submission-r20b/audit.py` — Read-only source/object preservation audit of the isolated candidate.
- `port/submission-r20b/build.sh` — Isolated incremental runtime build. No game-code generation or console access.
- `port/submission-r20b/client.py` — Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
- `port/submission-r20b/finish-tools.py` — Create private r20b audit/client from pinned project tools; no console access.
- `port/submission-r20b/generate.py` — Generate private r20b sources; never edit the r20/r19 inputs.
- `port/submission-r20b/observer-r20b.c`
- `port/submission-r20b/prepare.py` — Prepare private r20b from r20 without changing r20 or generated game data.
- `port/submission-r20b/receipt.py` — Finish build evidence locally; no console or network operations.

## port/title (43)
- `port/title/apply-hardware-r14.py` — Persist PS5 pipeline caches during play; leave the upstream checkout alone.
- `port/title/apply-hardware-r3.py` — Patch only the isolated build snapshot; preserve pre-r3 sources.
- `port/title/build-hardware-r10.sh`
- `port/title/build-hardware-r11.sh`
- `port/title/build-hardware-r12.sh`
- `port/title/build-hardware-r13.sh`
- `port/title/build-hardware-r14.sh`
- `port/title/build-hardware-r2.sh` — Preserve the original snapshot file; the published r1 package stays intact.
- `port/title/build-hardware-r3.sh`
- `port/title/build-hardware-r4.sh`
- `port/title/build-hardware-r5.sh`
- `port/title/build-hardware-r6.sh`
- `port/title/build-hardware-r7.sh`
- `port/title/build-hardware-r8.sh` — 793116 nonzero bytes out of 846624). Clear through a temporary mapping
- `port/title/build-hardware-r9.sh`
- `port/title/build-rename.sh`
- `port/title/build-runtime.sh`
- `port/title/collect-pc-shaders.py` — Inventory existing PC SPIR-V, retaining conflicting keys for review.
- `port/title/copy-to-nas.ps1`
- `port/title/deploy-title-r2.py` — Stage a NEW PPSA91761 title, stream SHA-256 verification, publish last.
- `port/title/finalize-build.py` — Save reproducible source bundle and evidence for the completed offline build.
- `port/title/launch_title.c` — SPDX-License-Identifier: GPL-3.0-or-later
- `port/title/monitor-title.py` — Read-only, bounded performance capture of an already running PPSA91761.
- `port/title/package-hardware-update.py` — Versioned source/evidence handoff; excludes game assets, binaries and SDKs.
- `port/title/package-r14-deliverables.py` — Package the installed r14 overlay and explicit backups into a handoff folder.
- `port/title/package-title.sh` — Convert/sign the full native image; package only after an error-free link.
- `port/title/performance.c`
- `port/title/prepare-build.sh` — Isolated, offline title build. Does not access or deploy to the PS5.
- `port/title/prepare-fps-hook.py` — Verify 2.0.2 and patch one isolated translated unit. Original AOT stays intact.
- `port/title/rename_title.c`
- `port/title/run-title.py` — Launch only the new native title; capture startup klog and sandbox evidence.
- `port/title/shader-compiler-worker.py` — Persistent WSL compiler for this task's bounded, content-addressed shaders.
- `port/title/shader-host.py` — Bounded developer helper for PPSA91761 only. Compile dumped GLSL, validate,
- `port/title/stage-branding.py` — Back up and update only this title's known metadata and optional FPS profile.
- `port/title/stage-city-save.py` — Stage the pinned 2.0.2 city Tepig save; the title imports it before guest boot.
- `port/title/stage-game.py` — Stage the already selected local 2.0.2 game; reject changed inputs.
- `port/title/stage-pc-shaders.py` — Add validated, absent SPIR-V keys. Never overwrite an existing console key.
- `port/title/stage-shaders.py` — Merge only matching 2.0.2 runs' portable SPIR-V, never GPU pipeline caches.
- `port/title/title_entry.c`
- `port/title/title_fs.c`
- `port/title/update-title.py` — Replace only the verified PPSA91761 executable while no title is running.
- `port/title/validate-pc-shaders.py` — Run in WSL: validate each unambiguous portable PC cache candidate.
- `port/title/verify-image.py` — Check that conversion retains runtime registration and initialization data.

## port/ui-v2 (26)
- `port/ui-v2/pc/build-pc-runtime.sh` — build-pc-runtime.sh - the Windows ZA Recomp runtime as lasrecomp-uiv2.exe WITHOUT the Dear ImGui UI, built wit
- `port/ui-v2/pc/pc_entry_stub.c` — pc_entry_stub.c - the symbols the no-UI Windows runtime build (pc-runtime.mk) needs from "the UI", as no-ops.
- `port/ui-v2/pc/pc_guest_calls.c` — pc_guest_calls.c - port/cheats-r28/za_items.c calls five recompiled game functions by name (f_<guest address>)
- `port/ui-v2/pc/relink-game-dll.sh` — relink-game-dll.sh - lasgame-uiv2.dll: the reference PC game code (the 2.0.2 AOT objects) with the r28 hook un
- `port/ui-v2/pc/run-pc-game.py` — run-pc-game.py - a bounded, scripted PC run of lasrecomp-uiv2.exe against an isolated data root with a fresh C
- `port/ui-v2/src/fonts_embedded.cpp`
- `port/ui-v2/src/items_picker.cpp`
- `port/ui-v2/src/launcher_core.cpp`
- `port/ui-v2/src/launcher_ps5.cpp` — ui-v2: launcher_run() - the randomizer launcher INSIDE the game's Vulkan window (the design's option C).
- `port/ui-v2/src/legacy_look.cpp`
- `port/ui-v2/src/mockups_main.cpp` — ui-v2 mockups: every PNG in port/ui-v2/mockups is rendered by the real rasterizer (ui_canvas), the real menu m
- `port/ui-v2/src/overlay_ps5.cpp` — ui-v2: the in-game L3+R3 overlay, replacing port/perf-r28/src/cheats-r28.cpp (the title's cheats.o).
- `port/ui-v2/src/png_write.cpp`
- `port/ui-v2/src/ui_canvas.cpp`
- `port/ui-v2/src/ui_launcher.cpp`
- `port/ui-v2/src/ui_model.cpp` — --------------------------------------------------------------------------------------------- the pages (data)
- `port/ui-v2/src/ui_overlay.cpp`
- `port/ui-v2/src/ui_pad.cpp`
- `port/ui-v2/src/ui_platform.cpp`
- `port/ui-v2/src/ui_quad.c`
- `port/ui-v2/src/ui_widgets.cpp`
- `port/ui-v2/tools/build-host.sh` — ui-v2 host build: the rasterizer, model, screens and legacy-look renderers with the same language constraints 
- `port/ui-v2/tools/compile-runtime-object.sh` — r29-ui: compile ONE runtime translation unit of a prepared merge tree with the command that reproduces the pin
- `port/ui-v2/tools/embed-font.py` — Embed the two Noto Sans subsets (fonts/*.ttf, OFL 1.1) as C arrays for the title: src/fonts_embedded.inc.
- `port/ui-v2/tools/gen-capabilities.py` — Generate src/capabilities_generated.inc from the generator's capabilities file (port/rando-v3/capabilities.jso
- `port/ui-v2/tools/subset-fonts.py` — Latin subsets of Noto Sans (OFL 1.1, no Reserved Font Name) for the ui-v2 rasterizer.

## port/vk-loader (3)
- `port/vk-loader/build-check.sh` — vk-loader for the PS5 port of Pokemon Legends Z-A Recomp: compile-only check with the toolchain of
- `port/vk-loader/gen_vk_loader.py` — gen_vk_loader.py - writes vk_loader.c, the static Vulkan "loader" of the PS5 port of Pokemon Legends Z-A Recom
- `port/vk-loader/vk_loader.c`

## research_notes/la-ps5-shader-comparison-20261028 (11)
- `research_notes/la-ps5-shader-comparison-20261028/check-reference.py` — Run reviewed reference cache tests on the host only; compile one PS5 object, never deploy.
- `research_notes/la-ps5-shader-comparison-20261028/current/device.c` — Vulkan device, window, swapchain and presentation (counterpart of the window/present half of metal.m).
- `research_notes/la-ps5-shader-comparison-20261028/current/exec.c` — Executes recorded NVN command lists with Vulkan (port of renderer.m; same structure, same behaviour).
- `research_notes/la-ps5-shader-comparison-20261028/current/shaderc_cache.c`
- `research_notes/la-ps5-shader-comparison-20261028/current/shaders.c` — GLSL -> SPIR-V (shaderc), descriptor layouts from the SPIR-V itself, translated NVN programs, built-in shaders
- `research_notes/la-ps5-shader-comparison-20261028/current/title_entry-r17.c`
- `research_notes/la-ps5-shader-comparison-20261028/upstream/ps5/tools/build-shaderc.py` — Fetch shaderc's pinned dependencies and build/validate it for PS5.
- `research_notes/la-ps5-shader-comparison-20261028/upstream/runtime/nvn/vulkan/device.c` — Vulkan device, window, swapchain and presentation (counterpart of the window/present half of metal.m).
- `research_notes/la-ps5-shader-comparison-20261028/upstream/runtime/nvn/vulkan/exec.c` — Executes recorded NVN command lists with Vulkan (port of renderer.m; same structure, same behaviour).
- `research_notes/la-ps5-shader-comparison-20261028/upstream/runtime/nvn/vulkan/prewarm_cache.c`
- `research_notes/la-ps5-shader-comparison-20261028/upstream/runtime/nvn/vulkan/shaders.c` — GLSL -> SPIR-V (shaderc), descriptor layouts from the SPIR-V itself, translated NVN programs, built-in shaders

## research_notes/perf-r24-handoff-results (1)
- `research_notes/perf-r24-handoff-results/package_results.py` — Package explicitly selected r24 reports/evidence, excluding saves and system logs.

## research_notes/ps5-resource-fit-r21 (1)
- `research_notes/ps5-resource-fit-r21/write-power-addendum.py` — Local-only resource/power audit supplement. No console access or runtime writes.

## research_notes/repeated-preparation-r20b (3)
- `research_notes/repeated-preparation-r20b/package_audit.py` — Package the four completed read-only reviews and verify the NAS delivery.
- `research_notes/repeated-preparation-r20b/shader-pipelines/extract_evidence.py` — Read-only source/log evidence extraction; writes only this audit directory.
- `research_notes/repeated-preparation-r20b/textures-buffers/audit.py` — Read-only source/profiler evidence for the parent (fourth) audit reviewer.

## save-workbench (6)
- `save-workbench/build.ps1`
- `save-workbench/package.py` — Package the private app and redistributable source; verify NAS copies.
- `save-workbench/prepare-assets.py` — Build a private, user-specific location catalogue from retained save snapshots.
- `save-workbench/src/Program.cs`
- `save-workbench/src/SaveEngine.cs`
- `save-workbench/src/WorkbenchForm.cs`

## tools/console-install-queue (1)
- `tools/console-install-queue/console_queue.py` — Cooperative, console-wide FIFO reservations. Never contacts console hardware.

## tools/labs (132)
- `tools/labs/hebrew-lab-tools/apply_final_editorial.py` — One-time reviewed terminology corrections; preserve prior frozen catalogs.
- `tools/labs/hebrew-lab-tools/apply_native_ui_build.py` — Create an immutable full candidate from validated text and native UI overlays.
- `tools/labs/hebrew-lab-tools/assemble_glossary.py` — Coordinator-owned draft assembly; never creates or assumes human approval.
- `tools/labs/hebrew-lab-tools/audit_text_coverage.py` — Measure installed message coverage against every English source record.
- `tools/labs/hebrew-lab-tools/battle_set_templates.py` — Source-bound factoring of battle messages; no approximate or fuzzy reuse.
- `tools/labs/hebrew-lab-tools/bfttf.py` — Nintendo .bfttf / .bfotf font containers: 4-byte magic, u32 big-endian size XOR key, then the sfnt XOR key
- `tools/labs/hebrew-lab-tools/build_font.py` — Build a single TrueType font with Latin + Hebrew + the symbols the game's text uses, from OFL Noto fonts.
- `tools/labs/hebrew-lab-tools/build_full_ui_text.py` — Compile reviewed English native UI image labels, preserving original geometry.
- `tools/labs/hebrew-lab-tools/build_header_mod.py` — Compile common and English UI labels into the game's native BC masks.
- `tools/labs/hebrew-lab-tools/build_hebrew_project.py` — Cumulative editorial Hebrew build; reports every category's remaining work.
- `tools/labs/hebrew-lab-tools/build_interface_headings.py` — Compile Hebrew settings headings into same-size native BC4 mask payloads.
- `tools/labs/hebrew-lab-tools/build_opening_phase.py` — Build the first editorial story batch; no console access or glossary approval claim.
- `tools/labs/hebrew-lab-tools/build_shared_headings.py` — Compile the inspected common screen headings, preserving native effects/icons.
- `tools/labs/hebrew-lab-tools/deliver_headers.py` — Package only final header deliverables and verify a versioned private NAS copy.
- `tools/labs/hebrew-lab-tools/deliver_hebrew_project.py` — Package a built Hebrew mod with measured coverage and bounded PC evidence.
- `tools/labs/hebrew-lab-tools/deliver_hebrew_trial.py` — Final scoped trial package: installed binary, pinned assets, sources and evidence.
- `tools/labs/hebrew-lab-tools/deliver_translation_stage0.py` — Private stage-zero handoff and glossary-review bundle, excluding games, saves, models and credentials.
- `tools/labs/hebrew-lab-tools/draft_remaining_text.py` — Prepare local-only reading drafts; never install or count these as translated.
- `tools/labs/hebrew-lab-tools/dump_file.py` — Print one message file (labels + token text), local inspection only.
- `tools/labs/hebrew-lab-tools/gfmsg.py` — Game Freak message files (Gen 8/9 Switch games; same layout in Pokemon Legends Z-A):
- `tools/labs/hebrew-lab-tools/glossary_manager.py` — Private terminology inventory and conflict-aware draft workflow.
- `tools/labs/hebrew-lab-tools/glossary_review.py` — Create a standalone, private searchable glossary review. The page cannot approve the glossary.
- `tools/labs/hebrew-lab-tools/index_messages.py` — Index (and optionally extract) the game's message files from a RomFS image, read-only.
- `tools/labs/hebrew-lab-tools/inventory_common_ui_text.py` — Inspect common-only UI packs not represented by an English variant.
- `tools/labs/hebrew-lab-tools/inventory_nested_ui_text.py` — Read-only audit of every SARC member in common/English UI packs.
- `tools/labs/hebrew-lab-tools/inventory_ui_text.py` — Read-only inventory of English UI image text, with decoded native masks.
- `tools/labs/hebrew-lab-tools/local_mt.py` — Local-only draft terminology generation. No game strings are sent to a translation service.
- `tools/labs/hebrew-lab-tools/localization_exemptions.py` — Narrow source-bound identifiers and attribution names; never exempt arbitrary prose.
- `tools/labs/hebrew-lab-tools/make_poc_en.py` — Proof of concept, alternative: Hebrew in the ENGLISH slot (works with an existing English save).
- `tools/labs/hebrew-lab-tools/make_poc_mod.py` — Proof of concept: Hebrew main menu / save screen in the Korean text slot, as a LayeredFS mod folder.
- `tools/labs/hebrew-lab-tools/nso_symbols.py` — List exported / imported symbols of the game's NSO modules matching a pattern (read-only).
- `tools/labs/hebrew-lab-tools/pack_translation.py` — Build a private English-slot LayeredFS candidate from approved, validated keyed translations.
- `tools/labs/hebrew-lab-tools/patch_bitmap_text_fonts.py` — Audit native bitmap-font message bindings; select an existing Hebrew-capable font.
- `tools/labs/hebrew-lab-tools/prepare_apparel_names.py` — Freeze explicitly reviewed clothing names and exact colour/pattern families.
- `tools/labs/hebrew-lab-tools/prepare_battle_set_editorial.py` — Expand explicitly edited battle sentences and inspected stat-change patterns.
- `tools/labs/hebrew-lab-tools/prepare_battle_state.py` — Freeze all battle-state labels and descriptions against inspected source.
- `tools/labs/hebrew-lab-tools/prepare_credits.py` — Freeze reviewed credit prose and original attribution names from two inspected tables.
- `tools/labs/hebrew-lab-tools/prepare_donut_flavor.py` — Compile complete reviewed donut effect families, frozen to every source row.
- `tools/labs/hebrew-lab-tools/prepare_donut_names.py` — Freeze full donut names; retain both dynamic name parts and all berry identities.
- `tools/labs/hebrew-lab-tools/prepare_hebrew_trial.py` — Compose the already-reviewed Hebrew sample and a scoped r27b menu variant.
- `tools/labs/hebrew-lab-tools/prepare_item_descriptions.py` — Freeze reviewed item-description prose and exact, inspected semantic families.
- `tools/labs/hebrew-lab-tools/prepare_items_editorial.py` — Generate frozen item forms from inspected semantic families and spellings.
- `tools/labs/hebrew-lab-tools/prepare_moves_editorial.py` — Freeze the inspected move lexicon and expand four exact battle templates.
- `tools/labs/hebrew-lab-tools/prepare_npc_names.py` — Freeze reviewed NPC spellings against exact source rows. No transliteration engine.
- `tools/labs/hebrew-lab-tools/prepare_place_names.py` — Freeze all direct and inflected place names with explicit local terminology.
- `tools/labs/hebrew-lab-tools/prepare_pokedex_categories.py` — Freeze complete Pokédex category labels from explicitly authored terminology.
- `tools/labs/hebrew-lab-tools/prepare_pokedex_forms.py` — Freeze every form label from reviewed names and explicit editorial form terms.
- `tools/labs/hebrew-lab-tools/prepare_rogue_battle.py` — Bind the 380 manually reviewed battle callouts to all 697 exact source rows.
- `tools/labs/hebrew-lab-tools/prepare_species_editorial.py` — Freeze a spelling review of all 1,026 species-name entries.
- `tools/labs/hebrew-lab-tools/qa_headers.py` — Bounded PC evidence for native headers, with isolated saves and source checks.
- `tools/labs/hebrew-lab-tools/qa_translation.py` — Bounded reproducible PC QA, using a private data root and a copied lab test save.
- `tools/labs/hebrew-lab-tools/reuse_translation_memory.py` — Conservative reuse of identical, previously edited messages.
- `tools/labs/hebrew-lab-tools/rtl.py` — Logical-order Hebrew message text -> visual order for the game's left-to-right text engine.
- `tools/labs/hebrew-lab-tools/run_poc.py` — One bounded run of the PC build for the Hebrew proof of concept.
- `tools/labs/hebrew-lab-tools/text_layout.py` — Font-aware logical wrapping before RTL conversion; all default window limits are heuristics.
- `tools/labs/hebrew-lab-tools/translation_memory.py` — Private deterministic GFMSG translation memory and source-only batch preparation.
- `tools/labs/hebrew-lab-tools/translation_validate.py` — Conservative validators for logical-order Hebrew translator output.
- `tools/labs/hebrew-lab-tools/trial_console.py` — Scoped, recorded Hebrew preview operations on PPSA91762 only.
- `tools/labs/hebrew-lab-tools/trial_log.py` — Capture task-scoped console logs until the local stop file is created.
- `tools/labs/hebrew-lab-tools/ui_color_codec.py` — Native BC1/BC3/BC7 color labels; untouched blocks and tiling padding are exact.
- `tools/labs/hebrew-lab-tools/ui_header_codec.py` — Native, local SARC/BNTX BC4U/BC5U mask codec. No image files or game writes.
- `tools/labs/hebrew-lab-tools/ui_header_extract.py` — Read-only native SARC/BNTX extraction of the requested English UI heading candidates.
- `tools/labs/hebrew-lab-tools/ui_lang_archives.py` — Count the UI archives that exist per language (ui/data/... _eng/_kor/... .arc): their textures can carry baked
- `tools/labs/hebrew-lab-tools/ui_layout_overrides.py` — Explicit message-window estimates for tables otherwise classified as menu labels.
- `tools/labs/hebrew-lab-tools/ui_nested_terms.py` — Reviewed labels in UI archives stored after a pack's first member.
- `tools/labs/hebrew-lab-tools/ui_text_terms.py` — Human-reviewed native image text from the 2.0.2 English UI inventory.
- `tools/labs/hebrew-lab-tools/var_usage.py` — Count control-code types per language (aggregate numbers only).
- `tools/labs/hebrew-lab-tools/volume.py` — Text volume per category (English slot), local analysis; prints aggregate numbers only.
- `tools/labs/hebrew-lab-tools/za_romfs.py` — Read-only access to Pokemon Legends Z-A game files: RomFS image -> arc/data.trpfs (ONEPACK) -> files by path.
- `tools/labs/pokeza-pc-scripts/analyze_run.py` — Summarize measured ZA Recomp logs and rendered images, without inferring playability.
- `tools/labs/pokeza-pc-scripts/bench_suite.py` — Sequential, bounded runs of the same saved scene; never overlapping games.
- `tools/labs/pokeza-pc-scripts/build_city_runtime.py` — VkG g_vk;
- `tools/labs/pokeza-pc-scripts/build_game.py` — Build the game DLL with the v0.1.3 recipe, limiting concurrent compilers.
- `tools/labs/pokeza-pc-scripts/build_lab.py` — Relink a separate diagnostic library with an application-level SDL test controller.
- `tools/labs/pokeza-pc-scripts/city_route.py` — Replay an observed, bounded street route through the application's test queue.
- `tools/labs/pokeza-pc-scripts/compare_state_filter.py` — A-B-B-A diagnostic of a pre-existing optimization; not a new speedup claim.
- `tools/labs/pokeza-pc-scripts/copy_quickstart_to_nas.py`
- `tools/labs/pokeza-pc-scripts/finalize_quickstart_report.py`
- `tools/labs/pokeza-pc-scripts/finish_mod_runtime_delivery.py`
- `tools/labs/pokeza-pc-scripts/finish_report.py` — Package measured evidence and user instructions. No credentials or caches.
- `tools/labs/pokeza-pc-scripts/lab_send.py` — Send a bounded command to this project's in-app test queue, and record it.
- `tools/labs/pokeza-pc-scripts/launch_city_probe.py`
- `tools/labs/pokeza-pc-scripts/map_pack_save_names.py` — Read-only bounded pack scan for event variable names; no exported assets.
- `tools/labs/pokeza-pc-scripts/map_save_names.py` — Map observed save keys to literal FNV-1a names in the game's NSO; read only.
- `tools/labs/pokeza-pc-scripts/package_architecture_review.py` — Deliver a versioned architectural review and bounded diagnostic evidence.
- `tools/labs/pokeza-pc-scripts/package_mods_and_runtime.py` — Package explicit deliverable allowlists. Never include game data, keys or caches.
- `tools/labs/pokeza-pc-scripts/package_pc.py` — Assemble a local playable folder, with an explicit allowlist and no keys/caches.
- `tools/labs/pokeza-pc-scripts/package_quickstart.py` — Package only reviewed source, city templates, UI and validation evidence.
- `tools/labs/pokeza-pc-scripts/prepare_profile.py` — Relink unchanged game objects with an address map for a separate profiling run.
- `tools/labs/pokeza-pc-scripts/prepare_quickstart_evidence.py` — Assemble observed checkpoint evidence; never runs or changes the game.
- `tools/labs/pokeza-pc-scripts/profile_render.py` — Capture renderer evidence from one isolated, copied game state.
- `tools/labs/pokeza-pc-scripts/profile_summary.py` — Map the runtime's sampled PCs using exact PE bounds and our game's linker map.
- `tools/labs/pokeza-pc-scripts/run_probe.py` — Bounded local tests using ZA Recomp's own documented test hooks.
- `tools/labs/pokeza-pc-scripts/setup_dotnet10.py`
- `tools/labs/pokeza-pc-scripts/snapshot_post_battle.py`
- `tools/labs/pokeza-pc-scripts/summarize_benchmark.py` — Describe measured log intervals; these are not per-frame percentiles/1% lows.
- `tools/labs/pokeza-pc-scripts/summarize_render.py` — Normalize upstream interval counters without adding overlapping categories.
- `tools/labs/pokeza-pc-scripts/try_hot_o1.py` — Compile only two sampled O0 units at O1, preserving all baseline outputs.
- `tools/labs/randomizer-lab/analyze_tables.py`
- `tools/labs/randomizer-lab/binary_xrefs.py` — Locate ADRP+ADD references; these are address references, not inferred function semantics.
- `tools/labs/randomizer-lab/extract_tables.py` — Also test schema partners for binary tables, and data partners for schemas.
- `tools/labs/randomizer-lab/inspect_game.py` — Read-only index of the locally supplied Z-A RomFS and NSO. No guest code execution.
- `tools/labs/randomizer-lab/inspect_support.py` — Read-only learnset/evolution and boss-support inspection for pinned 1.0.0.
- `tools/labs/randomizer-lab/reflection_reader.py` — Bounded FlatBuffers/BFBS inspection using the public reflection.fbs layout.
- `tools/labs/randomizer-lab/seed_plan.py` — Deterministic proposal generator. Does NOT patch, install or launch a mod.
- `tools/labs/randomizer-lab/validate_scalar_edits.py` — Edit copies in RAM and decode again. Never save or install changed game files.
- `tools/labs/species-lab-scripts/analyze_packs.py` — Group the 2.0.2 pack names (out/pack-names.json) by kind; per-species pack inventory. Names only.
- `tools/labs/species-lab-scripts/anim_inventory.py` — Read-only: resolve animation file names (.tranm/.traef) in Pokemon model folders by probing a motion-name voca
- `tools/labs/species-lab-scripts/catalog.py` — Parse ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog (Z-A 2.0.2) into JSON: species-info fields + 
- `tools/labs/species-lab-scripts/catalog_exists.py` — Read-only: which catalog-referenced paths (prefixed with ik_pokemon/data/) exist in the 2.0.2 pack index, per 
- `tools/labs/species-lab-scripts/catalog_summary.py` — Summarise catalog.json: species/form/gender keys, pm folder mapping, overlap with personal presence.
- `tools/labs/species-lab-scripts/decode_samples.py` — Decode a few extracted per-species tables with their shipped .bfbs schemas (read-only, prints a short summary)
- `tools/labs/species-lab-scripts/enum_species_files.py` — Read-only: enumerate exact NNNN_FF_VV names of per-species data files (behavior / collision / wild_single para
- `tools/labs/species-lab-scripts/extract_samples.py` — Read-only: extract a few small Z-A 2.0.2 files (by game path) into species-lab/samples for local analysis.
- `tools/labs/species-lab-scripts/fbwalk.py` — Heuristic schema-less FlatBuffers walker (read-only), for exploring Trinity files.
- `tools/labs/species-lab-scripts/folder_accounting.py` — Read-only: account for every file hash in a model folder's pack using names from the folder's own _base.tracr 
- `tools/labs/species-lab-scripts/list_packs.py` — Read-only: list RomFS loose files and Trinity pack names of Z-A 2.0.2 (no game bytes written, names only).
- `tools/labs/species-lab-scripts/model_pack.py` — Read-only: inventory of one Pokemon model folder (default pm0025_00_00): which packs hold its files, resolve
- `tools/labs/species-lab-scripts/more_tables.py` — Read-only: existence + species coverage of further per-species tables named by a community Z-A mod (Ansha pack
- `tools/labs/species-lab-scripts/nso_strings.py` — Read-only: decompress the 2.0.2 exefs/main NSO in memory (pure-Python LZ4) and list strings matching a regex.
- `tools/labs/species-lab-scripts/per_species_coverage.py` — Read-only: for every personal row (species/form), which per-species data files exist (present vs absent specie
- `tools/labs/species-lab-scripts/personal.py` — Decode Z-A 2.0.2 avalon/data/personal_array.bin (layout per pkNX ZA PersonalTable.fbs, as used by randomizer-l
- `tools/labs/species-lab-scripts/personal_dex.py` — Dex struct (index u16, group u8) of 2.0.2 personal rows: present vs absent; plus TM/reminder/egg vectors prese
- `tools/labs/species-lab-scripts/pilot_candidates.py` — Rank absent species as pilot candidates: personal row data, SV Paldea-dex leftover index, behaviour file, cry 
- `tools/labs/species-lab-scripts/pkhex_personal.py` — Read PKHeX's personal_za resource (PersonalInfo9ZA layout, 0x50 bytes/entry) and summarise presence.
- `tools/labs/species-lab-scripts/pm_folder_map.py` — Map every ik_pokemon/data/pmNNNN model folder (from pack names) to the species that the game's own catalog
- `tools/labs/species-lab-scripts/probe_anims.py` — Read-only: find a model folder's animation-config (.tracn) / skeleton-set / icon paths, and probe animation fi
- `tools/labs/species-lab-scripts/species_files_vs_presence.py` — Compare enumerated per-species data files with personal presence (internal vs national numbering).
- `tools/labs/species-lab-scripts/text_tables.py` — Read-only: line counts of species-related English message tables (names / dex entries), and whether absent spe
- `tools/labs/species-lab-scripts/trinity_headers.py` — Read-only: FlatBuffers vtable sizes ("struct lengths") of Z-A Trinity model files, for comparison with the pub
- `tools/labs/species-lab-scripts/wwise_cries.py` — Read-only: parse Wwise banks (in memory) for Event ids and test which 'PLAY_PV_%04u' cry events exist (FNV-1 3
- `tools/labs/species-lab-scripts/wwise_cry_media.py` — Read-only: for PLAY_PV_<species> events in PM_VOICE.bnk, follow Event -> Action -> Sound/Container -> source m

## tools/za-atlas (17)
- `tools/za-atlas/P1/index_functions.py` — Stream static-recompiler C units into the za-atlas P1 JSONL contract.
- `tools/za-atlas/P2/extract.py` — Read-only NSO metadata extraction; all derived game data goes outside git.
- `tools/za-atlas/P3/build_refs.py` — Build guest references from translated C without modifying game inputs.
- `tools/za-atlas/P3/finalize.py` — Write P3/DONE.json only after the full artifact passes validation.
- `tools/za-atlas/P3/validate_refs.py` — Validate the complete P3 artifact without retaining its records in memory.
- `tools/za-atlas/P4/crash.py` — Decode local crash logs against the exact ELF; never contacts a console.
- `tools/za-atlas/P4/index_runtime.py` — Index runtime registrations, never inventing dynamic HLE slot addresses.
- `tools/za-atlas/P4/llvm_bridge.sh` — All WSL tool invocations go through this file, including paths with spaces.
- `tools/za-atlas/P4/verify_and_finalize.py` — Verify P4 artifacts and write the common DONE contract while owning P4.
- `tools/za-atlas/P5/harvest.py` — P5 of the za-atlas: harvest the names the existing research already established into annotations.jsonl.
- `tools/za-atlas/P5/heartbeat-loop.sh` — Background heartbeat for the za-atlas claim board: every 10 minutes, stop on "lost" (exit 3).
- `tools/za-atlas/P5/index_functions.py` — P5 helper: index every translated function definition (addr -> module, unit, line) in the AOT tree.
- `tools/za-atlas/P5/knowledge.py` — P5 knowledge harvest: addresses that the existing research already identified, with the file:line that says so
- `tools/za-atlas/P6/acceptance.py` — P6 acceptance: run the za-atlas acceptance queries, record output and wall time, check the expected facts.
- `tools/za-atlas/P6/build_atlas.py` — P6 of the za-atlas: merge parts P1..P5 into za-atlas-data/atlas.sqlite.
- `tools/za-atlas/P6/za_atlas.py` — za-atlas: the code map of Pokemon Legends: Z-A 2.0.2 (translated C), queried from za-atlas-data/atlas.sqlite.
- `tools/za-atlas/claim.py` — Package claims for the parallel za-atlas build (analysis/CODE-ATLAS-PROMPT-HE.md).

## vk-probe (2)
- `vk-probe/build-vk-probe.sh` — ZA Native Probe - build the Vulkan/pad/audio/memory probe title (PPSA91760, r5) for the PS5.
- `vk-probe/src/za_vk_probe.c`

