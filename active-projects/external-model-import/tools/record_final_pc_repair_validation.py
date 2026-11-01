"""Attach actual per-model PC observations to staged repair metadata."""
import json
from collect_pc_model_results import collect
from run_pc_gallery import ROOT,QA

def main():
    assert (QA/'retests/final-retests-r1-results.json').exists()
    assert (QA/'exact-form-probes-r1/results.json').exists()
    overview=collect();targets={t['key']:t for t in overview['targets']};records={}
    path=QA/'transparency-repairs-r1/transparency-repairs.json'
    repair=json.loads(path.read_text(encoding='utf-8'));rows=[]
    for key in repair['models_affected']:
        target=targets[key];run=target.get('run')
        if run not in records:records[run]=json.loads((ROOT/'qa/runs'/run/'run.json').read_text(encoding='utf-8'))
        relevant=[r for r in repair['repairs'] if key in r['keys']]
        certified=all(records[run]['mods'].get('mods/00-auto-material-fixes/romfs/'+r['relative'])==r['sha256'] for r in relevant)
        rows.append({'key':key,'run':run,'body_visible':target['body_visible'],
                     'idle_pixel_motion':target.get('animation_status')=='motion_detected',
                     'repaired_material_files_in_profile':certified,'requested_model_resource_logged':target.get('model_resource_requested',False),
                     'form_probe_mode':target.get('form_probe_mode'),
                     'scope':'Normal-palette model body/idle observations. Shiny variants, all material effects and combat states are not validated.'})
    repair['runtime_validation']={'PC_only':True,'per_model':rows,'material_cache_present_in_all_retested_profiles':all(r['repaired_material_files_in_profile'] for r in rows)}
    path.write_text(json.dumps(repair,indent=1),encoding='utf-8')
    preview={'generated_utc':overview['generated_utc'],'counts':overview['counts'],
             'known_visual_defects':[{'key':t['key'],'finding':t['visual_finding']} for t in overview['targets'] if t.get('visual_status')=='known_visual_defect'],
             'imported_requested_resources_not_logged':[t['key'] for t in overview['targets'] if t['imported'] and t['body_visible'] and not t.get('model_resource_requested')],
             'failed_or_missing_bodies':[{'key':t['key'],'status':t['render_status']} for t in overview['targets'] if not t['body_visible']],
             'transparency_models':len(rows),'transparency_profiles_certified':sum(r['repaired_material_files_in_profile'] for r in rows)}
    (QA/'wide/final-validation-preview-r1.json').write_text(json.dumps(preview,indent=1),encoding='utf-8')
    print(json.dumps(preview),flush=True)

if __name__=='__main__':main()
