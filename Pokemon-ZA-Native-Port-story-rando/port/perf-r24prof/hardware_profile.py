"""Scoped execution of TEST-PROFILE-r24prof-HE.md; PIE stays on the host."""
import argparse
import ftplib
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'port/perf-r24'))
import hardware_run as h
import analyze_r24
from run_60_hardware import rows_from
from summarize_hardware import vk_windows
import symbolize_samples as sz

PROF_SHA='64acf8fa5101fb14be8d221a30b9abcda2ed9769d50cee11edc7979cd4284fb3'
PROFDIR=h.SANDBOX+'/download0/zarecomp/r24prof'
INI=h.SANDBOX+'/download0/zarecomp/larecomp.ini'


def state():return json.loads((h.OUT/'state.json').read_text())
def save(s):h.write(h.OUT/'state.json',s)


def bootlog(s):
    return (h.OUT/'all.klog.log').read_bytes()[s['current']['klog_offset']:].decode('utf-8','replace')


def guard(s):
    if not s['current'].get('sampling'):return
    log=bootlog(s)
    errors=[]
    for line in log.splitlines():
        if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b|\bEINTR\b',line,re.I):errors.append(line)
        m=re.search(r'\[za-r24prof\].*sent=(\d+) kill_err=(\d+)',line)
        if m and (int(m[2])>=100 or int(m[2])>max(2,int(m[1])*.01)):errors.append(line)
    if errors:
        record=dict(at=h.r.utc_now(),reason='sampling early-stop condition',lines=errors)
        h.write(h.OUT/'early-stop.json',record)
        raise RuntimeError(json.dumps(record))


def pause(s,seconds):
    until=time.monotonic()+seconds
    last_frame=None;last_change=time.monotonic()
    while time.monotonic()<until:
        guard(s)
        if s['current'].get('sampling') and s['current'].get('ready_capture'):
            frames=re.findall(r'\[vk\] t=[\d.]+ frame (\d+)',bootlog(s))
            frame=frames[-1] if frames else None
            if frame!=last_frame:last_frame=frame;last_change=time.monotonic()
            if time.monotonic()-last_change>10:
                record=dict(at=h.r.utc_now(),reason='No new render profiler frame for ten seconds in an already loaded sampling scene',last_frame=last_frame)
                h.write(h.OUT/'early-stop.json',record);raise RuntimeError(json.dumps(record))
        time.sleep(min(.25,max(0,until-time.monotonic())))


def initialize():
    s=state();c=h.r.Console()
    try:
        cur=h.owned(c,s);assert cur['build']=='r23c'
        ini=c.read(INI,65536);s['initial_ini']=ini.decode() if ini is not None else None
        try:s['initial_sample_files']=c.listing(PROFDIR)
        except ftplib.error_perm:s['initial_sample_files']=[]
        h.verify_save(c,s);save(s)
        print(json.dumps(dict(initial_ini=s['initial_ini'],initial_sample_files=s['initial_sample_files'])),flush=True)
    finally:c.close()


def launch(a):
    # Reuse the verified idle-only binary transport; inject the complete startup file before launch.
    h.BUILDS['r24']=('randomizer-r24-prof',PROF_SHA)
    full='gaps=1\ndcache=tls\nprof=0\nscale=1\nforce60=1\n'
    if a.sampling:full+='sample=1\nsample_us=1000\nsample_threads=all\nsample_seconds=20\n'
    put=h.put
    def options(c,name,data):
        return put(c,name,full.encode() if name=='perf-r24-options.txt' else data)
    h.put=options
    verify=h.verify_save
    def startup_verify(c,s):
        cur=s['current']
        sid=h.client.status(c.ftp)['session'];time.sleep(.5)
        assert h.client.status(c.ftp)['session']==sid
        if sid!=cur['session']:
            ps=h.r.eboot_processes();assert len(ps)==1 and h.r.process_pid(ps[0])==cur['pid']
            h.title(c);old=cur['session'];cur['session']=sid;s['boots'][-1]['session']=sid
            h.write(h.OUT/cur['label']/'startup-session-race.json',dict(previous=old,stable=sid,pid=cur['pid']))
            save(s);h.write(h.OUT/cur['label']/'identity.json',cur)
        return verify(c,s)
    h.verify_save=startup_verify
    a.build='r24' if a.build=='r24prof' else a.build;a.dcache='tls';a.prof=0;a.mode=None
    h.main(a)
    s=state();cur=s['current'];cur['build']='r24prof' if a.build=='r24' else a.build
    cur['options']=full if a.build=='r24' else ''
    cur['sampling']=bool(a.sampling);save(s);h.write(h.OUT/cur['label']/'identity.json',cur)


def ready():
    s=state();c=h.r.Console()
    try:
        cur=h.owned(c,s);out=h.OUT/cur['label']
        h.command(c,s,out,'continue',cur['run'],expected={'continue_requested'})
        print('Loading title screen',flush=True);pause(s,12)
        h.command(c,s,out,'input','A',1,expected={'input_armed'})
        print('Warming unchanged scene',flush=True);pause(s,35)
        capture=h.command(c,s,out,'snapshot',expected={'saved'});h.retire(c,s,capture,out)
        cur['ready_capture']=capture;cur['ready_capture_host_ns']=time.time_ns();save(s)
        print(json.dumps(capture),flush=True)
    finally:c.close()


def measured(c,s,label):
    guard(s);cur=h.owned(c,s);out=h.OUT/cur['label']/label;out.mkdir(exist_ok=False)
    seq=cur['seq']+1;cur['seq']=seq;save(s)
    h.client.issue(c.ftp,cur['session'],seq,'measure',20)
    print(json.dumps(dict(stage='measuring',boot=cur['label'],label=label,seq=seq)),flush=True)
    pause(s,23)
    rec=h.collect(c,cur['session'],seq,out,{'complete'});h.owned(c,s)
    # The supplied counter analyzer requires a stats report reaching the CSV's last frame.
    pause(s,2.5)
    csvfile=out/rec['files'][0]['name'];rows=rows_from(csvfile)
    timing=json.loads((out/(csvfile.stem+'-analysis.json')).read_text())
    assert timing['fps_modes']==[1],timing['fps_modes']
    assert timing['all_intervals']['duration_s']>=19.85 and not timing['capture_inside_window']
    log=h.OUT/cur['label']/'boot.klog.log';log.write_text(bootlog(s),encoding='utf-8')
    lo,hi=min(r['frame'] for r in rows),max(r['frame'] for r in rows)
    perf=analyze_r24.summarize(analyze_r24.parse(log,lo,hi))
    phase=dict(boot=cur['label'],label=label,sampling=cur['sampling'],options=cur['options'],
               csv=str(csvfile.relative_to(h.OUT)),timing=timing,perf=perf,vk=vk_windows(log,lo,hi),
               from_ns=rows[0]['now_ns']-rows[0]['dt_ns'],to_ns=rows[-1]['now_ns'],
               receipt=rec,save_check=h.verify_save(c,s))
    h.write(out/'phase.json',phase);s['phases'].append(phase);save(s)
    print(json.dumps(dict(boot=cur['label'],label=label,timing=timing['all_intervals'],
                          vk=phase['vk'],gpu_busy_ms=perf['per_frame']['gpu_busy_ms'])),flush=True)
    return phase


def series(a):
    s=state();c=h.r.Console()
    try:
        cur=h.owned(c,s);folder=h.OUT/cur['label']
        before=cur['ready_capture']
        if cur['sampling']:
            print('Stable-scene guard before the three sampling measurements (30 seconds)',flush=True);pause(s,30)
        phases=[measured(c,s,f'measure-{i+1}') for i in range(a.count)]
        if cur['sampling']:
            print('Waiting for overlapping sample windows to finish, without camera or FTP traffic (25 seconds)',flush=True);pause(s,25)
        after=h.command(c,s,folder,'snapshot',expected={'saved'});h.retire(c,s,after,folder)
        for p in phases:
            p['before']=before;p['after']=after
            p['capture_scope']='One scene capture before and after the whole same-configuration series; no screenshots between measurements.'
            h.write((h.OUT/p['csv']).parent/'phase.json',p)
        (folder/'boot.klog.log').write_text(bootlog(s),encoding='utf-8')
        save(s)
    finally:c.close()


def fetch(a):
    s=state();c=h.r.Console()
    try:
        h.owned(c,s)
        try:names=c.listing(PROFDIR)
        except ftplib.error_perm:names=[]
        folder=h.OUT/'samples';folder.mkdir(exist_ok=True)
        inventory=[]
        for name in names:
            if not re.fullmatch(r'samples-b\d+-s\d+\.bin(?:\.part)?',name):continue
            if name in s.get('initial_sample_files',[]):continue
            remote=PROFDIR+'/'+name;data=c.read(remote,4<<20)
            if data is None:continue
            assert data==c.read(remote,4<<20),'Sample file changed during read'
            sha=h.sha(data);assert c.sha256(remote)==sha
            path=folder/name
            if path.exists():assert h.sha(path.read_bytes())==sha
            else:path.write_bytes(data)
            info=dict(name=name,bytes=len(data),sha256=sha,double_read_verified=True,remote_sha256_verified=True)
            if not name.endswith('.part'):
                parsed=sz.parse_file(path)
                info['header']={k:parsed[k] for k in ('boot','window','t0','t1','anchor','text','period_us','flags','sent','dropped','skipped','kill_errors','render_slot')}
                info['records']=len(parsed['records']);info['threads']=len(parsed['threads'])
            inventory.append(info)
        h.write(h.OUT/'sample-copy-verification.json',dict(at=h.r.utc_now(),files=inventory))
        s['sample_files']=inventory;save(s)
        print(json.dumps(dict(copied=len(inventory),files=inventory)),flush=True)
    finally:c.close()


def cleanup():
    s=state();assert not s['current']['sampling'];c=h.r.Console()
    try:
        h.owned(c,s);inventory=s.get('sample_files',[])
        if not inventory:
            h.write(h.OUT/'sample-cleanup.json',dict(files=[],no_files=True));return
        for f in inventory:
            assert f['remote_sha256_verified'] and h.sha((h.OUT/'samples'/f['name']).read_bytes())==f['sha256']
            remote_hash=c.sha256(PROFDIR+'/'+f['name'])
            assert remote_hash in (None,f['sha256'])
        parent=PROFDIR.rsplit('/',1)[0]
        c.ftp.cwd(parent);lines=[];c.ftp.retrlines('LIST',lines.append);c.ftp.cwd('/')
        before=next(x for x in lines if x.endswith(' r24prof'));assert before.startswith('drwxr-xr-x '),before
        c.ftp.sendcmd('SITE CHMOD 777 '+PROFDIR)
        try:
            for f in inventory:
                if c.read(PROFDIR+'/'+f['name'],4<<20) is None:continue
                try:c.ftp.delete(PROFDIR+'/'+f['name'])
                except ftplib.error_reply as ex:
                    if not str(ex).startswith('226 File deleted'):raise
        finally:c.ftp.sendcmd('SITE CHMOD 755 '+PROFDIR)
        for f in inventory:assert c.read(PROFDIR+'/'+f['name'],4<<20) is None
        c.ftp.cwd(parent);lines=[];c.ftp.retrlines('LIST',lines.append);c.ftp.cwd('/')
        after=next(x for x in lines if x.endswith(' r24prof'));assert after.startswith('drwxr-xr-x ') and after.split()[2:4]==before.split()[2:4]
        h.write(h.OUT/'sample-cleanup.json',dict(at=h.r.utc_now(),files=[f['name'] for f in inventory],removed_after_verified_copy=True,directory_before=before,directory_after=after,permissions_restored=True))
        print(json.dumps(dict(cleaned=len(inventory),permissions_restored=True)),flush=True)
    finally:c.close()


def main(a):
    h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True)
    if a.op=='initialize':initialize()
    elif a.op=='launch':launch(a)
    elif a.op=='ready':ready()
    elif a.op=='series':series(a)
    elif a.op=='fetch':fetch(a)
    elif a.op=='cleanup':cleanup()
    else:h.main(a)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('op',choices=('initialize','launch','ready','series','fetch','cleanup','close','restore-config','inspect'))
    p.add_argument('--label');p.add_argument('--build',choices=('r23c','r24prof'),default='r24prof')
    p.add_argument('--sampling',type=int,choices=(0,1),default=0);p.add_argument('--count',type=int,choices=(1,2,3),default=1)
    main(p.parse_args())
