"""Compile NEXT-stress-and-play results and verified, save-free deliverables."""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import shutil
import zipfile
import hardware_stress_play as hw
from package_clock_results import sha,write
from analyze import stats

def report(out):
    state=json.loads((out/'state.json').read_text());assert 'current' not in state
    final=json.loads((out/'final-state.json').read_text())
    assert all(final[k] for k in ('installed_sha256_verified','original_six_configs_verified','ini_unchanged','save_unchanged','startup_30_fps_verified','force60_absent','runtime_tsc_disabled','application_closed'))
    assert len(state['phases'])==10
    groups={}
    for p in state['phases']:
        csv=out/p['csv'];rows=hw.hw.rows_from(csv);mode=1 if p['kind']=='stress' else 0
        assert {r['mode'] for r in rows}=={mode}
        lo,hi=hw.hw.ac.r24.csv_frames(csv);log=out/p['boot']/'boot.klog.log'
        windows,notes=hw.hw.ac.parse(log,lo,hi);assert windows
        for w in windows:
            assert all(f'cg_{c}{x}' in w for c in ('render','guest','other') for x in ('','_ns','_max_ns'))
            assert int(w.get('spans_dropped',0))==0
            if p['kind']=='stress':assert abs(int(w['gpu_busy_ns'])+int(w['idle_ns'])-int(w['gpu_span_ns']))<=3
        p['perf']=hw.hw.ac.summarize(windows,notes)
        write(csv.parent/'r24clock-analysis.json',dict(klog=str(log.relative_to(out)),csv=p['csv'],csv_frames=[lo,hi],**p['perf']))
        for kind in ('before','after'):
            for f in p[kind]['files']:
                capture=out/p['capture_directory']/f['name'];assert sha(capture)==f['sha256']
                f['relative_path']=str(capture.relative_to(out)).replace('\\','/')
        write(csv.parent/'phase.json',p)
        g=groups.setdefault(p['point'],dict(point=p['point'],kind=p['kind'],options=p['options'],rows=[],windows=[],phases=[]))
        g['rows']+=rows;g['windows']+=windows;g['phases'].append(p)
    points=[]
    for g in groups.values():
        rows=g.pop('rows');windows=g.pop('windows');pp=g.pop('phases');assert len(pp)==2
        timing=stats(rows);perf=hw.hw.ac.summarize(windows,pp[0]['perf']['clock_notes'])
        g.update(measurements=2,seconds_per_measurement=20,timing=timing,
            average_two_measurements_fps=sum(p['timing']['all_intervals']['interval_rate_fps'] for p in pp)/2,
            thresholds={f'over_{v:g}_ms':sum(r['dt_ns']>v*1e6 for r in rows) for v in (16.7,20,33)},
            perf=perf,shader_affected_intervals=sum(p['timing']['shader_affected_intervals'] for p in pp),
            min_frame_ms=min(r['dt_ns'] for r in rows)/1e6)
        if g['kind']=='stress':
            g['near_60_fps_in_static_windows']=timing['interval_rate_fps']>=59.5 and timing['frame_ms']['p99']<=17.5
            g['near_60_definition']='Pooled rate >=59.5 FPS and p99 <=17.5 ms; all stalls retained.'
            exe=perf['vk_per_frame']['exec_ms'];gpu=perf['gpu_busy_ms_per_frame']
            if g['near_60_fps_in_static_windows']:lim='60 FPS pacing limit in the sampled static scene'
            elif exe>=13 and gpu<13 and exe>=gpu*1.3:lim='CPU/executor side is indicated; executor consumes most of the 16.67 ms budget while GPU has headroom. Other CPU/submission costs are not isolated.'
            elif exe>=15 and gpu<15:lim='executor is the likely limiting side'
            elif gpu>=15 and exe<15:lim='GPU is the likely limiting side'
            elif exe>=15 and gpu>=15:lim='both CPU executor and GPU approach/exceed the frame budget'
            else:lim='Not isolated by mean exec/GPU counters; inspect intervals and other scheduling costs'
            g['limiting_indicator']=lim
        points.append(g)
    log=(out/'all.klog.log').read_text(encoding='utf-8',errors='replace')
    diagnostics=[l for l in log.splitlines() if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b|\bEINTR\b',l,re.I)]
    stress=[p for p in points if p['kind']=='stress'];play=next(p for p in points if p['kind']=='play')
    notes=['Point FPS and percentiles are pooled over both untouched 20-second static recorder windows. Arithmetic mean of the two FPS measurements is also supplied.',
        'Clock/GPU/CPU counters use complete ~2-second windows wholly inside each CSV frame range, weighted by their frame counts. CPU executor and GPU times overlap and must not be added.',
        'Thresholds are strictly >16.7, >20 and >33 ms as requested; these differ from the older analyzer thresholds of 16.667 and 33.333 ms.',
        'FPS is CPU present-submission interval rate, not independent display scanout or game simulation speed. The forced-60 stress mode can slow simulation below 60.',
        'The original r23 city-b input RSTICK_RIGHT 30 was replayed exactly. Its old mode-0 image and this mode-1 image have different camera framing, so no exact cross-build r23 scene-performance comparison is claimed.',
        'New locations were reached using bounded analog walking/camera inputs only, with no conversation, battle, building entry or save input. Routes and before/after save hashes are retained.',
        'Screenshots contain the internal 1920x1080 scene before FSR1 upscale to the actual 3840x2160 swapchain. Final display-image quality and audio audition were not available.',
        'Four short static city points do not establish worst-case performance across the city, combat, all effects or long play sessions. NPC density and visible effects are documented in scene descriptions.',
        'Play installation intentionally retains the original runtime clock and automatic 30/60 trial policy, without force60 or tsc=1.']
    summary=[f"בוצעו 8 מדידות עומס של 20 שניות בארבע נקודות בעיר ועוד שתי מדידות אימות של 20 שניות לגרסה לשימוש."]
    summary += [f"{p['point']}: {p['timing']['interval_rate_fps']:.3f} FPS, p95 {p['timing']['frame_ms']['p95']:.3f} ms, p99 {p['timing']['frame_ms']['p99']:.3f} ms, max {p['timing']['frame_ms']['max']:.3f} ms." for p in stress]
    summary += [f"גרסה לשימוש הותקנה: r24-clock עם vkprof=0, ticks=tsc, scale=1, בלי force60 ובלי tsc=1. אימות מצב 30: {play['timing']['interval_rate_fps']:.3f} FPS.",
        'ששת קובצי האפשרויות המקוריים ו-larecomp.ini נשמרו, גיבוי r23c אומת, השמירה נשארה זהה והאפליקציה נסגרה.',
        'למעבר ל-60: פותחים L3+R3, בוחרים FPS TRIAL ולוחצים X. מנגנון החזרה האוטומטית ל-30 נשאר פעיל.',
        'שמע וקצב סימולציה עצמאי לא נבדקו; נקודות קצרות אינן הוכחה ל-60 בכל המשחק.']
    result=dict(title='PPSA91762 r24-clock stress and play installation',date='2026-10-29',build_sha256=hw.hw.CLOCK_SHA,
        output='3840x2160',internal='1920x1080',measurements=10,stress_measurements=8,points=points,phases=state['phases'],
        visual_checks=json.loads((out/'visual-checks.json').read_text()),scene_descriptions=json.loads((out/'scene-descriptions.json').read_text()),
        city_b_reference=json.loads((out/'city-b-reference-input.json').read_text()),diagnostic_lines=diagnostics,
        installation_gate=json.loads((out/'installation-gate.json').read_text()),final_state=final,
        audio_audition_performed=False,independent_simulation_speed_verified=False,notes=notes,summary_he=summary)
    target=out/'Results-r24clock-stress-play-20261029.json';short=out/'Summary-r24clock-stress-play-HE.json'
    write(target,result);write(short,dict(תקציר=summary,points=points,final_state=final,notes=notes))
    print(json.dumps(dict(points=[dict(point=p['point'],fps=p['timing']['interval_rate_fps'],frame_ms=p['timing']['frame_ms'],thresholds=p['thresholds'],vk=p['perf']['vk_per_frame'],gpu_ms=p['perf']['gpu_busy_ms_per_frame']) for p in points]),indent=2),flush=True)
    return target,short

def package(out):
    target,short=report(out);state=json.loads((out/'state.json').read_text())
    dest=hw.ROOT/'deliverables'/('r24clock-stress-play-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'));dest.mkdir(exist_ok=False)
    for p in (target,short):shutil.copy2(p,dest/p.name)
    # Deliver the exact final option file as well as its hash, for review/reuse.
    options=dest/'perf-r24-options.txt';options.write_bytes(hw.OPTIONS['play'].encode())
    entries={p.name:p for p in (target,short,options)}
    entries['tools/NEXT-stress-and-play-HE.md']=out/'NEXT-stress-and-play-HE.md'
    for p in out.iterdir():
        if p.is_file() and p.suffix in ('.json','.log','.jsonl'):entries['raw/'+p.name]=p
    entries['raw/save-preservation.json']=out/'save-backup/verification.json'
    for b in state['boots']:
        for p in (out/b['label']).rglob('*'):
            if p.is_file() and p.suffix in ('.json','.csv','.log','.png'):entries['raw/'+str(p.relative_to(out)).replace('\\','/')]=p
    for name in ('hardware_stress_play.py','package_stress_play.py','hardware_clock.py','analyze_r24clock.py'):
        entries['tools/perf-r24clock/'+name]=Path(__file__).with_name(name)
    archive=dest/'r24clock-stress-play-evidence-20261029.zip'
    manifest=[dict(path=k,bytes=p.stat().st_size,sha256=sha(p)) for k,p in sorted(entries.items())]
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for k,p in sorted(entries.items()):z.write(p,k)
        z.writestr('Manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    files=[dest/target.name,dest/short.name,archive,options];sums=dest/'SHA256SUMS.txt'
    sums.write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files),encoding='ascii')
    info=dict(directory=str(dest),archive_crc_verified=True,files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in (*files,sums)])
    write(out/'delivery.json',info);print(json.dumps(info,indent=2),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args();package(a.out.resolve())
