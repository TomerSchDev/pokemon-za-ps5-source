"""Retain real Sword bone motion curves, converting centimetre translations to ZA metres.

GFBANM and TRANM share AnimationInfo/BoneAnimation layouts (PokeDocs). Root material/event fields
are hidden in the resulting TRANM; they need a separate material/event adapter.
"""
import struct
from source_archives import FB
from sword_animation_rate import explicit_rate


def convert_bone_animation(raw):
    data=bytearray(raw)
    fb=FB(data)
    root=fb.u32(0)
    root_fields=fb.table(root)
    if len(root_fields)<2 or not root_fields[1]:
        return None,dict(bone_tracks=0,material_only=True)
    bone_at=root_fields[1]+fb.u32(root_fields[1])
    bone_fields=fb.table(bone_at)
    count,pointer=fb.vec(bone_fields[0]) if bone_fields[0] else (0,0)
    converted=0
    for i in range(count):
        at=pointer+i*4
        fields=fb.table(at+fb.u32(at))
        if fields[0]:
            string_at=fields[0]+fb.u32(fields[0])
            length=fb.u32(string_at)
            data[string_at+4:string_at+4+length]=data[string_at+4:string_at+4+length].lower()
        if len(fields)<7 or not fields[5] or not fields[6]:
            continue
        kind=data[fields[5]]
        vector_fields=fb.table(fields[6]+fb.u32(fields[6]))
        if kind==1:
            vectors=[vector_fields[0]] if vector_fields[0] else []
        elif kind in (2,3,4):
            number,first=fb.vec(vector_fields[0 if kind==2 else 1])
            vectors=[first+j*12 for j in range(number)]
        elif kind==0:
            continue
        else:
            raise ValueError('Unknown source translation curve '+str(kind))
        for point in vectors:
            xyz=struct.unpack_from('<3f',data,point)
            struct.pack_into('<3f',data,point,*(v*.01 for v in xyz))
            converted+=1
    if len(bone_fields)>1 and bone_fields[1]:
        fields=fb.table(bone_fields[1]+fb.u32(bone_fields[1]))
        if len(fields)>1 and fields[1]:
            at=fields[1]+28
            xyz=struct.unpack_from('<3f',data,at)
            struct.pack_into('<3f',data,at,*(v*.01 for v in xyz))
    vtable=root-struct.unpack_from('<i',data,root)[0]
    for field_id in range(2,len(root_fields)):
        struct.pack_into('<H',data,vtable+4+field_id*2,0)
    output,rate_added=explicit_rate(bytes(data))
    return output,dict(bone_tracks=count,translation_keys_scaled=converted,
                           animation_rate_defaulted=30 if rate_added else None,
                           source_bone_curves_preserved=True,material_events_converted=False)
