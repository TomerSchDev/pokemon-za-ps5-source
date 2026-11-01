# Card: build a PS5 eboot

All builds run in WSL Ubuntu under `/home/tomer/ps5-za-native/`. No builder touches the console.
Env used by builders: `PS5_VULKAN=/home/tomer/ps5-za-native/PS5_Vulkan`, `PS5_CLANG=/usr/bin/clang-21`.

## Front door
```powershell
zw za profiles | doctor all | verify all          # pinned historical builds r27b / r28 / r28a / r28b
zw za reproduce all --out /home/tomer/ps5-za-native/za-reproduce-NEW
zw za build r29-ui --out /home/tomer/ps5-za-native/r29-ui-NEW --package <new dir>
```
(`zw za X` = `tools\za\za.cmd X`. Details: `tools/za/README-HE.md`.)

## The recipe every builder follows (copy it for a new feature)
1. Pin input SHA-256s. 2. Require a **new** output dir. 3. `cp -a --reflink` the base tree.
4. Rebuild unchanged "control" objects and `cmp` them byte-for-byte against the base — stop on mismatch.
5. Compile only changed objects. 6. Rewrite `ZA_PS5_EXTRA_INPUTS` from the base's `link-inputs.txt`.
7. `source/tools/ps5/link-title.sh` → `llvm-pie.elf`. 8. `verify-registration.py` + `verify-image.py`.
9. `llvm-strip` → `ps5-native-tool link --module-sdk 0x02000009 --companion-sdk 0x08050001` → `self --sign --magic 0x1D3D154F`.
10. Write `evidence/` (`build.log`, `SHA256SUMS`, self-inspection).

## Per-release builders (newest first)
| Build | Script | Base |
|---|---|---|
| r29-ui | `port/ui-v2/tools/build-r29-ui.py --out NEW [--package NEW]` (via `zw za build r29-ui`) | r28b DLC Dex + Music |
| r29-music | `port/rando-music/build-r29-music.sh PLAN.json PLAN_SHA [r28\|r27b\|tree=DIR]` | r28 / tree |
| r28b | `port/r28b-dlc-dex/`: prepare-merge-tree.py → build-feature.sh → build-music-variant.sh → finish-image.sh → final-audit.sh | r28a |
| r28a | `port/runtime-texfix/build-r28a-candidate.sh` → `build-r28a-final.sh` (+ `rando-dexcount/ps5/apply-r28a.sh`) | r28 |
| r28 | `port/perf-r28/build-r28-play.sh PC_PROOF.json` | r27b |

## Gotchas
- Paths with spaces/Hebrew break several scripts: keep build dirs under `/home/tomer/ps5-za-native/`.
- `za reproduce` relinks frozen objects; it is **not** a full AOT rebuild.
- Before shipping: PC proof when possible, Hebrew install + test + rollback instructions for Tomer.
- Merge rule: never put an r28a/r28b base over an eboot that already has music/model changes. Merge first.
- Overlay fd fix is in runtime branch `fix/overlay-fd-limit` 57e3b9d (test: `tools/test_fs_overlay_fds.sh`); every new build must include it (fs.o/ipc.o/kernel.o of r28b-dlc-dex-fd-20261031-r1).
