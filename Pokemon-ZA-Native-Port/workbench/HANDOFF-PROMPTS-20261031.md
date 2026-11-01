# פרומפטים להמשך העבודה, 31.10.2026 (Claude)

לכל סוכן חדש מעבירים את **החלק המשותף** ואחריו את **החלק של המסלול שלו** בלבד. אם מסלול רץ אצל סוכן שלא סיים, בודקים קודם אם הדוח שלו כבר קיים (הנתיב מופיע בכל מסלול). אם כן, ממשיכים ממנו.

---

## חלק משותף (מעבירים לכל סוכן)

```
You continue work on the Pokémon Legends: Z-A native PS5 port (static recompilation of 2.0.2). Owner: Tomer. Report to him in Hebrew; long summaries go in an HTML page (dir=rtl, light/dark, mobile-friendly, a short explanation per term), with 3–5 lines + the link in chat.

Repo (shared working tree, branch master — never switch branches here; other agents run scripts from it):
  C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port
Start: run `.\zw card rules`, `.\zw card main`, then `.\zw card <your topic>`. Tools via `.\zw` (atlas, pc run/shots/fps, za builds, queue, console verbs need --console-ok).
Branch model (approved): workbench/MAIN-BRANCH-HE.md. Git worktrees:
  PS5-13.60\Pokemon-ZA-Native-Port-main          branch main (1.0.0 = r29-ui, hardware-verified 31.10; commit 4b5295e)
  PS5-13.60\Pokemon-ZA-Native-Port-heb-trans     branch heb-trans
  PS5-13.60\Pokemon-ZA-Native-Port-save-reset    branch save-reset
  PS5-13.60\Pokemon-ZA-Native-Port-story-rando   branch story-rando
  Runtime repo PS5-13.60\pokeza-recomp-ps5: branch main (1655be8, = the real WSL build tree of r29-ui, worktree pokeza-recomp-ps5-main), branch fix/overlay-fd-limit (57e3b9d fix + ae5e0bd test, worktree pokeza-recomp-ps5-fdfix). Commits on project branches OK; no push.
Releases: tools/za/releases/ (main-1.0.0.lock.json, .hardware.json, MAIN → 1.0.0); `za build main` reproduces 1.0.0 byte-for-byte. New releases: tools/za/freeze_release.py. A release enters MAIN only after a console gate with Tomer.
Console (192.168.1.135, title PPSA91762): only in a session Tomer coordinated (he authorized remote install/test on 31.10 for these gates). Always: shared queue (tools/console-install-queue), all-runs double-read save backup first, eboot .new→readback→rename→readback, keep rollback files, never restore an old save over newer progress. Lease expires after 10 min idle: reconcile explicitly (release with resolution + expected_lease_id), then a new ticket.
Saves policy (Tomer): at each new MAJOR version all runs may be wiped — only after the NAS backup.
Overlay-fd fix: any build that loads many mod files MUST include it (without it the runtime keeps one fd per mod file read and crashes near 1024).
Game data/text/saves/keys never in git or uploaded. Other Pokémon games' assets only from Tomer's own Switch dumps (never Downloads\Pokemon).
```

---

## מצב הקונסולה (31.10, 16:15)

- **מותקן:** 1.0.0 = r29-ui (`51b7e65b…`), עם נכסי v3.
- **הריצה הפעילה:** ‏`r000000006ae50000-1234abcd`, ריצת v3 שנוצרה במחשב.
- **ריצות ישנות:** עדיין קיימות. ריצות v2 נתקעות ב־r29-ui אחרי הטעינה.
- **mods של ענפי צד:** כבויים, עם `_` בתחילת השם: ‏`_hebrew`, ‏`_00-console-fifty-20261031-r1`, ‏`_00-0-console-fifty-20261031-r1`, ‏`_000-rowlet-pilot-r1`. מחזירים אותם עם `port/main-install/install-main.py isolate --restore --local <dir>`.
- **נקודות חזרה בקונסולה:**
  - `eboot.bin.before-r28b-20261031-154922Z`: העברית, ‏2726483b.
  - `randomizer-assets.before-main-1.0.0-20261031-154835Z`.
  - `active.before-r000000006ae50000-1234abcd.json`.
- **גיבוי שמירות:** ‏`\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port\main-releases\main-1.0.0-gate-20261031-154546Z\save-backup`.
- **דוח בדיקת 1.0.0:** https://claude.ai/artifact/B5ckkbL4JN8ES7zyURnFfD

---

## מסלול 1: מערכת ניהול שמירות (ענף `save-reset`)

אם הדוח `Pokemon-ZA-Native-Port-save-reset\workbench\reports\save-reset\index.html` קיים, Tomer עוד צריך לאשר אותו. ממשיכים רק אחרי האישור.

```
Branch save-reset (worktree PS5-13.60\Pokemon-ZA-Native-Port-save-reset, from main). Goal, as Tomer specified:
1) The launcher (r29-ui UI v2: port/ui-v2/src/launcher_core.*, ui_launcher.*, ui_model.*, mockups_main.cpp, host build tools/build-host.sh) opens FIRST on a save-slots menu modelled on the Super Mario Odyssey randomizer (reference material: PS5-13.60\SMO-Randomizer-20261025, -Update-20261029, -User-20261029): each slot shows date, location, Pokémon caught, seed; whether it is supported or not; delete from there (per slot + delete all unsupported, with confirm); selecting an empty slot creates a new run (then the existing settings/seed/name flow).
2) Unsupported = runs made by an older generator (v2) — they hang in r29-ui after loading. Mark them invalid, disable Continue, never auto-continue them.
3) On every game save (manual or autosave) write a compact BINARY container next to the run (e.g. rando/<id>/slot.zrs): copy of the original game save, randomizer extra info (run id, generator version, date, location if available), caught (and seen) count, run settings. The game's own save is never modified or delayed; write only after the save commit succeeded, atomically; failures only log. Launcher reads only a small summary header. Caught count from the save (PKHeX in save-workbench/deps/PKHeX documents Z-A) or a live-object read like the MONEY hook.
Order: mockups + format spec to Tomer for approval FIRST (HTML page), then implement + host tests (ASan/UBSan), PC proof, then a PS5 build + console gate with Tomer.
```

---

## מסלול 2: ערבוב סדר הסיפור (ענף `story-rando`)

אם הדוח `Pokemon-ZA-Native-Port-story-rando\workbench\reports\story-rando\index.html` קיים, ממשיכים לפי התוכנית שבו.

```
Branch story-rando (worktree PS5-13.60\Pokemon-ZA-Native-Port-story-rando). Tomer wants the story ORDER randomized and insists it be researched for real ("we have the code; with enough research everything can be opened"). Map chapters main_01..main_10 (+DLC): phase values, flags, work values each requires/sets; the script engine and how a chapter's start condition is evaluated; Royale rank gates; unlocks per phase (shops use phase_condition e.g. 30600/40100). Find phase checks in code with the atlas (annotate findings). Investigate runtime hle keysanity.c/warp.c/doorjump.c/flags_ext.c. Prototype on PC (copied save, zw pc run --shot-at): start a later chapter early / swap independent missions; record exact results. Also list easier options (per-chapter Rogue Mega boss, mission rewards, gifts, side missions, Royale opponents, open-world unlocks) with effort. Deliver an HTML report with a dependency graph, feasibility verdict, experiment screenshots and a plan.
```

---

## מסלול 3: עברית ב־Main, גרסאות 1.0.1 ו־1.1.0 (ענף `heb-trans`)

אם הדוח `Pokemon-ZA-Native-Port-heb-trans\workbench\reports\hebrew-1.1.0\index.html` קיים, הצעד הבא הוא בדיקת הקונסולה עם Tomer.

```
Goal: Hebrew into main as release 1.1.0, via 1.0.1.
Step A, 1.0.1 = main-1.0.0 (r29-ui 51b7e65b, frozen inputs /home/tomer/ps5-za-native/za-main-1.0.0-frozen-20261031) + overlay-fd fix (runtime fix/overlay-fd-limit 57e3b9d → apply onto runtime main 1655be8; rebuild only services/fs.o, ipc.o, kernel.o; prove the other 61 runtime objects unchanged; control relink reproduces 51b7e65b first), freeze with tools/za/freeze_release.py (MAIN stays 1.0.0 until the console gate).
Step B, 1.1.0 = 1.0.1 + heb-trans: port/hebrew-rtl (build-r29-hebrew.sh with BASE_SPEC; renames f_700264efe4 → original_700264efe4 in AOT unit main_992.c (copy on the NAS AOT tree), links rtl_engine.c + FriBidi 1.0.16; test-host.sh = 5 RTL tests). Mods: hebrew-lab/build/hebrew-assistant-20261031-r6 (logical-order text r195 + Assistant 450/650; already on console app0 as hebrew-rtl-r6-e787deb75759, link currently disabled as _hebrew). Fix: (1) mod order — LayeredFS takes the first folder by name that has the file; other branches' 00-* mods beat 'hebrew' (HUD showed "Mudbray"); choose a scheme where Hebrew text wins and the species-names branch can join. (2) "מספר שנרשמו 5/5" number overlaps the right-aligned label (rtl_engine.c pane anchoring). (3) inventory UI v2 launcher/overlay strings (drawn by the UI, not GFMSG).
PC proof (hebrew-lab/runs/hebrew-assistant-r6-20261031-r1 shows the scene/command; Windows RTL proxy rtl-engine-20261031-proxy6). Prepare the console install (port/main-install/install-main.py pattern) but the gate is run with Tomer.
Proven history: on 31.10 Hebrew RTL ran on PS5 (eboot 2726483b = r28b+MUSIC+fd fix+RTL): title, menu, dialogue correct, no crash. Translation reviewed + fixed: translations/full-hebrew-20261031-r195.jsonl, terms r195-terms.tsv (Rogue=משתולל, Wild Zone=אזור פרא, districts in Hebrew colours, Sector=אזור N ברובע ה…, Lady=ליידי). Review: hebrew-lab/reports/translation-review-20261031-claude.md.
```

---

## מסלול 4: מודלים של כל הפוקימונים (הסוכן האחר של Tomer)

```
The models/new-species work belongs to Tomer's other agent (species-lab, console-fifty). Its console test mods are disabled on the console now (renamed with _; restore with port/main-install/install-main.py isolate --restore). Its builds need the overlay-fd fix (24,500+ mod files). Its QA eboot 41e7d81e is NOT a base to keep (Tomer). Merge into main only via the branch model, after 1.0.1. Hebrew names for the new species are ready at /home/tomer/ps5-za-native/hebrew-species-pretranslation-20261031-r1/delivery (a separate branch; coordinate the mod-order scheme with heb-trans).
```

---

## מה עוד פתוח

- **מחיקת הריצות הישנות בקונסולה:** Tomer מאשר מחיקה בגרסה ראשית, והגיבוי קיים. בפועל זה ייעשה דרך הכלי של מסלול 1, או ידנית אחרי אישור.
- **הסכמה על הכנסת `zw`, הכרטיסים וה־HANDOFF ל־master:** `workbench/` נכנס לענף `main`, אבל `master` לא עודכן.

---

## עדכון ערב 31.10: מה השתנה ומה רץ

- **1.1.0 מותקנת בקונסולה:** ‏eboot ‏`7d837a58…`, ובה 1.0.1, עברית ו־`0-hebrew`. עברה את בדיקת הקונסולה (כרטיס 9).
- **סוכן "promote":** ממזג את heb-trans ל־main, נועל את main-1.1.0 ומעביר את MAIN. אחר כך הוא מעביר את מסך השמירות לבסיס 1.1.0 ובונה את מועמד 1.2.0.
  - הדוח: `Pokemon-ZA-Native-Port-main\workbench\reports\main-1.2.0\index.html`.
  - בדיקות קונסולה על r29-ui מריצים דרך `port/main-install/gate_r29.py <installer> <step> --local DIR`.
- **הסיפור פוצל לשלושה ענפים** (כולם נפתחו מ־story-rando):
  - `skip-intro`: התחלה ישר בפרק 4. כולל מציאת המקום שבו נשמרת דרגת Royale (‏`port/story-rando/NOTES-royale-rank.md`). הדוח: `...-skip-intro\workbench\reports\skip-intro\index.html`.
  - `story-shuffle`: ערבוב פרקים 4–8. צריך להוכיח את השרשרת המלאה 4→6→5→7 ולבנות מחולל `story_shuffle.py`. הדוח: `...-story-shuffle\workbench\reports\story-shuffle\index.html`.
  - `open-world`: עולם פתוח מההתחלה (‏`open_world.py`). הדוח: `...-open-world\workbench\reports\open-world\index.html`.
- **דוח פשוט על הסיפור:** https://claude.ai/artifact/Ee8dqhXnmkZzWfTXuubtDM
- **Tomer רוצה דוחות פשוטים וברורים** בסגנון הזה.
