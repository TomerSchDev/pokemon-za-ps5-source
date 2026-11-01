"""Publish the visually reviewed Victini stage 4 patch and exact PC evidence."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,zipfile
from run_pc_gallery import ROOT,QA,WORK

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def copy(source,target):
 target.parent.mkdir(parents=True,exist_ok=True)
 if target.exists():assert digest(target)==digest(source),str(target)
 else:shutil.copyfile(source,target)
 assert digest(target)==digest(source)

def main():
 run=ROOT/'qa/runs/pc-victini-repair-20261031-r4'
 record=json.loads((run/'run.json').read_text(encoding='utf-8'))
 result=json.loads((run/'gallery-results.json').read_text(encoding='utf-8'))
 row=result['targets'][0]
 assert record['canonical_model_and_game_data_on_NAS'] and record['terminated_after_requested_captures']
 assert not result['crash_lines'] and row['model_resource_requested'] and row['summary_header_matches']
 assert row['body_pixels_changed_gt10']>100 and row['pixels_different_from_empty_panel']>500
 assert all((run/'build/frames'/('frame_%05d.png'%i)).is_file() for i in (2403,2422,2440))
 local=Path(__file__).resolve().parents[3]/'pc-check-results/victini-repair-20261031-r1'
 local.mkdir(exist_ok=True)
 source=QA/'victini-repair-20261031-r1/stage4/romfs'
 files=sorted(p for p in source.rglob('*') if p.is_file());assert len(files)==7
 hashes={p.relative_to(source).as_posix():digest(p) for p in files}
 checks=[]
 for i in (1,2,3,4):
  r=json.loads((ROOT/('qa/runs/pc-victini-repair-20261031-r%d/gallery-results.json'%i)).read_text())
  checks.append({'stage':i,'run':r['run'],'visual_status':'rejected_color_experiment' if i==3 else 'reviewed','crash_lines':r['crash_lines'],'motion_pixels_gt10':r['targets'][0]['body_pixels_changed_gt10']})
 report={
  'species':'Victini','national':494,'internal':494,'version':'20261031-r1',
  'scope':'PC Summary appearance and idle motion. Visually reviewed frames 2403, 2422, 2440 of stage 4.',
  'corrected_donor_identity':{'internal':1004,'national':936,'name':'Armarouge'},
  'changes':['Removed only the unsupported AuraEf1 FX mesh and its matching vertex/index buffer. The three original body meshes remain.','Adjusted Summary framing scalars using native Pikachu values; preserved unknown ZA config fields, skeleton, animation curves and world size scalars.','Disabled inherited color-mask layers, neutralized donor palette and hue controls, and preserved original 2x body U scale with unmodified Sword textures. The 1x UV color experiment was rejected.','Imported authentic Sword Victini icon, including its previously unsupported n filename suffix.'],
  'visual_review':{'black_stretched_polygons':'absent','framing':'centered and larger','colors':'reviewed against original body texture','authentic_icon':'visible','idle_motion':'detected'},
  'checks':checks,'patch_files':hashes,
  'limitations':['Requires the existing all-models experimental mod for ZA 2.0.2. Not a standalone species mod.','The legacy AuraEf1 mesh is disabled. Its conditional attack effect is not reimplemented.','Combat execution, attack effects, shiny appearance, world scale, collision and full animation set were not verified by these Summary tests.','Normal and shiny party icons currently share the normal source icon.'],
  'console_touched':False,'user_save_modified':False,'original_build_modified':False,
  'final_test_run':row,'game_archive_SHA_rechecked':False}
 report_path=local/'victini-repair-report-20261031-r1.json'
 assert not report_path.exists();report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 image=local/'victini-fixed-PC-20261031-r1.png';copy(run/'build/frames/frame_02403.png',image)
 copy(ROOT/'qa/runs/pc-wide-import-005-r1-s02/build/frames/frame_04503.png',local/'victini-before-PC-20261031-r1.png')
 readme=('Victini visual repair for the existing Pokemon ZA 2.0.2 all-models experimental mod.\n'
         'This is an additive patch, not a standalone mod. Extract mods/ alongside the existing mods folders.\n'
         'Validated in the isolated PC build only; no console deployment.\n'
         'Fixes idle FX debris, Summary framing, body materials and party icon.\n'
         'The unsupported legacy AuraEf1 mesh is disabled, not reimplemented. Combat and shiny were not tested.\n'
         'Do not replace a newer catalog from another mod without merging the Victini icon entry.\n')
 archive=local/'Victini-Visual-Repair-ZA-2.0.2-20261031-r1.zip';assert not archive.exists()
 with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
  for p in files:z.write(p,'mods/00-000-victini-repair/romfs/'+p.relative_to(source).as_posix())
  z.writestr('README.txt',readme);z.writestr('patch-files.json',json.dumps(hashes,indent=2))
 # Canonical validated overlay retained for future PC model tests.
 validated=QA/'victini-model-repairs-r1'
 for p in files:copy(p,validated/'romfs'/p.relative_to(source))
 copy(report_path,validated/report_path.name)
 (validated/'complete.json').write_text(json.dumps({'PC_Summary_validated':True,'version':'20261031-r1','files':hashes}),encoding='utf-8')
 destination=ROOT.parents[3]/'Victini-Repair-20261031-r1'
 for p in local.iterdir():
  if p.is_file():copy(p,destination/p.name)
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
 for name in ('prepare_victini_repair.py','run_victini_repair.py','inspect_victini_textures.py','import_source_icons.py','publish_victini_repair.py'):
  p=Path(__file__).with_name(name);target=ROOT/'tools'/name
  if target.exists() and digest(target)!=digest(p):
   copy(target,ROOT/'tools/pcqa-source-history'/stamp/name);target.unlink()
  copy(p,target)
 print(json.dumps({'local':str(local),'NAS':str(destination),'patch_files':len(files),'archive_bytes':archive.stat().st_size,'checks':checks},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
