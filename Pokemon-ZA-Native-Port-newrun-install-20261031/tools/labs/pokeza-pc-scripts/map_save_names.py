"""Map observed save keys to literal FNV-1a names in the game's NSO; read only."""
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path('research/pokeza-recomp/tools').resolve()))
from nso import Nso
n=Nso('research/pokeza-pc/game-v1.0.0/extracted/exefs/main')
report=json.loads(Path('research/pokeza-pc/postbattle-save-inspect.json').read_text(encoding='utf-8-sig'))
keys={int(k,16) for category in ('work','quest','flags') for k in report[category]}
matches={}
for m in re.finditer(rb'[\x20-\x7e]{4,}\x00',n.image):
    name=m.group()[:-1]
    h=0xcbf29ce484222645  # Game Freak's nonstandard basis, as in PKHeX FnvHash
    for b in name: h=((h^b)*0x100000001b3)&0xffffffffffffffff
    if h in keys:matches[f'{h:016X}']={'name':name.decode(),'offset':hex(m.start())}
Path('research/pokeza-pc/save-key-names.json').write_text(json.dumps(matches,indent=2))
print(json.dumps(matches,indent=2))
