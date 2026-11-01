"""Record human inspection independently of the pixel-change screening metric."""
import json
from run_pc_gallery import ROOT,QA

run=ROOT/'qa/runs/pc-wide-import-003-r1'
path=run/'gallery-results.json'
backup=run/'gallery-results.before-forretress-visual-review.json'
if not backup.exists():backup.write_bytes(path.read_bytes())
value=json.loads(path.read_text(encoding='utf-8'))
for row in value['targets']:
    if row['key']=='0205-00-0':
        row['render_status']='partial_body_requires_repair'
        row['visual_review']={'complete_body':False,'finding':'Only the eyes render; shell/body are absent. Motion pixels do not constitute a body pass.','frame':3003}
path.write_text(json.dumps(value,indent=1),encoding='utf-8')

report={
 'scope':'Human inspection of actual Summary contact sheets; captures show rendering and idle poses only.',
 'reviewed_import_batches':[1,2,3],
 'partially_reviewed_import_batches':[4],
 'latest_sheets':{'1':'import-001-20261031T003632Z','2':'import-002-20261031T003632Z','3':'import-003-20261031T003357Z','4':'import-004-20261031T003632Z'},
 'confirmed_incomplete_body':[{'key':'0205-00-0','run':'pc-wide-import-003-r1','finding':'Eyes only; mesh/material namespace mismatch identified.'}],
 'summary_framing_needs_review':[
  {'species':n,'finding':finding} for n,finding in [
   (12,'Flying wings intersect the Summary name panel.'),(49,'Wing and antenna crop.'),(73,'Head above the visible Summary model area.'),
   (103,'Alolan head out of frame; Kantonian leaf tips may clip.'),(110,'Galarian top hat crop.'),(131,'Neck and head crop.'),
   (144,'Kantonian head and wing crop; Galarian display can be low.'),(146,'Kantonian flying body above frame.'),
   (164,'Noctowl head/wing crop.'),(217,'Ursaring head crop.'),(224,'Octillery upper body crop.'),
   (245,'Suicune upper head crop.'),(249,'Lugia head and upper wings outside Summary area.'),(250,'Ho-Oh head outside Summary area.'),
   (297,'Hariyama head outside Summary area.'),(320,'Wailmer upper body crop.'),(321,'Wailord exceeds Summary model area.'),
   (330,'Flygon head/wing crop.'),(332,'Cacturne upper head crop.'),(342,'Crawdaunt head/claw crop.'),
   (357,'Tropius wing tips crop.'),(364,'Sealeo upper body crop.'),(379,'Registeel upper body crop.')]],
 'limitations':['Framing is specific to Summary and does not establish world-scale errors.','Temporary/Mega exact forms can normalize to the base in Summary.','No combat, TM, evolution or console testing in this sweep.']}
(QA/'wide/visual-review-r1.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
print('Recorded Forretress visual failure and imported batch 1–3 visual review.')
