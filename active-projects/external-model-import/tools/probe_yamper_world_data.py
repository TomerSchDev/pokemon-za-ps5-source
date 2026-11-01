"""PC diagnostic: stage absent world behavior/collision data for species and model IDs."""
from pathlib import Path
import argparse,json,hashlib,os,re
from build_smoliv_model import Z,encode_checked
from integrate_model_assets import atomic
import za_folder

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--national',type=int)
    parser.add_argument('--donor',type=int)
    parser.add_argument('--inspect-only',action='store_true')
    parser.add_argument('--mods-root',type=Path)
    parser.add_argument('--register-collision',action='store_true')
    a=parser.parse_args()
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    za_folder.GAME=str(lab/'hebrew-lab/qa-game-reference-20261030/romfs.bin');g=za_folder.game();changes=[]
    if a.inspect_only:
        assert a.national and a.donor
        selected=next(t for t in json.loads((work/'selection.json').read_text(encoding='utf-8-sig'))['targets'] if t['national']==a.national)
        catalog=Z.catalog_schema().decode(g.read(Z.CATALOG))['table']
        donor=next(t for t in catalog if t['species_info'].get('species')==a.donor and not t['species_info'].get('form',0) and not t['species_info'].get('gender',0))
        source_id=int(re.search(r'pm(\d+)',donor['model_path'])[1]);target_id=int(re.search(r'pm(\d+)',selected['model']['model_path'])[1])
        result=[]
        for base in (Z.BEHAVIOR,'world/ik_data/pokemon/collision/pokemon_collision_unique_data/'):
            for species in sorted({a.donor,source_id,a.national,target_id}):
                p=base+f'{species:04d}_00_00.bin'
                result.append(dict(path=p,exists=g.has(p)))
        registry_stem='world/ik_data/pokemon/pokemon_unique_path_data/pokemon_collision_unique_data'
        registry={ext:g.has(registry_stem+ext) for ext in ('','.bin','.bfbs','.json')}
        if registry['.bfbs'] and registry['.bin']:
            sc=Z.bfbs_schema(registry_stem);tree=sc.decode(g.read(registry_stem+'.bin'))
            registry.update(field_count=len(sc.tables[sc.root]),present_fields=len(tree),
                            nonempty=sum(bool(v) for v in tree.values()),
                            relevant={k:v for k,v in tree.items() if v in {f'{n:04d}_00_00' for n in (a.national,target_id,a.donor,source_id)}},
                            empty_slots=[k for _,k,_ in sc.tables[sc.root] if not tree.get(k)][:6])
        print(json.dumps(dict(read_only=True,donor_national=a.donor,donor_resource=source_id,target_national=a.national,target_resource=target_id,files=result,registry=registry)),flush=True)
        return
    pairs=((835,172),(2835,172),(836,135),(2836,135))
    if a.national or a.donor:
        assert a.national and a.donor and a.mods_root
        destination=a.mods_root.resolve();assert destination.is_relative_to(work.resolve()) and not destination.exists()
        selected=next(t for t in json.loads((work/'selection.json').read_text(encoding='utf-8-sig'))['targets'] if t['national']==a.national)
        resource=int(re.search(r'pm(\d+)',selected['model']['model_path'])[1])
        pairs=tuple((target,a.donor) for target in sorted({a.national,resource}))
        destination.mkdir()
        import _winapi
        for name in ('00-icon-identity-r2','all-models'):
            source=(work/'mods'/name).resolve();_winapi.CreateJunction(str(source),str(destination/name))
            assert os.path.samefile(source,destination/name)
        overlay=destination/'03-species-world-data-r1/romfs'
    else:overlay=work/'mods/03-yamper-world-data-r2/romfs'
    for base in (Z.BEHAVIOR,'world/ik_data/pokemon/collision/pokemon_collision_unique_data/'):
        for target,donor in pairs:
            for ext in ('.bin','.bfbs'):
                src=base+f'{donor:04d}_00_00'+ext;dst=base+f'{target:04d}_00_00'+ext;assert not g.has(dst)
                data=g.read(src);atomic(overlay/dst,data);changes.append(dict(source=src,target=dst,sha256=hashlib.sha256(data).hexdigest()))
    if a.register_collision:
        assert a.national and a.mods_root
        stem='world/ik_data/pokemon/pokemon_unique_path_data/pokemon_collision_unique_data'
        sc=Z.bfbs_schema(stem);raw=g.read(stem+'.bin');tree=sc.decode(raw);before=dict(tree)
        slots=[k for _,k,_ in sc.tables[sc.root] if not tree.get(k)]
        targets=[f'{target:04d}_00_00' for target,_ in pairs]
        assert len(slots)>=len(targets) and not set(targets).intersection(tree.values())
        for key,value in zip(slots,targets):tree[key]=value
        assert all(tree[k]==v for k,v in before.items() if v)
        data=encode_checked(sc,tree);atomic(overlay/(stem+'.bin'),data)
        changes.append(dict(source=stem+'.bin',target=stem+'.bin',source_sha256=hashlib.sha256(raw).hexdigest(),
                            sha256=hashlib.sha256(data).hexdigest(),added_registry_entries=dict(zip(slots,targets))))
    report=dict(PC_only=True,diagnostic_only=True,QA_pass_allowed=False,files=changes)
    report_path=a.mods_root/'world-data-probe.json' if a.mods_root else work/'yamper-world-data-probe-r2.json'
    atomic(report_path,json.dumps(report,indent=1).encode())
    print(json.dumps(dict(overlay=str(overlay),files=len(changes))),flush=True)

if __name__=='__main__':main()
