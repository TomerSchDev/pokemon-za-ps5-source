"""Offline r26 counters for one observer measurement; never accesses the console.

    python port/perf-r26/analyze_r26.py --klog SNAPSHOT.klog.log --csv .../measure_<seq>.csv [--out FILE.json]

port/perf-r25/analyze_r25.py's summary (r24's keys, r24-clock's clock counters, r25's render / submitter / clock /
driver keys) of the [za-r24-perf] windows inside the measurement CSV's frame range, plus r26's dynamic frame timing:
  dyn: the policy in effect and as asked (dyn / dyn_req), the frame modes and steps seen, the smoothed frame time,
       frames, wall and simulation time summed over the windows, sim/wall and the drift (wall - sim) per wall second,
       mode switches, visible step changes (>= 0.5 ms), gaps (> 250 ms) left out, and the H3-H5 / H6-H7 call counts
  boot: the boot's "[za-r26]" lines (the dyn decision, force60's override, LARECOMP_PACE) and "[za-dyn]" lines (the
       glue's init line, mode switches, and its last status line: the model's cumulative counters - orig / var /
       foreign / adopt / stand / fast / sim/wall - for the acceptance checks of TEST-r26-HE.md)
Window totals are summed (never differenced) and divided by their frames or wall time.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("analyze_r25", _here.parent / "perf-r25/analyze_r25.py")
r25 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r25)
r24 = r25.r24

DYN_NOTE = re.compile(r"\[za-r26\]")
DYN_LINE = re.compile(r"\[za-dyn\] (.*)")


def parse(klog, first, last):
    """r25's windows and notes of the boot that holds the measurement, with that boot's [za-r26] / [za-dyn] lines."""
    windows, notes = r25.parse(klog, first, last)
    boots, cur = [], dict(r26=[], dyn=[], frames=[])
    for line in Path(klog).read_text(encoding="utf-8", errors="replace").splitlines():
        if re.search(r"\[za-title-[^\]]*\] main reached", line):
            boots.append(cur)
            cur = dict(r26=[], dyn=[], frames=[])
            continue
        if DYN_NOTE.search(line):
            cur["r26"].append(line.strip())
        m = DYN_LINE.search(line)
        if m:
            cur["dyn"].append(m[1].strip())
        m = re.search(r"\[za-r24-perf\] frame=(\d+)", line)
        if m:
            cur["frames"].append(int(m[1]))
    boots.append(cur)
    boot = next((b for b in reversed(boots) if any(f >= last for f in b["frames"])), dict(r26=[], dyn=[]))
    return windows, notes, boot["r26"], boot["dyn"]


def pair(value):
    a, _, b = (value or "0/0").partition("/")
    return int(a or 0), int(b or 0)


def summarize(windows, notes, r26_lines, dyn_lines):
    out = r25.summarize(windows, notes)
    dw = [w for w in windows if "dyn" in w]
    tot = {k: sum(int(w.get(k, 0)) for w in dw)
           for k in ("dyn_frames", "dyn_wall_ns", "dyn_sim_ns", "dyn_sw", "dyn_stepchg", "dyn_gaps")}
    steps = [pair(w.get("dyn_steps")) for w in dw]
    anim = [pair(w.get("dyn_anim")) for w in dw]
    status = [d for d in dyn_lines if d.startswith("mode=")]
    last = dict(re.findall(r"([\w/]+)=(\S+)", status[-1])) if status else {}
    wall, sim = tot["dyn_wall_ns"], tot["dyn_sim_ns"]
    out["r26"] = dict(
        policies=sorted({w["dyn"] for w in dw}), requested=sorted({w.get("dyn_req", "-") for w in dw}),
        modes=sorted({int(w["dyn_mode"]) for w in dw if "dyn_mode" in w}),
        step_ms_min=min((int(w["dyn_step_ns"]) / 1e6 for w in dw), default=None),
        step_ms_max=max((int(w["dyn_step_ns"]) / 1e6 for w in dw), default=None),
        ema_ms_min=min((int(w["dyn_ema_ns"]) / 1e6 for w in dw), default=None),
        ema_ms_max=max((int(w["dyn_ema_ns"]) / 1e6 for w in dw), default=None),
        frames=tot["dyn_frames"], wall_s=wall / 1e9, sim_s=sim / 1e9,
        sim_over_wall=sim / wall if wall else None,
        drift_ms_per_wall_s=(wall - sim) / wall * 1e3 if wall else None,
        mode_switches=tot["dyn_sw"], step_changes=tot["dyn_stepchg"], gaps=tot["dyn_gaps"],
        steps_substituted=sum(s for s, _ in steps), steps_passed=sum(p for _, p in steps),
        anim_calls=sum(c for c, _ in anim), anim_same_mode=sum(s for _, s in anim),
        windows_with_dyn_keys=len(dw),
        boot_lines=r26_lines,
        glue_init=[d for d in dyn_lines if d.startswith("policy=")],
        glue_switches=[d for d in dyn_lines if " mode " in d and "->" in d][-20:],
        glue_last_status=last)
    out["caveats"] = out.get("caveats", []) + [
        "dyn_sim is the step handed out at each frame-mode read (the dynamic step, or the duration table's value for "
        "the returned mode); dyn_wall is the time between those reads, gaps over 250 ms left out. sim/wall below 1 is "
        "slow motion (static 60 under 60 FPS), 1.0 is real time.",
        "The glue's [za-dyn] counters are cumulative since its init; the window keys are differences per window."]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--klog", type=Path, required=True)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    first, last = r24.csv_frames(a.csv)
    windows, notes, r26_lines, dyn_lines = parse(a.klog, first, last)
    result = dict(klog=str(a.klog), csv=str(a.csv), csv_frames=[first, last],
                  **summarize(windows, notes, r26_lines, dyn_lines))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
