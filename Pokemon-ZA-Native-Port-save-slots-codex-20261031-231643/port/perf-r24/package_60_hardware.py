"""Package measurements and a Hebrew JSON summary, excluding game/save contents."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]


def digest(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1<<20),b''):h.update(chunk)
    return h.hexdigest()


def main(out,protocol):
    state=json.loads((out/'state.json').read_text());final=json.loads((out/'final-state.json').read_text())
    assert len(state['phases'])==16 and 'current' not in state
    assert all(final[k] for k in ('installed_sha256_verified','original_configs_verified','save_unchanged','ini_restored','application_closed','directory_permissions_restored'))
    resultpath=out/'Results-r24-60fps-4k-20261029.json';result=json.loads(resultpath.read_text(encoding='utf-8'))
    dest=ROOT/'deliverables'/('r24-60fps-4k-hardware-'+datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'));dest.mkdir(exist_ok=False)
    shutil.copy2(resultpath,dest/resultpath.name)
    summary={'כותרת':'תוצאות בדיקת 60 FPS ופלט 4K על r24', 'תקציר':result['summary_he'],
             'מדידות':[{'עלייה':s['boot'],'פלט':s['display'],'רינדור פנימי':s['internal'],'מצב FPS':s['fps_mode'],
                         'FPS':s['timing']['interval_rate_fps'],'p50 ms':s['timing']['frame_ms']['p50'],
                         'p95 ms':s['timing']['frame_ms']['p95'],'p99 ms':s['timing']['frame_ms']['p99'],
                         'פריימים מעל 16.7 ms':s['over_16_7_ms'],'GPU busy ms':s['perf']['per_frame']['gpu_busy_ms'],
                         'GPU idle ms':s['perf']['per_frame']['gpu_idle_ms'],'זמני חזרה אוטומטית בשניות':s['fallback_log_s'],
                         'render thread ms':s['render_thread']['per_frame']} for s in result['stages']],
             'מצב סיום':final}
    summarypath=dest/'Summary-r24-60fps-4k-HE.json'
    summarypath.write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    entries={resultpath.name:resultpath,summarypath.name:summarypath,'tools/TEST-60FPS-4K-r24-HE.md':protocol}
    for name in ('all.klog.log','events.jsonl','state.json','final-state.json','capture-capability.json','logger.json'):
        entries['raw/'+name]=out/name
    entries['raw/save-preservation.json']=out/'save-backup/verification.json'
    for boot in state['boots']:
        folder=out/boot['label']
        for name in ('identity.json','deploy.json','close.json','boot.klog.log','ini.json','ini-transport.json','ini-restored.json'):
            path=folder/name
            if path.exists():entries['raw/'+str(path.relative_to(out)).replace('\\','/')]=path
    for phase in state['phases']:
        for path in (out/phase['csv']).parent.iterdir():
            assert path.is_file() and path.suffix in ('.csv','.json','.png')
            entries['raw/'+str(path.relative_to(out)).replace('\\','/')]=path
    for name in ('run_60_hardware.py','results_60_hardware.py','package_60_hardware.py','hardware_run.py','analyze_r24.py','summarize_hardware.py'):
        entries['tools/'+name]=ROOT/'port/perf-r24'/name
    assert sum(key.endswith('.png') for key in entries)==32
    assert sum(key.endswith('.csv') for key in entries)==16
    manifest=[dict(path=k,bytes=p.stat().st_size,sha256=digest(p)) for k,p in sorted(entries.items())]
    archive=dest/'r24-60fps-4k-evidence-20261029.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for key,path in sorted(entries.items()):z.write(path,key)
        z.writestr('Manifest.json',json.dumps(manifest,indent=2)+'\n')
    with zipfile.ZipFile(archive) as z:assert z.testzip() is None
    files=[dest/resultpath.name,summarypath,archive]
    sums=dest/'SHA256SUMS.txt';sums.write_text(''.join(digest(p)+'  '+p.name+'\n' for p in files),encoding='ascii')
    info=dict(directory=str(dest),archive_crc_verified=True,files=[dict(name=p.name,bytes=p.stat().st_size,sha256=digest(p)) for p in (*files,sums)])
    (out/'delivery.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);p.add_argument('protocol',type=Path)
    a=p.parse_args();main(a.out.resolve(),a.protocol.resolve())
