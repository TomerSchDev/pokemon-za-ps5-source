"""Recompute full-window clock counters and package the scoped hardware evidence."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
import hardware_clock as hw
from analyze import stats

def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

def report(out):
    state=json.loads((out/'state.json').read_text());assert 'current' not in state
    final=json.loads((out/'final-state.json').read_text())
    assert all(final[k] for k in ('application_closed','installed_sha256_verified','original_configs_verified','ini_verified','save_unchanged'))
    groups={}
    for p in state['phases']:
        csv=out/p['csv'];rows=hw.rows_from(csv);assert {r['mode'] for r in rows}=={1}
        assert all(r['dt_ns']>0 for r in rows)
        lo,hi=hw.ac.r24.csv_frames(csv);log=out/p['boot']/'boot.klog.log'
        windows,notes=hw.ac.parse(log,lo,hi)
        assert windows and all(all(f'cg_{c}{suffix}' in w for c in ('render','guest','other') for suffix in ('','_ns','_max_ns')) for w in windows)
        for w in windows:
            assert int(w['spans_dropped'])==0
            assert abs(int(w['gpu_busy_ns'])+int(w['idle_ns'])-int(w['gpu_span_ns']))<=3
        p['perf']=hw.ac.summarize(windows,notes)
        write(csv.parent/'r24clock-analysis.json',dict(klog=str(log.relative_to(out)),csv=p['csv'],csv_frames=[lo,hi],**p['perf']))
        assert (p['perf']['vk_per_frame'] is None)==(p['variant'] in ('B','D','E'))
        for kind in ('before','after'):
            for f in p[kind]['files']:
                capture=out/p['boot']/f['name'];assert sha(capture)==f['sha256']
                f['relative_path']=str(capture.relative_to(out)).replace('\\','/')
        write(csv.parent/'phase.json',p)
        g=groups.setdefault(p['boot'],dict(boot=p['boot'],variant=p['variant'],options=p['options'],phases=[],rows=[],windows=[],notes=notes))
        g['phases'].append(p);g['rows']+=rows;g['windows']+=windows
    boots=[]
    for g in groups.values():
        pp=g.pop('phases');rows=g.pop('rows');windows=g.pop('windows');notes=g.pop('notes');assert len(pp)==2
        timing=stats(rows)
        g.update(measurements=2,seconds_per_measurement=20,
            protocol_label='A2 (final control of optional part 2)' if g['variant']=='A3' else g['variant'],
            average_two_measurements=dict(fps=sum(p['timing']['all_intervals']['interval_rate_fps'] for p in pp)/2,
                p50_ms=sum(p['timing']['all_intervals']['frame_ms']['p50'] for p in pp)/2,
                p95_ms=sum(p['timing']['all_intervals']['frame_ms']['p95'] for p in pp)/2),
            pooled_intervals=timing,frame_min_ms=min(r['dt_ns'] for r in rows)/1e6,
            perf=hw.ac.summarize(windows,notes),shader_affected_intervals=sum(p['timing']['shader_affected_intervals'] for p in pp),
            tsc_check_lines=[x for x in notes if '[sdl3-ps5] ticks: TSC at ' in x])
        boots.append(g)
    b={g['variant']:g for g in boots};assert {'A','B','A2'}<=b.keys()
    assert b['A']['options']==b['A2']['options']
    if 'A3' in b:assert b['A']['options']==b['A3']['options']
    fps=lambda v:b[v]['average_two_measurements']['fps']
    base=(fps('A')+fps('A2'))/2
    comparison=dict(ABA_control_mean_fps=base,B_fps=fps('B'),B_fps_gain_percent=(fps('B')/base-1)*100,
        A2_vs_A_percent=(fps('A2')/fps('A')-1)*100)
    ca=b['A']['perf']['clock_gettime']['render'];cb=b['B']['perf']['clock_gettime']['render'];ca2=b['A2']['perf']['clock_gettime']['render']
    comparison['render_clock_calls_reduction_percent']=100*(1-cb['calls_per_frame']/((ca['calls_per_frame']+ca2['calls_per_frame'])/2))
    comparison['render_clock_time_saved_ms_per_frame']=(ca['ms_per_frame']+ca2['ms_per_frame'])/2-cb['ms_per_frame']
    if {'C','D','E','A3'}<=b.keys():
        comparison.update(C_vs_ABA_controls_percent=(fps('C')/base-1)*100,
            D_vs_B_percent=(fps('D')/fps('B')-1)*100,E_vs_D_percent=(fps('E')/fps('D')-1)*100,
            final_A3_vs_initial_A_percent=(fps('A3')/fps('A')-1)*100)
    full=(out/'all.klog.log').read_text(encoding='utf-8',errors='replace')
    errors=[l for l in full.splitlines() if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b|\bEINTR\b',l,re.I)]
    visual=json.loads((out/'visual-checks.json').read_text()) if (out/'visual-checks.json').exists() else []
    notes=['FPS is CPU present-submission interval rate, not a measured display scanout or simulation speed.',
        'Each boot has two untouched 20-second recorder windows. FPS/p50/p95 are the arithmetic means of the two measurements; pooled statistics and every original interval are also included.',
        'Clock and GPU summaries use only complete ~2-second counter windows wholly inside each measurement, weighted by their frames; clock maxima are the largest captured per-call values.',
        'clock_gettime wrapping counts title objects and RADV calls, not calls internal to system modules. Per-call durations are measured with the TSC.',
        'The long stats lines truncate their trailing top-thread list. The host analyzer was repaired to ignore incomplete thread entries; intact clock and GPU counters are retained. The first completed raw CSV was reused after the repair, without rerunning or discarding intervals.',
        'Legacy thread CPU-time counters have shown implausible totals on this console and are not used to infer utilization.',
        'gaps=1 was identical in every test variant. In B/D/E, renderer CPU profiling is off: vk_per_frame is null, GPU busy remains available from the GPU timeline.',
        'force60 is a fixed timing test mode; below 60 FPS game simulation may slow. This does not certify full-speed gameplay.',
        'B/C/D/E may reach the approximately 60 FPS pacing limit. Similar capped FPS does not establish equal CPU headroom or prove additional clock changes have no benefit.',
        'TSC self-checks cover 1,000 calls on one thread. They do not establish cross-core synchronization under all workloads.',
        'No audio audition or independent game-speed measurement was available. Frame timings, logs and still scene captures were checked; this is not full gameplay validation.',
        'Observer screenshots are the 1920x1080 internal scene before upscale, not the final 3840x2160 display output.']
    summary=[f"הושלמו {len(state['phases'])} מדידות של 20 שניות ב-{len(boots)} עליות, באותה שמירה ובאותה מצלמה; פלט 4K, רינדור פנימי 1080p ו-force60.",
        f"מדידת renderer פעילה A: {fps('A'):.3f} FPS; כבויה B: {fps('B'):.3f}; חזרה A2: {fps('A2'):.3f}. השיפור ב-B מול ממוצע A/A2: {comparison['B_fps_gain_percent']:.2f}%.",
        f"קריאות clock_gettime ב-render לכל פריים: A {b['A']['perf']['clock_gettime']['render']['calls_per_frame']:.2f}, B {b['B']['perf']['clock_gettime']['render']['calls_per_frame']:.2f}, A2 {b['A2']['perf']['clock_gettime']['render']['calls_per_frame']:.2f}.",
        f"זמן קריאת clock_gettime ממוצעת ב-render בבקרה הוא כ-{(ca['us_per_call']+ca2['us_per_call'])/2:.3f} מיקרושנייה; זה נמוך מהשערת 20 המיקרושניות, אך מספר הקריאות הגדול גזל כ-13.15 מילישניות לפריים.",
        "הטבלאות המלאות כוללות p50/p95, קריאות וזמן שעון לפי render/guest/other, זמן GPU ושורות בדיקת TSC מקוריות.",
        "r23c וכל ההגדרות המקוריות הוחזרו ואומתו. השמירה נשארה זהה והאפליקציה נסגרה."]
    if {'C','D','E','A3'}<=b.keys():summary.insert(3,f"TSC: C {fps('C'):.3f}, D {fps('D'):.3f}, E {fps('E'):.3f} FPS; בקרה סופית A3 {fps('A3'):.3f}.")
    result=dict(title='PPSA91762 r24-clock hardware test',date='2026-10-29',build_sha256=hw.CLOCK_SHA,
        output='3840x2160',internal='1920x1080',force60=True,gaps_identical_all_variants=True,measurements=len(state['phases']),
        completed_parts=[1]+([2] if {'C','D','E','A3'}<=b.keys() else []),boots=boots,phases=state['phases'],comparisons=comparison,
        diagnostic_lines=errors,early_stop=json.loads((out/'early-stop.json').read_text()) if (out/'early-stop.json').exists() else None,
        visual_checks=visual,audio_audition_performed=False,independent_simulation_speed_verified=False,
        final_state=final,notes=notes,summary_he=summary)
    target=out/'Results-r24clock-20261029.json';write(target,result)
    short=out/'Summary-r24clock-HE.json';write(short,dict(תקציר=summary,comparisons=comparison,boots=boots,notes=notes,final_state=final))
    print(json.dumps(dict(boots=[dict(variant=g['variant'],**g['average_two_measurements'],clock=g['perf']['clock_gettime'],gpu_busy_ms=g['perf']['gpu_busy_ms_per_frame'],tsc_check_lines=g['tsc_check_lines']) for g in boots],comparisons=comparison),indent=2),flush=True)
    return target,short

def package(out):
    target,short=report(out);state=json.loads((out/'state.json').read_text())
    dest=hw.ROOT/'deliverables'/('r24clock-hardware-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'));dest.mkdir(exist_ok=False)
    for p in (target,short):shutil.copy2(p,dest/p.name)
    entries={target.name:target,short.name:short,'tools/TEST-CLOCK-r24clock-HE.md':out/'TEST-CLOCK-r24clock-HE.md'}
    for p in out.iterdir():
        if p.is_file() and p.suffix in ('.json','.log','.jsonl'):entries['raw/'+p.name]=p
    entries['raw/save-preservation.json']=out/'save-backup/verification.json'
    for boot in state['boots']:
        for p in (out/boot['label']).rglob('*'):
            if p.is_file() and p.suffix in ('.json','.csv','.log','.png'):
                entries['raw/'+str(p.relative_to(out)).replace('\\','/')]=p
    for name in ('hardware_clock.py','package_clock_results.py','analyze_r24clock.py','README-HE.md'):
        entries['tools/perf-r24clock/'+name]=Path(__file__).with_name(name)
    entries['tools/perf-r24clock/test/test_analyze.py']=Path(__file__).parent/'test/test_analyze.py'
    for name in ('hardware_run.py','run_60_hardware.py','analyze_r24.py','summarize_hardware.py'):
        entries['tools/perf-r24/'+name]=hw.ROOT/'port/perf-r24'/name
    entries['tools/perf-r24prof/hardware_profile.py']=hw.ROOT/'port/perf-r24prof/hardware_profile.py'
    archive=dest/'r24clock-hardware-evidence-20261029.zip'
    manifest=[dict(path=k,bytes=p.stat().st_size,sha256=sha(p)) for k,p in sorted(entries.items())]
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for k,p in sorted(entries.items()):z.write(p,k)
        z.writestr('Manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    files=[dest/target.name,dest/short.name,archive];sums=dest/'SHA256SUMS.txt'
    sums.write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files),encoding='ascii')
    info=dict(directory=str(dest),archive_crc_verified=True,files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in (*files,sums)])
    write(out/'delivery.json',info);print(json.dumps(info,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();package(a.out.resolve())
