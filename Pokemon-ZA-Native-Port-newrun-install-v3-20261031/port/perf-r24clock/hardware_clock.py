"""Scoped hardware execution of TEST-CLOCK-r24clock-HE.md, preserving raw intervals."""
import argparse
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'port/perf-r24'))
sys.path.insert(0,str(ROOT/'port/perf-r24prof'))
import hardware_profile as hp
import hardware_run as h
from run_60_hardware import logger, rows_from
import analyze_r24clock as ac

CLOCK_SHA='35ee54dacd03b217a30f9e18b7e57f8117a880b859013dee7b005da44b6d573e'
INI=h.SANDBOX+'/download0/zarecomp/larecomp.ini'
VARIANTS={'A':'','B':'vkprof=0\n','A2':'','C':'ticks=tsc\n',
          'D':'vkprof=0\nticks=tsc\n','E':'vkprof=0\nticks=tsc\ntsc=1\n','A3':''}

def guard(s):
    log=hp.bootlog(s);errors=[]
    for line in log.splitlines():
        if re.search(r'GPU_FAULT|VK_ERROR_DEVICE_LOST|fatal signal|\bFATAL\b|\bEINTR\b',line,re.I):errors.append(line)
        m=re.search(r'TSC backwards (\d+) of',line)
        if m and int(m[1]):errors.append(line)
        if 'TSC was asked for but its frequency reads 0' in line:errors.append(line)
    if errors:
        rec=dict(at=h.r.utc_now(),boot=s['current']['label'],reason='Clock/hardware early-stop condition',lines=errors)
        h.write(h.OUT/'early-stop.json',rec);raise RuntimeError(json.dumps(rec))

def pause(s,seconds):
    until=time.monotonic()+seconds;last_frame=None;last_change=time.monotonic()
    while time.monotonic()<until:
        guard(s)
        if s['current'].get('ready_capture'):
            fs=re.findall(r'\[vk\] t=[\d.]+ frame (\d+)',hp.bootlog(s));f=fs[-1] if fs else None
            if f!=last_frame:last_frame=f;last_change=time.monotonic()
            if time.monotonic()-last_change>10:
                rec=dict(at=h.r.utc_now(),boot=s['current']['label'],reason='No advancing renderer frame for ten seconds',last_frame=last_frame)
                h.write(h.OUT/'early-stop.json',rec);raise RuntimeError(json.dumps(rec))
        time.sleep(min(.25,max(0,until-time.monotonic())))

def launch(a):
    h.BUILDS['r24']=('randomizer-r24-clock',CLOCK_SHA)
    variant=a.variant
    base=(ROOT/'artifacts/randomizer-r24-clock/PPSA91762/perf-r24-options.txt').read_bytes()
    full=base+b'\n# Identical GPU timeline instrumentation in every hardware variant\ngaps=1\n'+VARIANTS[variant].encode()
    assert len(full)<1024
    original_put=h.put
    def put(c,name,data):return original_put(c,name,full if name=='perf-r24-options.txt' else data)
    h.put=put
    original_verify=h.verify_save
    def startup_verify(c,s):
        cur=s['current'];sid=h.client.status(c.ftp)['session'];time.sleep(.5)
        assert h.client.status(c.ftp)['session']==sid
        if sid!=cur['session']:
            ps=h.r.eboot_processes();assert len(ps)==1 and h.r.process_pid(ps[0])==cur['pid'];h.title(c)
            old=cur['session'];cur['session']=sid;s['boots'][-1]['session']=sid
            h.write(h.OUT/cur['label']/'startup-session-race.json',dict(previous=old,stable=sid,pid=cur['pid']))
            hp.save(s);h.write(h.OUT/cur['label']/'identity.json',cur)
        return original_verify(c,s)
    h.verify_save=startup_verify
    a.build='r24' if a.build=='r24clock' else a.build;a.dcache='tls';a.prof=0;a.mode=None
    h.main(a)
    s=hp.state();cur=s['current'];cur.update(build='r24clock' if a.build=='r24' else a.build,
        variant=variant,options=full.decode() if a.build=='r24' else '',sampling=False)
    s['boots'][-1].update(cur)
    hp.save(s);h.write(h.OUT/cur['label']/'identity.json',cur)

def initialize():
    s=hp.state();c=h.r.Console()
    try:
        h.owned(c,s);assert s['current']['build']=='r23c'
        ini=c.read(INI,65536);s['initial_ini']=ini.decode() if ini is not None else None
        s['initial_eboot_sha256']=c.sha256(h.APP+'/eboot.bin');h.verify_save(c,s);hp.save(s)
        print(json.dumps(dict(initial_ini=s['initial_ini'],initial_eboot_sha256=s['initial_eboot_sha256'])),flush=True)
    finally:c.close()

def ready():
    hp.pause=pause;hp.ready()
    s=hp.state();cur=s['current'];log=hp.bootlog(s)
    off=cur['variant'] in ('B','D','E')
    expected='off' if off else 'on'
    assert f'renderer CPU profile (LARECOMP_VK_PROF): {expected}' in log
    assert ('LARECOMP_VK_PROF unset' if off else 'profile is on') in log
    assert '[za-r24-options] gaps=1' in log
    if cur['variant'] in ('C','D','E'):
        assert '[sdl3-ps5] ticks: TSC at ' in log
        assert 'TSC backwards 0 of 1000' in log
    if cur['variant']=='E':assert '[ps5] clock: plat_now_ns from the TSC' in log
    guard(s)
    notes=[x for x in log.splitlines() if re.search(r'\[za-r24clock\]|\[sdl3-ps5\] ticks|\[ps5\] clock|\[za-r24-options\]',x)]
    h.write(h.OUT/cur['label']/'startup-clock-verification.json',dict(variant=cur['variant'],profile=expected,notes=notes))
    print(json.dumps(dict(variant=cur['variant'],notes=notes)),flush=True)

def series():
    s=hp.state();c=h.r.Console()
    try:
        cur=h.owned(c,s);folder=h.OUT/cur['label'];before=cur['ready_capture'];phases=[]
        for i in range(2):
            guard(s);out=folder/f'measure-{i+1}'
            if (out/'phase.json').exists():
                existing=json.loads((out/'phase.json').read_text());assert any(p['csv']==existing['csv'] for p in s['phases'])
                phases.append(existing);continue
            host_start=None
            if out.exists():
                receipts=[json.loads(p.read_text()) for p in out.glob('command_*.json')]
                receipts=[r for r in receipts if r['ack']['op']=='measure' and r['ack']['result']=='complete']
                assert len(receipts)==1;rec=receipts[0]
                print(json.dumps(dict(stage='reusing completed raw measurement after host-analysis repair',boot=cur['label'],measurement=i+1)),flush=True)
            else:
                out.mkdir(exist_ok=False)
                seq=cur['seq']+1;cur['seq']=seq;hp.save(s)
                host_start=time.monotonic_ns()
                h.client.issue(c.ftp,cur['session'],seq,'measure',20)
                print(json.dumps(dict(stage='measuring',boot=cur['label'],measurement=i+1,seq=seq)),flush=True)
                pause(s,23)
                rec=h.collect(c,cur['session'],seq,out,{'complete'});h.owned(c,s);pause(s,2.5)
            csv=out/rec['files'][0]['name'];rows=rows_from(csv)
            timing=json.loads((out/(csv.stem+'-analysis.json')).read_text())
            assert timing['fps_modes']==[1] and timing['all_intervals']['duration_s']>=19.85
            assert not timing['capture_inside_window']
            log=folder/'boot.klog.log';log.write_text(hp.bootlog(s),encoding='utf-8')
            lo,hi=ac.r24.csv_frames(csv);windows,notes=ac.parse(log,lo,hi);assert windows
            perf=ac.summarize(windows,notes);assert perf['clock_gettime_available']
            assert (perf['vk_per_frame'] is None)==(cur['variant'] in ('B','D','E'))
            phase=dict(boot=cur['label'],variant=cur['variant'],measurement=i+1,options=cur['options'],
                csv=str(csv.relative_to(h.OUT)),timing=timing,perf=perf,receipt=rec,save_check=h.verify_save(c,s))
            phase['host_elapsed_issue_through_collect_seconds']=(time.monotonic_ns()-host_start)/1e9 if host_start else None
            phase['frame_ms_min']=min(r['dt_ns'] for r in rows)/1e6
            h.write(out/'phase.json',phase);s['phases'].append(phase);hp.save(s);phases.append(phase)
            print(json.dumps(dict(boot=cur['label'],measurement=i+1,timing=timing['all_intervals'],clock=perf['clock_gettime'],gpu_busy_ms=perf['gpu_busy_ms_per_frame'])),flush=True)
            if cur['variant']=='E':
                d=[p for p in s['phases'] if p['variant']=='D'];assert d
                dmax=max(p['timing']['all_intervals']['frame_ms']['max'] for p in d)
                if min(r['dt_ns'] for r in rows)<=0 or timing['all_intervals']['frame_ms']['max']>max(50,dmax*2):
                    h.write(h.OUT/'early-stop.json',dict(at=h.r.utc_now(),boot=cur['label'],reason='E frame timing exceeds D guard',D_max_ms=dmax,E_timing=timing));raise RuntimeError('E timing guard')
        after=h.command(c,s,folder,'snapshot',expected={'saved'});h.retire(c,s,after,folder)
        for p in phases:
            p.update(before=before,after=after,capture_scope='One snapshot before and after the two-measurement series; no captures or FTP inside recorder windows.')
            h.write((h.OUT/p['csv']).parent/'phase.json',p)
        (folder/'boot.klog.log').write_text(hp.bootlog(s),encoding='utf-8');hp.save(s)
    finally:c.close()

def audit():
    s=hp.state();c=h.r.Console()
    try:
        h.owned(c,s);checks=h.verify_save(c,s)
        # The transport's generic r24 alias is replaced by the verified per-boot
        # clock identity when recording historical configuration metadata.
        for boot in s['boots']:
            identity=json.loads((h.OUT/boot['label']/'identity.json').read_text())
            for key in ('build','variant','options','sampling','session'):
                if key in identity:boot[key]=identity[key]
        hp.save(s)
        actual=c.sha256(h.APP+'/eboot.bin');assert actual==s['initial_eboot_sha256']
        configs={n:(lambda b:b.decode() if b is not None else None)(c.read(h.APP+'/'+n,4096)) for n in (*h.CONFIGS,'perf-r24-options.txt')}
        assert configs==s['initial_configs'];ini=c.read(INI,65536)
        assert ini==(s['initial_ini'].encode() if s['initial_ini'] is not None else None)
        rec=dict(at=h.r.utc_now(),installed_sha256=actual,installed_sha256_verified=True,original_configs_verified=True,
            ini_verified=True,configs=configs,save_unchanged=True,save_check=checks,application_closed=False)
        h.write(h.OUT/'final-state.json',rec);print(json.dumps(rec),flush=True)
    finally:c.close()

def main(a):
    h.OUT=a.out.resolve();h.OUT.mkdir(parents=True,exist_ok=True)
    h.BUILDS['r24']=('randomizer-r24-clock',CLOCK_SHA)
    if a.op=='log':logger(h.OUT)
    elif a.op=='launch':launch(a)
    elif a.op=='initialize':initialize()
    elif a.op=='ready':ready()
    elif a.op=='series':series()
    elif a.op=='audit':audit()
    else:
        h.main(a)
        if a.op=='close' and (h.OUT/'final-state.json').exists():
            rec=json.loads((h.OUT/'final-state.json').read_text());rec['application_closed']=not h.r.eboot_processes()
            assert rec['application_closed'];h.write(h.OUT/'final-state.json',rec)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',required=True,type=Path)
    p.add_argument('op',choices=('log','launch','initialize','ready','series','close','restore-config','inspect','audit'))
    p.add_argument('--label');p.add_argument('--build',choices=('r23c','r24clock'),default='r24clock')
    p.add_argument('--variant',choices=VARIANTS,default='A');main(p.parse_args())
