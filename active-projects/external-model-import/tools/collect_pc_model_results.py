"""Collect actual PC observations without equating captures or motion with a pass."""
from pathlib import Path
import collections,json
from datetime import datetime,timezone
from run_pc_gallery import ROOT,QA

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def collect():
    inventory_path=QA/('inventory-v4.json' if (QA/'inventory-v4.json').exists() else 'inventory-v3.json')
    inventory=read(inventory_path)['targets']
    observations={};records={};raw_reports={}
    def add(row):
        run=row['run']
        if run not in records:records[run]=read(ROOT/'qa/runs'/run/'run.json')
        record=records[run]
        if not record.get('canonical_model_and_game_data_on_NAS'):return
        if run not in raw_reports:
            raw_reports[run]={x['key']:x for x in read(ROOT/'qa/runs'/run/'gallery-results.json')['targets']}
        latest=raw_reports[run].get(row['key'],{})
        if latest.get('empty_panel_detector')=='two_verified_templates_v2':
            row=dict(row)
            for key in ('render_status','empty_panel_detector','pixels_different_from_empty_panel','visual_review'):
                if key in latest:row[key]=latest[key]
        stamp=record['finished_utc']
        current=observations.get(row['key'])
        prefer_exact=False
        if current and current['render_status']==row['render_status']=='captured_requires_visual_review':
            current_exact=bool(current.get('form_probe_mode') and current.get('model_resource_requested'))
            row_exact=bool(row.get('form_probe_mode') and row.get('model_resource_requested'))
            if current_exact and not row.get('model_resource_requested'):
                current['normalized_summary_observation']={'run':run,'observed_utc':stamp}
                return
            prefer_exact=row_exact and not current.get('model_resource_requested')
        if current and stamp<=current['observed_utc'] and not prefer_exact:return
        row=dict(row,observed_utc=stamp)
        if prefer_exact:
            row['normalized_summary_observation']={'run':current['run'],'observed_utc':current['observed_utc']}
        row['qa_controller_repairs_loaded']=any('00-native-control-fixes' in line for line in record.get('fs_lines',[]))
        row['qa_form_bindings_loaded']=any('00-form-fixes' in line for line in record.get('fs_lines',[]))
        visible=row['render_status']=='captured_requires_visual_review'
        row['body_visible']=visible
        row['fully_functional_verified']=False
        if row['imported']:
            row['identity_status']='requested_resource_observed_requires_visual_review' if visible and row.get('model_resource_requested') else 'unconfirmed'
            if visible and not row.get('model_resource_requested'):
                row['form_context_status']='Requested imported model resource not observed; Summary may normalize temporary forms to base.'
        else:
            row['identity_status']='native_body_observed_requires_visual_review' if visible else 'unconfirmed'
            if row['form']:row['form_context_status']='summary_can_show_base_form; exact_form_requires_review_or_battle_context'
        if not visible:row['requires_isolated_retry']=True
        row['animation_metric_limitation']='Pixel motion is a screening measurement; it does not validate pose, attacks, or all animation states.'
        observations[row['key']]=row
    for path in sorted((ROOT/'qa/runs').glob('pc-wide-native-*/gallery-results.json')):
        for row in read(path)['targets']:add(row)
    for path in sorted((QA/'wide').glob('pc-wide-import-*-results.json')):
        for row in read(path)['targets']:add(row)
    for path in sorted((QA/'wide').glob('pc-wide-import-*-checkpoint.json')):
        for row in read(path)['resolved_targets']:add(row)
    for name in ('pc-layer-registry-probe-r39','pc-native-module-probe-r40','pc-native-identity-probe-r41'):
        path=ROOT/'qa/runs'/name/'gallery-results.json'
        if path.exists():
            for row in read(path)['targets']:add(row)
    for path in sorted((ROOT/'qa/runs').glob('pc-quality-retest-*/gallery-results.json')):
        for row in read(path)['targets']:add(row)
    for path in sorted((ROOT/'qa/runs').glob('pc-exact-form-*/gallery-results.json')):
        for row in read(path)['targets']:add(row)
    rows=[]
    visual_path=QA/'wide/visual-review-r1.json'
    visual_issues={t['key']:t for t in read(visual_path).get('unresolved_visual_model_issues',[])} if visual_path.exists() else {}
    for target in inventory:
        row=observations.get(target['key'])
        if row and target['key'] in visual_issues:
            row=dict(row,visual_status='known_visual_defect',visual_finding=visual_issues[target['key']]['finding'],fully_functional_verified=False)
        rows.append(row if row else dict(target,render_status='not_yet_observed',body_visible=False,fully_functional_verified=False))
    visible=[x for x in rows if x['body_visible']]
    counts={}
    for label,subset in [('all',rows),('imported',[x for x in rows if x['imported']]),('native',[x for x in rows if not x['imported']])]:
        counts[label]={'targets':len(subset),'observed':sum(x['render_status']!='not_yet_observed' for x in subset),
                       'visible_bodies':sum(x['body_visible'] for x in subset),
                       'render_statuses':dict(collections.Counter(x['render_status'] for x in subset)),
                       'visible_with_pixel_motion':sum(x['body_visible'] and x.get('animation_status')=='motion_detected' for x in subset)}
    return {'generated_utc':datetime.now(timezone.utc).isoformat(),'PC_only':True,'source_build_unchanged':True,
            'coverage_species':len({x['national'] for x in inventory}),
            'species_with_at_least_one_visible_body':len({x['national'] for x in visible}),
            'counts':counts,'scope':'Actual isolated Test-save Summary rendering and idle-motion screening. Combat, TMs, and evolution are not tested by this sweep.',
            'limitations':['A visible body is not a full functional pass.','Summary normalizes some temporary and Mega forms to base models.','Earlier single-template classification is superseded by the two-template empty-panel detector.'],
            'targets':rows}

if __name__=='__main__':
    result=collect();path=QA/'wide/runtime-overview-r1.json'
    path.write_text(json.dumps(result,indent=1),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('coverage_species','species_with_at_least_one_visible_body','counts')}))
