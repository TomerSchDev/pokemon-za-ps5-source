"""Prepare compiled synthetic fixtures BEFORE taking a PC turn; run separately."""
import argparse,json,struct,subprocess
from pathlib import Path

ap=argparse.ArgumentParser();ap.add_argument('mode',choices=['prepare','run']);ap.add_argument('out',type=Path);args=ap.parse_args()
out=args.out.resolve();source=Path(__file__).resolve().parents[2]/'main-install/relocate_side_mods.c'
names=['valid','changed-current','changed-target','wrong-title','unknown-retained','symlink-current']
if args.mode=='prepare':
    out.mkdir(parents=True,exist_ok=False)
    for name in names:
        base=out/name;app=base/'app';mount=base/'mount';data=base/'download/zarecomp';ro=app/'hebrew-choice-mods'
        for p in [mount/'sce_sys',data/'mods/0-hebrew/romfs',data/'rando',ro/'romfs']:p.mkdir(parents=True,exist_ok=True)
        (mount/'sce_sys/param.json').write_text('{"titleId": "PPSA91990"}')
        rows=[('mods/0-hebrew/romfs/a.bin',b'synthetic asset A'),('mods/0-hebrew/romfs/b.bin',b'synthetic asset B'),('rando/current',b'old source save')]
        with (app/'init-data.bin').open('wb') as f:
            f.write(b'ZASIDE01'+struct.pack('<I',len(rows)))
            for path,raw in rows:
                encoded=path.encode();f.write(struct.pack('<HQ',len(encoded),len(raw))+encoded+raw)
                if path.startswith('mods/'):
                    (data/path).write_bytes(raw);(ro/path.split('mods/0-hebrew/',1)[1]).write_bytes(raw)
        (data/'rando/current').write_bytes(b'NEWER SAVE MUST SURVIVE')
        if name=='changed-current':(data/'mods/0-hebrew/romfs/b.bin').write_bytes(b'different current')
        if name=='changed-target':(ro/'romfs/b.bin').write_bytes(b'different target')
        if name=='wrong-title':(mount/'sce_sys/param.json').write_text('{"titleId": "PPSA91762"}')
        if name=='unknown-retained':(data/'mods/0-hebrew/private-extra').write_bytes(b'keep')
        if name=='symlink-current':
            target=data/'mods/0-hebrew/romfs/b.bin';target.unlink();target.symlink_to(ro/'romfs/b.bin')
        subprocess.run(['/usr/bin/cc','-O2','-Wall',f'-DSIDE_APP="{app}"',f'-DSIDE_DATA="{data}"',f'-DSIDE_MOUNT="{mount}"',f'-DSIDE_LINK_TARGET="{ro}"',str(source),'-o',str(base/'relocate')],check=True)
    (out/'fixture-manifest.json').write_text(json.dumps({'cases':names,'source':str(source),'prepared':True}))
    print('Prepared all six compiled fixtures; no tests executed')
else:
    results=[]
    for name in names:
        base=out/name;data=base/'download/zarecomp';save=data/'rando/current';before=save.stat()
        r=subprocess.run([str(base/'relocate')],capture_output=True,text=True,timeout=10)
        assert save.read_bytes()==b'NEWER SAVE MUST SURVIVE' and save.stat().st_mtime_ns==before.st_mtime_ns and save.stat().st_ino==before.st_ino
        if name in ('valid','unknown-retained'):
            assert r.returncode==0 and (data/'mods/0-hebrew').is_symlink(),r.stdout+r.stderr
            assert (data/'mods/0-hebrew/romfs/a.bin').read_bytes()==b'synthetic asset A'
            assert not (data/'mods/_before-readonly-hebrew/romfs/a.bin').exists()
            if name=='valid':assert subprocess.run([str(base/'relocate')],capture_output=True,timeout=10).returncode==0
            else:assert (data/'mods/_before-readonly-hebrew/private-extra').read_bytes()==b'keep'
        else:
            assert r.returncode!=0 and not (data/'mods/0-hebrew').is_symlink()
            assert (data/'mods/0-hebrew/romfs/a.bin').read_bytes()==b'synthetic asset A'
            if name!='wrong-title':assert 'removed_verified_copies=0' in r.stdout
        results.append({'case':name,'passed':True,'stdout':r.stdout})
    record={'passed':True,'tests':results,'scope':'synthetic copied assets only; no game or console'}
    (out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
