# Card: randomizer features (generator, options, music, cheats)

| Area | Where | State (2026-10-31) |
|---|---|---|
| Generator v3 | `port/rando-v3` (`src/rando_v3.cpp`, `tools/fb_codec.py`, oracle, tests) | Milestone 1 ready for UI: `port/rando-v3/HANDOFF.json` (`ready_for_ui=true`) — wild tiers, Alpha |
| UI v2 (9 pages, launcher in window) | `port/ui-v2` | Installed main-1.1.0 + JSON fix `36b3d5d`; two native PS5 new-run creations and runtime frames verified 31.10 |
| Settings words (`Warm-Snail-Fruit-Lime`) | `port/ui-v2/src/settings_codes.*` | Protocol `za-settings-words-1` |
| Music shuffle | `port/rando-music` (BGM.bnk decision-tree leaves, 94 songs / 4 categories, OFF default) | In r28b-music / r29-ui |
| Dex count incl. Mega Dimension | `port/rando-dexcount` | In r28a |
| In-game cheats (L3+R3) | `port/cheats-r28`, overlay `port/ui-v2/src/overlay_ps5.cpp` | MONEY, ITEMS, SHINY, CAPTURE, FPS rows |
| Option ideas | `analysis/RANDO-OPTIONS-BACKLOG-HE.md` | backlog |

## Rules for new options
- Story condition semantics proven from NSO `2308530d`: wire1..8 -> runtime [2,3,6,4,7,5,8,9]; wire7 strict,8 closed,100 [a,b),101 (a,b]; work SYS_WORK_PHASE aliases phase. Evidence `evidence/story-condition-research-20261101-r2`; no gameplay/release claim.
- Story continuation: typed numeric semantics resolved, but Lua heuristic wrongly rewrites three DLC-phase constants in order46578 (`evidence/story-condition-research-20261101-r2/lua-uses-r2.json`). Old matrix verdicts invalidated; namespace-aware fix in progress. No story UI/PS5 integration or full chapter proof.
- Resume audit 31.10: 22 source pins, 24 evidence pins and 173 assets verified; host new-run tests pass with 64KiB/8MiB worker stacks (`evidence/rando-v3-resume-20261031-223542`).
- JSON fix `36b3d5d`: localeconv/strtod wrappers; host equals reference over 164 JSON/1822 floats. Installed and PS5 generation passed twice; latest seed6123846995 used Levels+25%/AlphaAlways. Hardware logs: NAS `new-run-json-fix/gate-20261031-205347Z`.
- Live-object hooks only: save blocks in memory are copies the game overwrites (lesson from MONEY).
- The codec (`fb_codec.py`) is a decoder plus field-offset finder. It does **not** add trees, sub-tables or vectors. Use fields already in templates.
- Prefer a data change; else a narrow hook; else a generator guarantee. Isolate each patch in its own `port/<name>/`.
- Cutscene actors by randomization: **do not** (actors are inside the scene files).
- Tests: host tests + ASan/UBSan, a Python oracle over seeds, then PC proof, then PS5 build (`cards/build.md`).
- UI mockups go to Tomer **before** building UI (SMO-randomizer style, tiered options with descriptions).
