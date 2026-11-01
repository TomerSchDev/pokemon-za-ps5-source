# Card: more Pokémon species

## Facts (proven — don't re-research)
- `personal_array.bin` has rows for internal species 0–1010 with `IsPresentInGame`; only 364 are present. All 1025 names exist in text.
- Z-A model files use **SV** FlatBuffers layouts (not LA). Materials must be rewritten for Z-A's `IkCharacter` shader.
- A missing species needs: model + animations + icons, a catalog entry (`poke_resource_table.trpmcatalog`), and rows in 4 per-species tables:
  `wild_single`, `poke_model_param`, `poke_movement_param`, `chara_anime` (+2 optional).
- ~60 motions per species, listed in its `_base.tracr` (`.tranm` + `.tracm`, some `.traef`) + 7 animation-control files.
- 38% of missing species' learnset moves are not implemented in Z-A → movesets need remapping.
- **1011–1025 (SV DLC species) = Tier C**: no personal row, 16 code sites guard 1010/1011, save format change. Not recommended.
- Delivery: the mods folder (`cards/mods.md`).
- Sword UI icon IDs use catalogue model resource number, not National Dex: Yamper 835 → `poke_icon_0907_00s_n`, Boltund 836 → 0908 (Yamper HUD + toast verified on PC, 2026-10-31); forms follow catalogue form, not model variants 11/12. Helper `species-lab/import-all-20261030/tools/sword_icon_identity.py`; evidence `pc-fifty-20261031-r1/icon-identity-repair-r2.json` (4 wrong + 2 missing; preserve authentic Violet icons).
- PC fifty QA (2026-11-01): **2/50 full passes (Yamper→Boltund, Mudbray→Mudsdale), 48 pending**. Yamper Spark `r33/build/frames/frame_01430.png`, Tackle `r34/.../frame_01600,01740.png`, real Candy/evolution `r34/build/frame_04010.png`, field/icon04387, save reload `r37/build/frame_01172.png`, Bite defeat/EXP `r38/build/frame_01690.png` (runs prefixed `pc-fifty-...`). No diagnostic overlays required; original failed-attack cause unisolated. Console tests stopped.
- Grouped QA (2026-11-01, user replaces per-Pokémon manual workflow): `pc-fifty-20261031-r1/grouped-qa-20261101-r2/result.json` completes **833 imported variants / 631 species** core static checks; 833 pass (modules/tracks/source channel registry/move availability/evolution references), NOT icons/material visuals/gameplay. 232 state graph hashes / 358 source-category-module groups; start 9 source×ground/water/sky route representatives, expand into 34 module/body/form/gender representatives + graph/timing/asset exceptions. Runtime panel pending; 2 individual family passes retained. Source channel registry is the reference for Violet (skeleton also includes mesh/light nodes). Versioned metadata+source ZIP NAS `PC-QA-50-20261031-r1/Grouped-QA/grouped-imports-qa-20261101T044334Z.zip`, SHA256 `5f58bfb054e069425e1a4f66854d6e92ac6c8f260f591e7efdd7b3a21b9cca05`. Representative success never grants each member a full gameplay/visual pass.
- Mudbray full QA: Rock Smash win (`pc-fifty-mudbray-close-r41/build/frame_01580.png`), Bulldoze win + real Candy29→30 (`pc-fifty-mudbray-level-r42/build/frame_02140,02480.png`); explicit recovered Lv30 continuation, real evolution + saved750Lv30 (`pc-fifty-mudsdale-evolution-r43/build/frame_01710,02250.png`); actual Candy30→34/HeavySlam484 saved r44, reload/impact/Bunnelby empty HP + EXP (`pc-fifty-mudsdale-damage-r45/build/frame_01110,01220,01240.png`). Manually reviewed; videos/PNGs NAS SHA verified.
- Pidove unpassed: r46 Gust/QuickAttack no damage; same-move native Goodra Gust damages r47. Full Goodra catalog bundle on Pidove identity wins r49, but full native Fletchling flying bundle also fails r54; source animation alone not isolated. Transition/timeline/alias/animation-only/support-only probes r48/50–53 did not prove a fix. All diagnostic; no family pass.
- Native flying control: actual caught661 r58, stock/no-mods r60, uninterrupted r61, diverse original party r62, manual camera/open path r64 show no attack effect; SAME r64 battle native Goodra Tackle impact03140/reduced HP03390 proves input works. Blue flashes follow enemy Leer, not proved charging. Single isForceFloat-off r65 also no Tackle damage. No imported-model cause/fix established.
- Pidove partial r68: original geometry/clips + single TRACP category_int field3 2→0 yields Gust used01450/empty enemy HP-stars01520 (reads.log2590 proves parameter load); FIFO stop, Quick/evolution pending. Native animation-bundle-only706 r66 also restores Tackle but deforms rig; native state-only r67 no effect. Candidate isolated, sole-cause claim still needs matched original-Pidove manual control.
- Hebrew bank (2026-10-31): `/home/tomer/ps5-za-native/hebrew-species-pretranslation-20261031-r1/delivery` has 661 missing-species names, 1,398 translated original descriptions for 623 species, and 38 explicit source gaps; label/hash merger passed against the 995-species tables (`merge-validation.json`), PC/hardware untested.

## Pilot: Smoliv (internal 935 / national 928), PC first
Folder: `PS5-13.60\species-lab\pilot\` — `tools/run_pilot.py` (bounded PC run, own data root, copied save, scripted input),
`tools/build_mods.py`, `validate_mods.py`, `ablate_mods.py` (one table removed per run → `build/ablate-*`), `runs/`, `evidence/`.
Questions: (1) do mods load a never-listed path; (2) does Smoliv with a placeholder model appear, battle, get caught, save and load.
Check `species-lab\pilot\` for the latest run before starting; no `REPORT-HE.md` existed on 2026-10-31.

## Tools
- Inventory/analysis (read-only): `tools/labs/species-lab-scripts/` — `personal.py`, `catalog.py`, `model_pack.py`, `anim_inventory.py`, `per_species_coverage.py`, `pilot_candidates.py`, `wwise_cries.py`.
- Code questions (species limits, mission counters): `zw atlas find species` / `str`.

## Hard rule
Real models/animations come **only from Tomer's own SV/LA dumps** — never `Downloads\Pokemon`. Estimate: 5–9 weeks for the pipeline, then 2–5 days per species.
Deep reading only if needed: `analysis/new-species-feasibility-HE.md`.
