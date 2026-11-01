# Card: console observe — screenshot, FPS measure, input, klog

The installed randomizer builds ship an **observer** (protocol 17): a mailbox over FTP.
Commands go to `/data/homebrew/PPSA91762/observer-command.txt`; receipts and files come back from
`/mnt/sandbox/PPSA91762_000/download0/zarecomp/observer/session_<sid>/`.
Needs: game running, `/app0/observer-enable.txt` present (it is in r27b+ packages). **Requires `--console-ok`.**

```powershell
zw obs status --console-ok                                   # session id; proves observer is alive
zw shot --out <dir> --console-ok                             # snapshot + verified download -> frame_<frame>_<seq>.png
zw fps measure 20 --out <dir> --console-ok                   # 20 s present-interval CSV + analysis JSON
zw input A 4 --console-ok                                    # press a button for N frames
zw fps set 1 --console-ok                                    # request 60 (1) / 30 (0), same as the menu FPS TRIAL
zw klog --out <file.log> --seconds 60 --console-ok           # capture klog (TCP 3232)
```
`zw` keeps the per-session sequence counter for you in `PS5-13.60\zw-state\` (seq must increase per session).
Raw client (all ops): `py -3 -I port\perf-r24\observer\client.py <op> --session SID --seq N [value]`, then `collect --session SID --seq N --out DIR`.

## Gotchas
- **One caller at a time.** Don't run two agents against the observer.
- **No FTP traffic during `measure`.** `zw fps measure` waits `seconds + 3` before collecting; don't run other FTP tools meanwhile.
- `measure` is 1–120 s. Output: p50/p95/p99, 1% low, frames over 16.7 / 33.3 ms (`port/perf-r24/observer/analyze.py`).
- klog replays its buffer on connect. The first ~2 s are dropped.
- Screenshots stay on the console until retired (raw client, next seq by hand): `zw obs retire_capture --session SID --seq N <sid>:<shot seq> --console-ok`.
- Ports: FTP 2121 (anonymous), Payload Manager 8084, klog 3232.
