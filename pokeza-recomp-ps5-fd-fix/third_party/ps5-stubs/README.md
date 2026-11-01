# ps5-stubs — MINIMAL STUB HEADERS for compile-only checks (not real libraries)

Used by `tools/ps5/compile-runtime.sh` (and `make PLATFORM=ps5`, last in the include path) only when the real headers
are not at hand. Nothing here has an implementation and nothing links.

- `shaderc/shaderc.h`: the few declarations `runtime/nvn/vulkan/shaders.c` uses, with shaderc's real enum values.
- `SDL3/`, `libav*/`, `libswscale/`, `vma/`, `vulkan/`: markers that stop the compile with one clear `#error` naming
  where the real headers are (the PC's: SDL3 3.4.18 in `research/pokeza-pc/runtime-opt-r1`, MSYS2's `ucrt64/include`
  for shaderc / FFmpeg / VMA, `PS5_Mesa/include` for Vulkan — `tools/ps5/compile-runtime.sh` finds them, the Makefile
  takes `PS5_DEPS_INC`).

Real headers always win: they are earlier in the include path.
