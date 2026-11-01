Z-A native PS5 performance r16 — first build after the 60 FPS research

Scope
This update builds the Randomizer title PPSA91762 from the r15 runtime and the
unchanged cheats-r12 game archive. It does not modify the stock title PPSA91761,
ROM/DLC/mod data, runs, saves or the existing shader/pipeline caches.
Hardware validation is pending. No speedup or sustained 60 FPS is established.
This is the static 60 trial foundation, not the full Dynamic RC3.0 adaptation.

Changes
- Replace fixed program/pipeline hash tables with bounded, growable tables.
  Entries have render-thread ownership; worker-owned objects do not move.
  Failed allocation skips the affected draw instead of looping forever.
- Thread-local dynamic-state construction; pthread_once for worker startup.
- Packed atomic shader work counter includes queued/running work and completion
  generation. This avoids treating a finished-in-between-samples job as idle.
- Memoize exact program hash inputs and full pipeline dependencies by value.
  Preserve original key bytes, invalidation on reset, and fixed-function state.
  An optional pipeline shadow mode recomputes and checks original key/handle.
- Lean graphics driver constants compare only entries read by the shader.
  Compute constants and transform-feedback scale tables retain the r15 path.
- Default 30 FPS startup. L3+R3 menu has a fourth FPS TRIAL row; X toggles
  original/60-auto or directly retries after fallback. Selection is per session.
- Manual arming prevents startup from consuming the trial warmup. Shader work,
  clock/present rollback, and >250ms hook gaps reset the sample window. Five
  clean warmup windows precede five clean windows below 58.5 FPS for fallback.
  This is an eligibility heuristic, not full game/scene state recognition.
- Generic pacing disabled before renderer startup; tick scale stays 1.
  Game identity flag and GPU counter/DRS semantics are deliberately unchanged.
  Existing renderer CPU/GPU profiling is enabled for the hardware comparison.

Same-binary startup comparisons: /app0/performance-options.txt
optimized          : memo/lean on, generic pacing off (default)
shadow             : on, but pipeline memo hits recompute and compare
renderer-baseline  : memo/lean off, generic pacing off
pacing-baseline    : memo/lean off, original generic pacing on
Each file contains the word followed by LF. Restart the title to change it.
These profiles retain the stability fixes; pacing-baseline is not byte-identical
to r15. Invalid nonempty profile text disables memo/lean and keeps pacing off.
The old performance-profile.txt is not used to auto-arm r16.

Host validation
Actual changed helpers are extracted from patched exec.c for comparisons.
Tests use mocks for immutable Vulkan device mappings/handles, not a real GPU.
All are compiled with -Wall -Wextra -Werror, ASan and UBSan:
- 24,000 colliding cache entries, growth past both old capacities, full-table
  termination, replacement/reset and forced allocation failures.
- 40,000 randomized pipeline dependency comparisons against the r15 builder.
- 80,000 byte-exact program-hash comparisons, including ShaderKey padding.
- 4,096 constant-buffer comparisons, every 1..2048 byte length, both stages;
  submission and reboot lifetime invalidation.
- 64 host threads / 640,000 dynamic-state and work-accounting operations.
- Timing policy and actual API: cold startup, arm, gap/compiler exclusions,
  sustained slow fallback, direct retry, restoration and all four profiles.
The full PS5 runtime still emits its preexisting SDK/VMA warnings; do not
describe the entire upstream build as passing -Werror.

Reproduction in the existing development workspace
1. bash port/performance-r16/prepare.sh
2. python3 port/performance-r16/apply.py /home/tomer/ps5-za-native/perf-r16-20261028
3. python3 port/performance-r16/test-renderer.py /home/tomer/ps5-za-native/perf-r16-20261028
4. bash /home/tomer/ps5-za-native/perf-r16-20261028/build-r16.sh
The first application verifies the original exec.c SHA-256. Later applications
regenerate from the preserved original. Do not apply while a build runs.
The new final binary destination must not contain a different eboot.bin.
relink.sh is for runtime-only rebuilds after the first full candidate build.
This source/audit archive contains the changed code, not the user's generated
game source, SDK, RADV dependencies or game archive. Those existing inputs are
needed for the recipe. The original r15 source and binary remain unchanged.

Research provenance
https://github.com/Hexveil404/PokeZ-ARecomp/commit/ef8ed66140302bae9d54172f65498a2ece1de31c
https://github.com/Hexveil404/PokeZ-ARecomp/commit/465f0ed5a64870f69e270a210a171c6d64bcaa8f
https://github.com/Hexveil404/PokeZ-ARecomp/blob/51bd9277be93185d72f54126c78dcef989567244/runtime/nvn/vulkan/exec.c
The fixes and memo integrate these ideas into the older PS5 runtime selectively;
the new recorder, page tracking, CPU/GPU overlap and descriptor ABI were not
copied. cache_table.h and the policy are local implementations.

Remaining work
Hardware: same warmed save and route; 30/60 trial; record actual frame time,
simulation/attack/capture speed, visual correctness and long-session growth.
Dynamic RC3.0: finish mapping main flag 0x610b980 and SDK field at +0xf24;
SDK generated containing function is f_7008197a30, unit sdk_035.c. No semantics
such as VSync are asserted for this field yet. Do not stack its ARM byte patches
on the x86 executable. It requires guarded translated-C hooks and independent
timing/animation verification. It is not enabled in r16.
