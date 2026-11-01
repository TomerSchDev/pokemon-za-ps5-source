"""Offline r21 same-binary comparison evidence; never accesses the console.

Public API: analyze_suite(evidence, logs=None, phase_paths=None, session=None,
                         boot=None) -> JSON-serializable dict.
Only complete profiler windows wholly within a validated measurement CSV are
used. Cumulative counters are differenced only across adjacent samples in the
same process boot and uninterrupted preparation/submission profile epoch.
No winner, causal FPS claim, or sum of overlapping timers is produced.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

PROFILES = {"baseline": 0, "plan-only": 1, "lazy-only": 2, "optimized": 3}
COUNTERS = ("calls", "vs", "fs", "cs", "ordinary_visits", "special_visits",
            "rscale_builds", "rscale_skips", "allocs", "updates", "writes")
TIMER_PATTERNS = {
    "draws": r"\((\d+) draws", "passes": r"(\d+) passes",
    "dispatches": r"(\d+) dispatches", "compiles": r"compile (\d+)",
    "submit_ms": r"submit (\d+) ms", "exec_ms": r"cpu exec (\d+)",
    "draw_ms": r"cpu exec \d+ draw (\d+)", "sets_ms": r"sets (\d+)",
    "pre_ms": r"\(pre (\d+)", "key_ms": r" key (\d+)",
    "dyn_ms": r" dyn (\d+)", "tex_ms": r" tex (\d+) \(upload",
    "upload_ms": r"\(upload (\d+)\)", "vtx_ms": r" vtx (\d+)\)",
    "gpu_query_sum_ms": r"\| gpu (\d+)", "ring_ms": r"ring slot \d+x (\d+) ms",
}
CAVEATS = [
    "CSV rates measure CPU intervals between present submissions, not scanout or simulation speed.",
    "Profiler CPU timers nest/overlap; GPU query intervals may overlap. Never add these fields or infer a critical path by subtraction.",
    "sets_ms includes graphics constant/resource preparation and allocation/update; graphics descriptor binding and compute/post/present work are not all in this bucket.",
    "Preparation counters cover every stage_set call, including compute; they are not all limited to the graphics sets timer.",
    "Counter rates use only adjacent uninterrupted same-profile snapshots and complete windows inside the CSV. Coverage can be smaller than the CSV.",
    "A valid measurement does not establish visual correctness, equivalent scene/camera, stability, or causality. Interpretation belongs to the hardware reviewer.",
    "Preparation startup is baseline. This analyzer does not persist or change any profile.",
]


def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()


def parse_log_text(text, name="<memory>"):
    """Parse one klog snapshot; keep rejected windows and source lines as evidence."""
    windows, transitions, diagnostics = [], [], []
    boot, startup_seen, prep_epoch, submit_epoch = 0, False, 0, 0
    sessions = {0: set()}
    previous = pending_prep = pending_submit = None
    last_frame = None
    for lineno, line in enumerate(text.splitlines(), 1):
        if re.search(r"\[za-r20b?-submit\] startup", line):
            if startup_seen or previous is not None:
                boot += 1
            startup_seen = True
            sessions.setdefault(boot, set())
            previous = pending_prep = pending_submit = None
            last_frame = None
            prep_epoch = submit_epoch = 0
        session_match = re.search(r"session_([0-9a-f]{16})(?:/|\b)", line)
        if session_match:
            sessions.setdefault(boot, set()).add(session_match[1])
        applied = re.search(r"\[za-r21-prep\] applied frame=(\d+) profile=([\w-]+) flags=(\d+) previous=([\w-]+) drained_seq=(\d+)", line)
        if applied:
            prep_epoch += 1
            transitions.append(dict(log=name, line=lineno, boot=boot, frame=int(applied[1]),
                                    profile=applied[2], flags=int(applied[3]), previous=applied[4],
                                    drained_seq=int(applied[5]), prep_epoch=prep_epoch))
            pending_prep = None
        if re.search(r"\[za-r20b?-submit\] applied ", line):
            submit_epoch += 1
            pending_submit = None
        prep = re.search(r"\[za-r21-prep\] profile=([\w-]+) flags=(\d+) (.*)", line)
        if prep:
            values = {k: int(v) for k, v in re.findall(r"(\w+)=(\d+)", prep[3])}
            if prep[1] not in PROFILES or PROFILES[prep[1]] != int(prep[2]) or not all(k in values for k in COUNTERS):
                diagnostics.append(dict(line=lineno, reason="invalid_or_incomplete_preparation_counter_line"))
                pending_prep = None
            else:
                pending_prep = dict(line=lineno, profile=prep[1], flags=int(prep[2]),
                                    counters={k: values[k] for k in COUNTERS}, prep_epoch=prep_epoch)
        submit = re.search(r"\[za-r20b?-submit\] profile=(\w+) logical=(\d+) vk_calls=(\d+)", line)
        if submit:
            pending_submit = dict(line=lineno, profile=submit[1], logical=int(submit[2]),
                                  vk_calls=int(submit[3]), submit_epoch=submit_epoch)
        match = re.search(r"\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps", line)
        if not match:
            continue
        frame = int(match[2])
        if last_frame is not None and frame < last_frame:
            boot += 1
            sessions.setdefault(boot, set())
            previous = None
            diagnostics.append(dict(line=lineno, boot=boot, reason="frame_counter_reset_new_boot"))
        if last_frame is not None and frame == last_frame:
            diagnostics.append(dict(line=lineno, boot=boot, reason="duplicate_profiler_frame_ignored"))
            pending_prep = pending_submit = None
            continue
        current = dict(log=name, line=lineno, boot=boot, frame=frame, prep=pending_prep,
                       submit=pending_submit, prep_epoch=prep_epoch, submit_epoch=submit_epoch)
        if previous is not None:
            reasons = []
            row = dict(log=name, line=lineno, previous_line=previous["line"], boot=boot,
                       start=previous["frame"] + 1, end=frame, frames=frame - previous["frame"],
                       prep_epoch=prep_epoch, submit_epoch=submit_epoch)
            a, b = previous["prep"], current["prep"]
            if not a or not b:
                reasons.append("missing_adjacent_preparation_snapshot")
            else:
                row.update(profile=b["profile"], flags=b["flags"], counter_lines=[a["line"], b["line"]])
                if a["profile"] != b["profile"] or a["flags"] != b["flags"]:
                    reasons.append("preparation_profile_changed")
                if previous["prep_epoch"] != current["prep_epoch"]:
                    reasons.append("window_crosses_preparation_transition")
                delta = {k: b["counters"][k] - a["counters"][k] for k in COUNTERS}
                if any(v < 0 for v in delta.values()):
                    reasons.append("preparation_counters_reset_or_regressed")
                if not reasons:
                    if delta["calls"] != delta["vs"] + delta["fs"] + delta["cs"]:
                        reasons.append("stage_call_counter_invariant_failed")
                    if delta["allocs"] != delta["calls"] or delta["rscale_builds"] + delta["rscale_skips"] != delta["calls"]:
                        reasons.append("allocation_or_rscale_counter_invariant_failed")
                    if delta["updates"] > delta["calls"] or delta["writes"] < delta["updates"]:
                        reasons.append("update_counter_invariant_failed")
                row["counter_delta"] = delta
            sa, sb = previous["submit"], current["submit"]
            if not sa or not sb:
                reasons.append("missing_adjacent_submission_snapshot")
            else:
                row["submission_profile"] = sb["profile"]
                if sa["profile"] != sb["profile"] or previous["submit_epoch"] != current["submit_epoch"]:
                    reasons.append("window_crosses_submission_transition")
                row["logical"] = sb["logical"] - sa["logical"]
                row["vk_calls"] = sb["vk_calls"] - sa["vk_calls"]
                if row["logical"] < 0 or row["vk_calls"] < 0:
                    reasons.append("submission_counters_reset_or_regressed")
            for field, pattern in TIMER_PATTERNS.items():
                m = re.search(pattern, line)
                if m:
                    row[field] = int(m[1])
            row["valid"] = not reasons
            row["rejected_reasons"] = reasons
            windows.append(row)
        previous = current
        last_frame = frame
        # Never silently reuse a stale counter line when a reporter line is missing.
        pending_prep = pending_submit = None
    return dict(log=name, windows=windows, transitions=transitions,
                sessions_by_boot={str(k): sorted(v) for k, v in sessions.items()}, diagnostics=diagnostics)


def parse_log(path):
    path = Path(path)
    data = path.read_bytes()
    result = parse_log_text(data.decode("utf-8", errors="replace"), str(path))
    result.update(sha256=sha_bytes(data), bytes=len(data))
    return result


def interval_stats(rows):
    if not rows:
        return {"intervals": 0}
    ms = sorted(r["dt_ns"] / 1e6 for r in rows)
    def percentile(q):
        return ms[min(len(ms) - 1, max(0, math.ceil(q * len(ms)) - 1))]
    worst = max(1, math.ceil(len(ms) * .01))
    return dict(intervals=len(rows), duration_s=sum(ms) / 1000,
                interval_rate_fps=1000 * len(ms) / sum(ms), mean_frame_ms=sum(ms) / len(ms),
                frame_ms={"p50": percentile(.5), "p95": percentile(.95), "p99": percentile(.99), "max": ms[-1]},
                one_percent_low_fps=1000 / (sum(ms[-worst:]) / worst),
                over_16_667_ms=sum(x > 1000 / 60 for x in ms),
                over_33_333_ms=sum(x > 1000 / 30 for x in ms), over_50_ms=sum(x > 50 for x in ms),
                observer_cpu_us_mean=sum(r["observer_ns"] for r in rows) / len(rows) / 1000)


def read_intervals(path):
    import io
    data = Path(path).read_bytes()
    rows = [{k: int(v) for k, v in r.items()} for r in csv.DictReader(io.StringIO(data.decode("utf-8-sig")))]
    if not rows:
        raise ValueError("empty measurement CSV")
    required = {"frame", "now_ns", "dt_ns", "submitted_interval", "represented_interval", "shader_before", "shader_after", "mode", "observer_ns"}
    for i, row in enumerate(rows):
        if not required <= row.keys() or row["dt_ns"] <= 0 or row["observer_ns"] < 0:
            raise ValueError("invalid CSV fields/duration")
        if row["submitted_interval"] not in (0, 1) or row["represented_interval"] not in (0, 1):
            raise ValueError("invalid CSV submission flags")
        if i and (row["frame"] <= rows[i-1]["frame"] or row["now_ns"] <= rows[i-1]["now_ns"] or row["now_ns"] - rows[i-1]["now_ns"] != row["dt_ns"]):
            raise ValueError("nonmonotonic/inconsistent measurement CSV")
    valid = [r for r in rows if r["submitted_interval"] and not r["represented_interval"]]
    clean = [r for r in valid if not(r["shader_before"] & 0xffffffff) and not(r["shader_after"] & 0xffffffff) and r["shader_before"] == r["shader_after"]]
    return rows, dict(csv=str(path), csv_sha256=sha_bytes(data), csv_bytes=len(data),
                      csv_frames=[rows[0]["frame"], rows[-1]["frame"]],
                      all_intervals=interval_stats(rows), submitted_not_represented=interval_stats(valid),
                      without_shader_work_conditional=interval_stats(clean),
                      shader_affected_intervals=len(valid)-len(clean), fps_modes=sorted({r["mode"] for r in rows}))


def counter_summary(selected):
    frames = sum(w["frames"] for w in selected)
    totals = {k: sum(w["counter_delta"][k] for w in selected) for k in COUNTERS}
    calls = totals["calls"]
    ratios = {
        "ordinary_visits_per_call": totals["ordinary_visits"] / calls if calls else None,
        "special_visits_per_call": totals["special_visits"] / calls if calls else None,
        "total_visits_per_call": (totals["ordinary_visits"] + totals["special_visits"]) / calls if calls else None,
        "rscale_build_fraction": totals["rscale_builds"] / calls if calls else None,
        "rscale_skip_fraction": totals["rscale_skips"] / calls if calls else None,
        "updates_per_call": totals["updates"] / calls if calls else None,
        "descriptor_writes_per_call": totals["writes"] / calls if calls else None,
    }
    fields = list(TIMER_PATTERNS) + ["logical", "vk_calls"]
    return dict(covered_frames=frames, counters_total=totals,
                counters_per_frame={k: v/frames for k, v in totals.items()} if frames else {},
                ratios=ratios,
                profiler_per_frame={k: sum(w[k] for w in selected)/frames for k in fields if frames and all(k in w for w in selected)},
                submission_profiles=sorted({w["submission_profile"] for w in selected}),
                windows=selected)


def analyze_phase(phase_path, parsed_logs, boot=None):
    path = Path(phase_path)
    result = dict(phase=str(path), label=path.parent.name, status="invalid")
    try:
        data = path.read_bytes()
        phase = json.loads(data)
        result.update(phase_sha256=sha_bytes(data), session=phase.get("session"), profile=phase.get("profile"),
                      run=phase.get("run"), pid=phase.get("pid"), started=phase.get("at"), completed_at=phase.get("completed_at"))
        if not phase.get("completed"):
            result.update(status="incomplete", reason="phase receipt is not completed")
            return result
        profile, session = phase["profile"], phase["session"]
        transition = phase["transition"]
        if profile not in PROFILES or transition.get("op") != "preparation" or transition.get("result") != "applied":
            raise ValueError("no applied preparation receipt")
        if (transition.get("session") != session or transition.get("requested_profile") != profile or
                transition.get("profile") != profile or transition.get("flags") != PROFILES[profile] or
                transition.get("runtime_result") != PROFILES[profile]+1 or transition.get("seq") != phase["sequence_start"]):
            raise ValueError("preparation receipt identity/profile mismatch")
        measure = phase["measurement"]
        ack = measure["ack"]
        name = ack.get("file", "")
        if (ack.get("op") != "measure" or ack.get("result") != "complete" or ack.get("session") != session or
                ack.get("seq") != phase["sequence_start"]+2 or not re.fullmatch(r"measure_\d+\.csv", name)):
            raise ValueError("no matching complete measurement acknowledgement")
        records = [r for r in measure.get("files", []) if r.get("name") == name]
        if len(records) != 1 or not records[0].get("readback_verified"):
            raise ValueError("missing unique verified CSV file receipt")
        rows, timing = read_intervals(path.parent/name)
        if records[0].get("sha256") != timing["csv_sha256"] or records[0].get("bytes") != timing["csv_bytes"]:
            raise ValueError("measurement CSV no longer matches its receipt")
        lo, hi = timing["csv_frames"]
        if type(transition.get("frame")) is not int or not 0 < transition["frame"] < lo:
            raise ValueError("preparation switch was not before measurement")
        result.update(timing=timing, transition=transition, status="timing_valid_no_profiler_match")
        candidates = []
        for log in parsed_logs:
            for t in log["transitions"]:
                if t["frame"] != transition["frame"] or t["profile"] != profile or t["flags"] != PROFILES[profile]:
                    continue
                if boot is not None and t["boot"] != boot:
                    continue
                known_sessions = log["sessions_by_boot"].get(str(t["boot"]), [])
                if known_sessions and session not in known_sessions:
                    continue
                candidates.append((log, t))
        if len(candidates) != 1:
            result["profiler_reason"] = "ambiguous_transition_match" if candidates else "matching_logged_preparation_transition_missing"
            result["transition_candidates"] = [t for _, t in candidates]
            return result
        log, t = candidates[0]
        all_inside = [w for w in log["windows"] if w["boot"] == t["boot"] and w["start"] >= lo and w["end"] <= hi]
        selected, rejected = [], []
        for w in all_inside:
            reasons = list(w["rejected_reasons"])
            if w.get("profile") != profile or w.get("prep_epoch") != t["prep_epoch"]:
                reasons.append("not_phase_preparation_epoch")
            if reasons:
                rejected.append({"line": w["line"], "start": w["start"], "end": w["end"], "reasons": reasons})
            else:
                selected.append(w)
        result.update(log=log["log"], log_sha256=log["sha256"], boot=t["boot"],
                      logged_transition=t, rejected_profiler_windows=rejected)
        if not selected:
            result["profiler_reason"] = "no_complete_valid_profiler_window_inside_measurement"
            return result
        result.update(status="complete", preparation=counter_summary(selected))
        result["preparation"]["coverage_fraction_of_csv_intervals"] = result["preparation"]["covered_frames"] / len(rows)
        # A phase containing an unexpected later switch is not certified as one
        # profile merely because earlier uncontaminated windows exist.
        switches = [x for x in log["transitions"] if x["boot"] == t["boot"] and lo <= x["frame"] <= hi]
        if switches:
            result.update(status="mixed_profile_measurement", unexpected_transitions=switches)
        elif len({w["submit_epoch"] for w in selected}) > 1 or len(result["preparation"]["submission_profiles"]) > 1:
            result.update(status="mixed_submission_measurement", profiler_reason="multiple_submission_epochs_inside_measurement")
        return result
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result.update(status="invalid", reason=str(exc))
        return result


def analyze_suite(evidence, logs=None, phase_paths=None, session=None, boot=None):
    root = Path(evidence)
    log_paths = [Path(p) for p in logs] if logs is not None else sorted(root.glob("r21-*.klog.log"))
    if boot is not None and len(log_paths) != 1:
        raise ValueError("--boot requires exactly one --log")
    parsed = [parse_log(p) for p in log_paths]
    paths = [Path(p) for p in phase_paths] if phase_paths is not None else sorted(root.glob("session-*/**/phase.json"))
    phases = [analyze_phase(p, parsed, boot=boot) for p in paths]
    if session:
        phases = [p for p in phases if p.get("session") == session]
    summaries = []
    for sid, profile in sorted({(p["session"], p["profile"]) for p in phases if p["status"] == "complete"}):
        selected = [p for p in phases if p["status"] == "complete" and p["session"] == sid and p["profile"] == profile]
        summaries.append(dict(session=sid, profile=profile, labels=[p["label"] for p in selected],
                              samples=[dict(label=p["label"], interval_rate_fps=p["timing"]["all_intervals"]["interval_rate_fps"],
                                            mean_frame_ms=p["timing"]["all_intervals"]["mean_frame_ms"],
                                            frame_ms=p["timing"]["all_intervals"]["frame_ms"],
                                            fps_modes=p["timing"]["fps_modes"],
                                            shader_affected_intervals=p["timing"]["shader_affected_intervals"],
                                            submission_profiles=p["preparation"]["submission_profiles"],
                                            ratios=p["preparation"]["ratios"],
                                            profiler_per_frame=p["preparation"]["profiler_per_frame"])
                                       for p in selected]))
    return dict(schema_version=1, evidence=str(root), measurement="Present submission intervals and separate preparation/profiler evidence",
                phases=phases, profile_samples=summaries,
                logs=[{k: v for k, v in p.items() if k != "windows"} for p in parsed],
                limitations=CAVEATS, recommendation=None)


def self_test():
    def sample(frame, profile, n):
        flags = PROFILES[profile]
        counts = dict(calls=n, vs=n//2, fs=n-n//2, cs=0, ordinary_visits=n*8, special_visits=n*4,
                      rscale_builds=n if flags < 2 else n//2, rscale_skips=0 if flags < 2 else n-n//2,
                      allocs=n, updates=n, writes=n*3)
        return (f"[za-r20b-submit] profile=batch4 logical={frame*2} vk_calls={frame}\n"
                f"[za-r21-prep] profile={profile} flags={flags} "+" ".join(f"{k}={v}" for k,v in counts.items())+"\n"
                f"[vk] t=1.0 frame {frame} 25.0 fps (100 draws, 5 passes, 3 dispatches, compile 0 | gpu 20 cpu exec 24 draw 21 (pre 2 key 2 dyn 1 sets 4 tex 4 (upload 1) vtx 1) submit 1 ms | waits:ring slot 10x 14 ms)\n")
    text = "[za-r20b-submit] startup profile=batch4\n"
    text += "[za-r21-prep] applied frame=1 profile=baseline flags=0 previous=baseline drained_seq=1\n"
    text += sample(50,"baseline",100)+sample(100,"baseline",200)
    text += "[za-r21-prep] applied frame=101 profile=optimized flags=3 previous=baseline drained_seq=3\n"
    text += sample(150,"optimized",100)+sample(200,"optimized",200)
    text += "[za-r21-prep] applied frame=201 profile=baseline flags=0 previous=optimized drained_seq=4\n"
    text += sample(250,"baseline",300)+sample(300,"baseline",400)
    text += sample(350,"baseline",10)+sample(400,"baseline",110) # counter reset
    text += "[za-r20b-submit] applied frame=401 profile=each max_lists=1\n"
    text += sample(450,"baseline",210)
    parsed=parse_log_text(text)
    valid=[w for w in parsed["windows"] if w["valid"]]
    assert [w["end"] for w in valid]==[100,200,300,400]
    assert all(w["counter_delta"]["calls"]==100 for w in valid)
    assert any("preparation_counters_reset_or_regressed" in w["rejected_reasons"] for w in parsed["windows"])
    assert any("window_crosses_submission_transition" in w["rejected_reasons"] for w in parsed["windows"])
    summary=counter_summary(valid[:1]);assert summary["ratios"]["total_visits_per_call"]==12 and summary["profiler_per_frame"]["sets_ms"]==.08
    # Missing reporter lines cannot reuse stale snapshots.
    missing=parse_log_text(sample(10,"baseline",10)+"[vk] t=2.0 frame 20 25.0 fps\n"+sample(30,"baseline",30))
    assert all(not w["valid"] for w in missing["windows"])
    reset=parse_log_text(sample(100,"baseline",200)+sample(5,"baseline",10)+sample(10,"baseline",20))
    assert len(reset["windows"])==1 and reset["windows"][0]["boot"]==1
    timing=interval_stats([dict(dt_ns=40_000_000,observer_ns=1000)]*50)
    assert timing["interval_rate_fps"]==25 and timing["mean_frame_ms"]==40 and timing["frame_ms"]["p99"]==40
    # Full phase receipt/hash/log association, entirely in memory: no test files.
    from unittest.mock import patch
    phase_path=Path("/virtual/session-test/baseline-1/phase.json")
    csv_path=phase_path.parent/"measure_12.csv"
    csv_data=("frame,now_ns,dt_ns,submitted_interval,represented_interval,shader_before,shader_after,mode,observer_ns\n"+
              "".join(f"{frame},{frame*40000000},40000000,1,0,0,0,0,1000\n" for frame in range(51,101))).encode()
    phase=dict(completed=True,session="0000000000000021",profile="baseline",sequence_start=10,
               transition=dict(op="preparation",result="applied",session="0000000000000021",requested_profile="baseline",
                               profile="baseline",flags=0,runtime_result=1,seq=10,frame=1),
               measurement=dict(ack=dict(op="measure",result="complete",session="0000000000000021",seq=12,file="measure_12.csv"),
                                files=[dict(name="measure_12.csv",readback_verified=True,sha256=sha_bytes(csv_data),bytes=len(csv_data))]))
    fixtures={str(phase_path):json.dumps(phase).encode(),str(csv_path):csv_data}
    parsed["sha256"]="synthetic"
    with patch.object(Path,"read_bytes",lambda p:fixtures[str(p)]):
        result=analyze_phase(phase_path,[parsed])
        assert result["status"]=="complete" and result["preparation"]["covered_frames"]==50,result
        assert result["timing"]["all_intervals"]["interval_rate_fps"]==25
        fixtures[str(csv_path)]=csv_data+b"\n"
        assert analyze_phase(phase_path,[parsed])["status"]=="invalid"
        fixtures[str(csv_path)]=csv_data
        phase["transition"]["runtime_result"]=4
        fixtures[str(phase_path)]=json.dumps(phase).encode()
        assert analyze_phase(phase_path,[parsed])["status"]=="invalid"
    print("PASS: profile epochs/return-to-profile, cumulative reset, submission switch, missing counters, boot reset, counter ratios, interval math, full phase receipt/hash/log association and rejection")


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence",type=Path,default=Path(__file__).resolve().parents[2]/"evidence/preparation-r21-hardware")
    parser.add_argument("--log",type=Path,action="append")
    parser.add_argument("--phase",type=Path,action="append")
    parser.add_argument("--session")
    parser.add_argument("--boot",type=int)
    parser.add_argument("--out",type=Path)
    parser.add_argument("--self-test",action="store_true")
    args=parser.parse_args()
    if args.self_test:
        self_test();return
    result=analyze_suite(args.evidence,args.log,args.phase,args.session,args.boot)
    output=json.dumps(result,ensure_ascii=False,indent=2)+"\n"
    if args.out:
        args.out.write_text(output,encoding="utf-8")
    print(output,end="")


if __name__ == "__main__":
    main()
