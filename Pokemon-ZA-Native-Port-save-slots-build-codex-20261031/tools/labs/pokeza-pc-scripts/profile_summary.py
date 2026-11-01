"""Map the runtime's sampled PCs using exact PE bounds and our game's linker map.

Sampling includes sleeping threads and perturbs execution: counts are diagnostic,
not CPU-time percentages or a performance benchmark.
"""
import argparse
import bisect
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import struct

p = argparse.ArgumentParser()
p.add_argument('run', type=Path)
p.add_argument('--map', type=Path, required=True)
p.add_argument('--exe', type=Path, required=True)
a = p.parse_args()
log = (a.run / 'stderr.log').read_text(errors='replace')
m = re.search(r'lasgame\.dll at (?:0x)?([0-9a-fA-F]+), exe at (?:0x)?([0-9a-fA-F]+)', log)
if not m: raise SystemExit('Sampling completion line missing')
game_base, exe_base = (int(v, 16) for v in m.groups())

def pe_symbols(path):
    data = path.read_bytes()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    _, nsec, _, symptr, nsym, optlen, _ = struct.unpack_from('<HHIIIHH', data, pe+4)
    opt = pe+24
    if struct.unpack_from('<H', data, opt)[0] != 0x20b: raise ValueError('Expected PE32+')
    size = struct.unpack_from('<I', data, opt+56)[0]
    sections = []
    for i in range(nsec):
        base = opt+optlen+i*40
        sections.append((struct.unpack_from('<I',data,base+12)[0], struct.unpack_from('<I',data,base+36)[0]))
    stringbase = symptr+nsym*18
    result=[]
    i=0
    while i<nsym:
        base=symptr+i*18
        name=data[base:base+8]
        val, sec, typ, storage, aux = struct.unpack_from('<IhHBB',data,base+8)
        if name[:4]==b'\0'*4:
            start=stringbase+struct.unpack_from('<I',name,4)[0]
            name=data[start:data.index(b'\0',start)]
        else: name=name.split(b'\0',1)[0]
        if 0<sec<=nsec and sections[sec-1][1]&0x20 and typ&0x20:
            result.append((sections[sec-1][0]+val,name.decode(errors='replace')))
        i+=1+aux
    return size, sorted(result)

exe_size, exe_syms = pe_symbols(a.exe)
text=a.map.read_text(errors='replace')
preferred=int(re.search(r'Preferred load address is ([0-9a-fA-F]+)',text)[1],16)
game_syms=[]
for ln in text.splitlines():
    x=re.match(r'\s*0001:[0-9a-fA-F]+\s+(\S+)\s+([0-9a-fA-F]{16})\s+(.*)',ln)
    if x: game_syms.append((int(x[2],16)-preferred, x[1]))
game_syms.sort()
game_size, _ = pe_symbols(a.map.with_suffix('.dll'))
tables=[('game',game_base,game_size,game_syms,[x[0] for x in game_syms]),
        ('runtime',exe_base,exe_size,exe_syms,[x[0] for x in exe_syms])]
tot=Counter(); per=defaultdict(Counter)
for line in (a.run/'build/samples.txt').read_text().splitlines():
    tid,rip,n=line.split(); rip=int(rip,16); n=int(n)
    label='external-or-wait'
    for name,base,size,syms,offsets in tables:
        if base<=rip<base+size:
            at=bisect.bisect_right(offsets,rip-base)-1
            label=name+':'+(syms[at][1] if at>=0 else hex(rip-base))
            break
    tot[label]+=n; per[tid][label]+=n
result=dict(scope='Sample counts, including blocked threads; not execution-time percentages.',
            total_samples=sum(tot.values()), top_mapped=Counter({k:v for k,v in tot.items() if ':' in k}).most_common(30),
            per_thread={k:v.most_common(8) for k,v in per.items() if sum(n for f,n in v.items() if ':' in f)>20})
(a.run/'profile-summary.json').write_text(json.dumps(result,indent=2))
print(json.dumps({k:v for k,v in result.items() if k!='per_thread'},indent=2))
