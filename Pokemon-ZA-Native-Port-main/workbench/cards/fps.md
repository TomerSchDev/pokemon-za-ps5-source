# Card: FPS — control and measurement

Goal order (Tomer): stable 60 FPS → 4K → models/cutscene skip. Today: stable 30, output 4K, render 1080p.

## The three control layers
1. **`/app0/performance-options.txt`** — must be exactly `optimized` + newline. Anything else disables optimizations.
   The game always boots at 30 FPS.
2. **`/app0/perf-r24-options.txt`** — `key=value`, read once at boot (restart the title after a change).
   Shipped play config: `scale=1  ticks=tsc  vkprof=0  submit=thread  fps=1`.
   | key | values | meaning |
   |---|---|---|
   | `vkprof` | 0/1 | renderer timing; **1 costs ~14k clock_gettime/frame** (the old 39-FPS cap) |
   | `ticks` | `tsc` | clock source |
   | `submit` | `thread` | threaded submission (+6 FPS in the café scene) |
   | `fps` | 0/1 | FPS counter overlay default (r26p+) |
   | `force60` | 1 | lock 60 — **measurement only**, overrides `dyn` |
   | `dyn` | off/safe/rc3 | dynamic timing (r26). Built, **not hardware-tested** |
   | `radv_threaded`, `clock`, `prof`, `sample*`, `dcache`, `mode`, `gaps` | | research knobs (see `port/perf-r24clock/za_r24clock_options.h`, `port/perf-r26/`) |
3. **Runtime** — L3+R3 menu: *FPS TRIAL* (60, auto-fallback to 30; disabled when `force60`/`dyn` set) and *FPS COUNTER*.
   Remotely: `zw fps set 1|0 --console-ok`.

## Measure
- Console: `zw fps measure <seconds> --out <dir> --console-ok` → CSV + analysis (`cards/console-observe.md`).
- Offline re-analysis: `zw fps analyze <measure.csv>`; klog + CSV clock analysis: `py -3 -I port\perf-r24clock\analyze_r24clock.py --klog K --csv C`.
- PC: `zw pc run ... --fps 60` then `zw pc fps <run>` (knobs in `cards/pc-run.md`).
- Compare A/B on the **same saved scene**; never claim a speedup from one run.

## Known facts (don't re-prove)
- Café scene: 47.5 FPS base, 53.5 with `submit=thread` + queue depth 64. batch8 is worse; `radv_threaded` gives nothing.
- TSC cross-core check failed (affinity rc=34) — open item.
- Next lever: per-draw cost (texture-binding cache `vk_tex`, push descriptors, pre memo, dirty state; est. 2–4 ms).

Deep reading only if needed: `analysis/FPS-PLAN-HE.md`, `analysis/fps-headroom-audit-HE.md`, `analysis/dynamic-timing-design-HE.md`.
