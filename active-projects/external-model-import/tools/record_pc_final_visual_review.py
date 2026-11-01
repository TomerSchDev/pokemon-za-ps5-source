import json
from run_pc_gallery import ROOT,QA
from collect_pc_model_results import collect

overview=collect()
path=QA/'wide/visual-review-r1.json';value=json.loads(path.read_text(encoding='utf-8'))
assert set(value['reviewed_import_batches'])==set(range(1,11))
probes=[]
for run in ('pc-exact-form-early-001-r2','pc-exact-form-early-002-r2','pc-exact-form-early-001-r3'):
    report=json.loads((ROOT/'qa/runs'/run/'gallery-results.json').read_text(encoding='utf-8'))
    assert all(t.get('model_resource_requested') for t in report['targets'])
    probes.extend({'key':t['key'],'run':run,'resource_loaded':True,
                   'distinct_form_visual_review':t['key']!='0746-01-0',
                   'finding':'School body is severely above/cropped by the Summary camera; full-body appearance remains unverified.' if t['key']=='0746-01-0' else 'Distinct requested form visually confirmed; gameplay form switching is not tested.'} for t in report['targets'])
value['exact_form_probe_visual_review']=probes
value['quality_retest_visual_review']={'run':'pc-quality-retest-001-r1','reviewed_identities':39,'all_contact_sheets_reviewed':True,
                                      'normal_palette_only':True,'limitation':'Camera clipping is retained in the framing findings; these are not full combat or shader-state passes.'}
if not any(t['species']==746 for t in value['summary_framing_needs_review']):value['summary_framing_needs_review'].append({'species':746,'form':1,'finding':'Only the bottom of the School form is visible at the top of the Summary viewport; full model appearance remains unverified.'})
value['idle_motion_not_observed']=[{'key':t['key'],'run':t['run'],'status':t.get('animation_status')} for t in overview['targets'] if t.get('animation_status')!='motion_detected']
value['all_imported_model_resources_logged']=all(t.get('model_resource_requested') for t in overview['targets'] if t['imported'])
value['full_functionality_verified']=False
value['not_tested']=['combat and attack execution','evolution','TM compatibility and new moves','shiny model/material variants','all animation states','normal form-transition mechanics','world scale and collision','icon fidelity']
path.write_text(json.dumps(value,indent=1),encoding='utf-8')
print(json.dumps({'exact_form_resources':len(probes),'idle_motion_review':value['idle_motion_not_observed'],'framing_species':len(value['summary_framing_needs_review']),'all_imported_resources_logged':value['all_imported_model_resources_logged']}),flush=True)
