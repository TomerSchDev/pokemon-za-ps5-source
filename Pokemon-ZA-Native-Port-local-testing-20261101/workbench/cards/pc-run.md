# Card: run the PC build — bounded run, screenshots, input, FPS, logs

The PC runtime (`lasrecomp.exe`) runs the same translated game as the PS5. It is the cheap proof step before any console build.
Each run gets a **new** data root (the working dir), a **copied** save, its own `larecomp.ini`, and only its own process is killed at the budget.
Take a turn first: `cards/resource-queues.md`.

```powershell
zw pc run my-test --seconds 120 --save-src <dir holding save_0/main> --shot-at 900,1800 --input "240:A:8,420:A:8"
zw pc run hebrew-check --seconds 90 --mods <folder of mod folders> --fps 60
zw pc shots my-test          # list captures (build/frames/frame_NNNNN.png)
zw pc fps my-test            # [vk] fps intervals from stderr.log
```
`zw pc run` = `hebrew-lab/tools/run_poc.py` with `--game` set to the local game copy. Runs land in `PS5-13.60\hebrew-lab\runs\<NAME>` (`run.json`, `stdout.log`, `stderr.log`, `build/frames/`).
Other flags: `--capture-every N`, `--language`, `--font TTF`, `--cache-src <old run>` (seeds the shader cache, much faster), `--env K=V ...`.
Windows `--junction-mods --mods IMMUTABLE_LOCAL_SNAPSHOT` references a verified directory junction instead of creating thousands of hardlinks; proven by `pc-fifty-boltund-bite-r38` (23,676 assets loaded, Bite victory). Keep the snapshot unchanged while any run uses it. Do not combine with `--link-mods`.

## Runtime knobs (env, set through `--env`)
| Want | Env |
|---|---|
| Screenshot at frames | `LARECOMP_SHOT_AT=f1,f2` (ascending) → `build/frames/` |
| Screenshot every N frames | `LARECOMP_SCREENSHOT_EVERY=N` (+ `LARECOMP_EXIT_AFTER_SHOT`) |
| Scripted input | `LARECOMP_INPUT=frame:NAME[:len],...` (len default 10). NAME: A B X Y L R ZL ZR PLUS MINUS UP DOWN LEFT RIGHT LSTICK RSTICK STICK_UP/DOWN/LEFT/RIGHT RSTICK_* STICK_<deg>. Setting it blocks user input |
| FPS | `LARECOMP_FPS=60` forces 60, no fallback (`--fps 60`). ini `fps60=1` = 60 with fallback to 30 below `LARECOMP_FPS60_MIN` (default 50) for 5 s. `LARECOMP_PRESENT_INTERVAL=0` = unpaced: the sim speeds up, so don't use it for gameplay |
| FPS log period | `LARECOMP_FPS_INTERVAL` seconds (default 2): `[vk] t=… frame N X fps max Yms` |
| File reads | `LARECOMP_LOG_FILES=1`, `LARECOMP_LOG_READS=<file>` (used by the species pilot) |
| MRT resource observation | `LARECOMP_COPY_TRACE=N LARECOMP_DEBUG_FRAME=N LARECOMP_LOG_FSHASH=1`; DEBUG_FRAME retains dense texture indices; FS log hash covers512 native bytes, not full code |
| Font for Hebrew | `LARECOMP_FONT=<ttf>` |

## Other runners (when you need their specific features)
- Cheat/UI builds with a custom DLL: `port/ui-v2/pc/run-pc-game.py --exe --game --dll --save FILE --out NEW [--seconds] [--input] [--shots] [--item-id]`. All DLLs must sit next to the exe. Exits 3 if the fixture save changed.
- Hebrew QA with pass/fail: `zw hebrew qa_translation <name> --package DIR --scenario menu_save|appearance`.
- Species pilot: `zw species run_pilot ...`.
- PC runtime/DLL builds: `port/ui-v2/pc/build-pc-runtime.sh`, `port/ui-v2/pc/relink-game-dll.sh` (Git Bash; `README-pc-build.md`). The stock `lasgame.dll` needs the `stockname` exe copy (else error 126).

## Gotchas
- Windows `1455` caused r35's loading crash. `--preflight-only` reads capacity; runner needs 2 GiB disk + 18 GiB commit (r34 private16.27 GiB). Named mutex serializes games; canonical queue required. Runner heartbeats every20s and stops its own child at the30s cleanup margin (r41 verified,23s remained). Never stop another run to acquire a turn.
- **"guest address range" collision**: a random early failure. `run_poc` retries; rerun with a new NAME if it persists.
- `tools/labs/pokeza-pc-scripts/*` are a scripts-only snapshot; most expect NAS folders next to them. Use the runners above.
- Never point a run at a real save. Never write into the game folder.
- 2026-10-31 standard-mrt-trace-r1 reached the city in one isolated120s run; MRT1→3 sampled consumers recorded, source/copied save SHA unchanged. Prefix matches and material identity remain qualified: Work/CodeAudit/ShaderResearch/STANDARD-MRT-LIVE-HE.md.
