"""Append target bone names to a native TRACL without dropping unknown fields.

Native root channel lists explicitly include the donor's bones. Merely renaming
the model prefix leaves absent limbs outside that list. This probe retains every
original field and name, appending the target nodes to the channel/name vectors.
"""
import struct
from source_archives import FB

def _string(data,field):
    fb=FB(data);at=field+fb.u32(field)
    return bytes(data[at+4:at+4+fb.u32(at)]).decode('utf-8')

def _root(data):
    fb=FB(data);outer=fb.table(fb.u32(0))
    return fb.table(outer[0]+fb.u32(outer[0]))

def root_names(data):
    fb=FB(data);root=_root(data);count,first=fb.vec(root[2])
    return [_string(data,first+i*4) for i in range(count)]

def target_names(target,root):
    from pathlib import Path
    folder=Path(target['model_path']).parent;stem=folder.name
    if target['source']=='violet':
        path=root/'build/violet-model-candidates-r1/romfs/ik_pokemon/data'/folder/(stem+'_base.tracl')
        return root_names(path.read_bytes())
    path=root/'build/all-species-r1/all-models/romfs/ik_pokemon/data'/folder/(Path(target['model_path']).stem+'.trskl')
    data=path.read_bytes();fb=FB(data);fields=fb.table(fb.u32(0))
    count,first=fb.vec(fields[1]);assert 0<count<10000
    names=[]
    for i in range(count):
        at=first+i*4;node=fb.table(at+fb.u32(at));assert node and node[0]
        names.append(_string(data,node[0]))
    return names

def channel_names(data,group):
    fb=FB(data);root=_root(data)
    channels=fb.table(root[1]+fb.u32(root[1]))
    if len(channels)<=group or not channels[group]:return [],None
    fields=fb.table(channels[group]+fb.u32(channels[group]))
    if len(fields)<2 or not fields[1]:return [],None
    count,first=fb.vec(fields[1]);names=[]
    for i in range(count):
        at=first+i*4;table=fb.table(at+fb.u32(at))
        if group==0:assert len(table)==1,'Unknown bone-channel name extensions; do not rewrite'
        names.append(_string(data,table[0]))
    return names,fields[1]

def channel_is_inclusion(data,group):
    fb=FB(data);root=_root(data)
    channels=fb.table(root[1]+fb.u32(root[1]))
    if len(channels)<=group or not channels[group]:return False
    fields=fb.table(channels[group]+fb.u32(channels[group]))
    return bool(fields and fields[0] and data[fields[0]])

def retarget(raw,node_names):
    data=bytearray(raw);modified=[];details={}
    def align():data.extend(b'\0'*((-len(data))%4))
    def string(value):
        align();at=len(data);payload=value.encode('utf-8')
        data.extend(struct.pack('<I',len(payload))+payload+b'\0');return at
    def names_vector(values,tables):
        align();vector=len(data)
        data.extend(struct.pack('<I',len(values))+b'\0'*(4*len(values)))
        for i,value in enumerate(values):
            if tables:
                align();vtable=len(data)
                data.extend(struct.pack('<HHH',6,8,4)+b'\0\0')
                table=len(data);data.extend(struct.pack('<iI',table-vtable,0))
                text=string(value);struct.pack_into('<I',data,table+4,text-(table+4))
                target=table
            else:target=string(value)
            field=vector+4+i*4;struct.pack_into('<I',data,field,target-field)
        return vector
    def replace_vector(field,old,requested,tables,label):
        values=list(dict.fromkeys([*old,*requested]));added=len(values)-len(old)
        if not added:return
        vector=names_vector(values,tables)
        struct.pack_into('<I',data,field,vector-field);modified.append(field)
        details[label]={'original':len(old),'added':added,'total':len(values)}
    root=_root(raw)
    replace_vector(root[2],root_names(raw),node_names,False,'node_registry')
    old,field=channel_names(raw,0)
    if channel_is_inclusion(raw,0):
        assert field is not None,'Native positive bone channel list absent'
        replace_vector(field,old,node_names,True,'base_bone_channels')
    else:details['base_bone_channels']={'negative_or_unrestricted_mask_preserved':True}
    output=bytes(data)
    assert set(node_names)<=set(root_names(output))
    if channel_is_inclusion(output,0):assert set(node_names)<=set(channel_names(output,0)[0])
    # All unknown native data is byte-for-byte preserved. Only the existing
    # vector offsets can differ in the original prefix; new data is appended.
    allowed={i for field in modified for i in range(field,field+4)}
    assert all(a==b or i in allowed for i,(a,b) in enumerate(zip(raw,output)))
    return output,details
