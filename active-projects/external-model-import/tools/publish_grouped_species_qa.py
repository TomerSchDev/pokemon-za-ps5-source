"""Publish completed grouped QA metadata, never game assets, saves or credentials."""
import argparse,collections,csv,hashlib,json,shutil,zipfile
from datetime import datetime,timezone
from pathlib import Path

def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('audit',type=Path);args=parser.parse_args()
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1'
    audit=args.audit.resolve();assert audit.is_relative_to(work.resolve())
    result=read(audit/'result.json');inputs=read(audit/'inputs.json')
    assert result['version']==2 and result['audit_complete'] and result['audited']==result['total']==833
    source=Path(__file__).with_name('grouped_species_qa.py')
    assert sha(source)==inputs['audit_source_sha256'],'Auditor changed since execution'
    rows=[json.loads(line) for line in (audit/'model-results.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    assert len(rows)==len({r['key'] for r in rows})==833
    assert dict(collections.Counter(r['core_static_status'] for r in rows))==result['core_static_counts']
    members=[key for group in result['groups'] for key in group['members']]
    assert len(members)==len(set(members))==sum('shared_state_group' in r for r in rows)
    assert set(members)=={r['key'] for r in rows if 'shared_state_group' in r}
    by_key={r['key']:r for r in rows}
    routes=collections.defaultdict(list)
    for row in rows:
        if row['core_static_status']=='pass':routes[(row['source'],row['category_int'])].append(row)
    preferred={835:0,749:1,519:2}
    route_panel=[]
    for (pipeline,category),members in sorted(routes.items()):
        representative=min(members,key=lambda r:(preferred.get(r['national'],3),bool(r['form'] or r['gender']),r['key']))
        route_panel.append(dict(source=pipeline,category_int=category,
            route={0:'ground',1:'water',2:'sky'}.get(category,'other'),members=len(members),
            representative=representative['key'],runtime_status='pending',
            inference_limit='First-stage shared-route regression only; member graphs, clips, timing and appearance remain independent.'))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    destination=work/'evidence'/('grouped-imports-qa-'+stamp)
    destination.mkdir(parents=True,exist_ok=False)
    strategy=dict(stage_1=route_panel,stage_1_count=len(route_panel),
        stage_2_module_and_body_panel=result['initial_regression_panel_count'],
        stage_2_plan='Expand into the saved module/body/form/gender panel, then investigate unique graph, timing, geometry and icon exceptions.',
        representative_runtime_assertions=['Correct imported model and icon outside',
            'Actual supported physical/ranged/status move effects, including target HP or changed status; button input is not evidence',
            'Where applicable, actual level/evolution and a post-evolution attack, followed by saved reload'],
        preparation_status='Coverage selection only; per-run fixtures and pinned runtime manifests must be staged before queue submission.',
        inference_rule=result['inference_rule'],all_members_gameplay_passed=False)
    (destination/'coverage-strategy.json').write_text(json.dumps(strategy,indent=1),encoding='utf-8')
    with (destination/'models.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['key','national','internal','form','gender','source','donor_species','category_int','body_type',
                'shared_state_group','mechanism_bucket','core_static_status','gameplay_status','visual_status','icon_identity_status','problems']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for row in rows:
            record={k:row.get(k,'') for k in fields};record['problems']=json.dumps(row['problems'],ensure_ascii=False)
            writer.writerow(record)
    with (destination/'regression-panel.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        fields=['key','national','source','category_int','body_type','covers','runtime_status']
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
        for item in result['initial_regression_panel']:
            row=by_key[item['key']]
            writer.writerow({**{k:row.get(k,'') for k in fields[:5]},'covers':' | '.join(item['covers']),'runtime_status':item['runtime_status']})
    for name in ('inputs.json','result.json','model-results.jsonl'):
        shutil.copyfile(audit/name,destination/name);assert sha(audit/name)==sha(destination/name)
    # Preserve the earlier full dependency/icon audits as dated background only.
    # They do not silently become current checks or gameplay verdicts.
    old_icons=work/'all-imports-icon-audit-r1.json'
    if old_icons.is_file():
        shutil.copyfile(old_icons,destination/'prior-icon-audit.json')
        icon=read(old_icons)
        history=dict(source=str(old_icons),sha256=sha(old_icons),current_rerun=False,
                     scope=icon['scope'],resolved=icon['resolved'],unresolved=icon['unresolved'],
                     mismatching_existing=icon['mismatching_existing'],missing_icons=icon['missing_icons'],
                     caveat='Earlier baseline only; six cohort icon corrections exist separately. Re-audit effective icons before any bulk release.')
        (destination/'prior-icon-audit-scope.json').write_text(json.dumps(history,indent=1),encoding='utf-8')
    code=destination/'source';code.mkdir()
    helpers=[source,Path(__file__),source.with_name('probe_yamper_native_model.py'),
             source.with_name('native_donors.py'),source.with_name('retarget_layer_channels.py'),
             source.with_name('audit_missing_controller_modules.py'),source.with_name('sword_icon_identity.py'),
             source.with_name('pc_fifty_control.py'),lab/'hebrew-lab/tools/run_poc.py']
    for path in helpers:
        shutil.copyfile(path,code/path.name);assert sha(path)==sha(code/path.name)
    files={str(path.relative_to(destination)):dict(sha256=sha(path),bytes=path.stat().st_size)
           for path in destination.rglob('*') if path.is_file()}
    manifest=dict(created_utc=datetime.now(timezone.utc).isoformat(),metadata_only=True,
                  game_assets_saves_and_credentials_included=False,files=files,
                  checks='Complete static core audit; runtime panel pending; icons/material visual identity outside current audit.',
                  individual_full_pc_passes_retained=2,bulk_gameplay_pass=False)
    (destination/'manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
    archive=destination.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(destination.rglob('*')):
            if path.is_file():bundle.write(path,path.relative_to(destination).as_posix())
    with zipfile.ZipFile(archive) as bundle:assert bundle.testzip() is None
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1\Grouped-QA')/archive.name
    nas.parent.mkdir(parents=True,exist_ok=True)
    if nas.exists():assert sha(nas)==sha(archive),'Preserve different existing version'
    else:shutil.copyfile(archive,nas)
    assert sha(nas)==sha(archive)
    receipt=dict(local=str(archive),nas=str(nas),sha256=sha(archive),sha256_verified=True,
                 models=833,species=result['unique_imported_national_species'],
                 static_counts=result['core_static_counts'],state_groups=result['shared_state_groups'],
                 initial_panel=result['initial_regression_panel_count'],first_stage_route_panel=len(route_panel),all_runtime_passed=False)
    (destination/'nas-receipt.json').write_text(json.dumps(receipt,indent=1),encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
