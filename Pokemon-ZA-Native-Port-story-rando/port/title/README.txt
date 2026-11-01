NATIVE PS5 TITLE — CURRENT BUILD AND CONTINUATION

Scope
Pokemon Legends: Z-A 2.0.2 plus merged Mega Dimension, native runtime/RADV,
no Wine. Stock title PPSA91761; separate graphics probe PPSA91760 preserved.
The randomizer ARM64 subsdk9 is not included. See the dated hardware report
for current verification; a successful build is not a full-game compatibility test.

Inputs and build
Pinned SDK/PS5_Vulkan/PS5_Mesa live under /home/tomer/ps5-za-native.
Hardware fixes are in the isolated title-r1-20261027/source snapshot; the
original ../pokeza-recomp-ps5 checkout is not edited by hardware scripts.
The port/shim implementation snapshot is under title-r1-20261027/port.
The title integration files here are read live by build-runtime.sh.
Locked 2.0.2 AOT source is in the PC research update-2.0.2-20261025/aot folder.
The baseline archive has 1412 objects, 160 at O0 and 1252 at O1.

r13
build-hardware-r13.sh verifies the exact NSO build ID and ARM instruction,
patches only an isolated main_660.c, builds its object and an alternate static
archive under fps-r13/liblasgame-r13.a, then links/converts the native title.
Original generated source and baseline archive are retained.
performance-profile.txt contains exactly '60-auto\n' to enable the trial.
Absent/invalid/30 selects original frame configuration. A slow trial falls
back after five slow windows, following five warmup windows. It is not a
reliable dynamic FPS mod; the observed startup trial fell back before city.
The installed default was restored to 30. Test with test-performance.c.

r14
build-hardware-r14.sh applies the checkpoint integration to isolated device.c,
copies pipeline_cache.h, and links using the r13 alternate archive. It saves
native pipeline cache every ten seconds while running, validates device and
cache UUID on reload, uses a checked temporary file and atomic rename, and
keeps the previous cache on failure. test-pipeline-cache.c covers host I/O.
Two-boot hardware test: first boot initialized empty and saved while playing;
after PS5 Close Game the second boot loaded 2,925,828 bytes. User confirmed the
same place/action was smooth after reopening. This is not whole-game coverage.
See evidence/title-r14-persistence-and-performance.json for bounded results.
Do not ship a Windows/NVIDIA/AMD-PC driver binary cache as a PS5 cache.

Packaging and deployment
Always use a NEW TITLE_DIST for a different binary. verify-image.py checks
native conversion preserves registration/constructor/RELRO and game tables.
package-title.sh supplies the actual game icon/name and official city background.
The incremental update omits unchanged six-GB game data and one-shot save input.
update-title.py rejects running titles, checks the installed SHA, retains its
backup, uploads .new, verifies readback, renames, then verifies again.
run-title.py launches only PPSA91761 and captures three minutes of diagnostics.
monitor-title.py SECONDS TAG observes an already-running native title only.
The full-title address base is 0x400000; subtract it for addr2line against the
matching PIE. source/build/ps5/title/llvm-pie.elf is overwritten per build.

Paths
Read-only packaged game: /app0/game.
Writable state: /download0/zarecomp; when mounted this is
/mnt/sandbox/PPSA91761_000/download0/zarecomp.
The mount vanishes when closed. Never edit the raw backing download0.dat.
Console 192.168.1.135: FTP2121, Payload Manager8084, klogsrv3232.
Do not close an unrelated title or overwrite the user's current progress.

Shaders
shader-host.py SECONDS (1..900) watches only this title's missing GLSL,
verifies its source-derived hash, compiles using glslangValidator for Vulkan1.3,
validates, and atomically publishes to /data/homebrew/PPSA91761/cache/spirv
with SHA-256 readback. The runtime sees this through /app0. Old validated
deliveries are reused. Helper exits shortly after the title's sandbox disappears.
It is a bounded development dependency, not a permanent on-console compiler.
An unknown shader can still time out without the helper. index.txt is not a shader.
collect-pc-shaders.py inventories/deduplicates prior PC SPIR-V. Conflicting keys
are excluded; validate-pc-shaders.py validates unambiguous files in WSL;
stage-pc-shaders.py adds only absent keys while titles are closed.
No cache inventory is claimed exhaustive for the game's full content.

Save and branding
r12's save_import.h performs a one-shot, hash-checked city Tepig save import,
with an old-save backup, transaction journal and completion marker. Completed
imports never reapply over later progress. Interrupted imports stop boot safely.
Do not remove the completion marker to troubleshoot unrelated game problems.
The original save plus imported-save evidence is in title-r12-save-transfer-*.
stage-branding.py backs up 14 scoped metadata files and verifies each update.
rename_title.c uses a locked SQLite transaction and consistent backup; it changes
only PPSA91761's title name/JSON title fields. It never replaces app.db wholesale.
Its SQLite source dependency is sqlite-amalgamation-3500400 from sqlite.org.
No private keys or whole app.db backups belong in source/handoff archives.

Limits
FFmpeg stubs report unavailable video decoding. Desktop launcher/ImGui/text input
are absent, with text prompts cancelled explicitly. Some services are stubbed.
General dynamic-index push-constant correctness, clean CRT exit, full-game
stability, stable60, DLC progression and the native randomizer remain unproven.
The portable randomizer core generates tables/save per seed without compilation;
its native UI, overlays, restart/save handling and separate title need integration.

Delivery
package-hardware-update.py creates a versioned report/source/evidence archive.
It excludes game data, generated game C, SDKs and private-data. copy-to-nas.ps1
copies final deliverables to the user's versioned NAS folder and verifies hashes.
