# Card: Hebrew support

Status: Full Hebrew + runtime RTL proven in bounded PC scenes; current PC evidence is in `hebrew-lab/runs/rtl-proxy6-release-20261031`. The Windows RTL component is **not ported or hardware-proven on PS5**; do not treat a PC package as a console installer.

## How it works (decisions already made — don't reopen)
- Text: `ik_message/dat/<lang>/{common,script,sk}/*.dat` + `.tbl` = GFMSG (UTF-16, XOR key base `0x7C89` step `0x2983`, labels `AHTB`).
  Codec round-trips all 3,843 `.dat` of 9 languages byte-for-byte: `tools/labs/hebrew-lab-tools/gfmsg.py`.
- Volume (English): 427 files, 76,810 lines, ~461k words (main story ~172k, DLC ~85k).
- **Slot: English** + swap the EFIGS fallback font for a Hebrew TrueType. It works with the existing English save; rename the mod folder to revert.
- Font: scalable, glyph by code point (`nn::fontll`). No atlas. Build: `build_font.py` (Noto, OFL); containers: `bfttf.py`.
- RTL: current PC proof pairs **logical-order** text (`build/full-hebrew-logical-20261031-r4`) with FriBidi/TextBox proxy (`build/rtl-engine-20261031-proxy6`); never pair this proxy with legacy visual-order text. Evidence: `build/rtl-engine-20261031-tests/tests-final.log` (5 passed), `runs/rtl-proxy6-release-20261031`.
- UI images with baked English text: native BC masks (`ui_header_codec.py`, `build_header_mod.py`, `build_interface_headings.py`).
- Ships as `mods/hebrew/romfs/...` → `cards/mods.md`.

## Tools (live copies in `PS5-13.60\hebrew-lab\tools`, snapshot in `tools/labs/hebrew-lab-tools/`)
| Step | Script |
|---|---|
| Inspect a file | `dump_file.py`, `index_messages.py`, `volume.py` |
| Translation memory / batches | `translation_memory.py`, `reuse_translation_memory.py`, `translation_validate.py` |
| Glossary | `glossary_manager.py`, `glossary_review.py` (the page can't approve — Tomer approves) |
| Build mod | `build_hebrew_project.py` → `pack_translation.py` |
| Coverage | `audit_text_coverage.py` |
| PC QA (bounded, copied save) | `qa_translation.py`, `qa_headers.py`, `run_poc.py` |
| Console trial (PPSA91762) | `trial_console.py`, `trial_log.py` — paths resolve relative to `hebrew-lab`; run from there |

Gotchas: no game text in git or outside Tomer's machine; `local_mt.py` is local-only; drafts (`draft_remaining_text.py`) never count as translated.
Deep reading only if needed: `analysis/hebrew-text-plan-HE.md`, `analysis/HEBREW-TRANSLATION-PROMPT-HE.md`.

2026-10-31 font evidence: 8 OFL families compared; Assistant/Heebo/Rubik tested in PC dialogue+menu (`hebrew-lab/runs/font-{assistant,heebo,rubik}-20261031-r1`). Tomer selected Assistant 450/650; comparison and licenses: `hebrew-lab/deliverables/Hebrew-Font-Study-20261031-r1`.
Selected Assistant + rebuilt main menu heading passed a 255 s PC scene check (dialogue/menu/Pokédex/map, source save unchanged): `hebrew-lab/runs/font-assistant-selected-20261031-r1`. Local candidate: `/home/tomer/ps5-za-native/hebrew-font-assistant-20261031-r1`; other bitmap headings unchanged; no PS5 test.
2026-10-31 terms: latest text is translation `full-hebrew-20261031-r195` / build `full-hebrew-logical-20261031-r6`; with Assistant font: `build/hebrew-assistant-20261031-r6` (PC-checked). Rogue=משתולל, Wild Zone=אזור פרא, Lady=ליידי, districts in Hebrew colours (הרובע הירוק/הכחול/האדום/הצהוב; Sector=אזור N ברובע ה…), terms `full-hebrew-20261031-r195-terms.tsv`. RTL on PS5: `rtl_engine.c` (117 lines, portable, overrides `f_700264efe4`) is not in any PS5 eboot yet; `rtl_proxy.c` is the Windows-only loader. Review: `hebrew-lab/reports/translation-review-20261031-claude.md`.
PS5 today (checked 2026-10-31): no RTL engine in any PS5 eboot. Installed r28b(-music) carries the r27b **Hebrew Trial**: `hebrew_trial.o` + `hebrew_install.o` (sources `hebrew-lab/trial/src`, `port/perf-r28/src/hebrew_*.h`), L3+R3 row `HEBREW TRIAL` toggles `mods/000-hebrew-trial` ↔ `_000-hebrew-trial` and reboots. The installer only accepts its fixed 19-file table (`hebrew_install_files.inc`, SHA-256 baked into the eboot), so new text can't ship through it without a rebuild. Its text is **visual order** (pre-reversed, e.g. `תואספוק`). LayeredFS itself works on PS5 (`/download0/zarecomp/mods/<name>`), so a separate always-on mods folder bypasses the trial installer. Last full visual-order build: `hebrew-lab/build/full-hebrew-20261030-r193` (pre-RTL, before the term fixes).
PS5 RTL (2026-10-31): `port/hebrew-rtl/` — `build-r29-hebrew.sh` links rtl_engine.c + FriBidi 1.0.16 into the installed r28b+MUSIC image (base link reproduced byte-exact; main_992 only renames f_700264efe4→original_*) → eboot `2883b727…` (WSL `hebrew-rtl-ps5-20261031-r1/image`); `test-host.sh` runs the 5 native RTL tests on the same source+FriBidi (pass). Install: `install-r29-hebrew.py init|backup|upload|install|activate|shot|complete --local DIR` (mods → app0 `hebrew-rtl-r6-e787deb75759`, payload `activate_hebrew.c` links `mods/hebrew`, Rowlet pattern). Package: `artifacts/randomizer-r29-hebrew-rtl-20261031-r1`. Needs Tomer: game saved+closed, HEBREW TRIAL OFF. Not hardware-tested yet.
INSTALLED on PS5 2026-10-31 (ticket 6): eboot `2726483b…` = r28b+MUSIC + FD fix (4b4d1b50) + RTL; mods/hebrew → app0 `hebrew-rtl-r6-e787deb75759`. In-game proof: title + menu RTL correct, no crash, saves unchanged (`\TheOnePiece\...\hebrew-rtl\install-20261031-134500Z\screenshots*`). Rollbacks on console: `eboot.bin.before-r28b-20261031-134758Z` (= 2883b727, no FD fix), `…-133012Z` (= models QA 41e7d81e). Open: (1) the overlay-fd fix lives only as `r28b-dlc-dex-fd-20261031-r1/candidate/src/runtime-file-handles.patch` — NOT in pokeza-recomp-ps5 source, so any fresh build regresses (crash at ~1024 mod files read: `ov[i].fd` in services/fs.c is never closed); (2) models test mods `00-*console-fifty*` sort before `hebrew` and win shared text files (HUD species name showed "Mudbray"); (3) menu quest panel "מספר שנרשמו 5/5": number overlaps the right-aligned label.
