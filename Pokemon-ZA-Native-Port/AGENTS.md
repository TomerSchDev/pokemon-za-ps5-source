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
Keep operation and verification journals local during a resource turn. Archive the final journals/evidence to the NAS after the turn with content verification; do not make each progress update depend on a NAS write. Keep the verification itself complete and do not bypass candidate/install gates.
Readiness before enrollment (2026-11-01): before enqueue/submit to either resource queue or the structured testing journal, finish compilation/linking/packaging and stage every required artifact, dependency, runner, config and isolated test fixture. Record exact artifact paths/hashes, the ordered test commands/inputs, expected outcomes, time budget, evidence collection and a concrete bug/stop/cleanup/rollback plan. No speculative place-holding tickets and no deferred compilation, dependency setup or test-plan design while queued or holding a turn, even if nobody else waits. Backups and final live verification must also be complete BEFORE enrollment, so an installation turn begins with installation. Arrange earlier coordinated preparation access without interfering with an active owner or an FPS measurement; this does not authorize behind-the-owner console access. If evidence loses validity or state changes while waiting, withdraw the pending request, refresh outside the installation queue and re-enroll only ready. If a bug or changed baseline requires rebuilding/preparing, stop, preserve evidence, hand off safely under the existing ownership/offline rules, prepare outside the queue and enqueue a new request at the tail only when ready again. Never rewrite another agent's ticket or discard the disconnected-console protection as a shortcut.
FIFO: no waiter means unlimited use with heartbeat every <=30 seconds. First waiter sets a fixed handoff deadline: **5 minutes PC (provisional), 10 minutes console**, including cleanup.
Console connectivity exception: when the console is unavailable, retain the same ticket, owner and FIFO position; pause its handoff/liveness timers. Never complete, release or requeue merely because offline time exceeded the limit. Guarded FTP/HTTP failures record the pause automatically; `zw queue connection` records observed manual outages/reconnections. Resume remaining time after reconnection; if the outage was only detected after the old deadline, grant the owner a fresh 10-minute handoff window. PC timing is unchanged.
Poll while working/waiting, stop starting work that cannot fit, and release only after your activity stops and the resource is safe. Never steal a lease or kill another agent's process at the deadline.
Unfinished work re-enqueues at the tail with a new request ID. Do not hold one resource while waiting for the other.
PC proof before console; only Tomer's evidenced approval for an urgent fix or long PC queue permits bypassing PC testing, never the console queue.
Every console installation must target a separate side application, or be an update to the main game only after the exact candidate passed relevant tests with recorded evidence. Untested candidates, including supposedly small or urgent fixes, must not replace the main game. The side application must have a distinct title/install location and isolated writable data, saves, mods and config; never use PPSA91761 as a test slot without approval. PC-bypass approval does not authorize an untested main-game update. Preserve the working main game even if the agent cannot repair or roll back its candidate within the turn. Main-game baseline promotion requires the same passed-test evidence.
Enforcement: use canonical `zw install-bundle fingerprint|plan|install`. The immutable queued job declares deployment.mode=main_update with a SHA-256-bound test report (startup + relevant regression, passed results and verified evidence), OR side_app with a different titleId, matching param.json, and confined artifact destinations. Legacy/unproved main writes are rejected by the shared FTP guard, including uploads before begin-install. Do not bypass the guard, fabricate test reports, repin an old adapter without review, or use an older checkout to write. The read-only `Open-Queue-Monitor.vbs` viewer shows both queues independently of the agent.
Console handoff must restore its entry baseline OR register a new baseline with final readback hashes, full feature/config/mod/asset manifest, source/rebuild instructions and rollback. Preserve saves and other agents' features.
At your turn, re-read the latest baseline. If it changed, merge/rebuild and requeue; never install an old candidate by merely repinning expected_base.
`zw pc run` / console verbs require resource AGENT/TICKET/TOKEN environment variables; see the card. Direct/legacy tools are bound by the same rules.
This policy does not grant console access, promote any existing release, or claim that an unobserved console is idle. Existing agents must re-read it before their next resource operation.

### Tomer's complete request — verbatim

יש לנו חוקים לבנייה לפוקימון שעל הPS5 אבל אני ראיתי מספיק מקרים שסוכנים שונים "רבים" על המשאבים של המחשב או הקונסולה, לכן אני רוצה לעשות את זה ככה, יהיה לנו תור שימוש במחשב לבדיקות ותור התקנות בקונסולה, סוכן שרוצה לבצע בדיקות הולך לתור במחשב ונרשם שם, אם יש שם כבר סוכן שרץ אז הוא מחכה שהסוכן יסתיים, סוכן יכול להתשמש במשאב ללא הגבלה כל עוד אף אחד אחר לא נרשם לתור, מהרגע שמישהוא נרשם לתור הוא מקבל לסיים תוך 5 דקות את מה שהוא עשה (אולי 10 נחליט בהמשך כמה זמן זה מספיק) אחרי זה הוא מסיים ואם הוא לא סיים את כל הבדיקות הוא ירשם מחדש לתור וישתמש בו... בתור של הקונסולה, גם כן אותו סגנון סוכנים יכולים לקבל אישור להשתמש לצורך בדיקה (כלומר לדלג על בדיקה במחשב) במקרים מיוחדים כמו תיקון חשוב או שהתור במחשב מאוד ארוך, וכמו בתור במחשב אם מישהוא נרשם לתור בזמן שסוכן אחר משתמש בקונסולה הוא צריך לסיים תוך 10 דקות + לוודא שהוא מחזיר במצב שהוא בסיס, כלומר או שהוא מוריד את העדכון שלו עד שהוא מסיים לעבוד עליו בפעם הבאה או שהוא רושם את העדכון שלו בתור הבסיס הכי חדש ואז מי שנרשם בתור צריך לדעת שהוא לא יכול להרוס את זה

### Tomer's additional console-install rule — verbatim (2026-10-31)

אוקי הכנס גם לחוק של התור קונסולה ככה: "כל התקנה של הקונסולה חייבת להיות בתור אפליקציה צדדית או אם עבר בדיקות בתור עדכון על המשחק הראשי, ככה גם אם יש עדכון שאנחנו חושבים שהוא קטן והוא לא טוב המשחק הראשי לא יהרס גם אם הסוכן לא יכול לתקן בזמן"

### Tomer's install-enforcement and disconnected-console rule — verbatim (2026-10-31)

תוסיף גם אכיפה בכלי ההתקנה, שסוכן לא יוכל לעדכן את המשחק הראשי בלי הוכחה שהגרסה עברה בדיקות, ובכל מקרה אחר יוכל להתקין רק כאפליקציה צדדית, וגם אם אין גישה לקונסולה, התור לא זז, סוכן לא צריך לצאת מהתור גם אם עבר יותר מהזמן שנקבע אם הקונסולה לא מחובר

## Local structured testing (2026-11-01)

For automated PC game tests, read `workbench/cards/testing.md` and `docs/testing/AGENT_TESTING_RULES.md`.
Use the canonical `zw test prepare|submit|work|status|results|cancel|recover` and shared local config/state for supported structured jobs. Documented legacy runners remain available for unsupported custom-EXE/mod/font/cache scenarios, with the same canonical resource turns, isolation, locks and honest evidence requirements; identify that fallback explicitly.
The worker takes its own canonical PC FIFO turn and keeps the existing Windows game mutex; never create a private production resource queue or run concurrent games.
Every job requires a versioned manifest, timeout, reproducibility metadata, explicit assertions and a terminal result. Missing evidence, crashes, unsupported modes and unexecuted tests never pass.
Logic L1/L2/L3 remain UNSUPPORTED until typed state/tick adapters are proved; use an explicitly submitted supported fallback. Render captures do not establish visual correctness without an approved pinned comparison.
Inspect actual results/logs/images/metrics and `docs/testing/PERFORMANCE_BASELINE.md`; only executed, evidenced rows are verification. Never auto-replace approved baselines or weaken assertions.
Keep all previous resource, console, asset/save, licensing and confidentiality rules in force. This section grants no console or cloud access and does not authorize stale lease/mutex takeover.

### Tomer's readiness-before-queue rule — verbatim (2026-11-01)

תוסיף לחוק כי אני רואה את זה כבר יותר מידי, בשביל להכנס לתור (לכל אחד מהתורים) אתה צריך לבוא מוכן מראש עם הכל, כלומר אם הקובץ המקומפל שאתה רוצה להתקין ועם הסדרת בדיקות שאתה רוצה להריץ ומה לעשות אם יש באג, אני לא רוצה שתורים יתפסו על ידי סוכנים שרק כשמגיע התור שלהם מקמפלים את הציוד

### Tomer's pre-enrollment backup/live-verification rule — verbatim (2026-11-01)

לעתיד גם הגיבוי והאימות חי אחרונים לפני הכניסה לתור, אני רוצה שאם התור שלך מגיע את הישר מתקין, במיוחד בקונסולה

### Tomer's after-turn NAS-journal rule — verbatim (2026-11-01)

לא צריך לכל פעולה לשמור יומן אימות עם הNAS, אפשר לבצע את זה בסוף אחרי התור שלך


## Mandatory current-input check before every build (2026-11-01)

Effective immediately for ALL Z-A projects, tools, agents, subprojects and worktrees, including completed projects and direct/legacy builders: stop forward build work at a safe checkpoint and re-read this canonical file plus `docs/testing/CURRENT_BUILD_INPUT_RULES.md`. Do not start or continue into another build stage until the input check is documented and satisfied. Propagate this instruction to every delegated agent. Research may continue under the provenance rule below.
Before EVERY compile, relink, reproduction, code/tool compilation, mod/data generation, prepared-suite build or packaging step, consult `docs/testing/BUILD_DEPENDENCY_MAP.json` and `BUILD_DEPENDENCY_AUDIT.md`. Refresh the current authoritative component locations/versions, MAIN/release locks and registered-baseline metadata; the audit is a bounded dated snapshot, not an automatically current catalogue.
Record the map hash, actual source/overlay, recipe, compiler/SDK/flags, all direct/transitive inputs, exact resolved locations and hashes, the approved current version/location of each component and evidence of the comparison in a local per-job build-input check. Unknown, unmapped, obsolete or ad-hoc old-worktree/evidence/bytecode dependencies BLOCK the build until the mapping is updated and current replacements are established. Do not silently fall back to whatever old path still exists.
Use the newest approved compatible component, not the newest timestamp. Approved frozen releases and SDK pins retain their identity; do not mutate immutable locks, repin queued jobs or regress the installed JSON-number fix. Migration/control builds must first document the reviewed current candidate inputs and baseline controls; successful replacement is established only after the relevant tests. Historical reproduction is not an implicit exemption for new feature builds.
For RESEARCH ONLY, historical leftovers may be read. Record every relied-on component's exact path, version/hash (measured vs recorded), read time, map node, current authoritative location/version and any superseded_by relationship. If the current counterpart is unknown, record that gap and do not present the finding as current; locate/re-read it and refresh affected conclusions before using them in a build decision.
This is a binding agent workflow rule, not a claim that an executable guard has been installed. Stop new build activity safely; never kill another agent's process, steal/edit a queue ticket, interrupt a protected console operation, bypass disconnected-console safeguards, delete old inputs, upload restricted content or change the working main merely to satisfy the rule. Existing resource readiness and test/install gates remain fully binding.

### Tomer's current-input and research-provenance rule — verbatim (2026-11-01)

אוקי, אז בוא נעשה ככה, 
תעביר חוק עכשיו שמחייב את כל הפרויקטים לעצור ולפני כל בניה שלהם הם חייבים להשתמש במיפוי כדי לראות שהם משתמשים בחלקים הכי חדשים... 
במחקר שלהם הם יכולים להשתמש בשאריות שעדיין לא מחקנו , זה פחות משנה אבל שיהיה ידוע איפה כל חלק בעצם "קיים" כך שאם יש לנו חלק יותר חדש מאשר מה שהם קראו לצורך מחקר אז שידעו איפה לחפש את החלק עוד פעם


## Mandatory end-of-build cleanup (2026-11-01)

Every Z-A builder, including tool/mod/data/prepared-suite and legacy builders, must plan output retention before building and perform explicit intermediate cleanup after successful final validation. Read `docs/testing/BUILD_CLEANUP_RULES.md`. Preserve final artifacts, required proofs/logs/manifests, working baseline/rollback, source and all pinned/shared inputs; delete only reviewed generated intermediates owned by this job after their consumers have finished. Resolve absolute targets, refuse symlink escapes and record deletions/kept reasons/errors in a cleanup receipt. Do not silently leave ten full build generations by default. Keep additional history only for declared consumers/diagnostics or verified cold storage, then retire unneeded local outputs after dependency review.
Failure diagnostics and explicit debug retention are temporary, with a recorded reason/owner/review condition. Cleanup failure is not cleanup success. Never suppress a crash, weaken check-proof or erase required evidence to make cleanup pass. In the current za proof contract, llvm-pie.elf and eboot.bin remain required; conversion-only title-stripped.elf and eboot.elf may be removed after all relevant validation/package steps. Direct legacy scripts remain bound by the rule even where automatic integration is not implemented. Record actual guest and host storage effects separately; no uncoordinated WSL shutdown/compaction.

### Tomer's end-of-build cleanup instruction — verbatim (2026-11-01)

אז צריך למחוק אותם! 
צריך להוסיף שלב בסוף הבנייה שקבצי ביניים נמחקים בסוף! אנחנו לא יכולים להישאר עם 10 גרסאות אחורה!
