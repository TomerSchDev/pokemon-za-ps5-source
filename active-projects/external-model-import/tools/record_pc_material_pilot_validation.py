import json
from run_pc_gallery import QA
run='pc-quality-retest-000-r1'
report=json.loads((QA/'retests/material-pilot-r1-results.json').read_text(encoding='utf-8'))
assert all(t['render_status']=='captured_requires_visual_review' and t['animation_status']=='motion_detected' for t in report['targets'])
path=QA/'wide/visual-review-r1.json';review=json.loads(path.read_text(encoding='utf-8'))
for row in review['confirmed_incomplete_body']:
    if row['key']=='0205-00-0':row.update(status='resolved_in_PC_QA',validated_run=run,complete_body_visually_confirmed=True)
review['pending_transparency_validation']=[]
review['material_binding_retests_resolved']={'keys':['0205-00-0','0790-00-0'],'run':run,'normal_palette_only':True}
review['native_motion_alias_resolved']={'keys':['0397-00-0','0397-00-1','0821-00-0'],'run':run,'sample_offsets':[0,19,37]}
review['material_pilot_visual_validation']={'keys':[t['key'] for t in report['targets']],'run':run,'complete_bodies_and_idle_poses_reviewed':True,'screenshot':'gallery-box-01.jpg'}
path.write_text(json.dumps(review,indent=1),encoding='utf-8')
path=QA/'material-name-repairs-r1/material-bindings-audit.json';bindings=json.loads(path.read_text(encoding='utf-8'))
bindings['runtime_validation']={'normal_palette_models_visually_confirmed':['0205-00-0','0790-00-0'],'run':run,'shiny_materials_not_runtime_tested':True}
path.write_text(json.dumps(bindings,indent=1),encoding='utf-8')
print('Recorded seven actual PC regression validations, including full Forretress and Spiritomb faces.')
