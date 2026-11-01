"""Finalize measurement counters and package r24-prof evidence without executable/game/save files."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

import hardware_profile as hw
import analyze_r24
from analyze import stats
from summarize_hardware import vk_windows


def write(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def report(out):
    state=json.loads((out/'state.json').read_text());assert len(state['phases'])==6 and 'current' not in state
    final=json.loads((out/'final-state.json').read_text())
    assert all(final[k] for k in ('application_closed','installed_sha256_verified','original_configs_verified','ini_verified','save_unchanged','sample_files_removed'))
    groups={};phases=[]
    for p in state['phases']:
        path=out/p['csv'];rows=hw.rows_from(path);assert {r['mode'] for r in rows}=={1}
        first,last=min(r['frame'] for r in rows),max(r['frame'] for r in rows)
        log=out/p['boot']/'boot.klog.log';windows=analyze_r24.parse(log,first,last);assert windows
        for w in windows:
            assert abs(int(w['gpu_busy_ns'])+int(w['idle_ns'])-int(w['gpu_span_ns']))<=3
            assert int(w['spans_dropped'])==0
        p['perf']=analyze_r24.summarize(windows);p['vk']=vk_windows(log,first,last)
        for kind in ('before','after'):
            for f in p[kind]['files']:
                capture=out/p['boot']/f['name'];assert sha(capture)==f['sha256'];f['relative_path']=str(capture.relative_to(out)).replace('\\','/')
        write(path.parent/'phase.json',p);phases.append(p)
        g=groups.setdefault(p['boot'],dict(boot=p['boot'],sampling=p['sampling'],rows=[],windows=[],vk=[]))
        g['rows']+=rows;g['windows']+=windows;g['vk'].append(p['vk'])
    boots=[]
    for g in groups.values():
        rows=g.pop('rows');windows=g.pop('windows');vks=g.pop('vk');n=sum(v['frames'] for v in vks)
        g.update(timing=stats(rows),perf=analyze_r24.summarize(windows),
                 vk=dict(frames=n,per_frame={k:sum(v['frames']*v['per_frame'][k] for v in vks)/n for k in vks[0]['per_frame']}),
                 shader_affected_intervals=sum(bool((r['shader_before']&0xffffffff) or (r['shader_after']&0xffffffff) or r['shader_before']!=r['shader_after']) for r in rows))
        boots.append(g)
    aa=next(b for b in boots if b['boot']=='A-control');bb=next(b for b in boots if b['boot']=='B-sampling');a2=next(b for b in boots if b['boot']=='A2-control')
    control=(aa['timing']['interval_rate_fps']+a2['timing']['interval_rate_fps'])/2
    overhead=(bb['timing']['interval_rate_fps']/control-1)*100
    profile=json.loads((out/'Profile-functions-and-threads.json').read_text())
    main=next(t for t in profile['threads'] if t['role']=='main guest thread');render=next(t for t in profile['threads'] if t['role']=='render thread')
    log=(out/'all.klog.log').read_text(encoding='utf-8',errors='replace')
    diagnostics=[l for l in log.splitlines() if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b|\bEINTR\b',l,re.I)]
    result=dict(title='PPSA91762 r24-prof CPU sampling',date='2026-10-29',measurements=6,seconds_per_measurement=20,
                build_sha256=hw.PROF_SHA,pie_sha256='c8491adbe9fa5dd310aad4e586b7ebe3c87048af50b536fc5704a60d6159b36d',pie_uploaded_to_console=False,
                output='3840x2160',internal='1920x1080',upscaler='FSR1',fps_modes=[1],force60=True,
                boots=boots,phases=phases,sampling_cost=dict(control_fps=control,sampling_fps=bb['timing']['interval_rate_fps'],fps_change_percent=overhead),
                profile=profile,final_state=final,diagnostic_lines=diagnostics,audio_audition_performed=False,
                notes=['Sampling files have window timestamps only. The function reports use whole overlapping files, including stable scene guard periods, not exact per-record time filtering.',
                       'The aggregate profile contains five 20-second stable-scene windows (100 seconds) around three 20-second recordings.',
                       'External samples include libc work, system calls and waiting. Their exact system functions were not resolved; ext% is not a measured wait percentage.',
                       'The render thread is sampled more often than each worker. Raw aggregate percentages are not an unbiased total CPU-time distribution.',
                       'DWARF source attribution was missing or misleading for some runtime functions. Unique build-object ownership supplies source grouping where possible.',
                       'All original intervals and all 25 verified binary sample files are retained. No audio audition was available.'],
                operational_issues=['A stale observer session token during B startup was rebound to the stable new session before game input.',
                                    'The FTP server reports a successful delete as 226 instead of the usual 250; cleanup verified each file absent and restored directory mode 755.'])
    result['summary_he']=[f"שש מדידות של 20 שניות בפלט 4K עם 1080p פנימי ו-force60. בקרה A: {aa['timing']['interval_rate_fps']:.3f} FPS; דגימה B: {bb['timing']['interval_rate_fps']:.3f}; בקרה A2: {a2['timing']['interval_rate_fps']:.3f}.",
                          f"עלות הדגימה מול ממוצע A ו-A2: {overhead:.3f}% ב-FPS.",
                          f"נותחו {profile['total_samples']:,} דגימות בחמישה חלונות של סצנה יציבה. kill_err, drop ו-skip היו אפס, וטווח הטקסט זוהה.",
                          f"render thread {render['name']}: {render['ext_percent_hardware']:.2f}% חיצוניים; thread המשחק הראשי {main['name']}: {main['ext_percent_hardware']:.2f}% חיצוניים. אלה אינם אחוזי המתנה מוכחים.",
                          "בקוד ה-render שפוענח בולטים vk_tex ב-textures.c, ולאחריו exec_list ו-draw_ ב-exec.c. חלק גדול מהדגימות החיצוניות מציג קורא סביר draw_ או draw, אך לא פוענח לפונקציית מערכת מדויקת.",
                          "ה-giant הבולט ביותר הוא f_7001810220, יחידה main/main_591 המסומנת במדיניות כ-O0. רשימת 20 ה-giants המובילים ו-20 פונקציות self לכל thread מצורפות.",
                          "לא נמצאו בלוג סימני קריסה, GPU fault או EINTR. צילום ה-scene שנבדק היה תקין; שמע לא נבדק בהאזנה.",
                          "כל 25 קובצי הדגימה הועתקו, אומתו ב-SHA-256 ונמחקו מהקונסולה. r23c וההגדרות המקוריות הוחזרו, השמירה נשארה זהה והאפליקציה נסגרה."]
    raw={g['group']:g['samples'] for g in profile['raw_sample_groups']}
    components={name:sum(v for k,v in raw.items() if k.startswith('runtime/') and k.endswith('/'+name)) for name in ('exec.c','objects.c','textures.c','kernel.c','dispatch.c')}
    components.update(game=raw.get('game (translated code)',0),radv=raw.get('radv',0),
                      other_runtime=sum(v for k,v in raw.items() if k.startswith('runtime/'))-sum(components.values()),
                      libc_kernel_system_modules_unresolved=raw.get('ext (system modules: libkernel waits/syscalls, libc)',0),
                      waits_separately_identified=None)
    result['component_breakdown_raw_samples']=components
    target=out/'Results-r24prof-profile-20261029.json';write(target,result)
    summary=out/'Summary-r24prof-profile-HE.json';write(summary,dict(תקציר=result['summary_he'],measurements=boots,render=render,main_thread=main,giants=profile['top20_giant_functions'],limitations=result['notes']))
    print(json.dumps(dict(boots=[dict(boot=b['boot'],fps=b['timing']['interval_rate_fps'],gpu_busy_ms=b['perf']['per_frame']['gpu_busy_ms']) for b in boots],sampling_cost=result['sampling_cost']),indent=2),flush=True)
    return result,target,summary


def package(out,protocol):
    result,target,summary=report(out)
    dest=hw.ROOT/'deliverables'/('r24prof-profile-hardware-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'));dest.mkdir(exist_ok=False)
    for p in (target,summary):shutil.copy2(p,dest/p.name)
    entries={target.name:target,summary.name:summary,'tools/TEST-PROFILE-r24prof-HE.md':protocol}
    state=json.loads((out/'state.json').read_text())
    for p in out.iterdir():
        if p.is_file() and p.suffix in ('.json','.log','.jsonl'):entries['raw/'+p.name]=p
    entries['raw/save-preservation.json']=out/'save-backup/verification.json'
    for b in state['boots']:
        folder=out/b['label']
        for p in folder.rglob('*'):
            if p.is_file() and p.suffix in ('.json','.csv','.log','.png'):
                entries['raw/'+str(p.relative_to(out)).replace('\\','/')]=p
    for p in (out/'samples').iterdir():
        if p.is_file():entries['raw/samples/'+p.name]=p
    for name in ('hardware_profile.py','analyze_hardware_samples.py','run_reference_symbolizer.py','symbolize_samples.py','package_profile_results.py','README-HE.md'):
        entries['tools/'+name]=Path(__file__).with_name(name)
    manifest=[dict(path=k,bytes=p.stat().st_size,sha256=sha(p)) for k,p in sorted(entries.items())]
    archive=dest/'r24prof-profile-evidence-20261029.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for key,p in sorted(entries.items()):z.write(p,key)
        z.writestr('Manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    files=[dest/target.name,dest/summary.name,archive]
    sums=dest/'SHA256SUMS.txt';sums.write_text(''.join(sha(p)+'  '+p.name+'\n' for p in files),encoding='ascii')
    info=dict(directory=str(dest),archive_crc_verified=True,files=[dict(name=p.name,bytes=p.stat().st_size,sha256=sha(p)) for p in (*files,sums)])
    write(out/'delivery.json',info);print(json.dumps(info,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('protocol',type=Path)
    a=p.parse_args();package(a.out.resolve(),a.protocol.resolve())
