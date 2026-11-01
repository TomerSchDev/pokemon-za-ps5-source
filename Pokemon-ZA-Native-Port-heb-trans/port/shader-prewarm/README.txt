ZA randomizer-aware shader prewarming research — 2026-10-28

Status: OFFLINE PROTOTYPE. Nothing in this directory is installed in r15.
No console restart, game launch, upload, save change or cache replacement is performed.

1. forecast.py reconstructs the final wild table from the captured run, verifies
   SHA-256 against that run's console receipt, and joins explicit zone/scene IDs.
   It produces a conditional content superset, not a list of compiled shaders.
   Inputs are the last verified run, not a live query of the currently selected run.
   For another seed, provide that run's report and matching core output with --run.
   Party members, trainer parties, evolving Pokémon, story actors and global FX
   need separate inputs before the forecast can be used as a complete workload.

2. compiler.c exposes a narrow GLSL -> SPIR-V C interface using glslang 16.2.0.
   Calls must be serialized on one worker. Initialize/finalize once on that worker.
   Filesystem includes are rejected; optimization and local SPIRV-Tools validation
   are disabled. Validation is done by the HOST test; production integration still
   needs failure reporting, memory/queue budgets, cache identity and atomic writes.
   This is an adapter, not a full drop-in shaderc API implementation.

3. Build: use WSL Ubuntu, clang/clang++ 21, CMake, Ninja and the existing PS5 SDK.
   Clone https://github.com/KhronosGroup/glslang into
   /home/tomer/ps5-za-native/shader-prewarm-research/glslang and check out
   f0bd0257c308b9a26562c1a30c4748a0219cc951 (16.2.0).
   Run bash port/shader-prewarm/build-research.sh from the original workspace.
   The script verifies the pin; it does not download dependencies automatically.
   It builds native host and PS5 archives, links a PS5 ELF, then runs host tests.
   All build outputs are under /home/tomer/ps5-za-native/shader-prewarm-research.
   Archive/ELF build success is not proof of execution on a PS5.

4. link-check.sh uses the existing native-title link recipe: direct-memory heap,
   pthread wrappers, libc++, libc++abi, libunwind, RADV and SDK imports.
   The initial link exposed an unsupported link() import pulled from libc++
   filesystem operations. --gc-sections removed unused sections and the import
   audit then passed. The installed title link command has NOT been changed.
   Before integration, either validate GC against the full title or avoid pulling
   those unused filesystem operations through a carefully scoped link strategy.

5. Reproduce forecast on Windows using the project's gen-venv Python:
   python port/shader-prewarm/forecast.py --out evidence/shader-prewarm-research-20261028
   python port/shader-prewarm/test_forecast.py
   python port/shader-prewarm/inspect_assets.py --out evidence/shader-prewarm-research-20261028
   The portable adapter tests require captured GLSL already in the workspace.
   No game files, vendor SDK or compiled game archive are included in delivery.

Remaining integration work, in dependency order:
   A. A bounded PS5 compiler probe: valid and malformed shaders, time, peak heap,
      repeated calls, worker lifetime and shutdown. Preserve the installed game.
   B. Add local compile fallback after an SPIR-V cache miss, retaining the existing
      PC fallback until hardware behavior is verified. Version the compiler cache.
   C. Capture stable program/pipeline recipes and asset/area context. Serialize
      source-content IDs and plain state fields, NEVER Prog* or guest addresses.
   D. A deduplicated prewarm queue: common UI/FX + party + selected area's predicted
      encounters. Compile known recipes before gameplay/loading, then a bounded
      low-priority worker. Decide concurrency only after hardware measurements.
   E. Explore model/material/BNSH extraction for never-seen variants. Captured
      recipes alone cover encountered content; they do not discover all shaders.

Why two caches matter:
   The game's Maxwell shader programs are translated using ShaderKey and guest
   memory-window state to GLSL, then compiled to SPIR-V. Vulkan driver pipelines
   additionally require vertex formats, attachment formats, blend/depth/sample
   state, layouts and other fields. Loading SPIR-V or calling vkCreateShaderModule
   alone does not prebuild those pipelines. PipeKey currently contains a Prog*
   and is an in-process key only; persisting raw bytes would be incorrect.
   The existing periodic VkPipelineCache save helps repeat visits, but is not an
   enumerable list of recipes for new content. A PC driver cache is not a PS5 cache.

Primary references:
   https://github.com/KhronosGroup/glslang/tree/f0bd0257c308b9a26562c1a30c4748a0219cc951
   https://docs.vulkan.org/guide/latest/pipeline_cache.html
   Isolated runtime: runtime/nvn/vulkan/exec.c (Prog, get_program, PipeKey, build_pipeline)
   Current shim: port/shaderc-cache/shaderc_cache.c
   Driver cache: port/title/pipeline_cache.h
   PS5_Vulkan/docs/CTS.md: the existing title heap is required for glslang allocation.

This is an engineering feasibility result, not a promise that every first-use
stall is a shader or that all future encounters are now prepared.
