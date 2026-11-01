from inspect_game import *
from reflection_reader import Schema
g=Game(ROOT.parents[2]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/game/romfs.bin',ROOT.parent/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
pknx=ROOT.parents[1]/'pknx'
sources=[pknx/'pkNX.WinForms/Dumping/Gen9a/GameDumper9a.cs',pknx/'pkNX.WinForms/Subforms/Gen9a/Map/Dumping/SpawnGlobalInfo.cs']
paths=set()
for p in sources:
    for s in re.findall(r'"([^"\r\n]+\.(?:bfbs|bin))"',p.read_text(encoding='utf-8-sig')):
        if re.search(r'trainer|encount|pokemon_data|pokemon_spawner|megaevo|personal_array',s):paths.add(s)
paths.update(['ik_event/bin/event_boss_battle_data/boss_btl_data_global.bin','ik_event/bin/event_trainer_battle_data/trainer_btl_data_global.bin'])
# Also test schema partners for binary tables, and data partners for schemas.
paths|={s.rsplit('.',1)[0]+ext for s in list(paths) for ext in ['.bin','.bfbs']}
extracted={};records=[]
for path in sorted(paths):
    h=f'{fnv(path):016x}'
    if h not in g.fileindex:continue
    r=g.fileindex[h][0];d=g.file(path);dst=ROOT/'private-tables'/path;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(d);extracted[path]=d
    records.append(dict(path=path,hash=h,size=len(d),sha256=sha(d),pack=r['pack'],prefix=d[:16].hex()))
for r in records:
    path=r['path']
    if not path.endswith('.bfbs'):continue
    try:
        s=Schema(extracted[path]);r['root_table']=s.root
        target=ROOT/'schema-json'/Path(path).name;target.parent.mkdir(exist_ok=True)
        target.with_suffix('.json').write_text(json.dumps(dict(root=s.root,objects=s.objects,enums=s.enums),indent=2))
        binary=path[:-5]+'.bin'
        if binary in extracted:
            decoded=s.decode(extracted[binary]);out=ROOT/'decoded'/Path(binary).name;out.parent.mkdir(exist_ok=True)
            out.with_suffix('.json').write_text(json.dumps(decoded,indent=2));r['decoded']=True
    except Exception as e:r['error']=repr(e)
(ROOT/'table-inventory.json').write_text(json.dumps(records,indent=2))
print(json.dumps([{k:v for k,v in r.items() if k in ['path','size','root_table','decoded','error']} for r in records],indent=2))
