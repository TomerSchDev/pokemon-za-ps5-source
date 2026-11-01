"""Publish manually reviewed PC evidence; never infer a pass from scripted input."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,zipfile

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    lab=Path(__file__).resolve().parents[3];work=lab/'pc-fifty-20261031-r1';runs=lab/'hebrew-lab/runs'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    old=json.loads((work/'progress-20261031T115701Z.json').read_text(encoding='utf-8-sig'))
    selection=json.loads((work/'selection.json').read_text(encoding='utf-8-sig'))
    proof={
        'yamper-spark-windup.png':('pc-fifty-yamper-two-spark-r33','build/frames/frame_01360.png'),
        'yamper-spark-victory.png':('pc-fifty-yamper-two-spark-r33','build/frames/frame_01430.png'),
        'yamper-tackle-impact.png':('pc-fifty-yamper-two-tackle-r34','build/frames/frame_01600.png'),
        'yamper-tackle-victory.png':('pc-fifty-yamper-two-tackle-r34','build/frames/frame_01740.png'),
        'yamper-level25.png':('pc-fifty-yamper-two-tackle-r34','build/frame_03020.png'),
        'yamper-can-evolve.png':('pc-fifty-yamper-two-tackle-r34','build/frame_03112.png'),
        'yamper-evolved-into-boltund.png':('pc-fifty-yamper-two-tackle-r34','build/frame_04010.png'),
        'boltund-field-and-correct-icon.png':('pc-fifty-yamper-two-tackle-r34','build/frame_04387.png'),
    }
    post=work/'boltund-bite-manual-review.json'
    if post.is_file():
        reviewed=json.loads(post.read_text());assert reviewed['manually_viewed'] is True
        assert reviewed['move_id']==44 and reviewed['damage_visible'] is True
        for label,rel in reviewed['captures'].items():proof[label]=(reviewed['run'],rel)
    out=work/'evidence'/f'pc-fifty-results-{stamp}';out.mkdir(parents=True,exist_ok=False)
    hashes={}
    for name,(run,rel) in proof.items():
        src=runs/run/rel;assert src.read_bytes()[-8:]==b'IEND\xaeB`\x82'
        target=out/name;shutil.copyfile(src,target);assert sha(src)==sha(target)
        hashes[name]=dict(run=run,path=rel,sha256=sha(src))
    row=old['rows'][0];assert row['species']==835
    row.update(outside='observed_pass',attack_1='observed_pass',attack_2='observed_pass',
               level_up='observed_pass',evolution_animation='observed_pass',
               post_evolution_attack='observed_pass' if post.is_file() else 'pending',complete=post.is_file(),
               evidence=hashes,post_evolution_move=selection['targets'][0]['post_evolution_attack']['Move'],
               fixture_note='Isolated copied save; additional diagnostic party controls do not count as tested cohort members.')
    reviewed_rows=work/'reviewed-cohort-progress.json'
    if reviewed_rows.is_file():
        required=('outside','attack_1','attack_2','level_up','evolution_animation','post_evolution_attack')
        for review in json.loads(reviewed_rows.read_text(encoding='utf-8-sig')):
            assert review['manually_viewed'] is True
            target=next(r for r in old['rows'] if r['species']==review['species'])
            evidence={}
            for label,item in review['evidence'].items():
                rel=Path(item['path']);assert not rel.is_absolute() and '..' not in rel.parts
                src=runs/item['run']/rel;assert src.read_bytes()[-8:]==b'IEND\xaeB`\x82'
                name=f"species-{review['species']}-{label}.png"
                assert Path(name).name==name
                shutil.copyfile(src,out/name);assert sha(src)==sha(out/name)
                evidence[label]={**item,'sha256':sha(src),'delivered_file':name}
            target.update({key:review[key] for key in required})
            target.update(evidence=evidence,notes=review.get('notes',''),complete=all(target[k]=='observed_pass' for k in required))
    old.update(updated_utc=datetime.now(timezone.utc).isoformat(),pc_full_passes=sum(bool(r['complete']) for r in old['rows']),
               console_testing_stopped=True,evidence_rule='Manual review of actual game images, including visible damage; inputs alone are not a pass.')
    old['findings']={
        'yamper_two_original_attacks':True,'actual_level25_evolution_to_boltund':True,
        'diagnostic_world_overlay_required_for_attack':False,
        'prior_failed_attack_cause':'Unresolved; earlier targeting/range/input timing trials were not sufficient to establish a missing-model defect.',
        'r34_end':'Expected 1800-second harness stop; evolved copied save written before the stop.',
        'capture_disk_full':'Some incomplete PNGs were rejected, never accepted as evidence.'}
    for name in ('pc-fifty-boltund-bite-r35','pc-fifty-boltund-bite-r36'):
        record=runs/name/'run.json'
        if record.is_file():
            data=json.loads(record.read_text(encoding='utf-8-sig'))
            old['findings'][name]={key:data.get(key) for key in ('finished_utc','exit_code','terminated_by_harness','elapsed_seconds')}
    old['findings']['r35_cause']='Windows commit allocation failed with error 1455, then access violation during loading; no battle attempted.'
    old['findings']['r36_limit']='No progress beyond loading after coordinate-only fixture patch; controlled stop, not counted as pass.'
    old['findings']['r37_result']='Raw evolved copied save reloads successfully, showing Boltund Lv25 in the field; stopped for PC queue handoff.'
    if post.is_file():old['findings']['r38_result']='Bite selected through the in-game Change moves menu, then defeats Fletchling with EXP award; manually reviewed. Stopped for queue handoff.'
    (out/'progress.json').write_text(json.dumps(old,indent=1,ensure_ascii=False),encoding='utf-8')
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for src in out.iterdir():z.write(src,src.name)
    source_archive=out/'pc-qa-tools-source.zip'
    source_files=['hebrew-lab/tools/run_poc.py']+['species-lab/import-all-20261030/tools/'+name for name in (
        'pc_fifty_control.py','pc_fifty_video.py','collect_pc_fifty.py','publish_pc_fifty_progress.py',
        'Select-ConsoleFiftyPrimary.ps1','Stage-ConsoleFiftyObservedLevel.ps1',
        'Patch-ConsoleFiftyMovePP.ps1','Patch-YamperMoveControl.ps1',
        'probe_yamper_native_model.py','probe_yamper_transition_loops.py','probe_yamper_world_data.py',
        'pc_fifty_training.py','sword_animation_rate.py','inspect_yamper_parameters.py',
        'probe_pc_fifty_floating.py')]
    with zipfile.ZipFile(source_archive,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for rel in source_files:z.write(lab/rel,rel)
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1')/'Reviewed'/out.name
    nas.mkdir(parents=True,exist_ok=False)
    for src in [*out.iterdir(),archive]:
        target=nas/src.name;shutil.copyfile(src,target);assert sha(target)==sha(src)
    print(json.dumps(dict(full_pc_passes=old['pc_full_passes'],archive=str(archive),nas=str(nas),sha256=sha(archive),sha256_verified=True)),flush=True)

if __name__=='__main__':main()
