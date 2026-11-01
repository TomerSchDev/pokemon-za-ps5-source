"""Pinned r24 experiments: idle-only title update, reversible config, save backup.

Only PPSA91762; uses the existing staged/hash-verified deployment transport.
No process closure, game input, save replacement or arbitrary remote paths.
"""
import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import run_r3 as r

spec = importlib.util.spec_from_file_location('r24_transport', ROOT/'port/submission-r20-hardware/hardware.py')
t = importlib.util.module_from_spec(spec)
spec.loader.exec_module(t)
t.SOURCE = ROOT/'artifacts/randomizer-r24-perf/PPSA91762/eboot.bin'
t.BASE = ROOT/'artifacts/randomizer-r23c-slot-depth/PPSA91762/eboot.bin'
t.BASE_SHA = 'dd1df4862a08eab80a19790bb2b65b351adb8ff1fc3ce893def4a91417786677'
CANDIDATE = 'a7890eca75127adcdb9c464cdeb03e9c1d143fe099fbf853500a9349c56a5610'
E = ROOT/'evidence/perf-r24-hardware'
FIXED = {'performance-options.txt': b'optimized\n', 'performance-profile.txt': b'30\n',
         'observer-enable.txt': b'observe-r17\n', 'local-shader-options.txt': b'local\n',
         'submission-options.txt': b'batch4\n'}
PROFILES = {
    'default': b'gaps=1\ndcache=tls\nprof=0\n',
    'cpu': b'gaps=1\ndcache=cpu\nprof=0\n',
    '1080': b'gaps=1\ndcache=tls\nprof=0\nmode=1920x1080\n',
    'passes': b'gaps=1\ndcache=tls\nprof=1\n',
    'no-gaps': b'gaps=0\ndcache=tls\nprof=0\n',
}

def pinned():
    assert t.sha(t.SOURCE.read_bytes()) == CANDIDATE
    assert t.sha(t.BASE.read_bytes()) == t.BASE_SHA

def fixed(c):
    t.idle(); t.identity(c)
    for n, data in FIXED.items():
        assert c.read(t.APP+'/'+n, 1024) == data, n
    assert c.read(t.APP+'/local-shader-test.txt', 1024) is None

def replace_small(c, name, data, out):
    assert name in ('perf-r24-options.txt', 'slot-depth-options.txt')
    fixed(c)
    remote = t.APP+'/'+name
    old = c.read(remote, 4096)
    if old is not None: (out/('previous-'+name)).write_bytes(old)
    (out/name).write_bytes(data)
    backup = None
    if old != data:
        tag = r.stamp()
        stage, backup = remote+'.r24-stage-'+tag, remote+'.before-r24-'+tag
        c.store(stage, data)
        assert c.read(stage, 4096) == data
        fixed(c)
        assert c.read(remote, 4096) == old
        if old is not None: c.ftp.rename(remote, backup)
        try: c.ftp.rename(stage, remote)
        except Exception:
            if old is not None: c.ftp.rename(backup, remote)
            raise
    assert c.read(remote, 4096) == data
    return dict(name=name, sha256=t.sha(data), readback=True,
                previous_sha256=t.sha(old) if old is not None else None,
                remote_backup=backup if old is not None and old != data else None)

def configure(c, profile, out):
    fixed(c)
    assert c.sha256(t.APP+'/eboot.bin') in (CANDIDATE, t.BASE_SHA)
    return dict(profile=profile, files=[
        replace_small(c, 'perf-r24-options.txt', PROFILES[profile], out),
        replace_small(c, 'slot-depth-options.txt', b'16\n', out)])

def backup(c, out):
    sandbox='/mnt/sandbox/PPSA91762_000'
    assert json.loads(c.read(sandbox+'/app0/sce_sys/param.json',65536))['titleId']=='PPSA91762'
    base=sandbox+'/download0/zarecomp/rando'
    active=c.read(base+'/active.json',4096)
    run=json.loads(active)['id']
    assert run.startswith('r') and all(x.isalnum() or x=='-' for x in run)
    (out/'active.json').write_bytes(active)
    files=[]
    for name in ('report.json','save/save_0/main'):
        data=c.read(base+'/'+run+'/'+name)
        assert data is not None and data
        local=out/name; local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(data)
        digest=t.sha(data)
        assert c.sha256(base+'/'+run+'/'+name)==digest
        files.append(dict(path=name,sha256=digest,bytes=len(data)))
    assert c.read(base+'/active.json',4096)==active
    result=dict(at=r.utc_now(),run=run,files=files,double_read_verified=True)
    t.write(out/'verification.json',result)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('op',choices=('inspect','install24','install23','config','launch','backup'))
    p.add_argument('--profile',choices=tuple(PROFILES),default='default')
    p.add_argument('--version',choices=('r23c','r24'),default='r24')
    a=p.parse_args(); E.mkdir(parents=True,exist_ok=True)
    pinned()
    out=E/(a.op+'-'+r.stamp());out.mkdir(exist_ok=False)
    c=r.Console()
    try:
        if a.op=='inspect':
            result=dict(at=r.utc_now(),processes=r.eboot_processes(),
                        eboot_sha256=c.sha256(t.APP+'/eboot.bin'),
                        configs={n:(c.read(t.APP+'/'+n,4096) or b'').decode(errors='replace')
                                 for n in (*FIXED,'slot-depth-options.txt','perf-r24-options.txt')})
        elif a.op=='backup': result=backup(c,out)
        else:
            fixed(c)
            installed=c.sha256(t.APP+'/eboot.bin')
            assert installed in (CANDIDATE,t.BASE_SHA), installed
            if a.op in ('install24','install23'):
                t.options=lambda console,unused,dest:configure(console,a.profile,dest)
                result=t.deploy(c,CANDIDATE,out,rollback=a.op=='install23')
            elif a.op=='config': result=configure(c,a.profile,out)
            else:
                expected=CANDIDATE if a.version=='r24' else t.BASE_SHA
                assert installed==expected
                assert c.read(t.APP+'/slot-depth-options.txt',1024)==b'16\n'
                if a.version=='r24': assert c.read(t.APP+'/perf-r24-options.txt',4096)==PROFILES[a.profile]
                fixed(c)
                result=dict(at=r.utc_now(),version=a.version,sha256=installed,profile=a.profile,
                    response=r.http_text(r.PAYLOAD_MANAGER+'/loadpayload:/data/pldmgr/payloads/za_native_randomizer_launch/za_native_randomizer_launch.elf'))
        t.write(out/'result.json',result)
        print(json.dumps(dict(path=str(out),result=result),ensure_ascii=True),flush=True)
    finally:c.close()

if __name__=='__main__':main()
