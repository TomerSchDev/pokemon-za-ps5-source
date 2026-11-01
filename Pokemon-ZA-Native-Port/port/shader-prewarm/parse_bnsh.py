"""Bounded BNSH 2.4 binary-program extraction; no executable guest code runs.

Format cross-checked against ShaderLibrary BnshLoader/Structs and actual records.
Uses the same NVN stage numbering and const_offset that runtime/objects.c uses.
"""
from pathlib import Path
import collections, hashlib, json, struct
from forecast import ROOT


def parse(blob):
    def val(off,fmt):
        if off<0 or off+struct.calcsize('<'+fmt)>len(blob):raise ValueError('field out of bounds')
        return struct.unpack_from('<'+fmt,blob,off)[0]
    def take(off,n):
        if off<=0 or n<0 or off+n>len(blob):raise ValueError('data out of bounds')
        return blob[off:off+n]
    if blob[:8]!=b'BNSH\0\0\0\0' or val(28,'I')!=len(blob):raise ValueError('BNSH header/size')
    block=val(22,'H')
    if take(block,4)!=b'grsc':raise ValueError('grsc header')
    count=val(block+28,'I');table=val(block+32,'Q')
    if count>200000 or table+count*64>len(blob):raise ValueError('variation array')
    # BNSH pointer order: vertex, tess control/eval, geometry, fragment, compute.
    stage_map=[0,3,4,2,1,5]
    for index in range(count):
        entry=table+index*64;program=val(entry+16,'Q')
        if not program:yield dict(index=index,stages={},missing_binary=True);continue
        stages={}
        for i,stage in enumerate(stage_map):
            descriptor=val(program+8+8*i,'Q')
            if not descriptor:continue
            ctl_off=val(descriptor+8,'Q');code_off=val(descriptor+16,'Q')
            code_size=val(descriptor+24,'I');ctl_size=val(descriptor+28,'I')
            if code_size>4<<20 or ctl_size>1<<20:raise ValueError('shader exceeds bounds')
            code=take(code_off,code_size);control=take(ctl_off,ctl_size)
            if ctl_size<0x728:raise ValueError('control block too small')
            sph=(struct.unpack_from('<I',code,0x30)[0]>>10)&15
            actual={1:0,5:1,4:2,2:3,3:4}.get(sph,5) if code[:4]==b'\x78\x56\x34\x12' else 5
            if actual!=stage:raise ValueError(f'stage mismatch {stage} != {actual}')
            const_off=struct.unpack_from('<I',control,0x700)[0]
            if not const_off:const_off=min(code_size,0x10000)
            if not 0<const_off<=code_size:raise ValueError('const_offset outside bytecode')
            header=0x100 if stage==5 and code[:4]==b'\x79\x56\x34\x12' else 0 if stage==5 else 0x80
            if const_off<header+16:raise ValueError('shader code too short')
            stages[str(stage)]=dict(code=code,control=control,const_offset=const_off,
                code_size=code_size,code_sha256=hashlib.sha256(code).hexdigest(),
                control_sha256=hashlib.sha256(control).hexdigest())
        yield dict(index=index,stages=stages)


def main():
    private=ROOT/'private-data/offline-shaders-20261028';raw=private/'programs';raw.mkdir(exist_ok=True)
    evidence=ROOT/'evidence/offline-shaders-20261028';records=[];failures=[];stages=collections.Counter()
    for path in sorted((private/'bnsh').glob('*.bnsh')):
        try:
            variations=list(parse(path.read_bytes()))
            for v in variations:
                for stage,s in v['stages'].items():
                    stages[stage]+=1
                    for key,suffix in (('code','bin'),('control','ctl')):
                        dest=raw/(s[key+'_sha256']+'.'+suffix)
                        if not dest.exists():dest.write_bytes(s[key])
                        del s[key]
                records.append(dict(bnsh_sha256=path.stem,**v))
        except Exception as e:failures.append(dict(bnsh=path.name,error=str(e)))
    manifest=dict(schema=1,variations=records,failures=failures,stage_references=dict(stages))
    (evidence/'programs.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(dict(variations=len(records),unique_codes=len(list(raw.glob('*.bin'))),stages=dict(stages),failures=failures),indent=2))


if __name__=='__main__':main()
