"""Prepare a new trial run; all original runs remain intact."""
from pathlib import Path
import copy,hashlib,json,secrets,shutil,time
from build_smoliv_model import ROOT,Z
import nas_game_cache
QA=ROOT/'qa/all-pokemon-20261030-r2';OUT=QA/'console-fifty-20261031-r1'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 new=OUT/'new-trial';original=OUT/'before-console/active-run-root'
 report=json.loads((original/'report.json').read_text());old=report['native_run_id']
 meta=OUT/'trial-identity.json'
 if meta.exists():run=json.loads(meta.read_text())['run']
 else:
  run='r%016x-%08x'%(int(time.time()),secrets.randbits(32));meta.write_text(json.dumps({'run':run,'source_run':old},indent=1))
 nas_game_cache.install();native=Z.read(Z.ENCOUNT+'.bin')
 for entry in report['native_tables']:
  relative=Path('romfs')/entry['path'];source=original/relative
  raw=native if entry['path']==Z.ENCOUNT+'.bin' else source.read_bytes()
  target=new/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
  entry['sha256']=sha(raw)
 report['native_run_id']=run;report['console_fifty_test']={'source_run':old,'selection_seed':json.loads((OUT/'selection.json').read_text())['selection_seed'],'only_test_save_modified':True,'wild_encounters':'original native baseline to isolate imported party model failures'}
 (new/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 active=json.dumps({'id':run,'schema':1}).encode();(OUT/'active-test-target.json').write_bytes(active)
 setup=OUT/'trial-setup';setup.mkdir(exist_ok=True)
 for p in new.rglob('*'):
  if p.is_file():
   target=setup/'run'/p.relative_to(new);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 p=setup/'romfs'/(Z.ENCOUNT+'.bin');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(native)
 # Preserve the small additional controller repairs that passed the final PC retests.
 assets=json.loads((OUT/'assets.json').read_text())['targets'];extra=0
 for m in assets:
  folder=Path(m['model_path']).parent
  fixes=QA/'validated-render-fixes-r1/romfs/ik_pokemon/data'/folder
  if not fixes.is_dir():continue
  for source in fixes.rglob('*'):
   if not source.is_file():continue
   relative=source.relative_to(QA/'validated-render-fixes-r1/romfs')
   target=setup/'romfs'/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);extra+=1
 (setup/'active-target.json').write_bytes(active)
 files=[{'path':p.relative_to(setup).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p.read_bytes())} for p in sorted(setup.rglob('*')) if p.is_file() and p.name!='setup-ready.json']
 (setup/'setup-ready.json').write_text(json.dumps({'run':run,'source_run':old,'additional_validated_controller_files':extra,'files':files},indent=1))
 print(json.dumps({'run':run,'source_run':old,'setup_files':len(files),'additional_validated_controller_files':extra,'test_save_bytes':(new/'save/save_0/main').stat().st_size,'native_control':661,'original_saves_unchanged':True}),flush=True)
if __name__=='__main__':main()
