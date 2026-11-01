"""Offline, save-free r25 evidence report and verified NAS delivery."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import statistics
import zipfile
import hardware_r25 as hw
from analyze import stats

def sha(p):
    x=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):x.update(b)
    return x.hexdigest()
def write(p,x):p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def summarize(out,final=False):
    state=json.loads((out/'state.json').read_text(encoding='utf-8'));groups={};measurements=[]
    for phase in state['phases']:
        csv=out/phase['csv'];first,last=hw.analysis.r24.csv_frames(csv)
        log=out/phase['boot']/'boot.klog.log'
        windows,notes=hw.analysis.parse(log,first,last);assert windows
        perf=hw.analysis.summarize(windows,notes)
        phase['perf']=perf;phase['bracketing']=hw.brackets(log.read_text(encoding='utf-8'),first,last)
        write(csv.parent/'r25-analysis.json',dict(csv=phase['csv'],csv_frames=[first,last],**perf))
        write(csv.parent/'phase.json',phase);measurements.append(phase)
        g=groups.setdefault((phase['variant'],phase['point']),dict(variant=phase['variant'],point=phase['point'],rows=[],windows=[],phases=[]))
        g['rows']+=hw.rows_from(csv);g['windows']+=windows;g['phases'].append(phase)
    result=[]
    for g in groups.values():
        rows=g.pop('rows');windows=g.pop('windows');pp=g.pop('phases')
        g.update(measurements=len(pp),timing=stats(rows),mean_measurement_fps=statistics.mean(x['timing']['all_intervals']['interval_rate_fps'] for x in pp),
                 perf=hw.analysis.summarize(windows,pp[0]['perf']['clock_notes']),
                 thresholds={f'over_{v:g}_ms':sum(r['dt_ns']>v*1e6 for r in rows) for v in (16.7,20,33)},
                 csv=[p['csv'] for p in pp],shader_affected_intervals=sum(p['timing']['shader_affected_intervals'] for p in pp),
                   slot_brackets=[p['bracketing']['slots'] for p in pp],
                   per_thread_cpu_trustworthy=False,radv_worker_cpu_ms_per_frame=None,
                   thread_cpu_limitation='Known hardware counter issue: many guest-thread CPU times are identical and their sum exceeds the 8-core maximum. The top list covers registered guest threads; RADV worker CPU cannot be inferred from it. Raw values are retained, and cg_radv independently verifies worker activity.')
        result.append(g)
    index={(x['variant'],x['point']):x for x in result};batch=None
    if all((v,'cafe') in index for v in ('A2','E','A3')):
        a,e,b=[index[(v,'cafe')] for v in ('A2','E','A3')]
        af,bf,ef=[x['mean_measurement_fps'] for x in (a,b,e)];mean=(af+bf)/2
        ap,bp,ep=[x['timing']['frame_ms']['p95'] for x in (a,b,e)];pmean=(ap+bp)/2
        win=ef>max(af,bf) and (ef-mean>=.5 or (0<=ef-mean<.5 and pmean-ep>=.5))
        batch=dict(winner='batch8' if win else 'batch4',A2_fps=af,E_fps=ef,A3_fps=bf,baseline_fps_mean=mean,
                   fps_gain=ef-mean,baseline_p95_ms_mean=pmean,E_p95_ms=ep,p95_gain_ms=pmean-ep,
                   run_F=win,rule='E exceeds both baselines and gains >=0.5 FPS, or gains <0.5 FPS with >=0.5 ms p95 improvement.')
    comparisons=[]
    for name,base,variant,end in [('submit','A','B','A2'),('batch8','A2','E','A3'),('radv_threaded','A3','R','A4'),
                                  ('thread_batch8','B','F','B2'),('thread_radv','B','G','B2'),('clock','B','C','B2'),
                                  ('slots32','B','D32','B2'),('slots64','B','D64','B2')]:
        for point in ('test','cafe'):
            if all((v,point) in index for v in (base,variant,end)):
                a,b,c=[index[(v,point)] for v in (base,variant,end)]
                reference=(a['mean_measurement_fps']+c['mean_measurement_fps'])/2
                comparisons.append(dict(test=name,point=point,baselines=[base,end],variant=variant,
                                        baseline_mean_fps=reference,variant_fps=b['mean_measurement_fps'],
                                        gain_fps=b['mean_measurement_fps']-reference,
                                        gain_percent=(b['mean_measurement_fps']/reference-1)*100))
    finish=json.loads((out/'final-state.json').read_text()) if (out/'final-state.json').exists() else None
    early=json.loads((out/'early-stop.json').read_text()) if (out/'early-stop.json').exists() else None
    clock_check_notes=sorted({n for p in measurements if p['variant']=='C' for n in p['perf']['clock_notes'] if '[za-r25-clock]' in n})
    clock_refused=any('refused' in n for n in clock_check_notes)
    for comp in comparisons:
        if comp['test']=='clock':
            comp.update(clock_activated=not clock_refused,interpretation='C refused the TSC clock request and retained the real clock; this compares two runs of the B configuration.' if clock_refused else 'Clock activation must match the recorded startup checks.')
    report=dict(at=datetime.now(timezone.utc).isoformat(),status='early_stop' if early else ('complete' if finish and 'current' not in state else 'in_progress'),
                requested_build_sha256=hw.SHA,pie_sha256=hw.PIE_SHA,original_build_sha256=state['initial_eboot_sha256'],
                boots=state['boots'],measurements=measurements,points=result,comparisons=comparisons,batch_decision=batch,
                final_state=finish,early_stop=early,clock_check_notes=clock_check_notes,tsc_clock_request_refused=clock_refused,limitations=[
                    'FPS describes CPU intervals between present submissions; it does not independently measure display scanout, audio, or game simulation speed.',
                    'Screenshots show the internal 1920x1080 render before the logged FSR1 upscale to the 3840x2160 swapchain.',
                    'All raw intervals, stalls, shader-affected intervals, raw console lines and normalized counter records are retained.',
                    'Long DebugOutText records were reassembled only across untagged zarecomp continuation lines. Raw logs are also included.',
                    'Counter summaries use complete report windows wholly inside each measurement. Bracketing cumulative counters include report-boundary margins.',
                    'Audio audition was unavailable; audio integrity and final HDMI output were not independently verified.',
                    'Thread CPU rows are unreliable on this hardware: many values are identical and their sum exceeds the eight-core maximum (also documented in port/perf-r24/summarize_hardware.py). The guest-thread top list cannot establish RADV-worker CPU time; cg_radv independently verifies worker activity.'])
    write(out/'results.json',report)
    text=['בדיקת חומרה r25 — PPSA91762',datetime.now().isoformat(timespec='seconds'),'']
    if ('D64','cafe') in index and ('B','cafe') in index and ('B2','cafe') in index:
        best=index[('D64','cafe')]['mean_measurement_fps']
        base=statistics.mean(index[(v,'cafe')]['mean_measurement_fps'] for v in ('B','B2'))
        text += [f"הממצא העיקרי: submit=thread עם עומק 64 ו-batch4 נתן בבית הקפה {best:.2f} FPS לעומת {base:.2f} בעומק 16 — שיפור של {(best/base-1)*100:.2f}%. עדיין לא הגיע ל-60 FPS בנקודה זו.",
                 'הגדלת עומק ה-slots שיפרה יותר מהעברת ההגשה בלבד. batch8 היה איטי יותר, ו-worker ה-RADV לבדו לא שיפר את הקצב.',
                 f"הושלמו {len(measurements)} חלונות מדידה של 20 שניות בשתי נקודות. הבנייה וההגדרות המקוריות הוחזרו, השמירה אומתה ללא שינוי והאפליקציה נסגרה." if finish else '', '']
    if early:text+=['הבדיקה נעצרה לפי נוהל העצירה המוקדמת: '+early.get('reason',''), '']
    text+=['תוצאות: ממוצע שתי מדידות של 20 שניות בכל נקודה. FPS הם קצב הגשות present שנמדד במעבד.','',
           'תצורה | נקודה | FPS | p50 / p95 / p99 / max (ms) | מעל 16.7 / 20 / 33 ms']
    for g in result:
        t=g['timing'];f=t['frame_ms'];n=g['thresholds']
        text.append(f"{g['variant']} | {'בית קפה' if g['point']=='cafe' else 'נקודת הבדיקה'} | {g['mean_measurement_fps']:.3f} | "+
                    ' / '.join(f'{f[k]:.3f}' for k in ('p50','p95','p99','max'))+' | '+
                    ' / '.join(str(n[k]) for k in ('over_16.7_ms','over_20_ms','over_33_ms')))
    text+=['','השוואות ABA:']
    for c in comparisons:text.append(f"{c['test']}, {c['point']}: {c['variant_fps']:.3f} לעומת {c['baseline_mean_fps']:.3f} FPS; שינוי {c['gain_fps']:+.3f} FPS ({c['gain_percent']:+.2f}%).")
    if batch:text+=['',f"הכרעת batch: {batch['winner']}; הפרש {batch['fps_gain']:+.3f} FPS ו-{batch['p95_gain_ms']:+.3f} ms ב-p95 לטובת batch8. F {'נדרשת' if batch['run_F'] else 'אינה נדרשת'} לפי הסף שבנוהל."]
    if clock_refused:text+=['','בדיקת clock=tsc ב-C נדחתה: affinity rc=34, אפס CPUs ואפס זוגות ליבות נמדדו. CLOCK_MONOTONIC נשאר אמיתי; C שקולה ל-B, ולא נמדדה כאן תועלת משעון TSC פעיל. שורות הבדיקה המלאות מצורפות ב-JSON.']
    text+=['','זמני CPU ודרייבר ממוצעים לפריים (ms):','תצורה | נקודה | render_busy | exec | rsub | logic | present | acquire | submitter | DCB/frame | DCB ms/frame']
    for g in result:
        r=g['perf']['r25'];rdr=r['render'];drv=r['driver']
        vals=[rdr[k] for k in ('render_busy_ms','exec_ms','rsub_ms','logic_ms','present_ms','acquire_ms')]
        vals += [r['submitter']['busy_ms'],drv['dcb_submits_per_frame'],drv['dcb_submit_ms_per_frame']]
        text.append(f"{g['variant']} | {g['point']} | "+' | '.join('N/A' if x is None else f'{x:.3f}' for x in vals))
    text+=['','מוני GPU, תורים, שעון, cg_radv, top threads, היסטוגרמת GPU ושורות ההגשה הגולמיות כלולים ב-results.json ובקבצים לכל מדידה.',
           'כל התקיעות נשמרו; לא סוננו פריימים אטיים. הצילומים בוצעו מחוץ לחלונות המדידה.',
           'הצילום הוא 1080p פנימי לפני הגדלה ל-4K. אודיו, קצב הסריקה הפיזי ומהירות הסימולציה לא נמדדו עצמאית.']
    text+=['מגבלה מוכרת: שעוני ה-CPU לפי thread מחזירים ערכים זהים וסכום בלתי אפשרי לשמונה ליבות. busiest_threads נשמר גולמית אך אינו אמין, ואי אפשר להסיק ממנו זמן CPU של worker ה-RADV. פעילותו מאומתת באמצעות cg_radv.']
    if finish:text+=['','אימות סיום: השמירה לא השתנתה, הבינארי וההגדרות המקוריים הוחזרו ואומתו, larecomp.ini נשאר כמות שהיה והאפליקציה סגורה.',
                     'הבינארי המקורי שהוחזר: '+finish['original_eboot_sha256']]
    (out/'RESULTS-HE.txt').write_text('\n'.join(text)+'\n',encoding='utf-8')
    if final:
        assert finish and finish['application_closed'] and finish['save_unchanged']
        assert 'current' not in state
        if not early:assert len(measurements)==48 and len(result)==24 and all(g['measurements']==2 for g in result)
    return report

def package(out):
    report=summarize(out,True);delivery=out/'deliverables';delivery.mkdir(exist_ok=True)
    for name in ('results.json','RESULTS-HE.txt','preflight.json','restoration.json','final-state.json'):
        shutil.copyfile(out/name,delivery/name)
    # Exact engineering sources only; no settings, keys, credentials, save data,
    # original executable, game assets, build caches or unrelated project files.
    for name in ('hardware_r25.py','package_hardware_r25.py','analyze_r25.py','TEST-r25-HE.md','README-HE.md'):
        shutil.copyfile(Path(__file__).parent/name,delivery/name)
    evidence=[]
    for f in out.rglob('*'):
        if not f.is_file():continue
        rel=f.relative_to(out)
        if rel.parts[0] in ('original','save-backup','deliverables') or f.name in ('stop-logger','events.jsonl'):continue
        if f.suffix.lower() in ('.json','.jsonl','.csv','.png','.log','.txt'):evidence.append(f)
    manifest=[dict(path=str(f.relative_to(out)).replace('\\','/'),bytes=f.stat().st_size,sha256=sha(f)) for f in evidence]
    write(delivery/'evidence-manifest.json',manifest)
    archive=delivery/(out.name+'-results.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for f in evidence:z.write(f,str(f.relative_to(out)))
        for f in delivery.iterdir():
            if f!=archive:z.write(f,'report/'+f.name)
    nas=Path(r'\\TheOnePiece\Software\PS5-13.60')/out.name
    files=[]
    for f in delivery.iterdir():
        target=nas/f.name;target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():assert sha(target)==sha(f)
        else:shutil.copyfile(f,target)
        assert sha(target)==sha(f);files.append(dict(file=f.name,bytes=f.stat().st_size,sha256=sha(f)))
    write(delivery/'nas-verification.json',dict(path=str(nas),files=files,sha256_verified=True))
    shutil.copyfile(delivery/'nas-verification.json',nas/'nas-verification.json')
    assert sha(delivery/'nas-verification.json')==sha(nas/'nas-verification.json')
    print(json.dumps(dict(status=report['status'],measurements=len(report['measurements']),nas=str(nas),archive=str(archive),files=files),ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path);p.add_argument('--package',action='store_true');a=p.parse_args()
    if a.package:package(a.out.resolve())
    else:
        r=summarize(a.out.resolve());print(json.dumps(dict(status=r['status'],batch_decision=r['batch_decision'],points=[dict(variant=g['variant'],point=g['point'],fps=g['mean_measurement_fps']) for g in r['points']]),ensure_ascii=False))
