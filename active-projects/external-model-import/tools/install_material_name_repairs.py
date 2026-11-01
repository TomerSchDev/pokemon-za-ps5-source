"""Install the four certified material tables into the temporary PC test overlay."""
import hashlib,json,os
from run_pc_gallery import QA,WORK
source=QA/'material-name-repairs-r1'
report=json.loads((source/'material-bindings-audit.json').read_text(encoding='utf-8'))
assert not report['unresolved']
cache=WORK/'render-fixes';certificate=cache/'verified-hashes.json'
hashes=json.loads(certificate.read_text(encoding='utf-8'))
for row in report['repairs']:
    relative='mods/00-material-name-fixes/romfs/'+row['relative']
    raw=(source/'romfs'/row['relative']).read_bytes()
    assert hashlib.sha256(raw).hexdigest()==row['sha256']
    target=cache/relative;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():assert target.read_bytes()==raw
    else:
        temporary=target.with_name(target.name+'.qa-new');temporary.write_bytes(raw);os.replace(temporary,target)
    hashes[relative]=row['sha256']
temporary=certificate.with_suffix('.qa-new');temporary.write_text(json.dumps(hashes),encoding='utf-8');os.replace(temporary,certificate)
print('Certified material-name repair files:',len(report['repairs']))
