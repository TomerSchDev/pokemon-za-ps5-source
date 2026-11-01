"""Read native Z-A control templates and rank them without substituting donor geometry."""
from pathlib import Path
import json
import math
import struct
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parent/'pilot/tools'))
import za_schemas as Z
import za_folder
from build_smoliv_model import schema


def node_names(data):
    """Read only the stable name fields; retain native skeleton extensions untouched."""
    def u32(p):return struct.unpack_from('<I',data,p)[0]
    def fields(p):
        vt=p-struct.unpack_from('<i',data,p)[0]
        size=struct.unpack_from('<H',data,vt)[0]
        assert 4<=size<=256 and size%2==0
        return [p+o if (o:=struct.unpack_from('<H',data,vt+4+i*2)[0]) else None for i in range((size-4)//2)]
    root=fields(u32(0))
    pointer=root[1];vec=pointer+u32(pointer);count=u32(vec)
    assert count<10000
    names=[]
    for i in range(count):
        p=vec+4+i*4;p+=u32(p);field=fields(p)[0]
        if field:
            start=field+u32(field);length=u32(start)
            names.append(data[start+4:start+4+length].decode('utf-8').lower())
    return names


def make_index():
    game=za_folder.game()
    personal=Z.personal_schema().decode(Z.read(Z.PERSONAL))['Table']
    personals={(r['Info']['SpeciesInternal'],r['Info'].get('Form',0)):r for r in personal}
    catalog=Z.catalog_schema().decode(Z.read(Z.CATALOG))['table']
    movement=Z.bfbs_schema(Z.MOVEMENT_PARAM).decode(Z.read(Z.MOVEMENT_PARAM+'.bin'))['values']
    models=Z.bfbs_schema(Z.MODEL_PARAM).decode(Z.read(Z.MODEL_PARAM+'.bin'))['values']
    def lookup(values,key,form):
        return {(r[key],r.get(form,0),r.get('sex',0)):db for db in values for r in db['root']}
    move_by=lookup(movement,'devNo','formNo')
    model_by=lookup(models,'devId','formId')
    tracks_schema=schema('tracr','ZA/Flatbuffers')
    result=[];errors=[];seen=set()
    for entry in catalog:
        info=entry['species_info'];species=info.get('species',0)
        if not species or species in seen or info.get('form',0) or info.get('gender',0):continue
        seen.add(species)
        try:
            folder=str(Path(entry['model_path']).parent).replace('\\','/')
            stem=Path(entry['model_path']).stem
            base='ik_pokemon/data/'+folder+'/'
            tracks=tracks_schema.decode(game.read(base+stem+'_base.tracr'))
            key=(species,0,0)
            result.append(dict(species=species,personal=personals[(species,0)],catalog=entry,folder=folder,stem=stem,
                               bones=node_names(game.read(base+stem+'.trskl')),
                               track_names=[r['track_name'] for r in tracks['track_list']['list']],
                               movement=move_by[key],model_param=model_by[key]))
        except Exception as ex:
            errors.append(dict(species=species,error=str(ex)))
    return dict(donors=result,errors=errors)


def choose(personal,bones,donors):
    info=personal['Info'];types={personal.get('Type1',0),personal.get('Type2',0)}
    source_bones=set(bones)-{'root','origin','za_import_origin'}
    height=max(1,info.get('Height',1))
    def score(donor):
        target=donor['personal'];target_info=target['Info']
        movement=donor['movement']['root'][0]
        overlap=len(source_bones.intersection(donor['bones']))/max(1,len(source_bones))
        value=8*(target_info.get('BodyType')==info.get('BodyType'))+5*overlap
        value+=1.5*len(types.intersection({target.get('Type1',0),target.get('Type2',0)}))
        value-=abs(math.log(height/max(1,target_info.get('Height',1))))
        if 2 in types:value+=5 if movement.get('partnerMovementSky',0) else -10
        if 10 in types:value+=2 if movement.get('partnerMovementWater',0) else -3
        if info.get('SpeciesNational')==201:value+=25 if donor['species']==92 else 0
        return value
    return max(donors,key=lambda d:(score(d),-d['species']))


if __name__=='__main__':
    index=make_index()
    out=ROOT/'evidence/native-control-donors.json'
    out.write_text(json.dumps(index,indent=1),encoding='utf-8')
    print(json.dumps(dict(native_donors=len(index['donors']),errors=index['errors']),indent=2),flush=True)
