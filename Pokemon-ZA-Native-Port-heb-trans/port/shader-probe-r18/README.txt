ZA local shader compiler hardware probe r18b

Validated on the user's PS5 on 2026-10-28, run 20261028-151146z.
Uses the existing PPSA91760 development probe slot; not the game titles.
glslang 16.2.0, commit f0bd0257c308b9a26562c1a30c4748a0219cc951.
Output target: Vulkan 1.3, SPIR-V 1.6, optimizer disabled.

Result: 41 API/write cases passed; 36 game-shader outputs (12 inputs x 3)
matched the host SHA-256 references. All 38 positive outputs passed
spirv-val --target-env vulkan1.3. Compute smoke and error-recovery outputs
matched each other. See evidence/shader-probe-r18b/20261028-151146z.

Build (WSL): bash port/shader-probe-r18/build.sh
Requires the local SDK/glslang archives named in build.sh. The archives,
SDK, captured game shader inputs and runtime are not in the source zip.
After any rebuild, update hardware.py's pinned NEW SHA from the verified
build output; never remove its exact candidate/rollback checks.

Run hardware.py from Windows using the project's Python environment only
when the console is available for testing. It checks for an idle console,
backs up the existing known probe, stages inputs, verifies writes, launches,
collects the completed results, identifies its own PID using this run's
nonce, and closes that probe through Payload Manager. It restores the
original executable after confirming the title has stopped. It never
closes an unidentified game. File/source hashes are checked before upload.

Offline validation (WSL):
python3 port/shader-probe-r18/analyze.py evidence/shader-probe-r18b/<run-id>

Lifetime caveat: r18a returned normally and received SIGSYS in the SDK exit
path after completing compilation. r18b waits up to 60 seconds for host
collection and uses controlled host termination. This avoids that path in
the validated run, but does not fix normal native title shutdown. Its
timeout fallback retains the known exit limitation. The compile phase has
a separate 90-second watchdog. Do not mistake this harness policy for game
runtime behavior.

The measured mapped heap remained 64 MiB during three graphic-shader passes,
then reached 80 MiB with the compute smoke test, with no libc fallbacks.
This is neither live allocation size nor total process RSS. Three passes
do not establish long-run absence of leaks.

No game integration, GPU pipeline warm-up, background-game contention,
full shader coverage or in-game frame-time improvement is established by
this probe. Next: integrate a bounded compiler worker, retain disk caching,
then measure real game misses and Vulkan pipeline creation independently.
