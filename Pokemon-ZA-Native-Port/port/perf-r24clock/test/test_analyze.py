"""Host test of analyze_r24clock.py against a synthetic klog and CSV (no console)."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

here = Path(__file__).resolve().parent
tool = here.parent / "analyze_r24clock.py"


def perf(frame, frames, extra=""):
    return (f"[za-r24-perf] frame={frame} frames={frames} logic_ns=100 logic_n=10 present_ns=50 present_n=10 klock_takes=1 "
            f"klock_blocked=0 klock_wait_ns=0 dcache_tables=0 dcb=23 kwords=100 flush_ns=1 dcb_submit_ns=2 kick_ns=3 gaps=0"
            f"{extra}\n")


def vk(frame, gpu, exe, draw, sub):
    return (f"[vk] t=1.0 frame {frame} 39.0 fps max 27ms level - (955 draws, 0 skipped | gpu {gpu} cpu exec {exe} draw {draw} "
            f"(pre 1 key 1 dyn 1 sets 1 tex 1 (upload 1) vtx 1) submit {sub} ms | tex checks 1)\n")


def vk_plain(frame):
    return f"[vk] t=1.0 frame {frame} 39.0 fps max 27ms level - (955 draws, 0 skipped, 0 passes)\n"


def run(klog_text, csv_frames):
    with tempfile.TemporaryDirectory() as d:
        k, c = Path(d) / "k.log", Path(d) / "m.csv"
        k.write_text(klog_text, encoding="utf-8")
        c.write_text("frame,now_ns\n" + "".join(f"{f},{f}\n" for f in csv_frames), encoding="utf-8")
        out = subprocess.run([sys.executable, str(tool), "--klog", str(k), "--csv", str(c)], check=True,
                             capture_output=True, text=True).stdout
        return json.loads(out)


cg = " cg_render={} cg_render_ns={} cg_render_max_ns=30000 cg_guest=78 cg_guest_ns=1560000 cg_guest_max_ns=21000 cg_other=40 cg_other_ns=800000 cg_other_max_ns=20000"
# boot 1 (another launch; must be ignored), then boot 2 with the measurement: profile on
text = ("[za-title-randomizer-r24-clock] main reached\n" + perf(80, 78, cg.format(9999, 1)) + vk(80, 1, 1, 1, 1) +
        "[za-title-randomizer-r24-clock] main reached\n[sdl3-ps5] ticks: clock_gettime(CLOCK_MONOTONIC)\n"
        "[za-r24clock] vkprof: LARECOMP_VK_PROF set (r16 default); the renderer's CPU profile is on\n" +
        perf(78, 78, cg.format(78000, 1560000000)) + vk(78, 550, 1600, 1300, 230) +
        perf(156, 78, cg.format(78000, 1560000000)) + vk(156, 552, 1590, 1310, 228))
r = run(text, range(1, 157))
assert r["windows"] == 2 and r["frames"] == 156, r
assert r["clock_gettime"]["render"]["calls_per_frame"] == 1000.0
assert abs(r["clock_gettime"]["render"]["us_per_call"] - 20.0) < 1e-9
assert abs(r["clock_gettime"]["render"]["ms_per_frame"] - 20.0) < 1e-9
assert r["clock_gettime"]["guest"]["calls_per_frame"] == 1.0
assert r["vk_per_frame"] and abs(r["vk_per_frame"]["exec_ms"] - (1600 + 1590) / 156) < 1e-9
assert r["gpu_busy_source"].startswith("[vk]") and len(r["clock_notes"]) == 2
# profile off (vkprof=0): no [vk] gpu fields -> null, GPU busy only from gaps=1
text2 = ("[za-title-randomizer-r24-clock] main reached\n[za-r24clock] vkprof=0: LARECOMP_VK_PROF unset after r16's init\n" +
         perf(78, 78, cg.format(500, 10000000)) + vk_plain(78))
r2 = run(text2, range(1, 79))
assert r2["vk_per_frame"] is None and r2["gpu_busy_ms_per_frame"] is None and r2["gpu_busy_source"] is None
assert abs(r2["clock_gettime"]["render"]["calls_per_frame"] - 500 / 78) < 1e-9
# Actual hardware's long line can cut its trailing top-thread list mid-entry.
r3 = run(text2.replace("cg_other_max_ns=20000", "cg_other_max_ns=20000 top=122:12345:44:0:7008144a50,121:123"), range(1, 79))
assert r3["truncated_top_thread_entries_ignored"] == 1
assert r3["clock_gettime"] == r2["clock_gettime"]
assert len(r3["busiest_threads"]) == 1
print("PASS test_analyze: boot selection, clock_gettime per frame / per call, [vk] pairing with the profile on and off")
