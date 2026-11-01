import json
from run_pc_gallery import ROOT,QA

path=ROOT/'qa/runs/pc-wide-import-008-r2/gallery-results.json'
backup=path.with_name('gallery-results.before-cosmoem-material-review.json')
if not backup.exists():backup.write_bytes(path.read_bytes())
value=json.loads(path.read_text(encoding='utf-8'))
for row in value['targets']:
    if row['key']=='0790-00-0':
        row['render_status']='material_binding_requires_retest'
        row['visual_review']={'finding':'Mesh body_b has no matching material name in this pre-repair capture; recheck complete body with the certified material overlay.','audit':'material-name-repairs-r1/material-bindings-audit.json'}
path.write_text(json.dumps(value,indent=1),encoding='utf-8')

path=QA/'wide/visual-review-r1.json';value=json.loads(path.read_text(encoding='utf-8'))
value['reviewed_import_batches']=[1,2,3,4,8];value['partially_reviewed_import_batches']=[]
value['latest_sheets']['8']='import-008-20261031T004447Z'
value['batch4_final_segment']='pc-wide-import-004-r1-s03/gallery-box-01.jpg'
value['summary_normalizes_imported_forms']=['0421-01-0','0845-01-0','0845-02-0','0875-01-0']
additional=[785,787,791,792,794,796,797,799,800,804,805,812,838,851,874]
known={x['species'] for x in value['summary_framing_needs_review']}
value['summary_framing_needs_review'] += [{'species':n,'finding':'Body extends beyond the Summary model view; exact framing requires a camera/configuration adjustment.'} for n in additional if n not in known]
value['material_binding_retests']=['0205-00-0','0790-00-0']
path.write_text(json.dumps(value,indent=1),encoding='utf-8')
print('Recorded batch 8 visual inspection and the Cosmoem material-binding retest.')
