"""Retry explicit schema-adaptation failures and disable unsupported legacy alpha layer."""
from pathlib import Path
import argparse
import json
import struct
from integrate_model_assets import ROOT,Z,build_one,atomic
from build_smoliv_model import schema,encode_checked


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('build',type=Path);args=p.parse_args()
    file=args.build/'integration.json';data=json.loads(file.read_text());fixed=[];errors=[]
    if data['errors']:
        bank=json.loads((ROOT/'source-bank/source-bank.json').read_text())['models']
        donors=json.loads((ROOT/'evidence/native-control-donors.json').read_text())['donors']
        personals=Z.personal_schema().decode(Z.read(Z.PERSONAL))['Table']
        records=[]
        for game in ('violet','legacy'):records+=json.loads((ROOT/f'build/{game}-model-candidates-r1/conversion.json').read_text())['models']
        for error in data['errors']:
            rec=next(r for r in records if r['target_folder']==error['folder'])
            game=rec.get('source','violet')
            b=next(b for b in bank if b['source']==game and (b.get('folder')==rec.get('source_folder') if game=='violet' else any(row['model']==rec['source_model'] for row in b['catalogue_entries'])))
            row=b['catalogue_entries'][0] if game=='violet' else next(row for row in b['catalogue_entries'] if row['model']==rec['source_model'])
            personal=next(r for r in personals if r['Info'].get('SpeciesNational')==rec['national_species'] and r['Info'].get('Form',0)==row['info'].get('form',0))
            try:
                item=build_one(rec,b,personal,donors,args.build);item['gender']=row['info'].get('gender',0)
                item['catalog']['species_info']={k:v for k,v in dict(species=item['internal'],form=item['form'],gender=item['gender']).items() if v}
                data['models'].append(item);fixed.append(error)
            except Exception as ex:errors.append(dict(**{k:v for k,v in error.items() if k!='error'},error=str(ex)))
    materials=[];s=schema('trmtr')
    for m in data['models']:
        if m['source']=='violet':continue
        target=args.build/'all-models/romfs/ik_pokemon/data'/m['folder']
        for path in target.glob('*.trmtr'):
            candidate=ROOT/'build/legacy-model-candidates-r1/romfs/ik_pokemon/data'/m['folder']/path.name
            value=s.decode(candidate.read_bytes());count=0
            for material in value['materials']:
                for parameter in material.get('float_parameter',[]):
                    if parameter['float_name']=='LayerMaskScale4' and m['source']=='sword':
                        parameter['float_value']=0.0;count+=1
                if m['source']=='arceus':
                    # CategoryLabel is game-specific: LA uses 2 for Pokemon;
                    # ZA uses 6. Reusing 2 selects the wrong deferred lighting.
                    for parameter in material.get('int_parameter',[]):
                        if parameter['int_name']=='CategoryLabel':parameter['int_value']=6;count+=1
            if count:
                atomic(path,encode_checked(s,value));materials.append(dict(file=path.relative_to(args.build).as_posix(),materials=count))
        m['legacy_unused_alpha_layer_disabled']=m['source']=='sword'
        if m['source']=='arceus':
            m['legacy_linear_palette_to_srgb']=False;m['legacy_AO_neutral_fallback']=False
            m['native_ZA_material_category']=6
    data['errors']=errors
    data['summary'].update(models=len(data['models']),species=len({m['national'] for m in data['models']}),errors=len(errors))
    atomic(file,json.dumps(data,indent=1).encode())
    report=dict(retried=fixed,remaining_errors=errors,legacy_material_files=materials,
        reason='Sword unused alpha layer disabled. Arceus CategoryLabel 2 maps to native ZA Pokemon deferred lighting category 6; original source palette, AO and layer masks retained.')
    atomic(args.build/'bridge-repairs.json',json.dumps(report,indent=1).encode())
    print(json.dumps(dict(retried=len(fixed),remaining_errors=errors,legacy_material_files=len(materials))),flush=True)


if __name__=='__main__':main()
