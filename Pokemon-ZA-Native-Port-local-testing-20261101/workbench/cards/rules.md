# Rules (every agent reads this first — 1 minute)

Project: Pokémon Legends: Z-A 2.0.2 statically recompiled to native PS5. Owner: Tomer. Report to Tomer in Hebrew.

## Hard rules
0. Resource turns: read `cards/resource-queues.md`.
1. **Console (192.168.1.135)**: act on it only in a session Tomer coordinated, game closed, never kill an unknown process.
   Every console-touching `zw` verb refuses unless you pass `--console-ok` (or `ZW_CONSOLE_OK=1`).
2. **Saves**: back up and verify the save before any console change. Never restore an old save over newer progress.
3. **eboot upload**: `.new` → readback → rename → readback. Always keep a way back.
4. **Titles**: PPSA91762 = randomizer (the one Tomer plays). PPSA91761 = vanilla — do not touch without approval.
5. **Game data, text, saves, keys**: never in git, never uploaded anywhere. PC runs use a separate data root + copied save.
6. **Other Pokémon games' assets**: only from dumps of Tomer's own Switch. Never from `Downloads\Pokemon` or the internet.
7. **Config files on /app0**: `performance-options.txt` must be exactly `optimized`. r24+ knobs live only in `perf-r24-options.txt`.
   `force60` is for measurement only (below 60 the game slows down).
8. **Commits** only when asked. New builds always go to a **new** output folder.
9. **Code questions → atlas first** (`zw atlas ...`), and `annotate` every new name/address you learn. See `cards/atlas.md`.

## Where things are
| What | Path |
|---|---|
| Repo | `C:\Users\Tomer\Documents\ChatGPT\פריצות\PS5-13.60\Pokemon-ZA-Native-Port` |
| WSL build trees, SDK | `/home/tomer/ps5-za-native/` (run scripts via `wsl -d Ubuntu -- bash /mnt/c/.../x.sh`) |
| Runtime source | `PS5-13.60\pokeza-recomp-ps5` (branch `ps5`) |
| PC game (read-only) | `PS5-13.60\hebrew-lab\qa-game-reference-20261030` (the old Codex `...\game` path is gone; override with `ZA_PC_GAME_ROOT`) |
| PC runtime exe | `PS5-13.60\hebrew-lab\runtime\lasrecomp.exe` — copy it, never modify |
| NAS | `\\TheOnePiece\Software\PS5-13.60\` |
| Current state | top entries of `STATUS-HANDOFF-20261029-HE.md` and `analysis/CODEX-CONTINUATION-20261031-HE.md` |

Standing rules: `AGENTS.md` preserves Tomer's full prompt verbatim; `.cursor/rules/za-ps5-standing-rules.mdc` always applies, and `CLAUDE.md` imports `AGENTS.md`.
