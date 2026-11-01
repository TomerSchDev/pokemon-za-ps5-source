"""Add explicit TRANM playback rate without rebuilding bone/curve tables."""
import struct
from source_archives import FB

def replace_info(raw,loop,frames,rate):
    """Diagnostic timeline replacement; bone/curve bytes remain untouched."""
    assert loop in (0,1) and frames>0 and rate in (30,60)
    fb=FB(raw);root=fb.table(fb.u32(0));info=fb.table(root[0]+fb.u32(root[0]))
    old=[fb.u32(info[i]) if i<len(info) and info[i] else 0 for i in range(3)]
    if old==[loop,frames,rate]:return raw
    data=bytearray(raw)
    while len(data)%2:data.append(0)
    vt=len(data);data.extend(struct.pack('<5H',10,16,4,8,12))
    while len(data)%4:data.append(0)
    at=len(data);data.extend(struct.pack('<i3I',at-vt,loop,frames,rate))
    struct.pack_into('<I',data,root[0],at-root[0])
    assert data[:root[0]]==raw[:root[0]] and data[root[0]+4:len(raw)]==raw[root[0]+4:]
    return bytes(data)

def explicit_rate(raw,rate=30):
    assert rate in (30,60)
    fb=FB(raw);root=fb.table(fb.u32(0))
    assert root[0]
    info=fb.table(root[0]+fb.u32(root[0]))
    values=[fb.u32(info[i]) if i<len(info) and info[i] else 0 for i in range(3)]
    if values[2]:return raw,False
    assert values[1]>0
    data=bytearray(raw)
    while len(data)%2:data.append(0)
    vt=len(data);data.extend(struct.pack('<5H',10,16,4,8,12))
    while len(data)%4:data.append(0)
    at=len(data);data.extend(struct.pack('<i3I',at-vt,values[0],values[1],rate))
    struct.pack_into('<I',data,root[0],at-root[0])
    assert data[:root[0]]==raw[:root[0]] and data[root[0]+4:len(raw)]==raw[root[0]+4:]
    check=FB(data);new=check.table(at)
    assert [check.u32(p) for p in new]==[values[0],values[1],rate]
    return bytes(data),True
