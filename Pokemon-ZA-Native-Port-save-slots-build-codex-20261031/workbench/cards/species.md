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
- PC fifty QA (2026-10-31): **0/50 full passes**. Goodra Breaking Swipe damages Bunnelby with cohort mods in the prepared copied save (`pc-fifty-preserved-native-r21`); Yamper commands still do not execute at Lv24 or Lv5. Turning looping one-shot mappings off did not resolve it (`r22`); donor-model ablation was inconclusive (`r23`). Console tests remain stopped.
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
