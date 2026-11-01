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

## Shared resource turns — mandatory for every agent (2026-10-31)

Before PC testing, heavy tests that compete for the machine, or any console use, read `workbench/cards/resource-queues.md`.
Use the **canonical checkout's** `zw pc-queue` (PC) / `zw queue` (console), including from other worktrees; do not create private production queues.
FIFO: no waiter means unlimited use with heartbeat every <=30 seconds. First waiter sets a fixed handoff deadline: **5 minutes PC (provisional), 10 minutes console**, including cleanup.
Poll while working/waiting, stop starting work that cannot fit, and release only after your activity stops and the resource is safe. Never steal a lease or kill another agent's process at the deadline.
Unfinished work re-enqueues at the tail with a new request ID. Do not hold one resource while waiting for the other.
PC proof before console; only Tomer's evidenced approval for an urgent fix or long PC queue permits bypassing PC testing, never the console queue.
Every console installation must target a separate side application, or be an update to the main game only after the exact candidate passed relevant tests with recorded evidence. Untested candidates, including supposedly small or urgent fixes, must not replace the main game. The side application must have a distinct title/install location and isolated writable data, saves, mods and config; never use PPSA91761 as a test slot without approval. PC-bypass approval does not authorize an untested main-game update. Preserve the working main game even if the agent cannot repair or roll back its candidate within the turn. Main-game baseline promotion requires the same passed-test evidence.
Console handoff must restore its entry baseline OR register a new baseline with final readback hashes, full feature/config/mod/asset manifest, source/rebuild instructions and rollback. Preserve saves and other agents' features.
At your turn, re-read the latest baseline. If it changed, merge/rebuild and requeue; never install an old candidate by merely repinning expected_base.
`zw pc run` / console verbs require resource AGENT/TICKET/TOKEN environment variables; see the card. Direct/legacy tools are bound by the same rules.
This policy does not grant console access, promote any existing release, or claim that an unobserved console is idle. Existing agents must re-read it before their next resource operation.

### Tomer's complete request — verbatim

יש לנו חוקים לבנייה לפוקימון שעל הPS5 אבל אני ראיתי מספיק מקרים שסוכנים שונים "רבים" על המשאבים של המחשב או הקונסולה, לכן אני רוצה לעשות את זה ככה, יהיה לנו תור שימוש במחשב לבדיקות ותור התקנות בקונסולה, סוכן שרוצה לבצע בדיקות הולך לתור במחשב ונרשם שם, אם יש שם כבר סוכן שרץ אז הוא מחכה שהסוכן יסתיים, סוכן יכול להתשמש במשאב ללא הגבלה כל עוד אף אחד אחר לא נרשם לתור, מהרגע שמישהוא נרשם לתור הוא מקבל לסיים תוך 5 דקות את מה שהוא עשה (אולי 10 נחליט בהמשך כמה זמן זה מספיק) אחרי זה הוא מסיים ואם הוא לא סיים את כל הבדיקות הוא ירשם מחדש לתור וישתמש בו... בתור של הקונסולה, גם כן אותו סגנון סוכנים יכולים לקבל אישור להשתמש לצורך בדיקה (כלומר לדלג על בדיקה במחשב) במקרים מיוחדים כמו תיקון חשוב או שהתור במחשב מאוד ארוך, וכמו בתור במחשב אם מישהוא נרשם לתור בזמן שסוכן אחר משתמש בקונסולה הוא צריך לסיים תוך 10 דקות + לוודא שהוא מחזיר במצב שהוא בסיס, כלומר או שהוא מוריד את העדכון שלו עד שהוא מסיים לעבוד עליו בפעם הבאה או שהוא רושם את העדכון שלו בתור הבסיס הכי חדש ואז מי שנרשם בתור צריך לדעת שהוא לא יכול להרוס את זה

### Tomer's additional console-install rule — verbatim (2026-10-31)

אוקי הכנס גם לחוק של התור קונסולה ככה: "כל התקנה של הקונסולה חייבת להיות בתור אפליקציה צדדית או אם עבר בדיקות בתור עדכון על המשחק הראשי, ככה גם אם יש עדכון שאנחנו חושבים שהוא קטן והוא לא טוב המשחק הראשי לא יהרס גם אם הסוכן לא יכול לתקן בזמן"
