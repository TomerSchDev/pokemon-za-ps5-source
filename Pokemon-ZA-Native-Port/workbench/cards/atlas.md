# Card: code atlas (find anything in the game code)

Use before reading any `aot/main` C. 270k functions, 881k calls, 120k strings, RTTI, annotations.
DB: `PS5-13.60\za-atlas-data\atlas.sqlite` (outside git). Offline, read-only except `annotate`.
AOT C / NSOs moved to `\\TheOnePiece\Software\Pokemon-ZA-All-Models\Workstation-Data-20261030-v1\Research\pokeza-pc\update-2.0.2-20261025\aot\main` / sibling `game\exefs`; the old Codex source path is absent (verified 31.10).

```powershell
zw atlas find <word>            # names/annotations matching a word
zw atlas str "<text>"           # functions that reference a string
zw atlas fn <addr|name>         # one function: unit, line, callers, callees, refs
zw atlas who-calls <addr>       # callers;   zw atlas callees <addr>
zw atlas path <src> <dst>       # call path between two functions
zw atlas class <name>           # RTTI class / vtable
zw atlas crash <klog> --elf <llvm-pie.elf>
zw atlas annotate <addr> "<name>" --subsystem <sys> --confidence proven|derived|assumed --source <file:line> --note "..."
```
(`zw atlas X` = `py -3 -I tools\za-atlas\P6\za_atlas.py X`.)

## Gotchas
- Data-side pointer tables (e.g. flag descriptors in `.data`) are **not** in refs: scan relocations with `tools/za-atlas/P2/extract.py` (Nso + relocate).
- Always `annotate` what you prove. That is how the next agent saves the hours you spent.
- Long doc (only if needed): `analysis/CODE-ATLAS-HE.md`.
