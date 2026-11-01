שמור את כל מה שמתחת לקו כחוקים קבועים לפרויקט הזה (בזיכרון / ב־rules / ב־AGENTS.md שלך), ופעל לפיהם בכל משימה מעכשיו. אל תסכם אותם; שמור אותם כפי שהם.

---

# Z-A PS5 project — standing rules

Project: Pokémon Legends: Z-A 2.0.2, statically recompiled to native PS5. Owner: Tomer. Always report to Tomer in Hebrew.
Repo: `C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port`. All tools are reached through `.\zw` at the repo root.

## Start of every task (cheap first)
1. `.\zw card rules` — hard rules (1 min). Then `.\zw card <topic>` for **only** the card your task needs:
   `atlas, build, console-install, console-observe, crash, fps, hebrew, mods, pc-run, randomizer, species`.
2. `.\zw doctor` if anything seems missing.
3. Do **not** read the long handoff/analysis documents unless a card points you to one for your exact question.

## Tools — use these, don't rewrite them
| Need | Command | Console? |
|---|---|---|
| Find game code | `zw atlas find/str/fn/who-calls/callees/path/class` | no |
| Record a finding | `zw atlas annotate <addr> "<name>" --subsystem S --confidence proven\|derived\|assumed --source file:line` | no |
| Symbolize crash | `zw crash <klog> --elf <llvm-pie.elf>` | no |
| Build / verify eboot | `zw za profiles\|doctor\|verify\|reproduce\|build r29-ui ...` | no |
| PC run + screenshots | `zw pc run NAME --seconds N [--shot-at F,..] [--input "f:BTN:len,.."] [--fps 30\|60] [--mods DIR] [--save-src DIR]` | no |
| PC results | `zw pc shots NAME`, `zw pc fps NAME` | no |
| Lab tools | `zw hebrew <script> ...`, `zw species <script> ...` | no |
| Install turn | `zw queue status\|enqueue\|claim\|heartbeat\|complete\|release` | no (local) |
| Console screenshot | `zw shot --out DIR --console-ok` | yes |
| Console FPS | `zw fps measure SECONDS --out DIR --console-ok`, `zw fps set 0\|1 --console-ok`, `zw fps analyze CSV` | yes |
| Console input / log | `zw input BTN FRAMES --console-ok`, `zw klog --out FILE --seconds N --console-ok` | yes |
If a tool you need isn't in `zw`, add one `FORWARD` line in `workbench/zw.py`. Don't write a parallel tool.

## Hard rules
- **Console 192.168.1.135**: only in a session Tomer coordinated, with the game state known. Never kill an unknown process. Add `--console-ok` only then. One observer caller at a time, and no FTP traffic during `fps measure`.
- **Saves**: back up and verify before any console change. Never restore an old save over newer progress. PC runs only with their own data root and a copied save.
- **eboot install**: upload as `.new` → readback → rename → readback, and always keep a rollback. Take a turn in `zw queue` first.
- **Titles**: PPSA91762 = randomizer (Tomer plays it). PPSA91761 = vanilla: don't touch without approval.
- **Config**: `/app0/performance-options.txt` must be exactly `optimized`. r24+ knobs go only in `perf-r24-options.txt`. `force60` is for measurement only.
- **Game data, text, saves, keys**: never in git, never uploaded. Other Pokémon games' assets come only from dumps of Tomer's own Switch, never from `Downloads\Pokemon` or the internet.
- **Builds**: always into a **new** output folder under `/home/tomer/ps5-za-native/`. Prove on PC before the console when possible. Ship with Hebrew install, test and rollback instructions.
- **Git**: commit only when Tomer asks.
- **UI work**: show Tomer mockups before building.

## How to work
- Code questions go to the atlas before reading `aot/main` C. Every name or address you prove gets `annotate`d immediately.
- Facts listed under "Facts" / "Known facts" in a card are proven: don't re-research them.
- Claims need evidence (paths, hashes, logs, screenshots). Say "not tested on hardware" when that's the truth.
- When you finish: add any new proven fact (one line) to the relevant card in `workbench/cards/`, keeping each card under ~40 lines, and report to Tomer in Hebrew.
