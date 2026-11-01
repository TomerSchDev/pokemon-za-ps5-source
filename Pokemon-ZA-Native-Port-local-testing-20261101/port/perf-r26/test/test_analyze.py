"""Host test of analyze_r26.py on a synthetic klog and measurement CSV: the dyn_* window keys summed (sim/wall, drift,
switches, step and anim counts), the boot's [za-r26] / [za-dyn] lines, windows outside the measurement and other boots
excluded, and r25's summary still present."""
import importlib.util
from pathlib import Path
import tempfile

spec = importlib.util.spec_from_file_location("analyze_r26", Path(__file__).resolve().parents[1] / "analyze_r26.py")
a = importlib.util.module_from_spec(spec)
spec.loader.exec_module(a)


def window(frame, frames, dyn):
    return (f"[za-r24-perf] frame={frame} frames={frames} logic_ns={frames * 1_400_000} logic_n={frames} "
            f"present_ns={frames * 300_000} present_n={frames} klock_takes=1 klock_blocked=0 klock_wait_ns=0 dcache_tables=0 "
            f"dcb=2640 kwords=120000 flush_ns=1 dcb_submit_ns=448800000 kick_ns=607200000 gaps=0 "
            f"cg_render=10 cg_render_ns=10 cg_render_max_ns=1 cg_guest=0 cg_guest_ns=0 cg_guest_max_ns=0 "
            f"cg_other=0 cg_other_ns=0 cg_other_max_ns=0 submit=thread exec_ns=1 rsub_ns=1 render_busy_ns=1 " + dyn)


def dyn(policy, mode, step, frames, wall, sim, sw=0, chg=0, gaps=0, steps="0/0", anim="0/0", req="-"):
    return (f"dyn={policy} dyn_req={req} dyn_mode={mode} dyn_step_ns={step} dyn_ema_ns={step} dyn_frames={frames} "
            f"dyn_wall_ns={wall} dyn_sim_ns={sim} dyn_drift_ns={wall - sim} dyn_simwall={sim / wall:.4f} dyn_sw={sw} "
            f"dyn_stepchg={chg} dyn_gaps={gaps} dyn_steps={steps} dyn_anim={anim}")


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    klog = d / "k.log"
    lines = [
        "[za-title-randomizer-r26-perf] main reached; starting native runtime",
        "[za-r26] dyn=off: the frame mode is r16's (za_title_frame_cfg, force60 wrap: static 60), as r25",
        window(100, 90, dyn("off", 0, 16666667, 90, 2_000_000_000, 1_500_000_030)),  # (other boot: static 60 at 45)
        "[za-title-randomizer-r26-perf] main reached; starting native runtime",
        "[za-r26] dyn=safe: dynamic timing owns the game's frame mode; r16's za_title_frame_cfg is not called, ...",
        "[za-r26] LARECOMP_PACE=0 (r16): generic pacing off, as dyn=safe requires",
        "[zarecomp] [za-dyn] policy=safe: dynamic owns the frame mode (r16 trial / force60 bypassed); present interval 1; ...",
        "[zarecomp] [za-dyn] dynamic mode -1 -> 0 (fps 58.00, step 17.241 ms, orig 1, var 0)",
        window(50, 50, dyn("safe", 0, 16666667, 50, 833_000_000, 833_000_000, req="safe")),  # before: excluded
        window(140, 90, dyn("safe", 1, 22222222, 90, 2_000_000_000, 1_998_000_000, sw=1, chg=2,
                            steps="90/0", anim="400/400", req="safe")),
        "[zarecomp] [za-dyn] dynamic mode 0 -> 1 (fps 45.00, step 22.222 ms, orig 1, var 0)",
        window(230, 90, dyn("safe", 1, 22222222, 90, 2_000_000_000, 2_002_000_000, gaps=1, steps="90/0",
                            anim="400/400", req="safe")),
        "[zarecomp] [za-dyn] mode=1 present=0 step_us=22222.2 fps=45.00 ema_ms=22.222 lag_ms=0.10 sw=1/0 gaps=1 cap=0 "
        "rb=0 dup=0 foreign=0 adopt=0 stand=0 fast=0 reg=0 sim/wall=1.0001 orig=1 var=0 steps=180/0 anim=800/800 t=1",
        window(320, 90, dyn("safe", 1, 22222222, 90, 2_000_000_000, 2_000_000_000, req="safe")),  # after: excluded
    ]
    klog.write_text("\n".join(lines) + "\n")
    csv = d / "measure.csv"
    csv.write_text("frame,now_ns\n" + "".join(f"{f},{f}\n" for f in range(51, 231)))
    first, last = a.r24.csv_frames(csv)
    windows, notes, r26_lines, dyn_lines = a.parse(klog, first, last)
    out = a.summarize(windows, notes, r26_lines, dyn_lines)["r26"]
    assert out["windows_with_dyn_keys"] == 2, out
    assert out["policies"] == ["safe"] and out["requested"] == ["safe"] and out["modes"] == [1], out
    assert out["frames"] == 180 and abs(out["sim_over_wall"] - 1.0) < 1e-9, out
    assert abs(out["drift_ms_per_wall_s"]) < 1e-9 and out["mode_switches"] == 1 and out["step_changes"] == 2, out
    assert out["gaps"] == 1 and out["steps_substituted"] == 180 and out["steps_passed"] == 0, out
    assert out["anim_calls"] == 800 and out["anim_same_mode"] == 800, out
    assert len(out["boot_lines"]) == 2 and "dyn=safe" in out["boot_lines"][0], out["boot_lines"]
    assert out["glue_init"] and out["glue_init"][0].startswith("policy=safe"), out["glue_init"]
    assert len(out["glue_switches"]) == 2, out["glue_switches"]
    last = out["glue_last_status"]
    assert last["foreign"] == "0" and last["var"] == "0" and last["fast"] == "0" and last["sim/wall"] == "1.0001", last
    # the first boot in its own snapshot (the analyzers bind a measurement to the last boot reaching its frames):
    # static 60 at 45 FPS reads as 0.75 of real time
    klog1 = d / "k1.log"
    klog1.write_text("\n".join(lines[:3]) + "\n")
    csv.write_text("frame,now_ns\n" + "".join(f"{f},{f}\n" for f in range(11, 101)))
    first, last2 = a.r24.csv_frames(csv)
    w2, n2, r2, d2 = a.parse(klog1, first, last2)
    o2 = a.summarize(w2, n2, r2, d2)["r26"]
    assert o2["policies"] == ["off"] and abs(o2["sim_over_wall"] - 0.75) < 1e-6 and o2["drift_ms_per_wall_s"] > 249, o2
print("PASS analyze_r26: dyn window keys summed, boot lines bound to their boot, other boots and windows excluded")
