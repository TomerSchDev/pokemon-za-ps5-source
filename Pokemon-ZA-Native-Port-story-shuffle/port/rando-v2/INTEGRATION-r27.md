# r27 trainer-name integration

The new-run name implementation is ready for integration over r26p1. This directory does not change game assets, console storage, performance code, or Hebrew translation. Existing `README-HE.md` describes the keyboard and save format; this note supersedes its source list and repair limitation.

## Title build

Use `port/rando-v2/native_menu.cpp` instead of `port/randomizer/native_menu.cpp`. Compile these additional sources and link all four resulting objects:

```
port/rando-v2/za_player_name.cpp
port/rando-v2/name_keyboard.cpp
port/rando-v2/run_name.cpp
```

Add `-I$root/port/rando-v2`. Compile `za_player_name.cpp` with `-DMBEDTLS_CONFIG_FILE=\"za_mbedtls_config.h\"`, matching the Mbed TLS library objects. The existing randomizer/core and run_store objects remain required. No asset hash or data changes are needed.

The menu calls `nameRun(name, result, error)` after starter/progression/reward generation and before `publishRun`. This updates only the fresh generated save and its report. `player_name_algorithm = za202-trainer-name-v1` identifies the operation for deterministic replay.

## Host-core replay and repair

Include `run_name.hpp` and link `run_name.cpp`, `za_player_name.cpp`, `run_store.cpp`, the existing core and the Mbed TLS objects. Call:

```cpp
// Freshly generated initial result, never the saved gameplay snapshot:
if (!za::native::replayRunName(originalReport, generatedResult, error)) {
    // Refuse repair/reconstruction with this error.
}
// Now compare generatedResult.report["save_sha256"] to originalReport["save_sha256"].
```

The old report lacking `player_name` is an identity operation. An invalid name, invalid report, orphan algorithm marker or unknown algorithm is rejected without modifying the result. The marker may be absent on reports from the original offline prototype. If a host CLI accepts only the name, it must call `nameRun` after `generate` and before writing its output report/save; the caller must separately validate optional algorithm metadata.

`repair-existing-run.py` remains a narrowly scoped r11 wild-table repair: its `za202-field-capabilities-v1`, wild enabled, and not-already-repaired checks must remain. Names do not make other runs eligible. Reconstructed starting saves serve only as the deterministic reference. The repair must preserve the current snapshot's `save/save_0/main` byte-for-byte, retaining its source hash/manifest checks and publishing a separate run. Never copy the regenerated initial save over gameplay progress.

## Persistence and continued runs

- NAME is only a new-run setting. Continue and Saved Runs never invoke the name writer.
- `save_sha256` records the starting save. Continue intentionally validates immutable tables but does not compare a progressed save to that starting hash.
- Old reports with no name continue normally and have a blank name suffix in Saved Runs. Malformed name metadata affects only that display suffix, not selection of otherwise valid old runs.
- `player-name.txt` is a preference for the next new run. It is written only after `publishRun` succeeds. Writes validate the name, handle interrupted/partial writes, fsync, read back, then atomically rename. A stale `.new` symlink is unlinked rather than followed. Known unsupported directory-fsync results match the existing run-store policy.
- Preference write failure is logged but does not prevent starting an already published run. A missing/invalid preference falls back to the template's name, then `Trainer`.
- Changing the preference or starting another named run does not rename existing saves. The template stays unchanged.

## Verification

See `test/evidence-r27-name-20261029.log`. The host tests run ASan/UBSan with `-Werror` using PKHeX-generated fixture copies. The new lifecycle test additionally covers deterministic named replay, old-report identity, malformed metadata rejection, duplicate-publication refusal, switching between old/named runs while retaining changed save bytes, and preference failure/stale-stage behavior. PS5 compilation and symbol compatibility checks cover all four sources.

All tests use generated fixture copies and a unique temporary directory. These checks do not establish on-console behavior. The title still needs a new-run test of the keyboard, trainer card and starter OT, followed by Continue and a return to an older run.
