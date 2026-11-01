"""Read-only Victini source/converted geometry and rig diagnostics."""
from pathlib import Path
import collections,json,math,struct
from build_smoliv_model import ROOT,schema
from catalog_inventory import SWORD
from source_archives import Gfpak
from sword_geometry import SOURCE_FORMAT

qa=ROOT/'qa/all-pokemon-20261030-r2/victini-20261031-r1';qa.mkdir(exist_ok=True)
bank=json.loads((ROOT/'source-bank/source-bank.json').read_text(encoding='utf-8'))['models']
records=json.loads((ROOT/'build/legacy-model-candidates-r1/conversion.json').read_text(encoding='utf-8'))['models']
rec=next(r for r in records if r['national_species']==494)
entry=next(e for e in bank if e['source']=='sword' and any(c['model']==rec['source_model'] for c in e['catalogue_entries']))
model=schema('gfbmdl','SWSH/Flatbuffers/Model').decode(Gfpak(SWORD/entry['archive']).read_name(rec['source_model']))
folder=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data'/rec['target_folder']
stem=Path(rec['source_model']).stem.replace('pm0494','pm2494')
converted=schema('trskl').decode((folder/(stem+'.trskl')).read_bytes())
meshes=[]
for n,mesh in enumerate(model['mesh']):
    shape=model['shapes'][mesh.get('shapeID',0)];stride=0;layout=[]
    for a in shape['attributes']:
        fmt,size=SOURCE_FORMAT[a.get('format',0)];layout.append((a.get('type',0),fmt,a['count'],stride));stride+=size*a['count']
    raw=bytes(shape['vertices']);positions=[];joints=set();sums=[]
    for at in range(0,len(raw),stride):
        for kind,fmt,count,offset in layout:
            values=struct.unpack_from('<'+str(count)+fmt,raw,at+offset)
            if kind==0:positions.append(values[:3])
            if kind==11:joints.update(values)
            if kind==12:sums.append(sum(values))
    meshes.append({'index':n,'boneID':mesh.get('boneID',0),'shapeID':mesh.get('shapeID',0),'vertices':len(positions),'layout':layout,
                   'joint_range':(min(joints),max(joints)) if joints else None,
                   'weight_sum_range':(min(sums),max(sums)) if sums else None,
                   'position_bounds':[[min(p[i] for p in positions) for i in range(3)],[max(p[i] for p in positions) for i in range(3)]],
                   'materials':[model['materials'][p.get('materialId',0)]['name'] for p in shape['polygons']]})
result={'source_archive':str(SWORD/entry['archive']),'model':rec['source_model'],'boundingBox':model['boundingBox'],
        'source_bones':model['skeleton'],'source_meshes':meshes,'source_mesh_records':model['mesh'],'source_materials':model['materials'],'source_texture_files':model['textureFiles'],'converted_skeleton':converted,
        'converted_model':schema('trmdl').decode((folder/(stem+'.trmdl')).read_bytes())}
(qa/'geometry-rig-diagnostic.json').write_text(json.dumps(result,indent=1),encoding='utf-8')
print(json.dumps({'bounds':result['boundingBox'],'source_bone_count':len(model['skeleton']),'source_skin_bones':sum(bool(b.get('is_skin',1)) for b in model['skeleton']),
                  'nontrivial_bones':[dict(index=i,**b) for i,b in enumerate(model['skeleton']) if b.get('VecScale')!={'x':1.0,'y':1.0,'z':1.0} or any(abs(v)>1e-7 for k in ('VecScalePivot','VecRotatePivot') for v in b.get(k,{}).values())],
                  'segment_scale_compensation':dict(collections.Counter(b.get('segment_scale_compensate',False) for b in model['skeleton'])),
                  'meshes':meshes,
                  'material_controls':[{'name':m['name'],'shader':m['shader'],'active_flags':[f['flag_name'] for f in m.get('flags',[]) if f.get('flag_enable')],'texture_bindings':[{ 'sampler':t['sampler_name'],'file':model['textureFiles'][t.get('texture_index',0)]} for t in m.get('textures',[])]} for m in model['materials']]}),flush=True)
