from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,shutil,zipfile
root=Path(__file__).resolve().parent;workspace=root.parents[1]
src=workspace/'deliverables/Pokemon-ZA-Quick-Start-0.1.0-20261025'
archive=src.with_name(src.name+'.zip')
dest=Path(r'\\TheOnePiece\Software\Pokemon-ZA-PC')
def digest(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
records=json.loads((src/'SHA256.json').read_text())
for rec in records:
    p=src/rec['path'];assert digest(p)==rec['sha256'],str(p)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    expected={str(Path(src.name)/p.relative_to(src)).replace('\\','/') for p in src.rglob('*') if p.is_file()}
    assert set(z.namelist())==expected
dest.mkdir(parents=True,exist_ok=True)
targets=[]
for p in [archive,*sorted(x for x in src.rglob('*') if x.is_file())]:
    rel=p.relative_to(src.parent);target=dest/rel
    sha=digest(p)
    if target.exists():
        if digest(target)!=sha:raise RuntimeError(f'Preserving a different existing NAS file: {target}')
    else:
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,target)
    if digest(target)!=sha:raise RuntimeError(f'NAS copy mismatch: {target}')
    targets.append(dict(path=str(target),sha256=sha,bytes=target.stat().st_size))
receipt=dict(copied_utc=datetime.now(timezone.utc).isoformat(),verified=True,files=targets)
(root/'quickstart-nas-receipt.json').write_text(json.dumps(receipt,indent=2))
progress=json.loads((root/'progress.json').read_text(encoding='utf-8-sig'))
progress['updated_utc']=receipt['copied_utc'];progress['stage']='Daytime city movement measured; three-starter Quick Start delivered'
progress['quick_start']=dict(version='0.1.0',path=str(src),zip=str(archive),sha256=digest(archive),nas_copy_completed=True,
    nas_zip=str(dest/archive.name),starters_reloaded=['Chikorita','Tepig','Totodile'],checkpoint='Daytime street, Mission 03 before Wild Zone 1',
    later_tutorials_remain=True,stable_30_fps_mean=29.56,stable_30_fps_interval_range=[27.4,30.0],largest_gap_ms=150)
(root/'progress.json').write_text(json.dumps(progress,indent=2),encoding='utf-8')
print(json.dumps(dict(verified_files=len(targets),nas_zip=str(dest/archive.name),sha256=digest(archive),archive_bytes=archive.stat().st_size)))
