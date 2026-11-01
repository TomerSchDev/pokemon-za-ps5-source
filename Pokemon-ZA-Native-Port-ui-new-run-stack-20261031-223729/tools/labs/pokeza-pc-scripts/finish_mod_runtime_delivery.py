from pathlib import Path
from datetime import datetime, timezone
import json, shutil, zipfile
from package_mods_and_runtime import HERE,OUT,MOUT,ROUT,sha,js,cp,inventory,zipdir

smoke=HERE/'runtime-opt-r1/delivery-smoke-v2'
result=json.loads((smoke/'smoke-result.json').read_text(encoding='utf-8-sig'))
assert result['matching_game_pids'] and not result['launcher_exited'],result
assert not (smoke/'launcher-stderr.log').read_text(errors='replace').strip()
for name in ['smoke-result.json','launcher-stdout.log','launcher-stderr.log']:
    cp(smoke/name,ROUT/'evidence/launcher-smoke'/name)
for log in (smoke/'user-data/logs').glob('*.log'):
    cp(log,ROUT/'evidence/launcher-smoke'/log.name)
verification=json.loads((ROUT/'verification.json').read_text())
verification['delivery_launcher_smoke']=dict(seconds=35,game_process_alive=True,terminated_by_test=True,
    scope='Fresh save startup; no gameplay input or completed battle in this smoke test')
js(ROUT/'verification.json',verification)

nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-PC')
receipts=[]
for folder in [MOUT,ROUT]:
    js(folder/'SHA256.json',inventory(folder))
    archive=OUT/(folder.name+'.zip')
    zipdir(folder,archive)
    with zipfile.ZipFile(archive) as z: assert z.testzip() is None
    files=[*sorted(folder.rglob('*')),archive]
    for source in files:
        if not source.is_file():continue
        # The directory was constructed using explicit source allowlists. No
        # private integration workspace, key files, assets, caches or saves.
        rel=source.relative_to(OUT)
        target=nas/rel; target.parent.mkdir(parents=True,exist_ok=True)
        want=sha(source)
        if target.exists():
            if sha(target)!=want:raise RuntimeError('Different version exists; refusing overwrite: '+str(target))
        else:shutil.copy2(source,target)
        got=sha(target)
        if got!=want:raise RuntimeError('NAS hash mismatch: '+str(target))
        receipts.append(dict(local=str(source),nas=str(target),sha256=want,bytes=source.stat().st_size))
receipt=dict(verified_at_utc=datetime.now(timezone.utc).isoformat(),nas_root=str(nas),files=receipts)
js(HERE/'mod-runtime-nas-verification.json',receipt)
js(HERE/'mod-runtime-delivery.json',dict(mod_studio=str(MOUT),runtime=str(ROUT),nas_copy_completed=True,nas_root=str(nas)))
p=HERE/'progress.json';progress=json.loads(p.read_text())
progress['updated_utc']=datetime.now(timezone.utc).isoformat()
progress['runtime_optimization']=dict(version='r1',path=str(ROUT),nas_copy_completed=True,control_fps=verification['control_fps'],
    candidate_fps=verification['key_empty_16slots_fps'],percent_change=verification['percent_change'],
    final_shadow_comparisons=verification['final_shadow_comparisons'],promoted_to_stable=False)
progress['mod_studio']=dict(version='0.1.0',path=str(MOUT),nas_copy_completed=True,unit_tests=18,
    real_overlay_read_verified=True,gameplay_randomizer_implemented=False,base_version='1.0.0')
js(p,progress)
print(json.dumps(dict(nas_root=str(nas),verified_files=len(receipts),total_bytes=sum(x['bytes'] for x in receipts)),indent=2))
