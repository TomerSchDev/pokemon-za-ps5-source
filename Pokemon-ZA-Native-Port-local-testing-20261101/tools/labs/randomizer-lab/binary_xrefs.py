"""Locate ADRP+ADD references; these are address references, not inferred function semantics."""
from pathlib import Path
import json,struct,re,array
ROOT=Path(__file__).resolve().parent
strings=json.loads((ROOT/'binary-strings.json').read_text())
targets={x['offset']:x for x in strings if any(s in x['value'] for s in ['world/ik_data/trainer/trdata','personal_array.bin','ik_event/bin/event_boss','pokemon_spawner_streaming','pokemon_spawner','condition_boss_array'])}
raw=(ROOT/'main-image.bin').read_bytes();nso=(ROOT.parents[2]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/game/exefs/main').read_bytes()
off,size=struct.unpack_from('<II',nso,0x14);words=array.array('I');words.frombytes(raw[off:off+size]);found=[]
for i,w in enumerate(words):
    if w&0x9f000000 != 0x90000000:continue
    imm=((w>>5)&0x7ffff)<<2 | (w>>29)&3
    if imm&(1<<20):imm-=1<<21
    page=((off+i*4)&~0xfff)+(imm<<12);rd=w&31
    if not any(page<=t<page+4096 for t in targets):continue
    for j in range(i+1,min(i+9,len(words))):
        a=words[j]
        if a&0xffc00000==0x91000000 and (a>>5)&31==rd:
            target=page+((a>>10)&0xfff)
            if target in targets:found.append(dict(adrp_va=f'{0x7000000000+off+i*4:x}',add_va=f'{0x7000000000+off+j*4:x}',string_va=targets[target]['va'],string=targets[target]['value']))
        if (a&31)==rd:break
(ROOT/'binary-xrefs.json').write_text(json.dumps(found,indent=2));print(json.dumps(found,indent=2))
