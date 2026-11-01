"""Normalize upstream interval counters without adding overlapping categories."""
from pathlib import Path
import argparse
import json
import re
import statistics

def summarize(run, start=60, end=100):
    text = (run / 'stderr.log').read_text(errors='replace')
    rows, frames = [], []
    previous = None
    excluded = False
    for line in text.splitlines():
        if '[vk] saved ' in line or '[gpuprof]' in line:
            excluded = True
        header = re.search(r'\[gpuprof\] (\d+) marks, ([\d.]+) ms first to last', line)
        if header:
            frames.append(dict(marks=int(header[1]), elapsed_ms=float(header[2]), rows=[]))
        item = re.search(r'\[gpuprof\]\s+([\d.]+) ms\s+([\d.]+)%\s+(.*)', line)
        if item and frames:
            frames[-1]['rows'].append(dict(ms=float(item[1]), label=item[3]))
        m = re.search(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps max ([\d.]+)ms', line)
        if not m:
            continue
        current = (float(m[1]), int(m[2]))
        core = re.search(r'(\d+) draws, (\d+) skipped, (\d+) passes, (\d+) dispatches, (\d+) flushes, wait ([\d.]+)ms, compile (\d+)', line)
        times = re.search(r'gpu ([\d.]+) cpu exec ([\d.]+) draw ([\d.]+) \(pre ([\d.]+) key ([\d.]+) dyn ([\d.]+) sets ([\d.]+) tex ([\d.]+) \(upload ([\d.]+)\) vtx ([\d.]+)\) submit ([\d.]+) ms', line)
        if previous and core and times and previous[0] >= start and current[0] <= end and not excluded:
            count = current[1] - previous[1]
            counters = dict(zip(['draws','skipped','passes','dispatches','flushes','wait_ms','compiles'], map(float,core.groups())))
            timings = dict(zip(['gpu_submission_ms','exec_ms','draw_ms','pre_ms','key_ms','dyn_ms','sets_ms','tex_ms','upload_ms','vtx_ms','submit_ms'],map(float,times.groups())))
            waits = {label:dict(calls=int(n),ms=float(ms)) for label,n,ms in re.findall(r'(?:waits:|,)([^,|]+?) (\d+)x ([\d.]+) ms',line)}
            rows.append(dict(seconds=current[0],frames=count,fps=float(m[3]),counters=counters,timings=timings,waits=waits))
        previous, excluded = current, False
    if not rows:
        raise RuntimeError('No clean profiling intervals')
    total = sum(r['frames'] for r in rows)
    per_frame = {k:round(sum(r['timings'][k] for r in rows)/total,4) for k in rows[0]['timings']}
    counters = {k:round(sum(r['counters'][k] for r in rows)/total,4) for k in rows[0]['counters']}
    causes = sorted({k for r in rows for k in r['waits']})
    waits = {k:dict(calls_per_frame=round(sum(r['waits'].get(k,{}).get('calls',0) for r in rows)/total,4),
                    ms_per_frame=round(sum(r['waits'].get(k,{}).get('ms',0) for r in rows)/total,4)) for k in causes}
    for f in frames:
        f['top_intervals'] = sorted(f['rows'],key=lambda x:x['ms'],reverse=True)[:8]
    result = dict(run=run.name, interval_count=len(rows), total_frames=total,
        instrumented_mean_fps=round(statistics.mean(r['fps'] for r in rows),3),
        per_frame_ms=per_frame, counters_per_frame=counters, waits=waits,
        selected_gpu_frames=frames, samples=rows,
        limitations=[
            'exec includes nested draw, wait and submit work; draw includes pre/key/dyn/sets/tex/vtx. Do not sum these fields.',
            'CPU fields are elapsed wall time in the render thread, not CPU scheduler time or whole-game CPU cost.',
            'GPU submission timestamps omit gaps between submissions; per-pass timestamps can include host-fed gaps and barriers.',
            'GPU profile intervals and screenshot intervals are excluded from aggregate FPS/counter averages.',
            'Instrumented single stationary scene, rounded interval counters, no whole-game guarantee or 1% low claim.'])
    (run/'render-profile.json').write_text(json.dumps(result,indent=2))
    return result

if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('run',type=Path)
    a=p.parse_args()
    r=summarize(a.run)
    print(json.dumps({k:v for k,v in r.items() if k not in ('samples','selected_gpu_frames')},indent=2))
    for f in r['selected_gpu_frames']:
        print(json.dumps(dict(marks=f['marks'],elapsed_ms=f['elapsed_ms'],top=f['top_intervals'][:4]),indent=2))
