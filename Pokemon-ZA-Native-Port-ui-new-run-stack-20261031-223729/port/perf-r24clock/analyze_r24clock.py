"""Offline r24-clock counters for one observer measurement; never accesses the console.

    python port/perf-r24clock/analyze_r24clock.py --klog SNAPSHOT.klog.log --csv .../measure_<seq>.csv [--out FILE.json]

port/perf-r24/analyze_r24.py's summary (the [za-r24-perf] windows inside the measurement CSV's frame range, of the last
boot that reaches it) plus r24-clock's keys and the paired [vk] line of each window:
  clock_gettime per frame and per call, by thread class (cg_render / cg_guest / cg_other on the [za-r24-perf] line;
  calls counted and timed with the TSC in za_clock.c's --wrap=clock_gettime)
  the [vk] line's "gpu / cpu exec / draw / submit" window totals (ms), present only while the renderer's CPU profile
  is on (vkprof absent or 1); with vkprof=0 they are absent and reported as null
  GPU busy from either source: the [vk] line's gpu (profile on) and gaps=1's gpu_busy_ns (GPU timeline)
The boot's "[za-r24clock]" / "[sdl3-ps5] ticks" / "[ps5] clock" lines are listed, so the clocks in effect and the TSC
self-check are in the result. Window totals are summed (never differenced) and divided by their frames.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re

_spec = importlib.util.spec_from_file_location("analyze_r24", Path(__file__).resolve().parents[1] / "perf-r24/analyze_r24.py")
r24 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r24)

CLASSES = ("render", "guest", "other")
VK = re.compile(r"\| gpu (\d+) cpu exec (\d+) draw (\d+) \(.*?\) submit (\d+) ms")


def parse(klog, first, last):
    """The windows ([za-r24-perf] dicts, each with its following [vk] line's fields) and the clock notes of the last
    boot that reaches the measurement."""
    boots, current, notes = [], [], []
    for line in Path(klog).read_text(encoding="utf-8", errors="replace").splitlines():
        if re.search(r"\[za-title-[^\]]*\] main reached", line):
            if current or notes:
                boots.append((current, notes))
            current, notes = [], []
            continue
        if re.search(r"\[za-r24clock\]|\[sdl3-ps5\] ticks|\[ps5\] clock|\[za-r24-options\]", line):
            notes.append(line.strip())
            continue
        m = re.search(r"\[za-r24-perf\] (.*)", line)
        if m:
            current.append(dict(re.findall(r"(\w+)=(\S+)", m[1])))
            continue
        if "[vk] t=" in line and current and "vk" not in current[-1]:
            v = VK.search(line)
            current[-1]["vk"] = dict(zip(("gpu_ms", "exec_ms", "draw_ms", "submit_ms"), map(int, v.groups()))) if v else None
    if current or notes:
        boots.append((current, notes))
    for windows, notes in reversed(boots):
        if any(int(w.get("frame", -1)) >= last for w in windows):
            sel = [w for w in windows if int(w["frames"]) > 0 and int(w["frame"]) - int(w["frames"]) + 1 >= first
                   and int(w["frame"]) <= last]
            return sel, notes
    return [], []


def summarize(windows, notes):
    out = r24.summarize(windows)
    frames = out["frames"]
    pf = (lambda v: v / frames) if frames else (lambda v: None)
    clock = {}
    for c in CLASSES:
        calls = sum(int(w.get(f"cg_{c}", 0)) for w in windows)
        ns = sum(int(w.get(f"cg_{c}_ns", 0)) for w in windows)
        mx = max((int(w.get(f"cg_{c}_max_ns", 0)) for w in windows), default=0)
        clock[c] = dict(calls_per_frame=pf(calls), ms_per_frame=pf(ns / 1e6), us_per_call=ns / calls / 1e3 if calls else None,
                        max_us=mx / 1e3)
    out["clock_gettime"] = clock
    out["clock_gettime_available"] = any("cg_render" in w for w in windows)
    vk = [w["vk"] for w in windows if w.get("vk")]
    if vk and len(vk) == len(windows):
        tot = {k: sum(v[k] for v in vk) for k in vk[0]}
        out["vk_per_frame"] = {k: pf(v) for k, v in tot.items()}
    else:
        out["vk_per_frame"] = None  # (the renderer's CPU profile was off: vkprof=0)
    gpu_gaps = out["per_frame"]["gpu_busy_ms"] if out["per_frame"].get("gpu_spans") else None
    out["gpu_busy_ms_per_frame"] = gpu_gaps if gpu_gaps else (out["vk_per_frame"] or {}).get("gpu_ms")
    out["gpu_busy_source"] = "gaps=1 GPU timeline" if gpu_gaps else "[vk] gpu (renderer CPU profile)" if out["vk_per_frame"] else None
    out["clock_notes"] = notes
    out["caveats"] = out.get("caveats", []) + [
        "clock_gettime counts cover the title's own objects and the RADV archive (--wrap); calls made inside system "
        "modules are not counted. The time per call is TSC-timed around the real call.",
        "The [vk] gpu/exec/draw/submit fields exist only while the renderer's CPU profile is on; they are window totals "
        "(ms) divided here by the window's frames."]
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--klog", type=Path, required=True)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    first, last = r24.csv_frames(a.csv)
    windows, notes = parse(a.klog, first, last)
    result = dict(klog=str(a.klog), csv=str(a.csv), csv_frames=[first, last], **summarize(windows, notes))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if a.out:
        a.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
