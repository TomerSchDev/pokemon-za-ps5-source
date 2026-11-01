"""Read-only discovery of field-move obstacle rules in the pinned 2.0.2 data."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from inspect_game import Game,fnv,sha
from nso import Nso
from reflection_reader import Schema
out=ROOT/'evidence/randomizer-field-move-audit';out.mkdir(exist_ok=True)
game=PC/'update-2.0.2-20261025/game'
g=Game(game/'romfs.bin',PC/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
n=Nso(game/'exefs/main');matches=[];paths=set()
for m in re.finditer(rb'[ -~]{6,}',n.image):
    text=m.group().decode()
    if not re.search(r'waza|gimmick|obstruct|break|crush|burn|field.*move',text,re.I):continue
    matches.append({'offset':m.start(),'text':text})
    if '/' in text and re.fullmatch(r'[\w/.-]+',text) and len(text)<240:
        if text.endswith(('.bin','.bfbs')):paths.add(text)
        elif text.startswith(('world/','ik_event/','pml/')):
            paths.update(text+s for s in ('.bin','.bfbs'))
paths|={'world/exl/item_data/item_data/item_data.bin'}
config=out/'decoded/field_data_config_array.json'
if config.exists():
    for row in json.loads(config.read_text())['values']:
        info=row['info']
        if info['type'] in (9,10,11,12,25,38,41):paths.add(info['basePath']+'.bin')
dump=PC.parent/'pknx/pkNX.WinForms/Dumping/Gen9a/GameDumper9a.cs'
for path in re.findall(r'"([^"\r\n]+\.(?:bin|bfbs))"',dump.read_text(encoding='utf-8-sig')):
    if re.search(r'waza|gimmick|bullet|field_data_config|personal_array|pokemon_spawner|encount_data',path,re.I):paths.add(path)
paths|={p.rsplit('.',1)[0]+ext for p in list(paths) for ext in ('.bin','.bfbs')}
found=[]
for path in sorted(paths):
    if path in g.entries:raw=g.read(path)
    elif f'{fnv(path):016x}' in g.fileindex:raw=g.file(path)
    else:continue
    if len(raw)>8<<20:continue
    target=out/'extracted'/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
    found.append({'path':path,'bytes':len(raw),'sha256':sha(raw)})
(out/'strings.json').write_text(json.dumps(matches,indent=2),encoding='utf-8')
for row in found:
    if not row['path'].endswith('.bfbs'):continue
    path=out/'extracted'/row['path'];binary=path.with_suffix('.bin')
    try:
        schema=Schema(path.read_bytes());dest=out/'decoded'/path.stem;dest.parent.mkdir(exist_ok=True)
        dest.with_suffix('.schema.json').write_text(json.dumps({'root':schema.root,'objects':schema.objects,'enums':schema.enums},indent=2),encoding='utf-8')
        if binary.exists():
            dest.with_suffix('.json').write_text(json.dumps(schema.decode(binary.read_bytes()),indent=2),encoding='utf-8')
            row['decoded']=str(dest.with_suffix('.json').relative_to(out))
    except Exception as e:row['decode_error']=str(e)
(out/'inventory.json').write_text(json.dumps({'build_id':n.build_id,'files':found},indent=2),encoding='utf-8')
print(json.dumps({'matches':len(matches),'candidates':len(paths),'files':found},indent=2))
