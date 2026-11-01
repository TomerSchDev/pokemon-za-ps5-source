"""Inventory existing PC SPIR-V, retaining conflicting keys for review."""
from pathlib import Path
import hashlib,json,struct
root=Path(__file__).resolve().parents[2]
pc=Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1')
files=json.loads((root/'evidence/title-r14-pc-shader-inventory.json').read_text())
out=root/'artifacts/title-r14-pc-shaders';out.mkdir(exist_ok=True)
keys={};conflicts={};invalid=[]
for rel in files:
    p=pc/rel;data=p.read_bytes();sha=hashlib.sha256(data).hexdigest()
    if len(data)<20 or len(data)%4 or struct.unpack_from('<I',data)[0]!=0x07230203:
        invalid.append(rel);continue
    item={'source':str(p),'sha256':sha,'bytes':len(data)}
    if p.name in keys and keys[p.name]['sha256']!=sha:
        conflicts.setdefault(p.name,[keys[p.name]])
        if not any(x['sha256']==sha for x in conflicts[p.name]):conflicts[p.name].append(item)
    else:keys[p.name]=item
for name,item in keys.items():
    if name not in conflicts:
        dest=out/name
        data=Path(item['source']).read_bytes()
        if dest.exists():assert hashlib.sha256(dest.read_bytes()).hexdigest()==item['sha256']
        else:dest.write_bytes(data)
record={'input_files':len(files),'unique_keys':len(keys),'unambiguous':len(keys)-len(conflicts),'conflicts':conflicts,'invalid':invalid,'files':{k:v for k,v in keys.items() if k not in conflicts},'note':'Content-addressed portable SPIR-V candidates. Validate before deployment; preserve existing console entries. No PC GPU binary cache.'}
(root/'evidence/title-r14-pc-shader-candidates.json').write_text(json.dumps(record,indent=2))
print(json.dumps({k:record[k] for k in ['input_files','unique_keys','unambiguous']}));print('Conflicting keys:',len(conflicts),'Invalid:',len(invalid))
