"""Analyze render-thread present submission intervals, not GPU scanout FPS."""
import argparse
import csv
import json
import math
from pathlib import Path

def stats(rows):
    if not rows:
        return {'intervals':0}
    ms=sorted(r['dt_ns']/1e6 for r in rows)
    def percentile(p): return ms[min(len(ms)-1, math.ceil(p*len(ms))-1)]
    count=max(1,math.ceil(len(ms)*.01))
    return {'intervals':len(ms), 'duration_s':sum(ms)/1000,
            'interval_rate_fps':1000*len(ms)/sum(ms),
            'frame_ms':{'p50':percentile(.50),'p95':percentile(.95),'p99':percentile(.99),'max':ms[-1]},
            'one_percent_low_fps':1000/(sum(ms[-count:])/count),
            'over_16_667_ms':sum(x>1000/60 for x in ms),
            'over_33_333_ms':sum(x>1000/30 for x in ms),'over_50_ms':sum(x>50 for x in ms),
            'observer_cpu_us_mean':sum(r['observer_ns'] for r in rows)/len(rows)/1000}

def analyze(path):
    with Path(path).open(newline='') as f:
        rows=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(f)]
    for i,r in enumerate(rows):
        assert r['dt_ns']>0 and r['observer_ns']>=0
        if i: assert r['now_ns']>rows[i-1]['now_ns'] and r['frame']>rows[i-1]['frame'] and r['now_ns']-rows[i-1]['now_ns']==r['dt_ns']
    valid=[r for r in rows if r['submitted_interval'] and not r['represented_interval']]
    clean=[r for r in valid if not (r['shader_before']&0xffffffff) and not (r['shader_after']&0xffffffff) and r['shader_before']==r['shader_after']]
    return {'measurement':'CPU intervals between vkQueuePresentKHR submissions; display scanout and simulation speed are not measured',
            'all_intervals':stats(rows),'submitted_not_represented':stats(valid),
            'without_shader_work_conditional':stats(clean),
            'shader_affected_intervals':len(valid)-len(clean),
            'capture_inside_window':False, 'fps_modes':sorted({r['mode'] for r in rows}),
            'limitations':['No screenshot encoding/readback inside this recorder window; other runtime profiling remains enabled.',
                           'Clean-subset rate is conditional, not the overall experience. Do not discard stalls from the all-interval result.',
                           'A completed matching measure acknowledgement is required; a CSV alone does not certify a full run.',
                           'Observer overhead requires an on/off console comparison; the per-call counter is only a CPU estimate.']}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('csv',type=Path);parser.add_argument('--out',type=Path)
    args=parser.parse_args();text=json.dumps(analyze(args.csv),indent=2)+'\n'
    if args.out:args.out.write_text(text)
    print(text)
