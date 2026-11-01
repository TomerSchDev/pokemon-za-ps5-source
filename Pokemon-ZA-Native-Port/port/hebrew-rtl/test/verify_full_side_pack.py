"""Exercise the real initializer against the full private seed pack on Linux."""
import hashlib
import json
from pathlib import Path
import stat
import subprocess
import sys

package=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=False)
manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8-sig'))
source=Path(__file__).resolve().parents[2]/'main-install/seed-side-data.c'
app=out/'app';mount=out/'mount';data=out/'download/zarecomp'
for p in [app,mount/'sce_sys',data]:p.mkdir(parents=True,exist_ok=True)
(app/'init-data.bin').symlink_to(package/'init-data.bin')
(mount/'sce_sys/param.json').write_text('{"titleId": "PPSA91990"}')
binary=out/'seed'
subprocess.run(['cc','-O2','-Wall',f'-DSIDE_APP="{app}"',f'-DSIDE_MOUNT="{mount}"',f'-DSIDE_DATA="{data}"',str(source),'-o',str(binary)],check=True)
subprocess.run([str(binary)],timeout=120,check=True)
rows=[]
for row in manifest['seed_files']:
    path=data/row['relative']
    with path.open('rb') as f:digest=hashlib.file_digest(f,'sha256').hexdigest()
    if digest!=row['sha256']:raise ValueError('Full-pack readback mismatch: '+row['relative'])
    if stat.S_IMODE(path.stat().st_mode)!=0o666:raise ValueError('Side game cannot write copied data')
    rows.append({'relative':row['relative'],'sha256':digest,'bytes':path.stat().st_size})
log=(data/'side-seed.log').read_text()
if f'COMPLETE {len(rows)}/{len(rows)};' not in log:raise ValueError('No actual completion record')
record={'result':'passed','scope':'Full private seed pack on Linux host, not PS5/game execution',
        'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'files':rows,'bytes':sum(r['bytes'] for r in rows),
        'all_copied_files_writable_by_title':True,'log':log}
(out/'result.json').write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'result':'passed','files':len(rows),'bytes':record['bytes'],'scope':record['scope']}))
