"""Host test of analyze_r25.py on a synthetic klog and measurement CSV: r25's keys summed per frame, the boot's notes
(submit, clock, radv_threaded, the r20b batch profile), the driver's DCB counts per frame and per DCB, windows outside
the measurement and other boots excluded."""
import importlib.util
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location("analyze_r25", Path(__file__).resolve().parents[1] / "analyze_r25.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def window(frame, frames, extra):
    base = (f"[za-r24-perf] frame={frame} frames={frames} logic_ns={frames * 1_400_000} logic_n={frames} "
            f"present_ns={frames * 300_000} present_n={frames} klock_takes=1 klock_blocked=0 klock_wait_ns=0 dcache_tables=0 "
            f"dcb=2640 kwords=120000 flush_ns=1 dcb_submit_ns=448800000 kick_ns=607200000 gaps=0 "
            f"cg_render=10 cg_render_ns=10 cg_render_max_ns=1 "
            f"cg_guest=0 cg_guest_ns=0 cg_guest_max_ns=0 cg_other=0 cg_other_ns=0 cg_other_max_ns=0 ")
    return base + extra


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    klog = d / "k.log"
    lines = [
        "[za-title-randomizer-r25-perf] main reached; starting native runtime",
        "[za-r25] radv_threaded=0: RADV records on the calling thread (r24-clock)",
        "[za-r20b-submit] startup profile=batch4; bounded within one NVN call; lists=4 draws=400 commands=32768 ...",
        window(100, 100, "submit=inline exec_ns=1 rsub_ns=1 acquire_ns=0 acquires=0 render_busy_ns=1"),  # (other boot)
        "[za-title-randomizer-r25-perf] main reached; starting native runtime",
        "[za-r25-clock] cross-core TSC check: 13 CPUs (affinity rc 0), 12 pairs x 1000 rounds, all pinned=1, ...: accepted",
        "[za-r25] radv_threaded=1: RADV_THREADED_RECORDING=1 set before vkCreateInstance (...)",
        "[za-r25] submission: thread - vkQueueSubmit2 and vkQueuePresentKHR on the submitter (queue 64 items, ...)",
        "[za-r20b-submit] startup profile=batch8; bounded within one NVN call; lists=8 draws=400 commands=32768 ...",
        window(50, 50, "submit=thread exec_ns=1 rsub_ns=1"),  # before the measurement: excluded
        window(170, 120, "submit=thread exec_ns=1068000000 rsub_ns=60000000 acquire_ns=12000000 acquires=120 "
                         "render_busy_ns=1332000000 sub_items=2880 sub_presents=120 sub_busy_ns=516000000 sub_pushes=2880 "
                         "sub_push_waits=3 sub_push_wait_ns=600000 sub_depth_sum=5760 sub_depth_max=7 sub_lag=5 "
                         "cg_tsc=100000 cg_game=24000 ck=tsc ck_drift_ns=-150 cg_radv=60000 top=1:2:3:4:00000000000a"),
        "[vk] t=4.0 frame 170 60.0 fps max 17ms level - (955 draws)",
        window(290, 120, "submit=thread exec_ns=1068000000 rsub_ns=60000000 acquire_ns=12000000 acquires=120 "
                         "render_busy_ns=1332000000 sub_items=2880 sub_presents=120 sub_busy_ns=516000000 sub_pushes=2880 "
                         "sub_push_waits=1 sub_push_wait_ns=200000 sub_depth_sum=5760 sub_depth_max=9 sub_lag=3 "
                         "cg_tsc=100000 cg_game=24000 ck=tsc ck_drift_ns=210 cg_radv=36000"),
        window(400, 110, "submit=thread exec_ns=5 rsub_ns=5"),  # after the measurement: excluded
    ]
    klog.write_text("\n".join(lines) + "\n", encoding="utf-8")
    csv = d / "m.csv"
    csv.write_text("frame,now_ns\n" + "".join(f"{f},{f * 16_666_667}\n" for f in range(51, 291)), encoding="utf-8")
    first, last = a.r24.csv_frames(csv)
    windows, notes = a.parse(klog, first, last)
    assert [int(w["frame"]) for w in windows] == [170, 290], windows
    assert any("[za-r25] submission: thread" in n for n in notes) and any("[za-r25-clock]" in n for n in notes)
    out = a.summarize(windows, notes)
    r = out["r25"]
    assert out["frames"] == 240
    assert r["submit_modes"] == ["thread"]
    assert abs(r["render"]["exec_ms"] - 8.9) < 1e-9 and abs(r["render"]["rsub_ms"] - 0.5) < 1e-9
    assert abs(r["render"]["render_busy_ms"] - 11.1) < 1e-9 and abs(r["render"]["acquire_ms"] - 0.1) < 1e-9
    s = r["submitter"]
    assert s["items_per_frame"] == 24 and s["presents_per_frame"] == 1 and abs(s["busy_ms"] - 4.3) < 1e-9
    assert s["push_waits"] == 4 and s["mean_depth"] == 2 and s["max_depth"] == 9 and s["lag_max"] == 5 and s["lag_mean"] == 4
    c = r["clock"]
    assert c["modes"] == ["tsc"] and abs(c["tsc_calls_per_frame"] - 100000 / 120) < 1e-9 and c["game_calls_per_frame"] == 200
    assert c["drift_ns_min"] == -150 and c["drift_ns_max"] == 210
    assert c["radv_worker_calls_per_frame"] == 400
    assert r["radv_threaded"] is True and r["submission_profile"] == "batch8"  # the measured boot's, not the other's
    v = r["driver"]
    assert v["dcb_submits_per_frame"] == 22 and abs(v["dcb_submit_ms_per_frame"] - 3.74) < 1e-9
    assert abs(v["dcb_submit_ms_per_dcb"] - 0.17) < 1e-9 and abs(v["kick_ms_per_dcb"] - 0.23) < 1e-9
    assert v["kwords_per_frame"] == 1000
    assert r["windows_with_r25_keys"] == 2
    # a boot without the r25 / r20b lines (an older log): the modes are unknown, not guessed
    assert a.summarize(windows, [])["r25"]["radv_threaded"] is None
print("PASS analyze_r25.py: r25 keys per frame, notes (radv_threaded, batch profile), DCBs per frame and per DCB, "
      "windows of other boots / outside the measurement excluded")
