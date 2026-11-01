"""Scoped NEXT-stress-and-play hardware protocol; no save writes or interaction inputs."""
import argparse
import json
from pathlib import Path
import re
import sys
import time
import hardware_clock as hw
h=hw.h
hp=hw.hp
ROOT=hw.ROOT
OPTIONS={'stress':'scale=1\nforce60=1\nticks=tsc\ngaps=1\n',
         'play':'vkprof=0\nticks=tsc\nscale=1\n'}
NAV=('STICK_UP','STICK_DOWN','STICK_LEFT','STICK_RIGHT','RSTICK_UP','RSTICK_DOWN','RSTICK_LEFT','RSTICK_RIGHT','RELEASE')

def launch(a):
    h.BUILDS['r24']=('randomizer-r24-clock',hw.CLOCK_SHA)
    full=OPTIONS[a.kind];put=h.put;verify=h.verify_save
    def startup_put(c,name,data):return put(c,name,full.encode() if name=='perf-r24-options.txt' else data)
    h.put=startup_put
    def stable_verify(c,s):
        cur=s['current'];sid=h.client.status(c.ftp)['session'];time.sleep(.5)
        assert h.client.status(c.ftp)['session']==sid
        if sid!=cur['session']:
            ps=h.r.eboot_processes();assert len(ps)==1 and h.r.process_pid(ps[0])==cur['pid'];h.title(c)
            old=cur['session'];cur['session']=sid;s['boots'][-1]['session']=sid
            h.write(h.OUT/cur['label']/'startup-session-race.json',dict(previous=old,stable=sid,pid=cur['pid']))
            hp.save(s)
        return verify(c,s)
    h.verify_save=stable_verify
    a.build='r24';a.dcache='tls';a.prof=0;a.mode=None
    h.main(a)
    s=hp.state();cur=s['current'];cur.update(build='r24clock',kind=a.kind,options=full,sampling=False)
    s['boots'][-1].update(cur);hp.save(s);h.write(h.OUT/cur['label']/'identity.json',cur)

def ready():
    hp.pause=hw.pause;hp.ready()
    s=hp.state();cur=s['current'];c=h.r.Console()
    try:
        h.owned(c,s);log=hp.bootlog(s);kind=cur['kind'];off=kind=='play'
        assert c.read(h.APP+'/perf-r24-options.txt',4096)==OPTIONS[kind].encode()
        assert f'renderer CPU profile (LARECOMP_VK_PROF): {"off" if off else "on"}' in log
        assert '[sdl3-ps5] ticks: TSC at ' in log and 'TSC backwards 0 of 1000' in log
        assert '[ps5] clock: plat_now_ns from clock_gettime' in log
        assert 'memo=1 lean=1' in log and 'swapchain 3840x2160' in log
        assert '[post] 1920x1080 fsr1 -> 3840x2160' in log
        assert ('[za-r24-options] force60=1' in log)==(kind=='stress')
        hw.guard(s);checks=h.verify_save(c,s)
        notes=[l for l in log.splitlines() if re.search(r'\[za-r24clock\]|\[sdl3-ps5\] ticks|\[ps5\] clock|\[za-r24-options\]|\[post\]',l)]
        h.write(h.OUT/cur['label']/'startup-verification.json',dict(kind=kind,notes=notes,save_check=checks))
        print(json.dumps(dict(kind=kind,notes=notes)),flush=True)
    finally:c.close()

def snapshot(c,s,out):
    out.mkdir(parents=True,exist_ok=True)
    rec=h.command(c,s,out,'snapshot',expected={'saved'});h.retire(c,s,rec,out)
    return rec

def navigation(a):
    s=hp.state();c=h.r.Console()
    try:
        cur=h.owned(c,s);assert cur['kind']=='stress'
        out=h.OUT/cur['label']/'navigation'/a.label;out.mkdir(parents=True,exist_ok=False)
        before=h.verify_save(c,s)
        rec=h.command(c,s,out,'input',a.action,a.frames,expected={'input_armed'})
        hw.pause(s,a.frames/20+2)
        # Explicit release, even though observer inputs expire automatically.
        release=h.command(c,s,out,'input','RELEASE',1,expected={'input_armed'});hw.pause(s,2)
        image=snapshot(c,s,out)
        info=dict(at=h.r.utc_now(),action=a.action,frames=a.frames,input_receipt=rec,release=release,
                  screenshot=image,save_check_before=before,save_check_after=h.verify_save(c,s))
        h.write(out/'navigation.json',info);print(json.dumps(info),flush=True)
    finally:c.close()

def point(a):
    s=hp.state();c=h.r.Console()
    try:
        cur=h.owned(c,s);kind=cur['kind'];mode=1 if kind=='stress' else 0
        out=h.OUT/cur['label']/'points'/a.point;out.mkdir(parents=True,exist_ok=False)
        print(json.dumps(dict(stage='warming static point',point=a.point,seconds=15)),flush=True);hw.pause(s,15)
        before=snapshot(c,s,out);phases=[]
        for i in range(2):
            folder=out/f'measure-{i+1}';folder.mkdir(exist_ok=False)
            seq=cur['seq']+1;cur['seq']=seq;hp.save(s)
            h.client.issue(c.ftp,cur['session'],seq,'measure',20)
            print(json.dumps(dict(stage='measuring',point=a.point,measurement=i+1,seq=seq,expected_mode=mode)),flush=True)
            hw.pause(s,23)
            rec=h.collect(c,cur['session'],seq,folder,{'complete'});h.owned(c,s);hw.pause(s,2.5)
            csv=folder/rec['files'][0]['name'];rows=hw.rows_from(csv)
            timing=json.loads((folder/(csv.stem+'-analysis.json')).read_text())
            assert timing['fps_modes']==[mode] and timing['all_intervals']['duration_s']>=19.85
            assert not timing['capture_inside_window']
            log=h.OUT/cur['label']/'boot.klog.log';log.write_text(hp.bootlog(s),encoding='utf-8')
            lo,hi=hw.ac.r24.csv_frames(csv);windows,notes=hw.ac.parse(log,lo,hi);assert windows
            perf=hw.ac.summarize(windows,notes)
            assert (perf['vk_per_frame'] is None)==(kind=='play')
            for w in windows:
                assert all(f'cg_{c}{x}' in w for c in ('render','guest','other') for x in ('','_ns','_max_ns'))
            phase=dict(boot=cur['label'],kind=kind,point=a.point,measurement=i+1,options=cur['options'],
                csv=str(csv.relative_to(h.OUT)),receipt=rec,timing=timing,perf=perf,
                thresholds={f'over_{v:g}_ms':sum(r['dt_ns']>v*1e6 for r in rows) for v in (16.7,20,33)},
                save_check=h.verify_save(c,s))
            s['phases'].append(phase);hp.save(s);h.write(folder/'phase.json',phase);phases.append(phase)
            print(json.dumps(dict(point=a.point,measurement=i+1,timing=timing['all_intervals'],thresholds=phase['thresholds'],
                vk=perf['vk_per_frame'],gpu_busy_ms=perf['gpu_busy_ms_per_frame'])),flush=True)
        after=snapshot(c,s,out)
        for p in phases:
            p.update(before=before,after=after,capture_directory=str(out.relative_to(h.OUT)))
            h.write((h.OUT/p['csv']).parent/'phase.json',p)
        (h.OUT/cur['label']/'boot.klog.log').write_text(hp.bootlog(s),encoding='utf-8');hp.save(s)
    finally:c.close()

def install_gate():
    s=hp.state();points={p['point'] for p in s['phases'] if p['kind']=='stress'}
    assert points=={'city-a','city-b','city-c','city-d'}
    assert len([p for p in s['phases'] if p['kind']=='stress'])==8
    assert not (h.OUT/'early-stop.json').exists()
    visual=json.loads((h.OUT/'visual-checks.json').read_text())
    assert all(any(v['point']==p and v['no_obvious_corruption'] and v['menu_closed'] for v in visual) for p in points)
    c=h.r.Console()
    try:
        hw.guard(s);checks=h.verify_save(c,s)
        log=hp.bootlog(s)
        assert not re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b',log,re.I)
        rec=dict(at=h.r.utc_now(),passed=True,stress_points=sorted(points),measurements=8,save_check=checks,
                 basis='No fault/crash, visually inspected static scenes without obvious corruption; frame slowdowns are reported separately.')
        h.write(h.OUT/'installation-gate.json',rec);print(json.dumps(rec),flush=True)
    finally:c.close()

def audit():
    s=hp.state();c=h.r.Console()
    try:
        cur=h.owned(c,s);assert cur['kind']=='play'
        actual=c.sha256(h.APP+'/eboot.bin');assert actual==hw.CLOCK_SHA
        opts=c.read(h.APP+'/perf-r24-options.txt',4096);assert opts==OPTIONS['play'].encode()
        checks=h.verify_save(c,s)
        configs={n:c.read(h.APP+'/'+n,4096).decode() for n in h.CONFIGS}
        assert configs=={n:s['initial_configs'][n] for n in h.CONFIGS}
        ini=c.read(hw.INI,65536);assert ini==(s['initial_ini'].encode() if s['initial_ini'] is not None else None)
        deploy=json.loads((h.OUT/'stress-clock'/'deploy.json').read_text());remote=deploy['remote_backup']
        old=c.sha256(remote);assert old==s['initial_eboot_sha256']
        play=[p for p in s['phases'] if p['kind']=='play'];assert len(play)==2
        assert all(p['timing']['fps_modes']==[0] and 29.8<=p['timing']['all_intervals']['interval_rate_fps']<=30.2 for p in play)
        hw.guard(s)
        rec=dict(at=h.r.utc_now(),installed_sha256=actual,installed_sha256_verified=True,play_options=opts.decode(),
            original_six_configs_verified=True,configs=configs,ini_unchanged=True,save_unchanged=True,save_check=checks,
            r23c_backup=dict(remote_path=remote,sha256=old,verified=True,local_source=str(ROOT/'artifacts/randomizer-r23c-slot-depth/PPSA91762/eboot.bin')),
            startup_30_fps_verified=True,force60_absent=True,runtime_tsc_disabled=True,application_closed=False)
        h.write(h.OUT/'final-state.json',rec);print(json.dumps(rec),flush=True)
    finally:c.close()

def main(a):
    h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True)
    h.BUILDS['r24']=('randomizer-r24-clock',hw.CLOCK_SHA)
    if a.op=='launch':launch(a)
    elif a.op=='ready':ready()
    elif a.op=='point':point(a)
    elif a.op=='nav':navigation(a)
    elif a.op=='gate':install_gate()
    elif a.op=='audit':audit()
    else:
        h.main(a)
        if a.op=='close' and (h.OUT/'final-state.json').exists():
            rec=json.loads((h.OUT/'final-state.json').read_text());rec['application_closed']=not h.r.eboot_processes()
            assert rec['application_closed'];h.write(h.OUT/'final-state.json',rec)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('op',choices=('launch','ready','point','nav','gate','audit','close','inspect'))
    p.add_argument('--label');p.add_argument('--kind',choices=OPTIONS,default='stress')
    p.add_argument('--point');p.add_argument('--action',choices=NAV);p.add_argument('--frames',type=int,choices=range(1,121),default=1)
    main(p.parse_args())
