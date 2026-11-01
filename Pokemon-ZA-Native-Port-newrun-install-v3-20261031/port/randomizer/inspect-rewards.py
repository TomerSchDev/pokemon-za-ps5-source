"""Read-only reward-table discovery in the user's pinned local 2.0.2 game."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[2]
PC=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc')
sys.path.insert(0,str(PC/'randomizer-lab'))
from inspect_game import Game,fnv,sha
from reflection_reader import Schema
from nso import Nso

def main():
    out=ROOT/'evidence/randomizer-rewards-research';out.mkdir(exist_ok=True)
    game=PC/'update-2.0.2-20261025/game'
    g=Game(game/'romfs.bin',PC/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
    nso=Nso(game/'exefs/main')
    matches=[];paths=set()
    for m in re.finditer(rb'[ -~]{6,}',nso.image):
        s=m.group().decode()
        if re.search(r'research|reward|rankup|mable|momiji',s,re.I):
            matches.append({'offset':m.start(),'text':s})
            if re.fullmatch(r'[\w/.-]+\.(bin|bfbs)',s): paths.add(s)
            elif s.startswith('ik_event/bin/') and re.fullmatch(r'[\w/.-]+',s):
                for suffix in ('.bin','_global.bin','_array.bin'): paths.add(s+suffix)
    paths.add('ik_event/bin/za_reward_item_data/za_reward_item_data.bin')
    paths.add('world/exl/item_data/item_data/item_data.bin')
    paths.update(p for p in g.entries if re.search(r'research|reward|rankup|momiji',p,re.I) and p.endswith(('.bin','.bfbs')))
    paths|={p.rsplit('.',1)[0]+ext for p in list(paths) for ext in ('.bin','.bfbs')}
    found=[]
    for p in sorted(paths):
        if p in g.entries: data=g.read(p)
        elif f'{fnv(p):016x}' in g.fileindex: data=g.file(p)
        else: continue
        target=out/'extracted'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
        record={'path':p,'bytes':len(data),'sha256':sha(data)}
        if p.endswith('.bfbs'):
            try:
                schema=Schema(data)
                record['root']=schema.root
                schema_path=out/'schemas'/Path(p).with_suffix('.json').name
                schema_path.parent.mkdir(exist_ok=True)
                schema_path.write_text(json.dumps({'root':schema.root,'objects':schema.objects},indent=2),encoding='utf-8')
                binary=p[:-5]+'.bin'
                raw=g.read(binary) if binary in g.entries else g.file(binary)
                decoded=schema.decode(raw)
                dst=out/'decoded'/Path(binary).with_suffix('.json').name;dst.parent.mkdir(exist_ok=True)
                dst.write_text(json.dumps(decoded,indent=2),encoding='utf-8')
                record['decoded']=str(dst.relative_to(out))
            except Exception as e: record['error']=str(e)
        found.append(record)
    packs=[n for n in g.names if re.search(r'research|reward|rankup|momiji',n,re.I)]
    (out/'loose-paths.json').write_text(json.dumps(list(g.entries),indent=2),encoding='utf-8')
    (out/'pack-names.json').write_text(json.dumps(g.names,indent=2),encoding='utf-8')
    (out/'strings.json').write_text(json.dumps(matches,indent=2),encoding='utf-8')
    result={'build':nso.build_id,'game':str(game),'files':found,'candidate_packs':packs,'matching_strings':len(matches)}
    (out/'inventory.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
