"""Linux host safety regressions for the actual native side initializer source."""
import hashlib
import json
import os
from pathlib import Path
import struct
import stat
import subprocess
import sys

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
source=Path(__file__).resolve().parents[2]/'main-install/seed-side-data.c'
app=out/'app';mount=out/'mount';data=out/'download/zarecomp'
for p in [app,mount/'sce_sys',data]:p.mkdir(parents=True,exist_ok=True)
for p in [data/'mods',data/'rando']:p.mkdir(mode=0o555)
(mount/'sce_sys/param.json').write_text('{"titleId": "PPSA91990"}')
binary=out/'seed'
subprocess.run(['cc','-O2','-Wall','-Wextra',f'-DSIDE_APP="{app}"',f'-DSIDE_MOUNT="{mount}"',f'-DSIDE_DATA="{data}"',str(source),'-o',str(binary)],check=True)
def pack(rows):
    with (app/'init-data.bin').open('wb') as f:
        f.write(b'ZASIDE01'+struct.pack('<I',len(rows)))
        for name,contents in rows:
            b=name.encode();f.write(struct.pack('<HQ',len(b),len(contents))+b+contents)
def run():return subprocess.run([str(binary)],timeout=10).returncode
results=[]
def check(name,condition):
    results.append({'name':name,'passed':bool(condition)})
    if not condition:raise AssertionError(name)
pack([('rando/active.json',b'{"id":"fixture"}'),('mods/0-hebrew/romfs/test.bin',b'local synthetic data')])
check('valid pack copied and verified',run()==0 and (data/'mods/0-hebrew/romfs/test.bin').read_bytes()==b'local synthetic data')
check('existing directory permissions restored',all(stat.S_IMODE(p.stat().st_mode)==0o555 for p in [data/'mods',data/'rando']))
check('same pack can verify again without replacement',run()==0)
p=data/'rando/active.json';p.write_bytes(b'newer progress');before=p.stat()
check('differing existing save is never replaced',run()!=0 and p.read_bytes()==b'newer progress' and p.stat().st_mtime_ns==before.st_mtime_ns)
pack([('rando/../../escaped',b'BAD')]);check('parent traversal rejected',run()!=0 and not (out/'escaped').exists())
pack([('game/config',b'BAD')]);check('outside mods and runs rejected',run()!=0 and not (data/'game').exists())
outside=out/'outside';outside.mkdir();(data/'mods').chmod(0o777);(data/'mods/linked').symlink_to(outside,target_is_directory=True)
pack([('mods/linked/escaped',b'BAD')]);check('symlink parent rejected',run()!=0 and not (outside/'escaped').exists())
pack([('rando/nul\x00suffix',b'BAD')]);check('embedded NUL rejected',run()!=0 and not (data/'rando/nul').exists())
(mount/'sce_sys/param.json').write_text('{"titleId": "PPSA91762"}')
pack([('rando/another',b'BAD')]);check('main title mount rejected before writes',run()!=0 and not (data/'rando/another').exists())
record={'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'tests':results,'passed':True,'scope':'native host initializer; no game or console test'}
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
