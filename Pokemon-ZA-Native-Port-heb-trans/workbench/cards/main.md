# Card: main, project branches, merges (proposal 2026-10-31, see `workbench/MAIN-BRANCH-HE.md`)

**main** = one za release profile named in `tools/za/releases/MAIN` (now `main-1.0.0` = r29-ui, eboot `51b7e65b`, NOT console-tested yet).
A release = frozen link inputs + `tools/za/releases/<name>.lock.json` + the pinned package (eboot + randomizer-assets + mods) + app0 config.
Git (2026-10-31): this repo `main` (worktree `..\Pokemon-ZA-Native-Port-main`; r29-ui sources, `master` untouched), `heb-trans` (worktree `..\Pokemon-ZA-Native-Port-heb-trans`, = main + `port/hebrew-rtl`); runtime repo `main` = `1655be8` (worktree `..\pokeza-recomp-ps5-main`, = r29-ui WSL source tree, 62/64 objects byte-identical, 2 DWARF-only).
```powershell
zw za doctor main-1.0.0
zw za build main --out /home/tomer/ps5-za-native/main-NEW [--package /home/tomer/ps5-za-native/main-pkg-NEW]
zw za check-proof /home/tomer/ps5-za-native/main-NEW/main-1.0.0/proof.json
```
`build main` relinks main byte-for-byte and checks every package file. If it fails, stop. Do not repin anything.

## Start a project branch
1. Name it `<area>-<topic>`, e.g. `heb-trans`, `species-names`, `models`, `fd-fix`. Add one row to the branch table in `MAIN-BRANCH-HE.md`.
2. Base it on **main** only. Your recipe takes main's frozen tree as BASE (`/home/tomer/ps5-za-native/za-main-<ver>-frozen-*`) and reproduces main first as its control. Never base it on whatever eboot happens to be on the console.
3. Source: if you change pokeza-recomp-ps5 or a repo `port/<x>`, use a git branch of the same name, in your OWN `git worktree`. Never switch branches in a shared tree.
4. Put the work in `port/<x>/` (recipe, pins, tests). Outputs go to NEW folders. Data goes in `mods/<x>/` with its own manifest.

## Merge into main (only Tomer approves; one agent merges at a time)
1. Rebase onto the current main. Your recipe must start from main's frozen inputs, and its control must reproduce main's eboot byte-for-byte.
2. Controls: unchanged objects rebuild byte-for-byte. The changed objects are listed, with an `nm` symbol diff and no base symbols lost.
3. Tests: host tests, then a PC proof (bounded scene, copied save). For mods: count the files (over ~900 needs the FD fix) and check sort-order conflicts with other mods.
4. Console gate: Tomer coordinates, through `zw queue`, following the `cards/console-install.md` pattern. Pass = boots, saves stay readable, the feature works, and a rollback exists.
5. Freeze: `python3 tools/za/freeze_release.py --name main-<new> ...` writes a new lock that is never edited afterwards. Then reproduce it with `za build main` (after `MAIN` points to it) and add an evidence folder.
6. Bump the version. Use PATCH for a fix with no new option, MINOR for a feature or option, and MAJOR for a save/settings break. Update `MAIN` only after the console gate passes.
7. Merge the git branches (runtime repo, this repo) with the commit hashes recorded in the release lock's `release` block.

## Rules
- Never edit an existing `*.lock.json` or `profiles.lock.json`. Every release gets a new file.
- One feature per branch, so a revert is a single release step back (`MAIN` points to the previous profile).
- Never merge from the installed console image. Merge from branches whose recipes start at main.
- 1.0.0 = r29-ui PASSED the console gate 31.10.2026 (tools/za/releases/main-1.0.0.hardware.json). Old v2-generator runs hang after loading in r29-ui; use v3 runs. Release installer: port/main-install/install-main.py (init/backup/isolate/assets/install/pushrun/shot/complete).
