"""Verify the linked PE dispatcher table points to each newly compiled hook symbol."""
from pathlib import Path
import argparse,bisect,json,re,struct,subprocess
p=argparse.ArgumentParser();p.add_argument('dll',type=Path);a=p.parse_args()
symbols={}
for line in subprocess.check_output(['C:/msys64/ucrt64/bin/nm.exe','-n',str(a.dll)]).decode().splitlines():
    row=line.split()
    if len(row)==3 and (row[2].startswith('main_fn_') or row[2] in ('f_70006bfce0','f_70009c18d8','f_7000a718c8','f_7000dbb28c','f_700291eb18','f_700291eaf0')):symbols[row[2]]=int(row[0],16)
raw=a.dll.read_bytes();pe=struct.unpack_from('<I',raw,0x3c)[0];n=struct.unpack_from('<H',raw,pe+6)[0];opt_size=struct.unpack_from('<H',raw,pe+20)[0]
base=struct.unpack_from('<Q',raw,pe+24+24)[0];sections=[]
for i in range(n):
    off=pe+24+opt_size+40*i;vsize,rva,size,ptr=struct.unpack_from('<IIII',raw,off+8);sections.append((rva,max(vsize,size),ptr))
def offset(va):
    r=va-base
    for start,size,ptr in sections:
        if start<=r<start+size:return ptr+r-start
    raise ValueError(hex(va))
count=struct.unpack_from('<Q',raw,offset(symbols['main_fn_count']))[0]
addrs=struct.unpack_from('<'+'Q'*count,raw,offset(symbols['main_fn_addrs']))
results=[]
for name in ('f_70006bfce0','f_70009c18d8','f_7000a718c8','f_7000dbb28c','f_700291eb18','f_700291eaf0'):
    guest=int(name[2:],16);i=bisect.bisect_left(addrs,guest);assert addrs[i]==guest
    pointer=struct.unpack_from('<Q',raw,offset(symbols['main_fn_ptrs'])+8*i)[0]
    assert pointer==symbols[name],(name,hex(pointer),hex(symbols[name]))
    results.append(dict(function=name,table_index=i,linked_pointer=hex(pointer),matches_patched_symbol=True))
print(json.dumps(dict(main_function_count=count,table_verified=results),indent=2))
