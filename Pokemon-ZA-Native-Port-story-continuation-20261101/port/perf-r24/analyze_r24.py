"""Offline r24-perf counters for one observer measurement; never accesses the console.

    python port/perf-r24/analyze_r24.py --klog SNAPSHOT.klog.log --csv .../measure_<seq>.csv [--out FILE.json]

The runtime prints one "[za-r24-perf] frame=<presented so far> frames=<in window> key=value ..." line per ~2 s stats
window (exec.c za_r24_stats), right before that window's "[vk] t=..." line. Window totals reset every report, so
complete windows lying inside the measurement CSV's frame range are summed (never differenced) and divided by their
frames. Lines of other boots are excluded: only the last boot of the log that contains the CSV's frames is used
(a boot starts at "[za-title-... ] main reached"). GPU times are GPU-clock spans of logical submissions, CPU times
are host clocks; buckets overlap and are not a critical path. No winner is chosen here.
"""
import argparse
import csv
import json
from pathlib import Path
import re

INT_KEYS = ("frames", "logic_ns", "logic_n", "present_ns", "present_n", "klock_takes", "klock_blocked", "klock_wait_ns",
            "dcb", "kwords", "flush_ns", "dcb_submit_ns", "kick_ns", "spans", "gpu_span_ns", "gpu_busy_ns", "idle_ns",
            "idle_between_ns", "idle_within_ns", "idle_unknown_ns", "ngaps", "gap_lt100us", "gap_lt500us", "gap_lt2ms",
            "gap_lt8ms", "gap_ge8ms", "spans_dropped", "thread_cpu_ns")


def csv_frames(path):
    with Path(path).open(newline="") as f:
        frames = [int(r["frame"]) for r in csv.DictReader(f)]
    if not frames:
        raise ValueError("empty measurement CSV")
    return min(frames), max(frames)


def parse(klog, first, last):
    boots, current = [], []
    for line in Path(klog).read_text(encoding="utf-8", errors="replace").splitlines():
        if re.search(r"\[za-title-[^\]]*\] main reached", line):
            if current:
                boots.append(current)
            current = []
            continue
        m = re.search(r"\[za-r24-perf\] (.*)", line)
        if m:
            current.append(dict(re.findall(r"(\w+)=(\S+)", m[1])))
    if current:
        boots.append(current)
    for boot in reversed(boots):  # the last boot that reaches the measurement
        if any(int(w.get("frame", -1)) >= last for w in boot):
            return [w for w in boot if int(w["frames"]) > 0 and int(w["frame"]) - int(w["frames"]) + 1 >= first
                    and int(w["frame"]) <= last]
    return []


def summarize(windows):
    tot = {k: sum(int(w.get(k, 0)) for w in windows if int(w.get(k, 0)) >= 0) for k in INT_KEYS}
    frames = tot["frames"]
    pf = (lambda v: v / frames) if frames else (lambda v: None)
    threads = {}
    for w in windows:
        for item in filter(None, w.get("top", "").split(",")):
            tid, ns, prio, core, entry = item.split(":")
            t = threads.setdefault(tid, dict(prio=int(prio), core=int(core), entry="0x" + entry, cpu_ns=0, windows=0))
            t["cpu_ns"] += int(ns)
            t["windows"] += 1
    out = dict(
        windows=len(windows), frames=frames,
        first_window_end_frame=int(windows[0]["frame"]) if windows else None,
        last_window_end_frame=int(windows[-1]["frame"]) if windows else None,
        logic_ms_mean=tot["logic_ns"] / tot["logic_n"] / 1e6 if tot["logic_n"] else None,
        present_ms_mean=tot["present_ns"] / tot["present_n"] / 1e6 if tot["present_n"] else None,
        per_frame=dict(
            klock_takes=pf(tot["klock_takes"]), klock_blocked=pf(tot["klock_blocked"]),
            klock_wait_ms=pf(tot["klock_wait_ns"] / 1e6),
            dcb_submits=pf(tot["dcb"]), kwords=pf(tot["kwords"]),
            flush_ms=pf(tot["flush_ns"] / 1e6), dcb_submit_ms=pf(tot["dcb_submit_ns"] / 1e6),
            kick_ms=pf(tot["kick_ns"] / 1e6),
            gpu_spans=pf(tot["spans"]), gpu_busy_ms=pf(tot["gpu_busy_ns"] / 1e6), gpu_idle_ms=pf(tot["idle_ns"] / 1e6),
            gpu_idle_between_dcb_ms=pf(tot["idle_between_ns"] / 1e6), gpu_idle_within_dcb_ms=pf(tot["idle_within_ns"] / 1e6),
            gpu_idle_unknown_ms=pf(tot["idle_unknown_ns"] / 1e6), gaps=pf(tot["ngaps"]),
            thread_cpu_ms=pf(tot["thread_cpu_ns"] / 1e6)),
        gpu_busy_fraction=tot["gpu_busy_ns"] / tot["gpu_span_ns"] if tot["gpu_span_ns"] else None,
        gap_histogram=dict(lt100us=tot["gap_lt100us"], lt500us=tot["gap_lt500us"], lt2ms=tot["gap_lt2ms"],
                           lt8ms=tot["gap_lt8ms"], ge8ms=tot["gap_ge8ms"]),
        spans_dropped=tot["spans_dropped"],
        gaps_enabled=sorted({w.get("gaps") for w in windows}),
        thread_cpu_available=not any(w.get("threads") == "-1" for w in windows),
        busiest_threads=sorted(({"id": k, **v, "cpu_ms_per_frame": pf(v["cpu_ns"] / 1e6)} for k, v in threads.items()),
                               key=lambda t: -t["cpu_ns"])[:8],
        caveats=["Thread rows are summed only over the windows in which the thread was among the busiest six.",
                 "GPU busy/idle come from per-submission timestamps (gaps=1); idle_within_dcb is idle between "
                 "logical submissions inside one vkQueueSubmit2, idle_between_dcb between two.",
                 "flush/dcb_submit/kick are the PS5 winsys timers (radv_ps5_submit_times), read through link wraps."])
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--klog", type=Path, required=True)
    p.add_argument("--csv", type=Path, required=True)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    first, last = csv_frames(a.csv)
    windows = parse(a.klog, first, last)
    result = dict(klog=str(a.klog), csv=str(a.csv), csv_frames=[first, last], **summarize(windows))
    text = json.dumps(result, indent=2) + "\n"
    if a.out:
        a.out.write_text(text)
    print(text)


if __name__ == "__main__":
    main()
