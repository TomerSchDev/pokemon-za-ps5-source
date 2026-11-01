Native PS5 Pokemon Legends Z-A Randomizer

CURRENT UPDATE: randomizer r15, 2026-10-28, installed and SHA256-readback verified.
Binary SHA256: 5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0
Consult the matching installation report for current hardware status.
r15 carries r14's gameplay/cheat features plus a native staged-run importer:
download0 is mounted only while the title runs, so direct closed-title FTP
repair cannot work. The title imports before allowing game startup.
The r11 broad capability guard was too restrictive. It is replaced with an
early-rock route only: seeded natural learner by level 3 (29 candidates), or a
research-level-2 TM and compatible early spawn (Rock Smash:39, Brick Break:121).
Both original tutorial/regular early spawn triggers are retained. All 1700
ordinary encounters match the unconstrained portable generator. 120 authored
move-set encounters retain their original species, forms and moves.
Later research TMs remain at their original sources; optional species side
quests are not guaranteed. This is not a complete main-story dependency proof.
100 route/reward seeds and 16 full generations/toggle combinations pass host
tests and independent Python checks. Raw learnsets/TM compatibility are checked.

r14 also includes an in-game L3+R3 cheats overlay, default OFF, stored per run.
Shiny: normal / 4x,16x,64x rolls / always shiny for newly generated Pokemon.
Capture: normal / 2x,4x,8x score / max score, after eligibility checks.
D-pad changes options, Circle closes; the world keeps running under the menu.
Host tests pass. User confirmed the overlay opens and appears to work on PS5;
logs show option changes and the settings file was read back (shiny=4,capture=2).
Actual new shiny spawn/capture effects and restart persistence on PS5 remain
separate unverified checks. Consult the matching installation report.
Host persistence tests additionally exercise the actual fopen/fsync/rename code
with only path redirection: process restart, independent runs, corrupt settings
and failed rename retaining the previous settings all pass.

repair-existing-run.py previews a repair while the old title remains at its
launcher menu; --stage writes only /data/homebrew/PPSA91762/run-repair.
Direct --apply is disabled. Close the menu before replacing the executable.
At r15 boot, the importer rechecks the source report, every table and the current
save hash. It publishes a NEW folder, preserving progress/rewards/trainers/DLC
and the old run. No game save is reset if it has changed since the snapshot.
After independently verifying the imported run, archive the run-repair folder
under a timestamped applied name before letting the user select Saved Runs.
This removes the one-time import request and preserves all original runs.
If import failed, leave both the original run and import evidence intact.
An offline regression used the real progressed r11 save, not a fresh template.
The native repair was applied and read back on PS5. The old run's six files are
unchanged; fresh save SHA256 cb93edc5f59dad99d3114efb2e15ecb287905e3cd98e956fdc0c09440d937b08
matches the repaired run. The one-time request was archived after verification.
The user subsequently created a new Greavard run, seed 6177047620; its four tables
match the independent oracle. Never restore a backup over newer gameplay.

Expansion investigation: current-build boss event table has 169 records, 168
joined to battle spawners. Absol case study maps event to spawner, encounter and
arena. Numeric unknown fields remain inferred. 802 NPC species/form records
have 793 placement references to 406 distinct records. These are entry points,
not a tested cinematic substitution feature. Main-story boss order requires
mission/phase/arena/actor mapping; DLC rematch shuffling already exists.

The rest of this README records earlier implementation and release history.

User request: separate native PS5 application, controller menu to choose seed and
start a run. Reuse portable C++ generator; no recompilation for a new seed.
Title PPSA91762, stock remains PPSA91761. Original game data 2.0.2 plus merged DLC.

Menu: Continue current run; New run (explicit confirmation); decimal numeric
keypad for a seed of up to 16 digits. D-pad selects a key; Cross enters it;
Square backspaces; Triangle generates a fresh numeric seed; Clear empties the
field; Done confirms; Circle cancels. First digit replaces the prefilled value.
Starter choices are Random from seed, Chikorita, Tepig and Totodile. Random
still uses the full validated city-starter pool (343), deterministically.
Left/right or Cross cycles starters; Triangle returns to Random.
Wild, trainer, mega-trainer, DLC-rematch and research-reward toggles;
Saved Runs for revisiting earlier progress. Uses CPU VideoOut before Vulkan starts.
The logical canvas is 1280x720, presented at the already-proven 1920x1080 surface.
No Switch ARM64 subsdk9/menu/cheat hooks are included.

New run writes a unique hidden staging folder, verifies tables and starting save,
then renames the complete directory and atomically selects it. Every run keeps
its own save/save_0/main. Continue verifies immutable tables but does not compare
the live save with its starting template. Old runs are never overwritten/deleted.
Runtime rando_seed_dir and the existing Trinity/ROMFS overlay handle the tables.
LARECOMP_RANDO_SEED selects the completed run; LARECOMP_SAVE_DIR is unset.
Writable root: /download0/zarecomp/rando inside this title's own sandbox.

Sources in core/ are copied unchanged from the PC ingame-randomizer core.
provenance.json records their hashes. JSON and Mbed TLS build dependencies come
from the existing research/za-switch-mods/lib directory. The prepared-streamed
asset set is pinned by hashes and has 90 files (~17.5 MB); it includes the city
save and delta templates. None of these inputs is a user authentication key.

Build: wsl -d Ubuntu -- env RANDO_REV=rN bash port/randomizer/build-randomizer.sh
Use a NEW rN for a different binary; package guards preserve older versions.
Reuses r14 runtime objects and the r13 optional FPS hook archive, default profile30.
Stock code and game data are preserved. Native pipeline checkpoint remains r14.
Host test: port/randomizer/test-host.sh; covers progress preservation, separate
runs, duplicate refusal, interrupted generation, unsafe IDs and corrupt metadata.

Deployment: fixed copy_game_payload.c copies six pinned existing stock data
files to /data/.za-native-randomizer-r1/PPSA91762/game and checks source/destination
SHA-256. It never modifies the source. Total 6,029,333,792 bytes.
All six files passed on 2026-10-27. Overlay stages through deploy-randomizer.py.
Publish requires active games closed and atomically renames only the NEW title.
Dedicated launcher payload: za_native_randomizer_launch, title ID pinned at build.
run-title.py TAG PPSA91762, shader-host.py 900 PPSA91762; both allow only our IDs.
The shader host remains a bounded development helper, not a persistent service.

Hardware status at 2026-10-27 22:49 local:
- r6 installed SHA 4bfe480ae9b9f8c415328c73640e78ed782c8ed469b2d78bdcb7b531f6eecf0e.
- Native menu, controller input, generation, VideoOut-to-Vulkan transition and
  city gameplay verified on the PS5. User confirmed Gengar and normal control.
- Generated seed 4031C916F62655AE, run r000000006ae10d06-5a983292.
- All three PS5 output tables and starting-save SHA match the host generator.
  Runtime log confirms 3 entries unlisted from the Trinity pack and the run's
  independent save/save_0 directory mounted. Evidence: randomizer-run-20261027-204242Z.
- Continue passed: same run, Gengar and saved progress confirmed by the user.
  Saved main SHA before closing and at the reopened menu was identical:
  3adc955e9a0880f176a356eb573cb621b88a17c0642e64f7be08b0a58a574a7a.
  The previous process remained after user-confirmed save/close; its files were
  backed up and verified, then only its exact PID155 was terminated. Relaunch PID157.
  Evidence: randomizer-saved-before-close-20261027-204730Z and
  randomizer-run-20261027-204753Z. No new generation occurred on Continue.
- r3/r4 failed before any run was created: lstat returned EPERM in the native
  environment. r6 uses stat and the runtime's za_opendir/readdir/closedir.
- Cache seeding uses stat instead of access (access always returns EPERM here),
  so an existing native pipeline cache is preserved on subsequent launches.
- Host run-store tests pass: publish, progress preservation, independent runs,
  duplicate refusal, interrupted staging, invalid IDs and immutable table integrity.
- Directory fsync is best effort if the native filesystem rejects that operation;
  data-file fsync and readback remain mandatory. Power-loss recovery was not tested.
- Initial shader cache 947 entries plus a same-PS5 pipeline-cache snapshot;
  one additional compute shader was compiled/validated during the first run.
- Initial native pipeline cache loaded 4,204,908 bytes; during play the live cache
  grew to 4,447,116 bytes before close and exactly that size/fingerprint was loaded
  on Continue. This is a development snapshot, not full shader coverage.
- Old diagnostic probe PPSA91760 was opened by the user while preparing this app;
  it was safely identified by live PID/build JSON and closed (PID149). Its unrelated
  probe failures are not randomizer results.

Two seeds were generated on hardware before r8. Host tests
cover independent runs and integrity checks; Saved Runs selection and all 343
starters have not each been tested on PS5. New regions/species can still need
previously unseen shaders. A stable 60 FPS mode is not verified; default is 30.

r7 menu change requested after the successful r6 test: numeric keypad instead of
hex digit cycling; only the three regular starters or Random from seed. Existing
hex-seed runs remain readable and continue without regeneration or migration.
Host oracle seed 12345 verified Random/Chikorita/Tepig/Totodile and confirmed that
changing the starter does not change the randomized world tables for that seed.
r7 was installed and the user confirmed both UI changes work as requested.
Numeric seed 30081997 generated run r000000006ae11048-9b864a3e, starter
Chingling. The PS5's three tables and starting save matched the PC generator.

r8 adds independent research rewards for NEW runs only (default ON). Continue
keeps each existing run's immutable tables, including the old three-table format.
The exact 2.0.2 table is ik_event/bin/research_lv/research_lv.bin. Levels 2-49
receive 48 distinct replacement items from a validated 490-item pool, excluding
the original item for that level. Level 1 has no reward; level 50's key item
Shiny Charm stays unchanged. Research-point requirements and unrelated bytes
are unchanged. The pool intersects the actual game's item table with PKHeX's
ZA inventory allowlists, excluding key items and unreleased Cherish Balls.
Quantities retain the original reward amount subject to the actual item's stack
cap; TMs, Mega Stones and primal orbs are capped to one. It includes medicine,
balls, berries, TMs, Mega Stones, treasure and other supported inventory items.
Only research-level rewards are covered; story/event/quest/battle-rank rewards
have not been randomized. The new toggle has no effect on Pokemon generation.

research_rewards.cpp uses a separately domain-separated SHA-256 sampler. Its
results and full reward spoiler list are stored in the run report. The source
portable Pokemon generator remains byte-identical to its recorded provenance.
100 host seeds passed repeat determinism, independent Python byte comparison,
distinct-output checks, quantity/exclusion checks and unchanged XP/key reward
checks. Corrupt assets and invalid offsets were rejected. Run-store tests cover
old and new table formats, progress preservation and corrupt fourth tables.
r8 binary SHA: 91c3dc479bef63afdbcc89eb006ab5979cc7f9729733cd362b22896164046709.
Consult the accompanying final report for hardware validation of r8; a successful
build or host test alone does not verify that a reward was received in-game.

The initial r8 release snapshot included 972 SPIR-V entries, with 25 helper
outputs read back and verified from this title's console installation. The
snapshot remains incomplete: unseen rendering states can require the PC helper.

Every final package/report is also copied to a versioned NAS project folder and
SHA-256 verified, recorded in NAS-COPY-VERIFIED.json. Do not include SDKs, keys,
whole app.db files or generated game C sources in source archives.

2026-10-27 r8 hardware findings and r9 correction:
- r8 installed and all three asset metadata hashes verified at startup.
- Seed 9376797808 generated Pikachu and four tables; all four matched the host
  generator / independent reward oracle. Research level 2 is one Dream Ball.
- The first launch hit GPU_FAULT_PAGE_FAULT_ASYNC writing VA 0x77334b9000.
  The renderer had latched the temporary 105 MB region at 0x744fa80000;
  XFB then queued a copy to 0x77334b9260 outside that imported allocation.
- On relaunch the same run selected the established 3.2 GB game arena and
  played normally; the user confirmed control in the city with Pikachu.
  This is evidence against corrupt reward data, not proof of universal stability.
- Both older run reports and all six older tables were read back unchanged.
  Their saves were backed up with two matching reads after relaunch.
- r9 pins the game arena to 0x7676b00000+0xc9500000 for this exact packaged
  ZA 2.0.2 randomizer. Existing plat_commit is idempotent for populated pages.
  Stock title entry is not pinned. Revisit the address for another game build.
- r9 also bounds every XFB mirror copy to the actual imported allocation,
  including imports at offset zero. The old check skipped that case.
- A host harness executes the actual xm_prepare body: the crash address and
  a range crossing the allocation end are rejected after the fix, while valid
  zero/nonzero-offset ranges remain accepted. Reverting the conditional in
  the same harness reproduces both unsafe acceptances.
- r9 binary SHA: fb1262e709fb7754530dc1908e65a91213b6ddf881f42272e3ffaf5af0bc32f3.
  See the final report for r9 installation and console-test status. Actual
  receipt of a research reward is a separate check from table generation.
