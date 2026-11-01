# Card: randomizer features (generator, options, music, cheats)

| Area | Where | State (2026-10-31) |
|---|---|---|
| Generator v3 | `port/rando-v3` (`src/rando_v3.cpp`, `tools/fb_codec.py`, oracle, tests) | Milestone 1 ready for UI: `port/rando-v3/HANDOFF.json` (`ready_for_ui=true`) — wild tiers, Alpha |
| UI v2 (9 pages, launcher in window) | `port/ui-v2` | Built as r29-ui candidate: `artifacts/randomizer-r29-ui-codex-20261031-01`, not hardware-tested |
| Settings words (`Warm-Snail-Fruit-Lime`) | `port/ui-v2/src/settings_codes.*` | Protocol `za-settings-words-1` |
| Music shuffle | `port/rando-music` (BGM.bnk decision-tree leaves, 94 songs / 4 categories, OFF default) | In r28b-music / r29-ui |
| Dex count incl. Mega Dimension | `port/rando-dexcount` | In r28a |
| In-game cheats (L3+R3) | `port/cheats-r28`, overlay `port/ui-v2/src/overlay_ps5.cpp` | MONEY, ITEMS, SHINY, CAPTURE, FPS rows |
| Option ideas | `analysis/RANDO-OPTIONS-BACKLOG-HE.md` | backlog |

- Save-slots continuation: Claude implemented the menu/container/writer already; Codex host proof `save-slots-continuation-20261101-02` passes 111 saves + 14 directory + 14 atomic tests and 60 writer checks in ASan/O2. Preserve installed `36b3d5d`; native deletion still requires isolated API proof and fails closed when `lstat` is unavailable.
- Native-delete API observation source is `port/save-fs-probe/PROBE-PLAN.json`: provisional side title PPSA91780 (not known free), private synthetic scratch only; optional imports default off. Source preparation alone is not a target compile or hardware result.

## Rules for new options
- Live-object hooks only: save blocks in memory are copies the game overwrites (lesson from MONEY).
- The codec (`fb_codec.py`) is a decoder plus field-offset finder. It does **not** add trees, sub-tables or vectors. Use fields already in templates.
- Prefer a data change; else a narrow hook; else a generator guarantee. Isolate each patch in its own `port/<name>/`.
- Cutscene actors by randomization: **do not** (actors are inside the scene files).
- Tests: host tests + ASan/UBSan, a Python oracle over seeds, then PC proof, then PS5 build (`cards/build.md`).
- UI mockups go to Tomer **before** building UI (SMO-randomizer style, tiered options with descriptions).
