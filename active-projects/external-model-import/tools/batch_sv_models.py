"""Produce ZA geometry/material packages for every available missing-species SV model.

Each package has a unique pm2xxx/pm3xxx namespace. Existing ZA model folders are never replaced.
Models remain candidates until ZA animation/gameplay configuration and runtime QA are complete.
"""
import collections
import hashlib
import json
from pathlib import Path
import sys
from build_smoliv_model import schema,encode_checked,material_bridge,DONOR,STEM

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=Path(sys.argv[1])
    out.mkdir(parents=True,exist_ok=True)
    checkpoints=out/'progress'
    checkpoints.mkdir(exist_ok=True)
    converter_hash=hashlib.sha256(Path(__file__).read_bytes()+(ROOT/'tools/build_smoliv_model.py').read_bytes()).hexdigest()
    bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))
    model_schema=schema('trmdl')
    material_schema=schema('trmtr')
    native=material_schema.decode((DONOR/(STEM+'.trmtr')).read_bytes())['materials']
    # Reuse the neutral texture verified in the real game render pilot.
    neutral=ROOT/'build/smoliv-real-r6/mods/smoliv-real-model/romfs/ik_pokemon/data/pm0935/pm0935_00_00'
    report=[]
    for i,entry in enumerate([r for r in bank['models'] if r['source']=='violet'],1):
        folder=entry['folder']
        checkpoint=checkpoints/(folder.replace('/','--')+'.json')
        if checkpoint.exists():
            saved=json.loads(checkpoint.read_text(encoding='utf-8'))
            if saved.get('converter_sha256')==converter_hash and all((out/p).is_file() and hashlib.sha256((out/p).read_bytes()).hexdigest()==h for p,h in saved['record'].get('sha256',{}).items()):
                report.append(saved['record'])
                continue
        old_pm,old_stem=folder.split('/')
        species=entry['species'][0]
        new_pm=f'pm{2000+species:04d}'
        stem=old_stem.replace(old_pm,new_pm)
        source=ROOT/'source-bank/violet/pokemon/data'/folder
        target=out/'romfs/ik_pokemon/data'/new_pm/stem
        rec=dict(national_species=species,source_folder=folder,target_folder=f'{new_pm}/{stem}',
                 source_catalogue=entry['catalogue_entries'],status='candidate',runtime_tested=False,
                 gameplay_configuration_complete=False,files=0,warnings=[])
        try:
            target.mkdir(parents=True,exist_ok=True)
            for file in source.rglob('*'):
                if not file.is_file() or file.suffix=='.trmtr':
                    continue
                dest=target/str(file.relative_to(source)).replace(old_pm,new_pm)
                dest.parent.mkdir(parents=True,exist_ok=True)
                data=file.read_bytes().replace(old_pm.encode(),new_pm.encode())
                if file.suffix=='.trmdl':
                    value=model_schema.decode(data)
                    value['unk9']=3
                    data=encode_checked(model_schema,value)
                if not dest.exists() or dest.read_bytes()!=data:
                    dest.write_bytes(data)
            rec['materials']={}
            for file in source.glob('*.trmtr'):
                value=material_schema.decode(file.read_bytes())
                converted,mapping=material_bridge(value,native,old_pm,new_pm,stem)
                # A material with no source normal map needs an explicit native fallback.
                for material in converted['materials']:
                    for texture in material.get('textures',[]):
                        name=texture['texture_file']
                        if name.startswith('../') or (target/name).is_file() or name in (stem+'_white_msk.bntx',stem+'_black_msk.bntx'):
                            continue
                        original=DONOR/name
                        if not original.is_file():
                            raise ValueError('Unresolved material texture: '+name)
                        fallback=stem+'_native_'+original.name
                        (target/fallback).write_bytes(original.read_bytes())
                        texture['texture_file']=fallback
                        rec['warnings'].append('Native texture fallback: '+fallback)
                (target/file.name.replace(old_pm,new_pm)).write_bytes(encode_checked(material_schema,converted))
                rec['materials'][file.name]=mapping
            for suffix in ('_white_msk.bntx','_black_msk.bntx'):
                data=(neutral/(STEM+suffix)).read_bytes().replace(STEM.encode(),stem.encode())
                # Model stems are equal-length in the pmNNNN_FF_VV naming system.
                if len(stem)!=len(STEM):
                    raise ValueError('Unexpected variant stem length')
                (target/(stem+suffix)).write_bytes(data)
            rec['files']=sum(f.is_file() for f in target.rglob('*'))
            rec['sha256']={str(f.relative_to(out)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in target.rglob('*') if f.is_file()}
            rec['status']='geometry_materials_converted'
            rec['warnings']+=['Source animation controllers are retained for future ZA state-machine adaptation; no species is activated by this package.']
        except Exception as ex:
            rec['status']='conversion_failed'
            rec['error']=str(ex)
        report.append(rec)
        temp=checkpoint.with_suffix('.tmp')
        temp.write_text(json.dumps(dict(converter_sha256=converter_hash,record=rec)),encoding='utf-8')
        temp.replace(checkpoint)
        if i%20==0:
            print('CONVERT',i,'/',616,'complete',sum(r['status']=='geometry_materials_converted' for r in report),'failed',sum(r['status']=='conversion_failed' for r in report),flush=True)
    summary=dict(models=len(report),status=dict(collections.Counter(r['status'] for r in report)),
                 converted_species=len({r['national_species'] for r in report if r['status']=='geometry_materials_converted'}),
                 species_activated=0,installable_gameplay_mod=False)
    (out/'conversion.json').write_text(json.dumps(dict(summary=summary,models=report),indent=1),encoding='utf-8')
    print(json.dumps(summary,indent=2),flush=True)


if __name__=='__main__':
    main()
