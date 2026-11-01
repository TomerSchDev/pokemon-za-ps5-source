# ZA Recomp runtime for Windows without the ImGui UI (`lasrecomp-uiv2.exe`)

Facts only. Built 2026-10-31 on this PC (Windows 11 10.0.26200, i7-12700F, RTX 3050) from a copy of the runtime
source repo `pokeza-recomp-ps5` (branch `ps5`, commit `d06e23f22dcde3f6827c3f953b4582d93b87824a`, repo untouched).
Everything built lives in `..\..\..\..\ui-v2-work\pc\` (outside git; no game data in git). Scripts here:

| file | role |
|---|---|
| `build-pc-runtime.sh` | copies the source, sets up SDL3 3.4.18, compiles the runtime objects + cheat helpers, links the exe, verifies it |
| `pc-runtime.mk` | `include Makefile` + targets: the object set (RT_OBJ + BACKEND_OBJ minus `imgui_glue.o`), flag printers |
| `pc_entry_stub.c` | the no-UI stand-ins (the exact symbol list below); the parent replaces this file |
| `pc_guest_calls.c` | forwarders for the five `f_<addr>` game functions `za_items.c` calls (the helper now lives in the exe) |
| `relink-game-dll.sh` | `lasgame-uiv2.dll`: the reference AOT objects + r28 hook units linked against the exe's import library |
| `run-pc-game.py` | bounded scripted run with an isolated data root and a copy of the fixture save |

## Prerequisites found on this PC

- MSYS2 UCRT64 (`C:\msys64`): clang 21.1.7, lld 21.1.7, GNU make 4.4.1 (`/usr/bin/make`), binutils `windres`,
  `dlltool`, `objdump`, `nm`, `strings` (no `llvm-nm` / `llvm-readobj` / `gendef` installed: binutils used instead).
- MSYS2 packages: ffmpeg 8.0.1-2 (`avcodec-62` / `avformat-62` / `avutil-60` / `swscale-9`, the same ABI the shipped
  DLLs have), shaderc 2025.4-1 (`libshaderc_shared`), vulkan-headers + loader 1.4.328.1, vulkan-memory-allocator 3.3.0
  (`vma/vk_mem_alloc.h`), sdl3 3.2.28-1 (too old, see below).
- Python 3.12 (`C:\Users\Tomer\AppData\Local\Programs\Python\Python312\python.exe`) for `run-pc-game.py`
  (`hashlib.file_digest` needs 3.11+).
- The shell: the Bash tool / Git Bash here is MSYS2's bash (`uname` = MINGW64_NT, `/` = `C:\msys64`); the scripts put
  `/c/msys64/ucrt64/bin:/c/msys64/usr/bin` first on PATH themselves.

## SDL3 handling

- The runtime uses SDL 3.4 API (`SDL_SavePNG` in `nvn/vulkan/device.c`, `SDL_LoadPNG` in `nvn/vulkan/textures.c` and
  `paths.c`). MSYS2's headers/import lib are 3.2.28 and lack them. `C:\libs\SDL3` holds a 3.3.6 prerelease (not used).
  Nothing on the NAS Research folder.
- The shipped `hebrew-lab\runtime\SDL3.dll` is `SDL-release-3.4.18-0-g829a65d76` (sha256
  `4659d5a1e240e7d58fb92808f84afeb53395818cec62385d4796b72977a7d859`).
- Headers: the official `SDL3-devel-3.4.18-mingw.tar.gz` from github.com/libsdl-org/SDL releases (sha256
  `049b9dd711e3fb3f8d84feb998dfec54a75e17cf539c4a80ff4d058d839771cf`, pinned in the script), extracted to
  `ui-v2-work\pc\deps\sdl3-devel-3.4.18\`, its `x86_64-w64-mingw32\include` copied to `deps\sdl3\include`.
- Import library: generated from the shipped DLL itself: `objdump -p SDL3.dll` export table (1271 names) ->
  `deps\sdl3\lib\SDL3.def` -> `dlltool -d SDL3.def -D SDL3.dll -l libSDL3.dll.a -m i386:x86-64` (sha256
  `6b58154d5d18f9943eabd1573a376308eb2cfd392c8795ed51c64adef4a4ff9a`). The package's own `libSDL3.dll.a` is kept in
  `deps\sdl3\lib-package\` for reference only.
- The Makefile sees it as `DEPS=../deps/sdl3` (`-I../deps/sdl3/include`, `-L../deps/sdl3/lib`; relative because make
  runs inside `ui-v2-work\pc\src`). The exe imports 55 `SDL_*` functions, every one exported by the shipped DLL
  (checked by `build-pc-runtime.sh verify`, incl. `SDL_SavePNG` / `SDL_LoadPNG`).

## Runtime objects

`build-pc-runtime.sh objects`:

1. `ui-v2-work\pc\src\` = copy of `runtime\`, `third_party\smaa`, `third_party\imgui\imstb_*.h` (headers only:
   `nvn/texpatch.c` includes imgui's stb_truetype copy; no ImGui source is compiled), `tools\`, `docs\icon`,
   `Makefile`, plus `pc-runtime.mk`. `SOURCE-REVISION.txt` records the commit.
2. `make -f pc-runtime.mk -j20 PLATFORM=windows GAMELIB_ID=7b03da558e0b6144 DEPS=../deps/sdl3 B=build pc-objects`
   - flags are the Makefile's: `RTFLAGS = -O2 -g -fno-strict-aliasing -Wall -Wno-unused-function -Iruntime
     -Iruntime/nvn -I../deps/sdl3/include -D_FILE_OFFSET_BITS=64 -D_POSIX_THREAD_SAFE_FUNCTIONS -D_CRT_RAND_S
     -DWIN32_LEAN_AND_MEAN -DNOMINMAX`; `gamelib.o` and `gamebuild.o` get `-DGAMELIB_ID='"7b03da558e0b6144"'` and
     `gamebuild.o` the Makefile's `GAMELIB_CFLAGS` / `GAMELIB_SHARED`; `vma.cpp` with `CXXFLAGS` + `OSFLAGS`;
     `platform/windows_rc.o` via `windres -I docs/icon -O coff` (icon + the UTF-8 code page manifest: embedded,
     checked with `strings`).
   - 64 objects: 56 `RT_OBJ` (runtime/*.c, hle/*.c, services/*.c, nvn/*.c, nvn/maxwell/translate.c,
     platform/windows.c) + 7 Vulkan backend objects (compat, compat_rp, device, exec, shaders, textures, vma) +
     windows_rc.o. `imgui_glue.o` and all of `runtime/ui/*.mm` / `third_party/imgui` are left out.
   - Object list: `ui-v2-work\pc\src\build\pc-objects.txt` (one path per line, relative to `src\`).
   - No source change was needed: the ps5 branch compiles for Windows as is (2 upstream make warnings about the
     `GENOBJ ?= $(B)/obj  # ...` line, nothing from clang with these flags).
3. Cheat helpers -> `src\build\helpers\` (listed in `build\pc-helpers.txt`), compiled with the game DLL's `GENFLAGS`
   minus `-fvisibility=hidden` (they must be exported), i.e. `-O1 -fno-strict-aliasing -Wno-return-type
   -Wno-unused-label -Iruntime -D_FILE_OFFSET_BITS=64 -march=x86-64-v3 -DGUEST_VOLATILE -g -I<port/cheats-r28>
   -I<port/cheats-r27> -DGAMELIB_ID="7b03da558e0b6144"`:
   - `port/cheats-r28/za_items.c` (+ `-DZA_ITEMS_TRACE=1`; sha256 `ebd16bf7...` as in pc-build-05),
   - `port/cheats-r27/za_money.cpp` (`-std=c++20 -fno-exceptions -fno-rtti -DZA_MONEY_TRACE=1`),
   - `pc_guest_calls.c` (RTFLAGS): `f_70002bc8ec f_70002bc9d0 f_700099e47c f_7000a5a228 f_700048963c` resolved through
     `dispatch_lookup()` on first call (inside the DLL these were direct calls to hidden units; the exe cannot link
     against the DLL).
   `ZA_TRACE=0` drops the trace defines; `PC_HELPERS=0` leaves the helpers out entirely.

## The exe and the link interface for the parent

`build-pc-runtime.sh link ENTRY... [-- LDEXTRA...]` (runs `objects` first, incrementally):

- ENTRY files: `.o` used as is; `.c` compiled with RTFLAGS (+ `ENTRY_CFLAGS`); `.cpp/.cc` with CXXFLAGS + OSFLAGS
  (+ `ENTRY_CXXFLAGS`, e.g. `-std=c++20 -include pc_compat.h -I../src`). Each gets `-DPC_RT_VERSION="<LARECOMP_VERSION
  of launcher.mm>"`.
- Link (cwd `src\`): `clang++ -o OUT/link/lasrecomp-uiv2.exe @build/pc-objects.txt <helpers> <entry objects>
  -fuse-ld=lld -Wl,--stack,16777216 -L../deps/sdl3/lib -lSDL3 -lavformat -lavcodec -lavutil -lswscale -lvulkan-1
  -lwinmm -lole32 -lshell32 -lcomdlg32 -luuid -lshaderc_shared -Wl,--export-all-symbols
  -Wl,--out-implib,build/lasrecomp.dll.a`, then moved to `OUT\lasrecomp-uiv2.exe`; `OUT\lasrecomp.dll.a` copied.
  The name is fixed: the import library records it (`dlltool -I` prints `lasrecomp-uiv2.exe`) and `lasgame-uiv2.dll`
  is bound to that name. `OUT` = `ui-v2-work\pc\out\` by default.
- The DLLs: every `*.dll` of `hebrew-lab\runtime\` (copied, never moved) + `Baloo2-SemiBold.ttf` + `icon.png` are put
  next to the exe. The exe imports: SDL3, avcodec-62, avformat-62, avutil-60, swscale-9, vulkan-1, libshaderc_shared,
  libgcc_s_seh-1, libstdc++-6, libwinpthread-1 + system DLLs. `verify` checks each is present.
- `RT_MAIN_SYMBOL=za_game_main` compiles `runtime/main.c`'s `main()` under that name if the entry wants its own
  `main()` (as the PS5 title does); default: the runtime's `main()` is the entry point.
- `build-pc-runtime.sh stub` = `objects` + `link pc_entry_stub.c` (what was built here).

### The stub symbol set (what ENTRY must define)

Every symbol the no-UI runtime objects need from "the UI" (link verified: nothing else was missing):

```
const char *rt_version(void);                                     // runtime/main.c log_system
bool menu_handle_event(const SDL_Event *e);                       // nvn/vulkan/device.c
bool menu_is_open(void);
bool menu_input_captured(void);                                   // hle/input.c
void menu_apply_window_requests(void *sdl_window);                // nvn/vulkan/device.c
void menu_render(void *cmd, uint32_t target_w, uint32_t target_h);
void menu_test_open(void);
void menu_notice(const char *text, int seconds);                  // hle/framepace.c
int  menu_keyboard_run(const char *initial, int max_len, char *out, int cap);   // hle/swkbd.c
void launcher_prompts_kick(const char *root);                     // runtime/main.c
void launcher_run(const char *root);                              // runtime/main.c (not called with --play)
void input_note_rstick(int32_t ry);                               // hle/input.c
void save_editor_frame(uint64_t frame);                           // nvn/vulkan/device.c
void save_editor_file_read(const char *path, uint64_t addr, int64_t off, int64_t size);   // services/fs.c
void shader_tour_tick(uint64_t frame);                            // hle/warp.c
uint64_t chaos_dgnmap_obj(void);                                  // hle/warp.c
int  inventory_items_cursor(void);                                // hle/pets.c
```

Plus the two imports of `lasgame-uiv2.dll` that are PC-diagnostic hooks of the r28 proof, as no-ops:
`void za_items_pc_batch(void *cpu)` (called by hook units main_097/220/339 after `za_items_pump`) and
`void za_money_pc_start(void)` (called by the DLL's `lasgame_tables`). The exe exports everything
(`--export-all-symbols`: 897 symbols), so the DLL also resolves `rt_dispatch rt_udf rt_brk rt_svc rt_ticks
rt_setjmp_site fnprof_hit g_fnprof` and the helpers `za_items_pump za_items_reset za_cheat_money_component
za_money_lifecycle_reset` from it.

## The relinked game DLL `lasgame-uiv2.dll`

`relink-game-dll.sh all` (`verify-aot` + `link`), `symbols` for the import report:

- AOT objects: `\\TheOnePiece\...\Research\pokeza-pc\update-2.0.2-20261025\aot\obj\` copied once to
  `ui-v2-work\pc\aot-obj\` (1412 `.o`, 455,677,473 bytes, 225 s). `verify-aot`: count and total bytes equal, 24
  sha256 samples equal (`dll\aot-verify.txt`); `dll\objects.rsp` is the NAS `aot\objects.rsp` (1412 lines, its paths
  point at the old `C:\Users\Tomer\Documents\Codex\...` location that no longer exists).
- `symbols`: across all 1412 objects the only non-game imports are `g_fnprof fnprof_hit rt_dispatch rt_udf
  ___chkstk_ms rt_setjmp_site __imp__setjmp(6) rt_ticks rt_svc` + the table symbols (`dll\aot-undefined-symbols.txt`);
  `pc_compat.o` stays in the DLL for the six `__imp__setjmp` references.
- Hook units: the 8 audited objects + `gamelib_entry.o` + `pc_compat.o` of
  `port\cheats-r28\work\pc-build-05\obj\` copied to `dll\hooks\` (sha256 in `dll\hooks\SHA256SUMS.txt`). Their imports
  (nm -u): `za_items_pump za_items_pc_batch za_items_reset za_cheat_money_component za_money_lifecycle_reset`
  (hooks), `za_money_pc_start` (gamelib_entry).
- `dll\objects-uiv2.rsp`: the reference rsp with the local object paths, the 9 stems replaced by `dll\hooks\`,
  `pc_compat.o` appended; `za_items.o`, `za_money.o`, `pc_command.o` NOT appended (1413 objects).
- Link (cwd `dll\`): `clang++ -shared -fuse-ld=lld -static-libstdc++ -static-libgcc -Wl,--stack,8388608
  @objects-uiv2.rsp OUT/lasrecomp.dll.a -o OUT/lasgame-uiv2.dll` (4 s; the rsp must hold `C:/...` paths: clang
  reads it itself, MSYS2 only translates `/c/...` on the command line); `OUT\lasgame-uiv2.dll.id` = `7b03da558e0b6144`.
- Result: `ui-v2-work\pc\out\lasgame-uiv2.dll`, 380,975,104 bytes, sha256
  `fca8958ba2189d58370ba7b2e70c83c6520df1025d793c39a5d2d3ee66402598`. `objdump -p` (`dll\dll-verify.txt`): it imports
  from `lasrecomp-uiv2.exe` exactly `fnprof_hit g_fnprof rt_dispatch rt_setjmp_site rt_svc rt_ticks rt_udf
  za_cheat_money_component za_items_pc_batch za_items_pump za_items_reset za_money_lifecycle_reset za_money_pc_start`;
  other imports KERNEL32 + api-ms-win-crt-*; the one export is `lasgame_tables`. Hook object hashes
  (`dll\hooks\SHA256SUMS.txt`): gamelib_entry `5e51de52...`, main_097 `1538268b...`, main_1035 `4ccb34c3...`,
  main_220 `56bf7864...`, main_303 `9aaccaf5...`, main_315 `6a3a1106...`, main_333 `8d993da3...`, main_339
  `f3ce7667...`, main_384 `23f9e4ee...`, pc_compat `0972eb9c...`.
- The STOCK `lasgame.dll` (qa-game-reference, sha256 `a3e0da9a4f07e82c5db23f7eec90982b25edc0e7f240e73503a65e5f510b78fe`,
  the same bytes as the NAS `aot` build result) and pc-build-05's DLL import from a module named `lasrecomp.exe`: a
  process whose exe is `lasrecomp-uiv2.exe` cannot load them (`LoadLibrary` error 126, seen in the first attempt).
  `build-pc-runtime.sh stockname` makes `ui-v2-work\pc\out-stockname\lasrecomp.exe` (a byte-identical copy of the
  uiv2 exe) + the DLLs for runs with the stock DLL. `lasgame-uiv2.dll` needs no such copy.

## Runs (`run-pc-game.py`)

Isolated data root per run under `ui-v2-work\pc\runs\<run>\`: `save\save_0\main` = copy of the fixture
`pc-perf-c2\saves\updated\save_0\main` (sha256 `f5c64116c3fa0c39b407272b0646212c7bb27fdbb5bfbbf3601e232ecebd3c27`,
read-only, unchanged after every run), `larecomp.ini` as the r28 harness wrote it, env `LARECOMP_DATA_ROOT /
LARECOMP_SAVE_DIR / LARECOMP_SETTINGS / LARECOMP_GAME_LIB / LARECOMP_NO_USER_INPUT=1 / LARECOMP_INPUT / LARECOMP_SHOT_AT /
LARECOMP_REEXEC=20 / LARECOMP_SCREENSHOT_EVERY=0 / LARECOMP_WAIT_DUMP=10 / LARECOMP_SKIP_WHY=1 / LARECOMP_NO_UPDATE_CHECK=1`,
game root argument = `hebrew-lab\qa-game-reference-20261030` + `--play`, bounded by `--seconds`, then only the child
PID is terminated. PATH is not extended (the exe folder must hold every DLL). Screenshots: `<run>\build\frames\`.
