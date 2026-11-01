"""Normalize complete 2s game-profiler windows inside an observer CSV.
Timers may overlap; no combined CPU/GPU duration or display FPS is inferred.
"""
import argparse, csv, hashlib, json, re
from pathlib import Path

def windows(path):
    result=[]; lastframe=None; prev=None; pending=None; boot=-1
    for lineno, line in enumerate(path.read_text(encoding="utf-8",errors="replace").splitlines(),1):
        if re.search(r"\[za-r20b?-submit\] startup", line):
            boot+=1;lastframe=None;prev=None;pending=None
        m=re.search(r"\[za-r20b?-submit\] profile=(\w+) .*?logical=(\d+) vk_calls=(\d+)",line)
        if m: pending=dict(profile=m[1],logical=int(m[2]),vk_calls=int(m[3]))
        f=re.search(r"\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps",line)
        if not f:continue
        frame=int(f[2])
        if lastframe is not None and frame<lastframe:
            boot+=1;lastframe=None;prev=None
        if lastframe is not None and pending and prev:
            row=dict(boot=boot,line=lineno,start=lastframe+1,end=frame,frames=frame-lastframe,profile=pending["profile"],
                     vk_calls=pending["vk_calls"]-prev["vk_calls"],logical=pending["logical"]-prev["logical"])
            patterns={"draws":r"\((\d+) draws","passes":r"(\d+) passes","compiles":r"compile (\d+)",
                      "submit_ms":r"submit (\d+) ms","exec_ms":r"cpu exec (\d+)","gpu_query_sum_ms":r"\| gpu (\d+)",
                      "ring_ms":r"ring slot \d+x (\d+) ms"}
            for name, pattern in patterns.items():
                v=re.search(pattern,line)
                if v:row[name]=int(v[1])
            result.append(row)
        lastframe=frame;prev=pending.copy() if pending else None
    return result

def analyze(log,csv_path,boot=None):
    samples=list(csv.DictReader(csv_path.open()))
    lo=int(samples[0]["frame"]);hi=int(samples[-1]["frame"])
    selected=[w for w in windows(log) if w["start"]>=lo and w["end"]<=hi and (boot is None or w["boot"]==boot)]
    assert selected, "No complete profiler windows"
    assert len({w["boot"] for w in selected})==1, "Specify boot to avoid mixed process sessions"
    frames=sum(w["frames"] for w in selected)
    fields=("vk_calls","logical","draws","passes","compiles","submit_ms","exec_ms","gpu_query_sum_ms","ring_ms")
    per_frame={name:sum(w[name] for w in selected)/frames for name in fields if all(name in w for w in selected)}
    return dict(log=log.name,csv=str(csv_path),csv_sha256=hashlib.sha256(csv_path.read_bytes()).hexdigest(),
                csv_frames=[lo,hi],covered_frames=frames,profiles=sorted({w["profile"] for w in selected}),
                per_frame=per_frame,windows=selected,
                caveat="Complete profiler windows only; CPU timers nest/overlap and GPU query intervals may overlap. These are not additive, unique GPU time, simulation-speed or scanout measurements.")

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--log",type=Path,required=True);p.add_argument("--csv",type=Path,required=True)
    p.add_argument("--boot",type=int);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
    data=analyze(a.log,a.csv,a.boot);a.out.write_text(json.dumps(data,indent=2)+"\n")
    print(json.dumps({k:v for k,v in data.items() if k!="windows"},indent=2))

