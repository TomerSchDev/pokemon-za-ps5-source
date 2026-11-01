"""Scoped r25 hardware runner. Only PPSA91762; raw evidence and exact restoration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'port/perf-r24'))
import hardware_run as h
from run_60_hardware import logger, rows_from
import analyze_r25 as analysis

SHA = '804205b794fa1b513b662a23e957fbaee14204c8a626afae32a5e3a6c8aab2d6'
PIE_SHA = '0f440a5b8f8d9a90e662bf74eede4c9da4a527927f6c2e42390789654372f59a'
INI = h.SANDBOX + '/download0/zarecomp/larecomp.ini'
BASE = 'scale=1\nforce60=1\nticks=tsc\nvkprof=0\ngaps=1\n'
VARIANTS = {'A':'', 'B':'submit=thread\n', 'A2':'', 'E':'', 'A3':'',
            'R':'radv_threaded=1\n', 'A4':'', 'F':'submit=thread\n',
            'G':'submit=thread\nradv_threaded=1\n',
            'C':'submit=thread\nclock=tsc\n', 'B2':'submit=thread\n',
            'D32':'submit=thread\n', 'D64':'submit=thread\n'}

def load(): return json.loads((h.OUT/'state.json').read_text(encoding='utf-8'))
def save(s): h.write(h.OUT/'state.json', s)
def emit(x): print(json.dumps(x, ensure_ascii=False), flush=True)
def digest(b): return hashlib.sha256(b).hexdigest()
def rawbootlog(s): return (h.OUT/'all.klog.log').read_bytes()[s['current']['klog_offset']:].decode('utf-8','replace')
def normalize_log(raw):
    # DebugOutText splits long records across 1023-byte console writes. Join
    # only the untagged continuation of a tagged performance record, retaining
    # every original byte in boot.raw.klog.log and all.klog.log.
    lines=[];pending=False
    for line in raw.splitlines():
        if pending and line.startswith('[zarecomp] ') and not line[len('[zarecomp] '):].startswith('['):
            lines[-1]+=line[len('[zarecomp] '):]
            continue
        pending='[za-r24-perf]' in line or '[za-r20b-submit] profile=' in line
        lines.append(line)
    return '\n'.join(lines)+'\n'
def bootlog(s): return normalize_log(rawbootlog(s))
def save_bootlogs(s):
    out=h.OUT/s['current']['label']
    (out/'boot.raw.klog.log').write_text(rawbootlog(s),encoding='utf-8')
    (out/'boot.klog.log').write_text(bootlog(s),encoding='utf-8')

def guard(s):
    if (h.OUT/'early-stop.json').exists():raise RuntimeError('EARLY STOP: recorded stop condition')
    log = bootlog(s)
    errors = [l for l in log.splitlines() if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b',l,re.I)]
    if errors:
        h.write(h.OUT/'early-stop.json',dict(at=h.r.utc_now(),boot=s['current']['label'],reason='Hardware fault',lines=errors))
        raise RuntimeError('EARLY STOP: hardware fault')

def pause(s, seconds, heartbeat=False):
    until=time.monotonic()+seconds; previous=None; changed=time.monotonic()
    while time.monotonic()<until:
        guard(s)
        if heartbeat:
            frames=re.findall(r'\[za-r24-perf\].*?\bframe=(\d+)',bootlog(s))
            frame=frames[-1] if frames else None
            if frame!=previous: previous=frame; changed=time.monotonic()
            if time.monotonic()-changed>12:
                h.write(h.OUT/'early-stop.json',dict(at=h.r.utc_now(),boot=s['current']['label'],reason='No advancing frame for 12 seconds',frame=frame))
                raise RuntimeError('EARLY STOP: renderer stopped')
        time.sleep(min(.3,max(0,until-time.monotonic())))

def copy_nas(source):
    dest=NAS/source.relative_to(h.OUT);dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists(): assert digest(dest.read_bytes())==digest(source.read_bytes()),str(dest)
    else: shutil.copyfile(source,dest)
    assert digest(source.read_bytes())==digest(dest.read_bytes())

def initial(c):
    h.idle(); h.title(c)
    assert not (h.OUT/'state.json').exists()
    eboot=c.read(h.APP+'/eboot.bin',512<<20);assert eboot
    configs={n:c.read(h.APP+'/'+n,4096) for n in (*h.CONFIGS,'perf-r24-options.txt')}
    assert configs['performance-options.txt']==b'optimized\n'
    assert configs['submission-options.txt']==b'batch4\n'
    assert configs['slot-depth-options.txt']==b'16\n'
    src=ROOT/'artifacts/randomizer-r25-perf'
    assert digest((src/'PPSA91762/eboot.bin').read_bytes())==SHA
    assert digest((src/'llvm-pie-r25.elf').read_bytes())==PIE_SHA
    backup=h.OUT/'original';backup.mkdir()
    (backup/'eboot.bin').write_bytes(eboot)
    records={}
    for n,b in configs.items():
        records[n]=None if b is None else {'sha256':digest(b),'bytes':len(b)}
        if b is not None:(backup/n).write_bytes(b)
    assert c.sha256(h.APP+'/eboot.bin')==digest(eboot)
    s=dict(at=h.r.utc_now(),initial_eboot_sha256=digest(eboot),initial_configs={n:None if b is None else b.decode() for n,b in configs.items()},
           original_files=records,boots=[],phases=[],nas=str(NAS))
    save(s)
    for f in backup.iterdir():copy_nas(f)
    h.write(h.OUT/'preflight.json',dict(at=s['at'],original_sha256=s['initial_eboot_sha256'],r25_sha256=SHA,pie_sha256=PIE_SHA,original_files=records,nas_backup_verified=True))
    emit(dict(stage='preflight complete',original_sha256=s['initial_eboot_sha256'],nas_backup_verified=True))
    return s

def launch(c,s,label,variant=None):
    h.idle();h.title(c)
    out=h.OUT/label;out.mkdir(exist_ok=False)
    if variant:
        options=BASE+VARIANTS[variant]
        for n in h.CONFIGS:
            actual=c.read(h.APP+'/'+n,4096)
            expected=s['initial_configs'][n].encode()
            if n=='submission-options.txt':expected=b'batch8\n' if variant in ('E','F') else b'batch4\n'
            if n=='slot-depth-options.txt':expected=({'D32':b'32\n','D64':b'64\n'}.get(variant,b'16\n'))
            if actual!=expected:
                assert n in ('submission-options.txt','slot-depth-options.txt'),n
                h.put(c,n,expected)
        h.put(c,'perf-r24-options.txt',options.encode())
        wanted=SHA;binary=(ROOT/'artifacts/randomizer-r25-perf/PPSA91762/eboot.bin').read_bytes()
    else:
        wanted=s['initial_eboot_sha256'];binary=(h.OUT/'original/eboot.bin').read_bytes();options=s['initial_configs']['perf-r24-options.txt']
    assert digest(binary)==wanted
    old=c.sha256(h.APP+'/eboot.bin');assert old in (s['initial_eboot_sha256'],SHA)
    if old!=wanted:
        target=h.APP+'/eboot.bin';stage=target+'.r25-stage-'+h.r.stamp()
        c.store(stage,binary);c.chmod(stage,'755');assert c.sha256(stage)==wanted
        h.idle();h.title(c);assert c.sha256(target)==old
        previous=target+'.before-r25-'+h.r.stamp();c.ftp.rename(target,previous)
        try:c.ftp.rename(stage,target)
        except Exception:c.ftp.rename(previous,target);raise
        assert c.sha256(target)==wanted
        h.write(out/'deploy.json',dict(old_sha256=old,new_sha256=wanted,remote_backup=previous,verified=True))
    try:prior=h.client.status(c.ftp)['session']
    except h.ftplib.error_perm:prior=None
    offset=(h.OUT/'all.klog.log').stat().st_size
    response=h.r.http_text(h.r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf')
    emit(dict(stage='launched',boot=label,response=response))
    deadline=time.monotonic()+85;last=None;stable=0
    while time.monotonic()<deadline:
        try:
            status=h.client.status(c.ftp);ps=h.r.eboot_processes();active=c.read(h.DATA+'/active.json',4096)
            log=(h.OUT/'all.klog.log').read_bytes()[offset:]
            if len(ps)==1 and active and status['session']!=prior and b'main reached' in log:
                sid=status['session'];stable=stable+1 if sid==last else 0;last=sid
                if stable>=2:break
        except h.ftplib.error_perm:pass
        time.sleep(.5)
    else:raise RuntimeError('Launch did not reach stable observer')
    run=json.loads(active)['id']
    if not (h.OUT/'save-backup/verification.json').exists():
        h.backup(c,run,h.OUT/'save-backup')
        ini=c.read(INI,65536);s['initial_ini']=None if ini is None else ini.decode()
        if ini is not None:(h.OUT/'original/larecomp.ini').write_bytes(ini)
        for f in (h.OUT/'save-backup').rglob('*'):
            if f.is_file():copy_nas(f)
    cur=dict(label=label,variant=variant,pid=h.r.process_pid(ps[0]),session=sid,run=run,
             sha256=wanted,seq=0,klog_offset=offset,options=options,at=h.r.utc_now(),backup_verified=True)
    s['current']=cur;s['boots'].append(cur.copy());save(s);h.write(out/'identity.json',cur)
    h.verify_save(c,s);guard(s);emit(dict(stage='observer ready',**cur))

def snapshot(c,s,label):
    out=h.OUT/s['current']['label']/label;out.mkdir(parents=True,exist_ok=False)
    checks=h.verify_save(c,s);rec=h.command(c,s,out,'snapshot',expected={'saved'});h.retire(c,s,rec,out)
    h.write(out/'snapshot.json',dict(receipt=rec,save_check=checks))
    emit(dict(stage='snapshot',folder=str(out),files=[f['name'] for f in rec['files']]))
    return rec

def ready(c,s):
    cur=h.owned(c,s);out=h.OUT/cur['label'];h.verify_save(c,s)
    h.command(c,s,out,'continue',cur['run'],expected={'continue_requested'})
    emit(dict(stage='waiting for title screen',boot=cur['label']));pause(s,12)
    h.command(c,s,out,'input','A',1,expected={'input_armed'})
    emit(dict(stage='loading unchanged save and warming shaders',boot=cur['label']));pause(s,35)
    cur['loaded']=True;save(s);snapshot(c,s,'ready')
    verify_startup(s)

def verify_startup(s):
    cur=s['current'];out=h.OUT/cur['label'];log=bootlog(s);variant=cur['variant']
    if variant:
        assert '[za-r25] submission: '+('thread' if variant in ('B','F','G','C','B2','D32','D64') else 'inline') in log
        assert '[za-r25] radv_threaded='+('1' if variant in ('R','G') else '0') in log
        assert '[za-r20b-submit] startup profile='+('batch8' if variant in ('E','F') else 'batch4') in log
        assert 'renderer CPU profile (LARECOMP_VK_PROF): off' in log
        assert '[za-r24-options] force60=1' in log
        assert 'swapchain 3840x2160' in log and '[post] 1920x1080 fsr1 -> 3840x2160' in log
        assert '[sdl3-ps5] ticks: TSC at ' in log and 'TSC backwards 0 of 1000' in log
        assert '[ps5] clock: plat_now_ns from clock_gettime' in log
        if variant=='C':assert '[za-r25-clock]' in log and re.search(r'\[za-r25-clock\].*(accepted|refused)',log)
        notes=[l for l in log.splitlines() if analysis.NOTE.search(l)]
        h.write(out/'startup-verification.json',dict(variant=variant,notes=notes,verified=True))
    guard(s)

def nav(c,s,action,frames,label):
    assert action in ('STICK_UP','STICK_DOWN','STICK_LEFT','STICK_RIGHT','RSTICK_UP','RSTICK_DOWN','RSTICK_LEFT','RSTICK_RIGHT','RELEASE')
    out=h.OUT/s['current']['label']/'navigation'/label;out.mkdir(parents=True,exist_ok=False)
    before=h.verify_save(c,s)
    rec=h.command(c,s,out,'input',action,frames,expected={'input_armed'})
    pause(s,frames/20+2,True)
    release=h.command(c,s,out,'input','RELEASE',1,expected={'input_armed'});pause(s,1.5,True)
    h.write(out/'navigation.json',dict(at=h.r.utc_now(),action=action,frames=frames,input=rec,release=release,save_before=before,save_after=h.verify_save(c,s)))
    snapshot(c,s,'nav-'+label)

def route(c,s):
    # Exact recorded route to city-c (the 46.97-FPS cafe point). The exploratory
    # city-b right/left camera pair is kept, so camera clamping matches that run.
    moves=[('RSTICK_RIGHT',30),('RSTICK_LEFT',30),('STICK_DOWN',60),
           ('RSTICK_DOWN',20),('STICK_DOWN',120),('RSTICK_UP',60),
           ('STICK_DOWN',120),('RSTICK_RIGHT',60),('RSTICK_DOWN',20),('RSTICK_UP',25)]
    for i,(action,frames) in enumerate(moves,1):
        nav(c,s,action,frames,f'route-{i:02}')

def brackets(log,first,last):
    profiles=[];slots=[];p=None;q=None
    for line in log.splitlines():
        if '[za-r20b-submit] profile=' in line:p=line
        if '[za-r23-slots]' in line:q=line
        m=re.search(r'\[za-r24-perf\] frame=(\d+)',line)
        if m:
            frame=int(m[1])
            if p:profiles.append(dict(frame=frame,line=p,values=dict(re.findall(r'(\w+)=(\S+)',p))));p=None
            if q:slots.append(dict(frame=frame,frames=int(re.search(r'\bframes=(\d+)',line)[1]),line=q,values=dict(re.findall(r'(\w+)=(\S+)',q))));q=None
    def pair(items,keys):
        before=[x for x in items if x['frame']<first];after=[x for x in items if x['frame']>=last]
        if not before or not after:return dict(available=False)
        a,b=before[-1],after[0]
        return dict(available=True,before=a,after=b,delta={k:int(b['values'][k])-int(a['values'][k]) for k in keys if k in a['values'] and k in b['values']},
                    scope='Counter reports immediately bracketing the measurement; includes report-boundary margins.')
    selected=[q for q in slots if q['frame']-q['frames']+1>=first and q['frame']<=last]
    nframes=sum(q['frames'] for q in selected)
    # Slot counters reset each report; they must be summed, never differenced.
    totals={k:sum(int(q['values'].get(k,0)) for q in selected) for k in ('samples','incomplete_on_entry','wait_ns','incomplete_ns','ready_ns')}
    slot_result=dict(available=bool(selected),windows=selected,frames=nframes,totals=totals,
                     active_depths=sorted({int(q['values']['active']) for q in selected}),
                     incomplete_wait_ms_per_frame=totals['incomplete_ns']/nframes/1e6 if nframes else None,
                     scope='Per-report slot counters summed over complete windows inside the recorder range; counters reset each report.')
    return dict(submission=pair(profiles,('logical','vk_calls','lists','end','present','cbs','merged')),slots=slot_result)

def point(c,s,point):
    cur=h.owned(c,s);assert cur['loaded'];assert point in ('test','cafe')
    folder=h.OUT/cur['label']/'points'/point;folder.mkdir(parents=True,exist_ok=False)
    emit(dict(stage='warming static point',boot=cur['label'],point=point,seconds=15));pause(s,15,True)
    before=snapshot(c,s,'point-'+point+'-before');phases=[]
    for i in range(1,3):
        out=folder/f'measure-{i}';out.mkdir();seq=cur['seq']+1;cur['seq']=seq;save(s)
        h.client.issue(c.ftp,cur['session'],seq,'measure',20)
        emit(dict(stage='measuring',boot=cur['label'],point=point,measurement=i,seq=seq))
        pause(s,23,True)  # Only local klog is read; no FTP, screenshots or input.
        rec=h.collect(c,cur['session'],seq,out,{'complete'});h.owned(c,s);pause(s,2.7,True)
        csv=out/rec['files'][0]['name'];rows=rows_from(csv)
        timing=json.loads((out/(csv.stem+'-analysis.json')).read_text())
        assert timing['fps_modes']==[1] and timing['all_intervals']['duration_s']>=19.85
        assert not timing['capture_inside_window']
        save_bootlogs(s);log=h.OUT/cur['label']/'boot.klog.log'
        first,last=analysis.r24.csv_frames(csv);windows,notes=analysis.parse(log,first,last);assert windows
        perf=analysis.summarize(windows,notes);assert perf['r25']['windows_with_r25_keys']>0
        profiles=[]
        for line in log.read_text(encoding='utf-8').splitlines():
            if re.search(r'\[za-r20b-submit\] profile=',line):profiles.append(line)
        # Full log and report frame counters retained for exact bracketing offline.
        phase=dict(boot=cur['label'],variant=cur['variant'],point=point,measurement=i,options=cur['options'],
                   csv=str(csv.relative_to(h.OUT)),receipt=rec,timing=timing,perf=perf,
                   thresholds={f'over_{v:g}_ms':sum(r['dt_ns']>v*1e6 for r in rows) for v in (16.7,20,33)},
                   save_check=h.verify_save(c,s),submission_profile_lines=profiles,bracketing=brackets(log.read_text(encoding='utf-8'),first,last),
                   caveat='Audio and simulation speed are not measured by the observer.')
        h.write(out/'phase.json',phase);s['phases'].append(phase);save(s);phases.append(phase)
        emit(dict(stage='measurement complete',boot=cur['label'],point=point,measurement=i,
                  fps=timing['all_intervals']['interval_rate_fps'],p95_ms=timing['all_intervals']['frame_ms']['p95'],
                  render_busy_ms=perf['r25']['render']['render_busy_ms'],dcb_per_frame=perf['r25']['driver']['dcb_submits_per_frame'],
                  cg_radv=perf['r25']['clock']['radv_worker_calls_per_frame'],thresholds=phase['thresholds']))
    after=snapshot(c,s,'point-'+point+'-after')
    for p in phases:
        p.update(before=before,after=after);h.write((h.OUT/p['csv']).parent/'phase.json',p)
    save_bootlogs(s);save(s)

def close(c,s):
    cur=h.owned(c,s);checks=h.verify_save(c,s)
    ini=c.read(INI,65536);assert ini==(None if s['initial_ini'] is None else s['initial_ini'].encode())
    response=h.r.http_json('/process_kill?pid='+str(cur['pid']))
    deadline=time.monotonic()+15
    while h.r.eboot_processes():
        assert time.monotonic()<deadline;time.sleep(.5)
    out=h.OUT/cur['label'];save_bootlogs(s)
    h.write(out/'close.json',dict(at=h.r.utc_now(),pid=cur['pid'],response=response,save_check=checks,ini_unchanged=True))
    del s['current'];save(s);emit(dict(stage='closed',boot=cur['label'],save_unchanged=True))

def restore(c,s):
    h.idle();h.title(c)
    for n,txt in s['initial_configs'].items():
        wanted=None if txt is None else txt.encode();actual=c.read(h.APP+'/'+n,4096)
        if actual==wanted:continue
        if wanted is None:c.ftp.rename(h.APP+'/'+n,h.APP+'/'+n+'.test-r25-'+h.r.stamp())
        else:h.put(c,n,wanted)
        assert c.read(h.APP+'/'+n,4096)==wanted
    wanted=s['initial_eboot_sha256'];target=h.APP+'/eboot.bin';old=c.sha256(target)
    if old!=wanted:
        assert old==SHA
        binary=(h.OUT/'original/eboot.bin').read_bytes();assert digest(binary)==wanted
        stage=target+'.restore-r25-'+h.r.stamp();c.store(stage,binary);c.chmod(stage,'755');assert c.sha256(stage)==wanted
        h.idle();c.ftp.rename(target,target+'.tested-r25-'+h.r.stamp());c.ftp.rename(stage,target)
    assert c.sha256(target)==wanted
    s['restored_at']=h.r.utc_now();save(s)
    h.write(h.OUT/'restoration.json',dict(at=s['restored_at'],binary_sha256=wanted,configs=s['initial_configs'],byte_exact=True,application_closed=True))
    emit(dict(stage='original binary and configs restored',sha256=wanted))

def review_wait(s,point):
    path=h.OUT/s['current']['label']/('review-'+point+'.json')
    emit(dict(stage='awaiting visual inspection',boot=s['current']['label'],point=point,review=str(path)))
    while not path.exists():guard(s);time.sleep(.5)
    review=json.loads(path.read_text(encoding='utf-8'));assert review['no_obvious_corruption'] and review['menu_closed']

def sequence():
    import package_hardware_r25 as pkg
    s=load();assert 'current' not in s
    variants=['A2','E','A3','R','A4','F','G','C','B2']
    for variant in variants:
        if (h.OUT/variant/'close.json').exists():continue
        if variant=='F':
            decision=pkg.summarize(h.OUT)['batch_decision'];assert decision is not None
            if not decision['run_F']:
                h.write(h.OUT/'F-skipped.json',dict(reason='batch4 wins the prespecified rule',decision=decision));continue
        c=h.r.Console()
        try:launch(c,s,variant,variant);ready(c,s)
        finally:c.close()
        review_wait(s,'ready')
        c=h.r.Console()
        try:point(c,s,'test');route(c,s)
        finally:c.close()
        review_wait(s,'cafe')
        c=h.r.Console()
        try:point(c,s,'cafe')
        finally:c.close()
        review_wait(s,'after')
        c=h.r.Console()
        try:close(c,s)
        finally:c.close()
        pkg.summarize(h.OUT)
    # D is conditional, as the supplied test protocol specifies.
    evidence=pkg.summarize(h.OUT)
    incomplete=sum(p['bracketing']['slots'].get('totals',{}).get('incomplete_on_entry',0)
                   for p in evidence['measurements'] if p['variant'] in ('B','F','G','C','B2'))
    h.write(h.OUT/'D-decision.json',dict(ring_incomplete_entries=incomplete,run_D=incomplete>0))
    if incomplete>0:
        for variant in ('D32','D64'):
            if (h.OUT/variant/'close.json').exists():continue
            c=h.r.Console()
            try:launch(c,s,variant,variant);ready(c,s)
            finally:c.close()
            review_wait(s,'ready')
            c=h.r.Console()
            try:point(c,s,'test');route(c,s)
            finally:c.close()
            review_wait(s,'cafe')
            c=h.r.Console()
            try:point(c,s,'cafe')
            finally:c.close()
            review_wait(s,'after')
            c=h.r.Console()
            try:close(c,s)
            finally:c.close()
    c=h.r.Console()
    try:
        restore(c,s);launch(c,s,'original-final-verification')
        checks=h.verify_save(c,s)
        assert c.sha256(h.APP+'/eboot.bin')==s['initial_eboot_sha256']
        assert c.read(INI,65536)==(None if s['initial_ini'] is None else s['initial_ini'].encode())
        close(c,s)
        h.write(h.OUT/'final-state.json',dict(at=h.r.utc_now(),save_unchanged=True,save_check=checks,ini_unchanged=True,
                original_configs_verified=True,original_eboot_sha256=s['initial_eboot_sha256'],application_closed=True))
    finally:c.close()
    emit(dict(stage='sequence complete; restored and verified'))

def main(a):
    if a.op=='log':logger(h.OUT);return
    if a.op=='sequence':sequence();return
    c=h.r.Console()
    try:
        if a.op=='init':s=initial(c);launch(c,s,'original-before-test');return
        s=load()
        if a.op=='launch':launch(c,s,a.variant,a.variant)
        elif a.op=='ready':ready(c,s)
        elif a.op=='snapshot':snapshot(c,s,a.label)
        elif a.op=='nav':nav(c,s,a.action,a.frames,a.label)
        elif a.op=='route':route(c,s)
        elif a.op=='point':point(c,s,a.point)
        elif a.op=='close':close(c,s)
        elif a.op=='restore':restore(c,s)
        elif a.op=='verify-restored':
            launch(c,s,'original-final-verification')
            checks=h.verify_save(c,s);assert c.sha256(h.APP+'/eboot.bin')==s['initial_eboot_sha256']
            assert c.read(INI,65536)==(None if s['initial_ini'] is None else s['initial_ini'].encode())
            close(c,s);h.write(h.OUT/'final-state.json',dict(at=h.r.utc_now(),save_unchanged=True,save_check=checks,ini_unchanged=True,original_configs_verified=True,original_eboot_sha256=s['initial_eboot_sha256'],application_closed=True))
            emit(dict(stage='final verification passed',save_unchanged=True,application_closed=True))
    finally:c.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('op',choices=('log','init','launch','ready','snapshot','nav','route','point','close','restore','verify-restored','sequence'))
    p.add_argument('--variant',choices=VARIANTS);p.add_argument('--point',choices=('test','cafe'))
    p.add_argument('--label');p.add_argument('--action');p.add_argument('--frames',type=int,default=1)
    a=p.parse_args();h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True)
    NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/h.OUT.name
    try:main(a)
    except Exception as e:
        h.write(h.OUT/('host-error-'+h.r.stamp()+'.json'),dict(at=h.r.utc_now(),op=a.op,type=type(e).__name__,error=str(e)))
        raise
