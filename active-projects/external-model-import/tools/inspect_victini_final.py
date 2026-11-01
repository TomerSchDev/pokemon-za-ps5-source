"""Read-only diagnosis. Does not patch a game, save or runtime cache."""
import hashlib,json,shutil,struct
from pathlib import Path
from build_smoliv_model import ROOT,schema,Z
from source_archives import FB
import nas_game_cache

qa=ROOT/'qa/all-pokemon-20261030-r2/victini-20261031-r1'
folder=ROOT/'build/all-species-r1/all-models/romfs/ik_pokemon/data/pm2494/pm2494_00_00'
integration=json.loads((ROOT/'build/all-species-r1/integration.json').read_text(encoding='utf-8'))
rec=next(x for x in integration['models'] if x['national']==494)
meshes=schema('trmsh').decode((folder/'pm2494_00.trmsh').read_bytes())['meshes']
materials=schema('trmtr').decode((folder/'pm2494_00.trmtr').read_bytes())['materials']
def cfg(raw):
 f=FB(raw);fields=f.table(f.u32(0))
 return {'field_count':len(fields),'float_fields':{str(i):struct.unpack_from('<f',raw,p)[0] for i,p in enumerate(fields) if p and 1<=i<=12}}
nas_game_cache.install()
catalog=Z.catalog_schema().decode(Z.read(Z.CATALOG))['table']
donor=next(x for x in catalog if x['species_info'].get('species')==1004 and not x['species_info'].get('form'))
donor_path='ik_pokemon/data/'+donor['config_path']
native=Z.read(donor_path);imported=(folder/'pm2494_00_00.trpokecfg').read_bytes()
diagnostic=json.loads((qa/'geometry-rig-diagnostic.json').read_text(encoding='utf-8'))
idle=[x for x in rec['animation_mapping'] if x['target'] in ('00000_defaultwait01_loop','00400_attack01','00450_rangeattack01')]
result={
 'species':'Victini','national':494,'model':rec['catalog']['model_path'],
 'scope':'Read-only inspection of existing PC capture, current converted assets, source geometry, native donor config and converter code. No new runtime A/B test and no deployed fix.',
 'existing_capture_run':'pc-wide-import-005-r1-s02','frame':4503,
 'observed':['Body is small and close to lower edge of Summary panel.','Large black stretched polygons appear above head.','Party icon is inherited rather than authentic (integration icon_authentic=false).'],
 'config':{'donor_species':1004,'donor_config':donor_path,'byte_identical_to_donor':imported==native,'values':cfg(imported)},
 'source_meshes':diagnostic['source_meshes'],
 'converted_meshes':[{'name':m.get('mesh_name'),'materials':m.get('materials'),'bounds':m.get('bounds')} for m in meshes],
 'converted_materials':[{'name':m['name'],'alpha_type':m.get('alpha_type'),'shaders':m.get('shaders'),'textures':m.get('textures')} for m in materials],
 'likely_causes':[
  {'issue':'Black stretched geometry','candidate':'Source AuraEf1 mesh remains active under a generic body shader. Legacy effect visibility/material event tracks are omitted by sword_animation.convert_bone_animation. Aura UV1 is also omitted by sword_geometry.mesh_buffers.','confidence':'Strong candidate, not proven by runtime isolation. BodyAVco overlays also require validation.'},
  {'issue':'Summary framing','candidate':'The full 24-field configuration is borrowed from species 1004, with vertical origin -1.973 and center offset 2.208 despite source body height about 0.399 m.','confidence':'Donor mismatch confirmed; exact field-to-camera effect requires runtime test. Do not infer wrong world scale from Summary alone.'}],
 'animation':{'source_clip_count':rec['source_animations'],'selected_mappings':idle,'material_events_converted':False,'existing_idle_pixel_delta':3306,'combat_execution_verified':False},
 'not_supported_by_evidence':['No missing main body mesh found.','No non-unit bind-pose bone scales or nonzero pivots found.'],
 'proposed_next_test':['Isolate AuraEf1 mesh by removing matching TRMSH mesh and TRMBF buffer together in a separate QA overlay.','Compare original and effect-free captures with unchanged framing first.','Then tune only known Summary config scalars using append/preserve semantics, retaining all 24 fields.','Verify attack animations separately; available clip mapping does not establish functioning combat.'],
 'fix_applied':False,'console_touched':False,'original_build_modified':False}
local=Path(__file__).resolve().parents[3]/'pc-check-results/victini-20261031-r1'
local.mkdir(parents=True,exist_ok=True)
report=local/'victini-diagnostic-20261031-r1.json'
report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
capture=local/'victini-existing-pc-capture-20261031-r1.png'
shutil.copyfile(ROOT/'qa/runs/pc-wide-import-005-r1-s02/build/frames/frame_04503.png',capture)
dest=ROOT.parents[3]/'Victini-Check-20261031-r1'
dest.mkdir(parents=True,exist_ok=True)
for p in (report,capture):
 target=dest/p.name
 if target.exists():assert target.read_bytes()==p.read_bytes()
 else:shutil.copyfile(p,target)
 assert hashlib.sha256(target.read_bytes()).digest()==hashlib.sha256(p.read_bytes()).digest()
print(json.dumps({'report':str(report),'capture':str(capture),'NAS':str(dest),'config':result['config'],'meshes':len(meshes),'materials':[{k:v for k,v in m.items() if k in ('name','alpha_type','shaders')} for m in result['converted_materials']]},ensure_ascii=False))
