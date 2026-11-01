"""Read-only learnset/evolution and boss-support inspection for pinned 1.0.0."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import struct

from inspect_game import Game, ROOT, fnv
from reflection_reader import Buffer, Schema


def main():
    raw = (ROOT/'private-tables/avalon/data/personal_array.bin').read_bytes()
    b = Buffer(raw)
    catalog = json.loads((ROOT/'personal-catalog.json').read_text())
    known = {(p['internal'], p['form']) for p in catalog}
    rows = []
    for entry in catalog:
        p = entry['offset']
        q = b.field(p,25)
        learnset = [dict(zip(['move','level','mastery_level'],struct.unpack_from('<Hbb', raw, v)))
                    for v in b.vector(q,4)] if q is not None else []
        q = b.field(p,21)
        evolutions = []
        for v in b.vector(q,16) if q is not None else []:
            level,method,arg,_,_,_,species,form = struct.unpack_from('<8H',raw,v)
            evolutions.append(dict(level=level,method=method,argument=arg,species=species,form=form,
                                   target_in_personal=(species,form) in known))
        rows.append(dict(species=entry['internal'],form=entry['form'],name=entry['name'],present=entry['present'],
                         learnset=learnset,evolutions=evolutions))
    (ROOT/'learnset-evolution-catalog.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    present = [r for r in rows if r['present'] and r['form']==0 and r['species']]
    summary = dict(personal_sha256=hashlib.sha256(raw).hexdigest(),
                   layout_source='pkNX d191cd0e5c05f2af81d9a41c1f1d82e6621b351a; fields 21/25, not the changed Dex field',
                   present_base_species=len(present),with_nonempty_learnset=sum(bool(r['learnset']) for r in present),
                   present_base_learnset_entries=sum(len(r['learnset']) for r in present),
                   unresolved_evolution_targets=[dict(source=r['species'],**e) for r in present for e in r['evolutions'] if not e['target_in_personal']],
                   example=next(r for r in present if r['species']==25),
                   status='External schema interpretation with structural/reference checks, not runtime validation')
    game = Game(ROOT.parents[2]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/game/romfs.bin',
                ROOT.parent/'release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
    files=[]
    for stem in ['param_ai/data/ai/trigger/condition_boss/condition_boss_array',
                 'param_ai/data/battle/personal_waza_param/personal_waza_param_array',
                 'world/ik_data/pokemon/ai/pokemon_species_cant_action/pokemon_species_cant_action_array',
                 'avalon/data/waza_array']:
        extracted={}
        for ext in ['.bin','.bfbs']:
            path=stem+ext
            if f'{fnv(path):016x}' not in game.fileindex:continue
            data=game.file(path); extracted[ext]=data
            dst=ROOT/'private-tables'/path;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(data)
            files.append(dict(path=path,size=len(data),sha256=hashlib.sha256(data).hexdigest()))
        if '.bfbs' in extracted:
            schema=Schema(extracted['.bfbs']);files[-1]['root_table']=schema.root
            files[-1]['object_types']=[o['name'] for o in schema.objects]
            (ROOT/'schema-json'/(Path(stem).name+'.json')).write_text(json.dumps(dict(root=schema.root,objects=schema.objects,enums=schema.enums),indent=2),encoding='utf-8')
            if '.bin' in extracted:
                decoded=schema.decode(extracted['.bin'])
                (ROOT/'decoded'/(Path(stem).name+'.json')).write_text(json.dumps(decoded,indent=2),encoding='utf-8')
                files[-1]['decoded']=True
    summary['supporting_files']=files
    (ROOT/'supporting-tables.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
