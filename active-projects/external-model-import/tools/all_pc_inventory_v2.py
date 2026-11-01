"""Local-only, per-identity asset audit and motion-family correction overlay.

No archive rehash, NAS access, console connection, or source asset mutation.
"""
from pathlib import Path
import argparse,copy,json,collections,posixpath,re,sys,time,struct,traceback,os
from catalog_inventory import Z
from build_smoliv_model import schema,encode_checked,motion_match
from integrate_model_assets import read_motion_list,atomic
from register_species import key_catalog
from fbcodec import same,Schema
import za_folder
import nas_game_cache
nas_game_cache.install()

from storage_paths import data_root
ROOT=data_root()
QA=ROOT/'qa/all-pokemon-20261030-r2'
BUILD=ROOT/'build/all-species-r1'


class SkeletonAuditSchema(Schema):
 # Read-only audit: Z-A TransformNode extends SV with field 8. Do not
 # discard this unknown field when writing assets; this class never writes.
 def _table(self,d,p,name):
  if p%4:raise ValueError('Unaligned skeleton table')
  vt=p-struct.unpack_from('<i',d,p)[0]
  vlen,tlen=struct.unpack_from('<HH',d,vt)
  assert 0<=vt<len(d) and 4<=vlen and vt+vlen<=len(d) and p+tlen<=len(d),'Skeleton table bounds'
  offs=struct.unpack_from('<%dH'%((vlen-4)//2),d,vt+4)
  fields={fid:(fn,t) for fid,fn,t in self.tables[name]};out={}
  for fid,o in enumerate(offs):
   if not o:continue
   assert 4<=o<tlen,'Skeleton field offset'
   if fid not in fields:
    if name=='Titan.Model.TransformNode' and fid==8:
     self.extensions.add(name+':8');continue
    raise ValueError('Unknown skeleton field '+name+':'+str(fid))
   fn,t=fields[fid];out[fn]=self._value(d,p+o,t)
  return out

def main():
 QA.mkdir(parents=True,exist_ok=True)
 integration=json.loads((BUILD/'integration.json').read_text())
 models={tuple(m[k] for k in ('internal','form','gender')):m for m in integration['models']}
 ps=Z.personal_schema();personal=ps.decode((BUILD/'all-models/romfs'/Z.PERSONAL).read_bytes())['Table']
 original=ps.decode(Z.read(Z.PERSONAL))['Table']
 bykey={(p['Info']['SpeciesInternal'],p['Info'].get('Form',0)):p for p in personal}
 byinternal={p['Info']['SpeciesInternal']:p for p in personal if not p['Info'].get('Form',0)}
 cats=Z.catalog_schema().decode((BUILD/'all-models/romfs'/Z.CATALOG).read_bytes())['table']
 native_cats=Z.catalog_schema().decode(Z.read(Z.CATALOG))['table']
 native_bykey={key_catalog(r):r for r in native_cats}
 native_personal_preserved=all(same(a,b) for a,b in zip(original,personal) if a.get('IsPresentInGame'))
 assert native_personal_preserved
 g=za_folder.game();ts=schema('tracr','ZA/Flatbuffers')
 skl_schema=SkeletonAuditSchema.from_bfbs((ROOT/'ref/SV/Flatbuffers/model/trskl.bfbs').read_bytes())
 targets=[];errors=[];overlay_count=0;family_tracks=0;started=time.monotonic()
 # Names are supplied by PKHeX when producing the fixtures; identities come from game tables.
 for cat in cats:
  internal,form,gender=key_catalog(cat)
  if not internal:continue
  p=bykey.get((internal,form),byinternal.get(internal))
  if p is None or not p.get('IsPresentInGame'):continue
  national=p['Info']['SpeciesNational'];m=models.get((internal,form,gender))
  rec={'key':f'{national:04d}-{form:02d}-{gender}','national':national,'internal':internal,'form':form,'gender':gender,
       'source':m['source'] if m else 'native_ZA','imported':bool(m),'model_path':cat['model_path'],
       'catalog':cat,'asset_status':'pending','render_status':'pending','animation_status':'pending',
       'combat_status':'not_tested','evolution_status':'not_tested','issues':[]}
  targets.append(rec)
  try:
   if not m:assert same(cat,native_bykey[(internal,form,gender)])
   folder=posixpath.dirname(cat['model_path']);local=BUILD/'all-models/romfs/ik_pokemon/data'/folder
   local_names=set(os.listdir(local)) if m else set()
   def read_model(name):
    if m:return (local/name).read_bytes()
    return g.read('ik_pokemon/data/'+folder+'/'+name)
   def exists_model(name):
    if m:return name in local_names if '/' not in name and '\\' not in name else (local/name).is_file()
    return g.has('ik_pokemon/data/'+folder+'/'+name)
   for field in ('model_path','config_path','material_table_path'):
    if cat.get(field):assert exists_model(posixpath.basename(cat[field])),field
   stem=Path(cat['model_path']).stem
   skl_schema.extensions=set()
   skeleton=skl_schema.decode(read_model(stem+'.trskl'))
   rec['skeleton_schema_extensions_read_only']=sorted(skl_schema.extensions)
   rec['skeleton_nodes']=len(skeleton.get('transform_nodes',[]));rec['skeleton_bones']=len(skeleton.get('bones',[]))
   assert rec['skeleton_nodes']>0 and rec['skeleton_bones']>0,'Empty body skeleton'
   controller_name=posixpath.basename(folder)+'_base.tracr'
   tracks=ts.decode(read_model(controller_name))
   rec['controller_name']=controller_name
   for t in tracks['track_list']['list']:
    for resource in t['track_resource'].values():assert exists_model(resource['filename']),resource['filename']
   rec['animation_tracks']=len(tracks['track_list']['list'])
   assert rec['animation_tracks']>0,'No animation tracks'
   if m and m['source'] in ('violet','arceus'):
    sc=next((local/'source-controllers').glob('*.tracr'))
    source_tracks,_=read_motion_list(sc.read_bytes(),ts)
    available={t['track_name']:copy.deepcopy(t['track_resource']) for t in source_tracks}
    if m['source']=='arceus':
     oldpm=re.search(r'pm\d{4}',sc.name).group();newpm=folder.split('/')[0]
     for resources in available.values():
      for kind in ('animation','material'):
       if kind in resources:resources[kind]['filename']=resources[kind]['filename'].replace(oldpm,newpm)
    changes=[]
    for t in tracks['track_list']['list']:
     chosen,method=motion_match(t['track_name'],available)
     for kind in ('animation','material'):
      before=t['track_resource'].get(kind);after=available[chosen].get(kind)
      if before!=after:
       changes.append({'track':t['track_name'],'kind':kind,'old':before,'new':after,'selected':chosen})
       if after is None:t['track_resource'].pop(kind,None)
       else:t['track_resource'][kind]=copy.deepcopy(after)
      if after:assert exists_model(after['filename']),after['filename']
    rec['motion_family_repairs']=changes
    if changes:
     path=QA/'motion-overlay/romfs/ik_pokemon/data'/folder/controller_name
     atomic(path,encode_checked(ts,tracks));overlay_count+=1;family_tracks+=len(changes)
     rec['controller_overlay']=str(path.relative_to(QA))
   rec['asset_status']='passed';rec['animation_status']='resources_valid_runtime_pending'
  except Exception as e:
   rec['asset_status']='failed';rec['issues'].append(type(e).__name__+': '+str(e));rec['traceback']=traceback.format_exc();errors.append({'key':rec['key'],'error':type(e).__name__+': '+str(e)})
  if len(targets)%100==0:print(json.dumps({'audited':len(targets),'asset_failures':len(errors),'motion_overlays':overlay_count}),flush=True)
 present={p['Info']['SpeciesNational'] for p in personal if p.get('IsPresentInGame')}
 rendered_species={t['national'] for t in targets}
 assert present==rendered_species,sorted(present-rendered_species)
 report={'scope':'Every registered species and every registered model identity with a present personal record',
         'PC_only':True,'console_access':False,'data_storage':'NAS','archive_SHA_recheck':False,
         'species':len(present),'model_identities':len(targets),'imported_variants':sum(t['imported'] for t in targets),
         'native_catalog_entries_preserved':len(native_cats),'native_personal_rows_preserved':native_personal_preserved,
         'static_failures':errors,'motion_overlays':overlay_count,'motion_resource_selections_corrected':family_tracks,
         'source_build_unchanged':True,'tested_candidate':'all-species-r1 plus this QA motion-overlay',
         'previous_ZIP_contains_older_controllers':bool(overlay_count),'elapsed_seconds':round(time.monotonic()-started,1),
         'targets':targets,'unsupported_species_without_source':[19,20,21,22,165,166,276,277,300,301,327,351,366,367,368],
         'unsupported_species_requiring_engine_extension':list(range(1011,1026))}
 atomic(QA/'inventory.json',json.dumps(report,indent=1).encode())
 print(json.dumps({k:v for k,v in report.items() if k not in ('targets','static_failures')},indent=1),flush=True)

if __name__=='__main__':main()
