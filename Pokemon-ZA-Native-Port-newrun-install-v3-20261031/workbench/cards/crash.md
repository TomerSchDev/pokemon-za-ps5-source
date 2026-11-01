# Card: crash / log symbolization (offline)

Input: a klog text file with `[za-native-fault] sig= fa= pc=` and `[zarecomp] #` frames.
Need: the **exact** `llvm-pie.elf` of the build that crashed (in its WSL work tree), load base `0x400000`.

```powershell
zw crash <klog.txt> --elf /home/tomer/ps5-za-native/<tree>/llvm-pie.elf [--runtime <runtime.elf>] [--all] [--json]
```
(= `py -3 -I tools\za-atlas\P4\crash.py ...`; uses `tools/za-atlas/P4/llvm_bridge.sh` through WSL Ubuntu.)

- Wrong ELF = confidently wrong names. Match the eboot SHA-256 to the tree first (`zw za verify <profile>` for r27b/r28/r28a/r28b).
- Getting the klog in the first place: `cards/console-observe.md` → `zw klog`.
- Crash logs Tomer exports land in `PS5-13.60\Pokemon-ZA-Crash-Logs-*`.
