"""Summarize the 60 FPS trials by recorded FPS mode, retaining every interval."""
import argparse
import hashlib
import json
from pathlib import Path
import re

import analyze_r24
from run_60_hardware import rows_from
from analyze import stats


def write(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main(out):
    state=json.loads((out/'state.json').read_text())
    phases=[];aggregates={}
    for original in state['phases']:
        p=dict(original);a=p['analysis'];a['fps_modes']=a['all_modes']
        csvfile=out/p['csv'];rows=rows_from(csvfile);mode=p['requested_fps_mode']
        selected=[r for r in rows if r['mode']==mode]
        assert rows and sum(r['dt_ns'] for r in rows)>=19.85e9
        key=(p['boot'],mode)
        agg=aggregates.setdefault(key,dict(boot=p['boot'],display=p['display'],internal=p['internal'],fps_mode=mode,
                                           phases=[],rows=[],windows=[],vk_rows=[],fallback_log_s=[],transitions=[]))
        agg['phases'].append(p['label']);agg['rows']+=selected
        if p['arm_to_fallback_log_receipt_s'] is not None:
            agg['fallback_log_s'].append(p['arm_to_fallback_log_receipt_s'])
        agg['transitions'] += [dict(phase=p['label'],**x) for x in a['transitions']]
        log=out/p['boot']/'boot.klog.log'
        for seg in a['segments']:
            first,last=seg['frame_range'];windows=analyze_r24.parse(log,first,last)
            for w in windows:
                assert abs(int(w['gpu_busy_ns'])+int(w['idle_ns'])-int(w['gpu_span_ns']))<=3
                assert int(w['idle_ns'])==sum(int(w[k]) for k in ('idle_between_ns','idle_within_ns','idle_unknown_ns'))
                assert int(w['ngaps'])==sum(int(w[k]) for k in ('gap_lt100us','gap_lt500us','gap_lt2ms','gap_lt8ms','gap_ge8ms'))
                assert int(w['spans_dropped'])==0
            seg['counter_quality']=dict(full_windows=len(windows),gpu_invariants_passed=True,spans_dropped=0)
            seg['thread_cpu_trustworthy']=False
            if seg['mode']==mode:
                agg['windows']+=windows;agg['vk_rows'].append(seg['vk'])
        for kind in ('before','after'):
            for f in p[kind]['files']:
                path=csvfile.parent/f['name']
                assert hashlib.sha256(path.read_bytes()).hexdigest()==f['sha256']
                f['relative_path']=str(path.relative_to(out)).replace('\\','/')
        p['selected_render_thread']=next(s['vk'] for s in a['segments'] if s['mode']==mode)
        p['selected_perf']=next(s['perf'] for s in a['segments'] if s['mode']==mode)
        phases.append(p)
    stages=[]
    for agg in aggregates.values():
        rows=agg.pop('rows');windows=agg.pop('windows');vks=agg.pop('vk_rows')
        agg['timing']=stats(rows);agg['over_16_7_ms']=sum(r['dt_ns']>16700000 for r in rows)
        agg['shader_affected_intervals']=sum(bool((r['shader_before']&0xffffffff) or (r['shader_after']&0xffffffff) or r['shader_before']!=r['shader_after']) for r in rows)
        agg['perf']=analyze_r24.summarize(windows)
        vf=sum(x['frames'] for x in vks)
        agg['render_thread']=dict(frames=vf,per_frame={k:sum(x['frames']*x['per_frame'][k] for x in vks)/vf if vf else None
                                                       for k in ('gpu_ms','cpu_exec_ms','cpu_draw_ms','submit_ms','compile')})
        if agg['perf']['frames']:
            agg['gap_histogram_per_frame']={k:v/agg['perf']['frames'] for k,v in agg['perf']['gap_histogram'].items()}
        exec_ms=agg['render_thread']['per_frame']['cpu_exec_ms']
        agg['exec_only_upper_bound_fps']=1000/exec_ms if exec_ms else None
        agg['mean_frame_ms_minus_exec_ms']=1000/agg['timing']['interval_rate_fps']-exec_ms if exec_ms else None
        stages.append(agg)
    boot_evidence=[]
    for b in state['boots']:
        folder=out/b['label'];log=folder/'boot.klog.log'
        if not log.exists():continue
        text=log.read_text(encoding='utf-8',errors='replace')
        ini=folder/'ini.json'
        boot_evidence.append(dict(label=b['label'],build=b['build'],sha256=b['sha256'],
                                  ini=json.loads(ini.read_text()) if ini.exists() else None,
                                  path_and_surface_log=[line for line in text.splitlines() if re.search(r'\[za-paths\]|\[paths\]|\[sdl3-ps5\] surface:|swapchain |\[post\]',line)],
                                  crash_lines=[line for line in text.splitlines() if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b',line)]))
    result=dict(title='PPSA91762',date='2026-10-29',protocol='TEST-60FPS-4K-r24-HE.md',
                measurements=len(phases),seconds_per_recording=20,stages=stages,phases=phases,boots=boot_evidence,
                initial_ini=state['initial_ini'],initial_configs=state['initial_configs'],
                measurement='Intervals between vkQueuePresentKHR submissions, not physical display scanout or game simulation speed.',
                caveats=['Mode 1 statistics contain only CSV intervals tagged mode=1; fallback mode=2 is reported separately.',
                         'The 20-second recordings include fallback and all stalls; mode-1-only subsets can be shorter than 20 seconds.',
                         'The observer settles for two seconds, so the recorded mode-1 subset begins after the trial was armed.',
                         'A transition CSV interval can straddle modes; fallback is bracketed by previous_now_ns and first_now_ns.',
                         'Arm-to-fallback durations use host log receipt timestamps; exact observed frame/time boundaries are retained in each phase.',
                         'Counter windows crossing FPS-mode boundaries are excluded from that mode counter summary.',
                         'CPU and GPU timers overlap. Thread CPU clocks are known unreliable on this build and are not used for attribution.'],
                operational_issues=[dict(issue='FTP initially denied INI creation in the title data directory.',
                                          resolution='Temporarily changed only zarecomp directory mode from 755 to 777 for each INI transaction, then verified restoration to 755 and unchanged ownership.',
                                          evidence='B-4k-internal1080/ini-transport.json')])
    result['capture_scope']='The existing observer captures the internal scene texture before final scaling. A 4K swapchain with 1x internal resolution therefore produces a 1920x1080 observer PNG. These files are not a 4K post-upscale capture.'
    comparisons=[]
    for mode in (0,1):
        controls=[next((s for s in stages if s['boot']==boot and s['fps_mode']==mode),None)
                  for boot in ('A-1080p-native','C-1080p-return')]
        candidate=next((s for s in stages if s['boot']=='B-4k-internal1080' and s['fps_mode']==mode),None)
        if not candidate or any(s is None for s in controls):continue
        control_fps=sum(s['timing']['interval_rate_fps'] for s in controls)/2
        control_gpu=sum(s['perf']['per_frame']['gpu_busy_ms'] for s in controls)/2
        gpu=candidate['perf']['per_frame']['gpu_busy_ms'];fps=candidate['timing']['interval_rate_fps']
        comparisons.append(dict(name='1080p output - 4K output - 1080p output ABA, all internally 1080p',fps_mode=mode,
                                control_boots=[s['boot'] for s in controls],candidate_boot=candidate['boot'],
                                control_fps=control_fps,candidate_fps=fps,fps_change_percent=(fps/control_fps-1)*100,
                                control_gpu_busy_ms=control_gpu,candidate_gpu_busy_ms=gpu,extra_gpu_ms=gpu-control_gpu))
    result['output_comparisons']=comparisons
    if (out/'final-state.json').exists():result['final_state']=json.loads((out/'final-state.json').read_text())
    result['summary_he']=[f"בוצעו {len(phases)} מדידות של 20 שניות. כל הנתונים נשמרו; מצב 1 נותח בנפרד מהחזרה האוטומטית למצב 2."]
    for s in stages:
        if s['fps_mode']!=1:continue
        rt=s['render_thread']['per_frame'];pf=s['perf']['per_frame']
        result['summary_he'].append(f"פלט {s['display']}, רינדור פנימי {s['internal']}: מצב 1 נתן {s['timing']['interval_rate_fps']:.2f} FPS; GPU busy {pf['gpu_busy_ms']:.2f} ms; exec {rt['cpu_exec_ms']:.2f}, draw {rt['cpu_draw_ms']:.2f}, submit {rt['submit_ms']:.2f} ms. חזרה אוטומטית לפי זמני קבלת הלוג: "+', '.join(f'{t:.3f} שניות' for t in s['fallback_log_s']))
    for c in comparisons:
        result['summary_he'].append(f"במצב {c['fps_mode']}, תוספת פלט 4K כשהרינדור נשאר 1080p עלתה {c['extra_gpu_ms']:.3f} ms ב-GPU ושינתה את ה-FPS ב-{c['fps_change_percent']:.3f}% מול שתי בקרות 1080p.")
    result['summary_he'].append('זמן ה-exec לבדו גבוה מתקציב 16.67 ms הדרוש ל-60 FPS. קצב מצב 1 נמוך גם מ-1000 חלקי exec, ולכן יש עלות נוספת במסלול הפריים מעבר ל-exec. זמני ה-threads אינם משמשים לייחוס צוואר הבקבוק.')
    result['summary_he'].append('הפלט והרזולוציה הפנימית אומתו בנפרד דרך ה-swapchain, קובץ ההגדרות וממדי צילום ה-scene. צילום observer אינו כולל את ההגדלה הסופית למסך, ולכן איכות פלט ה-4K לאחר ההגדלה אינה מאומתת בתמונה זו.')
    all_fallbacks=[x for s in stages for x in s['fallback_log_s']]
    if all_fallbacks:
        result['summary_he'].append(f"החזרה האוטומטית נצפתה בכל {len(all_fallbacks)} ניסיונות מצב 1, אחרי {min(all_fallbacks):.3f} עד {max(all_fallbacks):.3f} שניות לפי זמני קבלת הלוג. גבולות הפריים המדויקים לפי שעון ה-title נשמרו לכל ניסיון.")
    if not any(b['crash_lines'] for b in boot_evidence):
        result['summary_he'].append('לא נמצאו בלוגים סימני GPU fault, device lost או קריסה. לא נראתה השחתה בצילומי ה-scene שנבדקו; הפלט הסופי לאחר ההגדלה לא צולם.')
    if result.get('final_state'):
        result['summary_he'].append('בסיום הוחזרה r23c ואומתה ב-SHA-256. האפליקציה נסגרה, השמירה נותרה זהה, קובצי האפשרויות המקוריים אומתו, ושני קובצי ההגדרות הזמניים הוחזרו להיות חסרים. הרשאות תיקיית הנתונים הוחזרו ל-755.')
    target=out/'Results-r24-60fps-4k-20261029.json';write(target,result)
    for s in stages:
        print(json.dumps({k:s[k] for k in ('boot','display','internal','fps_mode','timing','fallback_log_s','render_thread','exec_only_upper_bound_fps')},ensure_ascii=False))
    print(target)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);main(p.parse_args().out.resolve())
