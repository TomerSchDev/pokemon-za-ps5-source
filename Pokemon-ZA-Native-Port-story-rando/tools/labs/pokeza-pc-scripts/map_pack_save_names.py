"""Read-only bounded pack scan for event variable names; no exported assets."""
import json,re,sys,time
from pathlib import Path
sys.path.insert(0,str(Path('research/pokeza-recomp/tools/za').resolve()))
from trinity import Oodle,pack_files
report=json.loads(Path('research/pokeza-pc/postbattle-save-inspect.json').read_text(encoding='utf-8-sig'))
keys={int(k,16) for c in ('work','quest','flags') for k in report[c]}
matches=json.loads(Path('research/pokeza-pc/save-key-names.json').read_text())
oodle=Oodle('research/pokeza-pc/release-v0.1.4/ZA Recomp/zaprompts/_internal/ooz.dll')
start=time.monotonic();count=0
seen=set()
for pi,fh,d in pack_files('research/pokeza-pc/private-data/arc/data.trpfs',oodle,max_size=1024*1024):
    count+=1
    for m in re.finditer(rb'[A-Za-z_][A-Za-z0-9_]{3,120}\x00',d):
        name=m.group()[:-1]
        if name in seen:continue
        seen.add(name);h=0xcbf29ce484222645
        for b in name:h=((h^b)*0x100000001b3)&0xffffffffffffffff
        if h in keys and f'{h:016X}' not in matches:
            matches[f'{h:016X}']={'name':name.decode(),'pack':pi,'file_hash':f'{fh:016X}'}
            print(name.decode(),f'{h:016X}',flush=True)
    if count%2000==0:print('scanned',count,'seconds',round(time.monotonic()-start),flush=True)
Path('research/pokeza-pc/save-key-names-full.json').write_text(json.dumps(matches,indent=2))
print('DONE',count,'matched',len(matches),flush=True)
