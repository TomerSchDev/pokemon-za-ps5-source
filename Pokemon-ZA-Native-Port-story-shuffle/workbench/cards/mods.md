# Card: mods folder (LayeredFS) — how any game-file change ships

Both Hebrew and new species ship this way. No code change and no `romfs.bin` rebuild are needed.

- The runtime (`pokeza-recomp-ps5/runtime/services/fs.c`) scans `<data root>/mods/<name>/romfs/...`.
  - **PC** data root: `LARECOMP_DATA_ROOT` (the run's working dir). **PS5**: `/download0/zarecomp` → upload to `/download0/zarecomp/mods/<name>/romfs/...`.
- Up to 15 folders, scanned by name; the **first layer that has the file wins**. A folder starting with `_` or `.` is disabled.
- Existing RomFS files are replaced. **New** files are added to a virtual RomFS (`add_new_files`).
- Files inside packs (`arc/data.trpfs`): the runtime serves the game a copy of `arc/data.trpfd` with the replaced hashes removed (`trpfd_unlist`), so the game reads them as loose files. A mod's own `data.trpfd` is **never read**.
- Log lines to look for: `[fs] mod: <name>`, `arc/data.trpfd: N files the mods have taken out of the packs' list`, `N new romfs files`.
- Community Atmosphere mods: only `romfs/` applies. `exefs/` IPS/exlaunch patches do not apply to translated code (they become generator patches).
- Proven on PS5 with the randomizer (`4 new romfs files`). A path never listed in `data.trpfd` (a new model folder) is what the species pilot tests.

Reading game files offline: `tools/labs/hebrew-lab-tools/za_romfs.py` (RomFS → `arc/data.trpfs` ONEPACK → files by path).
