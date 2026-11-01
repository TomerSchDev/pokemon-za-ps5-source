Z-A Randomizer r17a — remote visual/performance observer
2026-10-28

Status
Built on the validated r16 performance candidate for title PPSA91762 only.
Host tests and PS5 cross-compilation passed. r17a was installed with SHA256
readback on 2026-10-28. Follow matching hardware evidence for current test status.
The user explicitly handed over console use after the SMO agent stopped.
r17 launched its menu successfully; the current save was backed up twice-read.
The first command failed because the sandbox refuses FTP file creation. r17a
reads commands through /app0/observer-command.txt instead. No directory access
permissions were widened. Results remain in the title's writable download0.

What was reviewed and reused
SMO-Native-Port/port/title/title_png.c was copied byte-for-byte. SHA256:
cb48dab39d67a0be428e545427f675eeab69f4f13c3944b911cc513775ae3bb1
It implements SDL_SavePNG through a local linker wrapper, using PNG RGBA8 and
stored DEFLATE blocks. It honors signed row pitch and handles errors by deleting
partial output. It does not capture pixels by itself: the existing Vulkan
renderer copies the game texture to host memory and then calls this encoder.
The actual SMO console image frame_00001.png decoded independently as 1600x900
RGBA, RGB extrema all zero. It proves a decodable file, not successful gameplay.
The encoder's independent patterned-pixel tests passed in both channel formats,
with positive/negative pitch, padding, DEFLATE block boundaries and failures.

Added here
- Opt-in enable file /app0/observer-enable.txt must contain exactly observe-r17 LF.
  With no file the observer is dormant. This candidate bundle includes the file.
- Session-scoped, increasing sequence-number commands through the existing FTP
  service. The PC writes only /data/homebrew/PPSA91762/observer-command.txt via
  a staged readback-verified atomic rename; the game reads its /app0 alias.
  The game writes results in download0/zarecomp/observer; FTP reads them there.
- snapshot: game texture PNG on request, with measured readback+encode time.
- measure 1..120: two seconds settling, then per-frame samples buffered in RAM;
  no observer disk polling, file writes or screenshot calls during the window.
  A CSV is written afterward. Maximum 32768 samples (about 2.4 MiB); a full
  buffer or frame/clock reset is reported, never mislabeled as completion.
- input: a whitelist of guest buttons or sticks held for 1..120 presented frames,
  then released. Not wall-clock input: stalls delay expiry until frames resume.
- fps 0/1: original mode or the existing r16 static 60-auto trial.
- continue RUN_ID: menu only, must match the current active run exactly; runs
  normal integrity validation, never creates a new seed or imports another save.

Measurement meaning and limits
Intervals are measured on the CPU immediately after presentation submission.
They are not direct display scanout timestamps, proof of unique rendered images,
GPU frame completion time or proof that game simulation runs at the right speed.
Unsuccessful presentation intervals and explicit re-presentation are labeled.
Queued/running shader work and completion epochs tag affected intervals.
Analysis includes ALL measured intervals, plus clearly conditional subsets.
It computes rate, median/p95/p99/max frame time, 1% low and >50ms stutters.
Never replace the all-interval result with the shader-free subset.
No filtering of long game stalls is done. A stalled renderer cannot answer a
new screenshot request; timeout/incomplete acknowledgement is not success.
Screenshots contain the game texture, not PS5 system menus or the native
randomizer launcher/cheat overlay. PNG is uncompressed and can take significant
CPU, GPU synchronization and I/O time. Take sparse shots outside measurement,
and fetch files only after a measurement finishes. Do not enable the runtime's
other SHOT/SCREENSHOT/DEBUG capture environment variables during a benchmark.
Existing Vulkan profiling, black probes and cache maintenance retain r16 behavior.
CPU observer-call cost is only a partial overhead estimate. Console on/off
comparisons remain necessary before claiming overhead is negligible.

No save isolation is provided by the observer. Normal gameplay can autosave.
Before an autonomous play test, back up the active run's save and active.json
while the title is closed, preserving existing progress. Observe images before
deciding which buttons to send; do not blindly repeat an unverified route.
Do not deploy or launch while another agent/user owns the console.

Build in the existing workspace
The private copy /home/tomer/ps5-za-native/capture-r17-20261028 is based on
/home/tomer/ps5-za-native/perf-r16-20261028. Shared r15/r16 sources remain intact.
Check available Windows disk space before copying or building (at least 6 GiB
free is prudent for the current toolchain). An early scratch copy filled C:;
an obsolete rejected binary was removed and older build artifacts compressed
in place, preserving their contents. WSL resumed without this task issuing a
shutdown/restart. No user game/save data was removed.
python3 port/observer-r17/prepare.py
/home/tomer/ps5-smo-native/venv/bin/python port/observer-r17/test.py
python3 port/observer-r17/test-client.py
bash port/observer-r17/build.sh
Preparation regenerates four patched sources from r16/baseline inputs and
copies existing r16 objects; don't run it while compiling. Native game archive
and SDK/driver dependencies are reused and not distributed in the source ZIP.
The full upstream runtime retains its preexisting warnings. The new observer,
PNG code and changed launcher compile with -Wall -Wextra -Werror.

Hardware procedure
1. Coordinate exclusive console use. Back up current eboot/config and save.
2. Install only the candidate eboot.bin, performance-options.txt and opt-in
   observer-enable.txt into the existing PPSA91762 app. Do not replace shader
   caches, game data, randomized runs, saves, libc or branding from this update.
   Verify every transfer by SHA256; keep the known working r15 rollback image.
3. Launch normally. client.py status returns the observer session token. Read
   the active run ID from download0/zarecomp/rando/active.json if Continue is
   needed, then use the exact ID, with a fresh positive increasing --seq.
4. Send snapshot, then collect its ack/image and inspect. Use bounded input A
   only when the observed screen calls for it; confirm the city via another shot.
5. Warm the same scene. Request measure 30, wait at least 32 seconds without FTP
   transfers, then collect. Require ack.result=complete. Collect a later shot.
6. Repeat identically with fps 1 only after city gameplay is confirmed. Record
   fallback and mixed FPS modes. Compare same warmed save/camera/state.
7. Measure the renderer-baseline/pacing-baseline profiles in separate launches,
   and compare observer-enabled versus disabled via the existing runtime logs.
   Retest capture/attack animation speed and visual correctness, not just FPS.

Client examples (replace SESSION with status output; single mailbox writer)
python client.py status
python client.py snapshot --session SESSION --seq 1
python client.py collect --session SESSION --seq 1 --out captures/session
python client.py input A 3 --session SESSION --seq 2
python client.py measure 30 --session SESSION --seq 3
python client.py collect --session SESSION --seq 3 --out captures/session
python client.py fps 1 --session SESSION --seq 4
python client.py continue EXACT_ACTIVE_RUN_ID --session SESSION --seq 5
The client never deploys, launches, stops titles or writes game data. It verifies
command readback and downloaded outputs and prevents output-path traversal.
Its read-only status may be stale if the game has closed: a fresh matching ack
is required to establish liveness. Only completed measurements get analysis.
Pillow is used when decoding fetched PNGs; other client operations use stdlib.

Deliverables
Update ZIP: candidate eboot + two opt-in/profile files only.
Source ZIP: observer/PNG/client/analyzer, guards/tests/build scripts, r16 source
foundation and build audit. No game assets, ROM, DLC, saves, keys or credentials.
SHA256SUMS and NAS-COPY-VERIFIED record final copy checks.
