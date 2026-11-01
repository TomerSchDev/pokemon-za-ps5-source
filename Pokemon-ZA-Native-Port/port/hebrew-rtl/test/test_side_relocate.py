"""Synthetic safety checks for the actual native read-only asset relocation."""
import json,struct,subprocess,sys
from pathlib import Path

out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=False)
source=Path(__file__).resolve().parents[2]/'main-install/relocate_side_mods.c'
results=[]
def case(name,change=None):
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
    save=data/'rando/current';save.write_bytes(b'NEWER SAVE MUST SURVIVE');before=save.stat().st_mtime_ns
    if change:change(app,mount,data,ro)
    binary=base/'relocate'
    subprocess.run(['cc','-O2','-Wall',f'-DSIDE_APP="{app}"',f'-DSIDE_DATA="{data}"',f'-DSIDE_MOUNT="{mount}"',f'-DSIDE_LINK_TARGET="{ro}"',str(source),'-o',str(binary)],check=True)
    r=subprocess.run([str(binary)],capture_output=True,text=True,timeout=10)
    assert save.read_bytes()==b'NEWER SAVE MUST SURVIVE' and save.stat().st_mtime_ns==before
    return base,data,ro,binary,r

b,d,ro,exe,r=case('valid');assert r.returncode==0 and (d/'mods/0-hebrew').is_symlink()
assert (d/'mods/0-hebrew/romfs/a.bin').read_bytes()==b'synthetic asset A'
assert not (d/'mods/_before-readonly-hebrew/romfs/a.bin').exists()
assert subprocess.run([str(exe)],capture_output=True,timeout=10).returncode==0
results.append('verified relocation, unchanged newer save, and idempotent retry')
for name,change in [
    ('changed-current',lambda a,m,d,r:(d/'mods/0-hebrew/romfs/b.bin').write_bytes(b'different current')),
    ('changed-target',lambda a,m,d,r:(r/'romfs/b.bin').write_bytes(b'different target')),
    ('wrong-title',lambda a,m,d,r:(m/'sce_sys/param.json').write_text('{"titleId": "PPSA91762"}')),
]:
    b,d,ro,exe,r=case(name,change);assert r.returncode!=0 and not (d/'mods/0-hebrew').is_symlink()
    assert (d/'mods/0-hebrew/romfs/a.bin').read_bytes()==b'synthetic asset A'
    results.append(name+' refuses before removing any original file')
b,d,ro,exe,r=case('unknown-retained',lambda a,m,d,r:(d/'mods/0-hebrew/private-extra').write_bytes(b'keep'))
assert r.returncode==0 and (d/'mods/_before-readonly-hebrew/private-extra').read_bytes()==b'keep'
results.append('unknown extra file retained in the renamed directory')
print(json.dumps({'passed':True,'tests':results,'scope':'synthetic copied assets only; no game or console'}))
