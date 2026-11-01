"""Prepare an isolated Victini PC repair; heavy canonical assets stay on NAS."""
import hashlib,json,os,shutil,struct,sys,time
from pathlib import Path
from build_smoliv_model import ROOT,schema,encode_checked,Z
from storage_paths import game_root
from catalog_inventory import SWORD
from source_archives import FB
from sword_geometry import canonical
from run_pc_gallery import QA,WORK

OUT=QA/'victini-repair-20261031-r1'
REL=Path('ik_pokemon/data/pm2494/pm2494_00_00')
SRC=ROOT/'build/all-species-r1/all-models/romfs'/REL
def write(path,data):
 path.parent.mkdir(parents=True,exist_ok=True)
 if path.exists():assert path.read_bytes()==data,str(path)
 else:path.write_bytes(data)
def setup():
 OUT.mkdir(exist_ok=True)
 targets=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
 victim=next(x for x in targets if x['key']=='0494-00-0')
 guards=[next(x for x in targets if x['national']==n and x['form']==0 and x['gender']==0) for n in (10,44,46,201,722,928)]
 write(OUT/'assets.json',json.dumps({'targets':[victim]+guards},indent=1).encode())
 write(OUT/'fixture.json',json.dumps({'mode':'box','targets':[victim],'body_frame_pairs':[[2403,2422,2440]]},indent=1).encode())
 # Verified canonical runtime, no hashing of the source game archive.
 runtime=WORK/'runtime';runtime.mkdir(parents=True,exist_ok=True)
 runtime_src=ROOT.parent/'pilot/runtime'
 assert hashlib.sha256((runtime_src/'lasrecomp.exe').read_bytes()).hexdigest()=='c74c94359182e6749b92eab82c066b6963dd33c25b0d0314e2a3667e1623e7fc'
 for p in runtime_src.iterdir():
  if p.is_file() and p.suffix.lower() in ('.dll','.exe'):shutil.copyfile(p,runtime/p.name)
 game=game_root()
 for name in ('romfs.bin','lasgame.dll'):
  p=game/name;shutil.copyfile(p,runtime/name);assert p.stat().st_size==(runtime/name).stat().st_size
 for name in ('exefs','aoc'):shutil.copytree(game/name,runtime/name,dirs_exist_ok=True)
 p=game/'romfs.bin';st=p.stat()
 write(runtime/'temporary-game-cache.json',json.dumps({'source':str(p),'size':st.st_size,'mtime_ns':st.st_mtime_ns}).encode())
 print('Temporary local runtime prepared; original game archive was not hashed.',flush=True)
 # Seed with a compatible prior shader cache, without changing canonical copy.
 candidates=[p/'cache' for p in (ROOT.parent/'pilot/runs').iterdir() if p.is_dir() and (p/'cache').is_dir()]
 candidates.sort(key=lambda p:p.stat().st_mtime,reverse=True)
 if candidates:
  shutil.copytree(candidates[0],WORK/'warm-cache',dirs_exist_ok=True)
  print('Warm cache: '+str(candidates[0]),flush=True)
 fixes=WORK/'render-fixes';fixes.mkdir(exist_ok=True)
 write(fixes/'verified-hashes.json',b'{}')
 import install_control_repairs
 install_control_repairs.main()
 certificate=fixes/'verified-hashes.json';hashes=json.loads(certificate.read_text())
 path=Path('mods/00-form-bindings/romfs/ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
 data=(QA/'form-bindings-r1/romfs/ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog').read_bytes()
 write(fixes/path,data);hashes[path.as_posix()]=hashlib.sha256(data).hexdigest()
 certificate.write_text(json.dumps(hashes),encoding='utf-8')
def repair(stage):
 stage=int(stage);assert stage in (1,2,3,4)
 msh=schema('trmsh').decode((SRC/'pm2494_00.trmsh').read_bytes())
 mbf=schema('trmbf').decode((SRC/'pm2494_00.trmbf').read_bytes())
 assert len(msh['meshes'])==len(mbf['buffers'])==4
 fx=[i for i,m in enumerate(msh['meshes']) if any(x['material_name']=='AuraEf1' for x in m['materials'])]
 assert fx==[3]
 msh['meshes']=[m for i,m in enumerate(msh['meshes']) if i not in fx]
 mbf['buffers']=[b for i,b in enumerate(mbf['buffers']) if i not in fx]
 payload={'pm2494_00.trmsh':encode_checked(schema('trmsh'),msh),'pm2494_00.trmbf':encode_checked(schema('trmbf'),mbf)}
 report={'stage':stage,'removed_meshes':fx,'preserved_body_meshes':[0,1,2],'skeleton_and_animations_unchanged':True,'source_build_unchanged':True,'console_touched':False}
 icon=SWORD/'bin/appli/icon_pokemon/poke_icon_0494_00n_n.bntx'
 icon_data=icon.read_bytes();assert icon_data[:4]==b'BNTX'
 for rare in (0,1):payload['icon/pm2494_00_00_00_%d.bntx'%rare]=icon_data
 report.update(icon_source=str(icon),icon_authentic=True,shiny_icon_distinct=False)
 if stage>=2:
  import nas_game_cache
  nas_game_cache.install()
  cat=Z.catalog_schema().decode(Z.read(Z.CATALOG))['table']
  choices=[]
  for n in (25,172,280,179):
   r=next(r for r in cat if r['species_info'].get('species')==n and not r['species_info'].get('form') and not r['species_info'].get('gender'))
   raw=Z.read('ik_pokemon/data/'+r['config_path']);f=FB(raw);fields=f.table(f.u32(0))
   choices.append({'species':n,'raw':raw,'values':{i:struct.unpack_from('<f',raw,p)[0] if p else 0.0 for i,p in enumerate(fields) if 1<=i<=12}})
  # Small grounded native model, same nominal height as Victini. Keep all unknown fields.
  reference=choices[0];raw=bytearray((SRC/'pm2494_00_00.trpokecfg').read_bytes());fb=FB(raw);fields=fb.table(fb.u32(0))
  changed={};root=fb.u32(0);vtable=root-struct.unpack_from('<i',raw,root)[0]
  for i in (3,4,5,6,8):
   old=struct.unpack_from('<f',raw,fields[i])[0] if fields[i] else 0.0
   new=reference['values'][i]
   if not fields[i]:
    raw.extend(b'\0'*((-len(raw))%4));position=len(raw);raw.extend(b'\0'*4)
    assert position-root<65536
    struct.pack_into('<H',raw,vtable+4+2*i,position-root)
    struct.pack_into('<H',raw,vtable+2,len(raw)-root)
   else:position=fields[i]
   struct.pack_into('<f',raw,position,new);changed[i]={'old':old,'new':new}
  check=FB(raw);assert len(check.table(check.u32(0)))==24
  # Opaque ZA-only fields retain their original locations and bytes.
  original=(SRC/'pm2494_00_00.trpokecfg').read_bytes()
  for i,p in enumerate(fields):
   if i>=13 and p:assert raw[p:p+12]==original[p:p+12]
  payload['pm2494_00_00.trpokecfg']=bytes(raw)
  report.update(config_reference_species=25,config_changed_scalar_fields=changed,config_opaque_fields_preserved=True,native_config_values=[{'species':x['species'],'values':x['values']} for x in choices])
 if stage>=3:
  material=schema('trmtr').decode((SRC/'pm2494_00.trmtr').read_bytes());changes=[]
  for m in material['materials']:
   if m['name']=='AuraEf1':continue
   for p in m.get('float_parameter',[]):
    if p['float_name'].startswith('LayerMaskScale'):
     changes.append({'material':m['name'],'parameter':p['float_name'],'old':p.get('float_value',0),'new':0.0})
     p['float_value']=0.0
   for t in m.get('textures',[]):
    if t['texture_name']=='LayerMaskMap':t['texture_file']='pm2494_00_00_black_msk.bntx'
   if m['name'] in ('BodyA00','BodyA01','BodyAVco'):
    for p in m.get('float4_parameter',[]):
     if p['color_name']=='UVScaleOffset':
      changes.append({'material':m['name'],'parameter':'UVScaleOffset','old':p['color_value'],'new':{'r':1.0,'g':1.0,'b':0.0,'a':0.0}})
      p['color_value']={'r':1.0,'g':1.0,'b':0.0,'a':0.0}
  if stage>=4:
   for m in material['materials']:
    if m['name']=='AuraEf1':continue
    for p in m.get('float_parameter',[]):
     if p['float_name'] in ('HueShiftBias','MidAreaHueOffset','DarkAreaHueOffset','HueShiftAreaValue','ShadowingShift'):p['float_value']=0.0
    for p in m.get('float4_parameter',[]):
     if p['color_name'].startswith('BaseColorLayer'):p['color_value']={'r':1.,'g':1.,'b':1.,'a':1.}
     if p['color_name'].startswith('ShadowingColorLayer'):p['color_value']={'r':.7,'g':.6332666,'b':.518,'a':1.}
     if p['color_name']=='UVScaleOffset' and m['name'] in ('BodyA00','BodyA01','BodyAVco'):p['color_value']={'r':2.,'g':1.,'b':0.,'a':0.}
   report.update(neutral_donor_color_and_hue_parameters=True,body_U_scale=2)
  material=canonical(material);changes=[]
  original_materials={m['name']:m for m in schema('trmtr').decode((SRC/'pm2494_00.trmtr').read_bytes())['materials']}
  for m in material['materials']:
   for field,key in (('float_parameter','float_name'),('float4_parameter','color_name')):
    before={p[key]:p for p in original_materials[m['name']].get(field,[])}
    for p in m.get(field,[]):
     if before.get(p[key])!=p:changes.append({'material':m['name'],'parameter':p[key],'old':before.get(p[key]),'new':p})
  payload['pm2494_00.trmtr']=encode_checked(schema('trmtr'),material)
  report.update(material_changes=changes,original_texture_bytes_unchanged=True,material_animations_not_converted=True)
 dest=OUT/('stage%d'%stage)/'romfs'/REL
 fixes=WORK/'render-fixes';certificate=fixes/'verified-hashes.json';hashes=json.loads(certificate.read_text())
 for name,data in payload.items():
  write(dest/name,data)
  rel=Path('mods/00-000-victini-repair/romfs')/REL/name;target=fixes/rel;target.parent.mkdir(parents=True,exist_ok=True)
  tmp=target.with_suffix(target.suffix+'.new');tmp.write_bytes(data);os.replace(tmp,target)
  hashes[rel.as_posix()]=hashlib.sha256(data).hexdigest()
 catalog_path=Path('ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
 catalog=Z.catalog_schema().decode((QA/'form-bindings-r1/romfs'/catalog_path).read_bytes())
 entry=next(r for r in catalog['table'] if r['species_info'].get('species')==494 and not r['species_info'].get('form'))
 entry['icon_path']='pm2494/pm2494_00_00/pm2494_00_00_00.bntx'
 data=encode_checked(Z.catalog_schema(),catalog)
 write(OUT/('stage%d'%stage)/'romfs'/catalog_path,data)
 rel=Path('mods/00-000-victini-repair/romfs')/catalog_path
 target=fixes/rel;target.parent.mkdir(parents=True,exist_ok=True)
 tmp=target.with_suffix('.new');tmp.write_bytes(data);os.replace(tmp,target)
 hashes[rel.as_posix()]=hashlib.sha256(data).hexdigest()
 certificate.write_text(json.dumps(hashes),encoding='utf-8')
 write(OUT/('stage%d.json'%stage),json.dumps(report,indent=1).encode())
 print(json.dumps(report),flush=True)
if __name__=='__main__':
 if sys.argv[1]=='setup':setup()
 else:repair(sys.argv[1])
