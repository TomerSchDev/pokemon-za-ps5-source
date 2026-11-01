"""Offline r25 counters for one observer measurement; never accesses the console.

    python port/perf-r25/analyze_r25.py --klog SNAPSHOT.klog.log --csv .../measure_<seq>.csv [--out FILE.json]

port/perf-r24clock/analyze_r24clock.py's summary (r24-perf's keys, clock_gettime per thread class, the [vk] line's
profile fields when present) of the [za-r24-perf] windows inside the measurement CSV's frame range, plus r25's keys:
  render thread (TSC-timed on the thread that calls nvnQueueSubmitCommands, profile or not):
    exec_ms / rsub_ms per frame - exec_list, and its submission calls (vk_submit_extra + the r20b flush: with
    submit=inline that includes vkQueueSubmit2; with submit=thread the queueing and any back-pressure wait)
    acquire_ms per frame - vkAcquireNextImageKHR (inside present_ms), render_busy_ms = exec + rsub + logic + present
  submitter (submit=thread): items / presents per frame, busy_ms per frame (its vkQueueSubmit2 + vkQueuePresentKHR),
    pushes that found the queue full and their wait, the mean / largest queue depth, and the logical-submission lag
    (logical submissions not yet handed to the driver, sampled at each report)
  clock (za_clock_r25.c): calls answered from the TSC and through the game's real clock per frame, the mode, the
    TSC-derived minus real CLOCK_MONOTONIC drift sampled once a window, and RADV's recording worker's calls (cg_radv,
    radv_threaded=1 only: > 0 shows the worker runs)
  driver: AGC submissions (DCBs) per frame, dcb_submit / kick ms per frame and per DCB, command kwords per frame (r24's
    winsys timers, restated for the batch4 / batch8 comparison), with the r20b submission profile of the boot
The boot's "[za-r25]" / "[za-r25-clock]" / "[za-r20b-submit] startup" lines join r24-clock's notes, so the modes in
effect (submit, clock, radv_threaded, the batch profile) and the cross-core check are in the result. Window totals are
summed (never differenced) and divided by their frames.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("analyze_r24clock", _here.parent / "perf-r24clock/analyze_r24clock.py")
r24clock = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(r24clock)
r24 = r24clock.r24

NOTE = re.compile(r"\[za-r25\]|\[za-r25-clock\]|\[za-r24clock\]|\[sdl3-ps5\] ticks|\[ps5\] clock|\[za-r24-options\]"
                  r"|\[za-r20b-submit\] startup")
SUM_KEYS = ("exec_ns", "rsub_ns", "acquire_ns", "acquires", "render_busy_ns", "sub_items", "sub_presents", "sub_busy_ns",
            "sub_pushes", "sub_push_waits", "sub_push_wait_ns", "sub_depth_sum", "cg_tsc", "cg_game", "cg_radv",
            "dcb", "dcb_submit_ns", "kick_ns")


def note_value(notes, pattern):
    """The last boot note's capture for pattern (the boot's own setting), or None."""
    found = [m[1] for m in (re.search(pattern, n) for n in notes) if m]
    return found[-1] if found else None


def parse(klog, first, last):
    """As analyze_r24clock.parse, with r25's boot lines among the notes."""
    boots, current, notes = [], [], []
    for line in Path(klog).read_text(encoding="utf-8", errors="replace").splitlines():
        if re.search(r"\[za-title-[^\]]*\] main reached", line):
            if current or notes:
                boots.append((current, notes))
            current, notes = [], []
            continue
        if NOTE.search(line):
            notes.append(line.strip())
            continue
        m = re.search(r"\[za-r24-perf\] (.*)", line)
        if m:
            current.append(dict(re.findall(r"(\w+)=(\S+)", m[1])))
            continue
        if "[vk] t=" in line and current and "vk" not in current[-1]:
            v = r24clock.VK.search(line)
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
    out = r24clock.summarize(windows, notes)
    frames = out["frames"]
    pf = (lambda v: v / frames) if frames else (lambda v: None)
    tot = {k: sum(int(w.get(k, 0)) for w in windows) for k in SUM_KEYS}
    ms = lambda k: pf(tot[k] / 1e6)
    modes = sorted({w.get("submit") for w in windows if w.get("submit")})
    lags = [int(w["sub_lag"]) for w in windows if "sub_lag" in w]
    drifts = [int(w["ck_drift_ns"]) for w in windows if "ck_drift_ns" in w and w.get("ck") == "tsc"]
    per_call = lambda k: tot[k] / tot["dcb"] / 1e6 if tot["dcb"] else None
    radv_threaded = note_value(notes, r"\[za-r25\] radv_threaded=(\d)")
    out["r25"] = dict(
        submit_modes=modes,
        radv_threaded=None if radv_threaded is None else radv_threaded == "1",
        submission_profile=note_value(notes, r"\[za-r20b-submit\] startup profile=(\w+)"),
        driver=dict(dcb_submits_per_frame=pf(tot["dcb"]), dcb_submit_ms_per_frame=ms("dcb_submit_ns"),
                    dcb_submit_ms_per_dcb=per_call("dcb_submit_ns"), kick_ms_per_dcb=per_call("kick_ns"),
                    kwords_per_frame=out["per_frame"]["kwords"]),
        render=dict(exec_ms=ms("exec_ns"), rsub_ms=ms("rsub_ns"), acquire_ms=ms("acquire_ns"),
                    render_busy_ms=ms("render_busy_ns"), logic_ms=out.get("logic_ms_mean"),
                    present_ms=out.get("present_ms_mean")),
        submitter=dict(items_per_frame=pf(tot["sub_items"]), presents_per_frame=pf(tot["sub_presents"]),
                       busy_ms=ms("sub_busy_ns"), pushes_per_frame=pf(tot["sub_pushes"]),
                       push_waits=tot["sub_push_waits"], push_wait_ms_per_frame=ms("sub_push_wait_ns"),
                       mean_depth=tot["sub_depth_sum"] / tot["sub_pushes"] if tot["sub_pushes"] else None,
                       max_depth=max((int(w.get("sub_depth_max", 0)) for w in windows), default=0),
                       lag_mean=sum(lags) / len(lags) if lags else None, lag_max=max(lags) if lags else None),
        clock=dict(modes=sorted({w.get("ck") for w in windows if w.get("ck")}), tsc_calls_per_frame=pf(tot["cg_tsc"]),
                   game_calls_per_frame=pf(tot["cg_game"]), radv_worker_calls_per_frame=pf(tot["cg_radv"]),
                   drift_ns_min=min(drifts) if drifts else None, drift_ns_max=max(drifts) if drifts else None),
        windows_with_r25_keys=sum(1 for w in windows if "render_busy_ns" in w))
    out["caveats"] = out.get("caveats", []) + [
        "render_busy = exec + rsub + logic + present on the render thread (the audit's metric); present includes the "
        "acquire (reported separately) and logic includes the game's own recording and waits between its submissions.",
        "With submit=thread the [vk] line's submit field and rsub are the render thread's queueing cost; the driver "
        "submission time is the submitter's busy_ms (and r24's dcb_submit / flush / kick, now on the submitter).",
        "sub_lag is a gauge sampled once per window, not a time average.",
        "With radv_threaded=1 RADV's recording moves to its worker: the render thread's exec / logic keep only the "
        "argument copies and vkEndCommandBuffer's wait for that worker; the worker's clock reads are cg_radv alone."]
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
