"""WSL offline translation with the installed runtime's exact Maxwell translator.

Content hashes must match runtime source hashes; no approximate shader replacement.
Produces baseline float vertex/render-target variants plus optional flip/depth variants.
"""
from pathlib import Path
import argparse, collections, ctypes, hashlib, json, os, shutil, time
from forecast import ROOT

WORK=Path('/home/tomer/ps5-za-native/shader-prewarm-research/offline')


def cache_hash(source,stage):
    h=(0xcbf29ce484222325 ^ stage)+3
    for c in source:h=((h^c)*0x100000001B3)&0xffffffffffffffff
    return f'{h:016x}'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expand',action='store_true')
    p.add_argument('--manifest',default='programs.json',choices=('programs.json','programs-combined.json'))
    a=p.parse_args()
    for key in ('LARECOMP_SAVE_MSL',):os.environ.pop(key,None)
    lib=ctypes.CDLL(str(WORK/'libza_translate.so'))
    u=ctypes.c_uint;sz=ctypes.c_size_t
    lib.za_translate.argtypes=[ctypes.c_char_p,sz,ctypes.c_int,u,u,u,u,u,ctypes.POINTER(u),ctypes.POINTER(u),ctypes.c_char_p,sz]
    lib.za_translate.restype=ctypes.c_void_p
    lib.za_translate_free.argtypes=[ctypes.c_void_p]
    evidence=ROOT/'evidence/offline-shaders-20261028';raw=ROOT/'private-data/offline-shaders-20261028/programs'
    source_dir=WORK/'sources';source_dir.mkdir(exist_ok=True)
    programs=json.loads((evidence/a.manifest).read_bytes())['variations']
    known={}
    for folder in list((ROOT/'evidence').glob('randomizer-shaders-*'))+list((ROOT/'evidence').glob('title-r11-shaders-*')):
        for ext in ('vert','frag','comp'):
            for path in folder.glob('*.'+ext):
                key=path.stem;digest=hashlib.sha256(path.read_bytes()).hexdigest()
                if key in known:assert known[key]==digest
                known[key]=digest
    existing={p.stem for p in (ROOT/'artifacts/randomizer-r15/PPSA91762/cache/spirv').glob('*.spv')}
    for item in json.loads((ROOT/'evidence/randomizer-shaders-20261028-041124Z/manifest.json').read_bytes()):existing.add(item['source'].split('.')[0])
    memo={};sources={};failures=[];references=[];start=time.monotonic();last=start
    journal=WORK/'translation-journal.jsonl'
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:item=json.loads(line)
            except json.JSONDecodeError:continue
            if item.get('key') and not (source_dir/(item['key']+'.'+item['ext'])).exists():continue
            memo[tuple(item['signature'])]=item
            if item.get('key'):sources[item['key']]=item
    jf=journal.open('a',buffering=1)
    def translate(s,stage,mask=0,flip=0,depth=0):
        sig=(stage,s['code_sha256'],s['const_offset'],mask,flip,depth,0,0)
        if sig in memo:return memo[sig]
        if shutil.disk_usage('/mnt/c').free < 2 << 30:raise RuntimeError('C: free space below 2 GiB; outputs preserved')
        code=(raw/(s['code_sha256']+'.bin')).read_bytes()
        assert hashlib.sha256(code).hexdigest()==s['code_sha256']
        out=u();attrs=u();error=ctypes.create_string_buffer(1024)
        ptr=lib.za_translate(code,s['const_offset'],stage,mask,flip,depth,0,0,ctypes.byref(out),ctypes.byref(attrs),error,len(error))
        item=dict(signature=sig,out_mask=out.value,attr_mask=attrs.value,stage=stage)
        if ptr:
            source=ctypes.string_at(ptr);lib.za_translate_free(ptr)
            digest=hashlib.sha256(source).hexdigest();key=cache_hash(source,stage)
            ext={0:'vert',1:'frag',5:'comp'}[stage]
            item.update(key=key,ext=ext,source_sha256=digest,bytes=len(source),previous_key=key in existing,
                matches_recorded_source=key in known)
            if key in known:assert known[key]==digest,'Same runtime hash but different GLSL'
            if key in sources:assert sources[key]['source_sha256']==digest,'FNV collision'
            dest=source_dir/(key+'.'+ext)
            if dest.exists():assert hashlib.sha256(dest.read_bytes()).hexdigest()==digest
            else:dest.write_bytes(source)
            sources[key]=item
        else:item['error']=error.value.decode(errors='replace');failures.append(item)
        memo[sig]=item;jf.write(json.dumps(item)+'\n')
        return item
    try:
        for index,p in enumerate(programs):
            ss=p['stages'];pairs=[]
            if '0' in ss:
                vs=translate(ss['0'],0)
                if a.expand and vs.get('key'):
                    for flip,depth in ((0,1),(1,0),(1,1)):translate(ss['0'],0,flip=flip,depth=depth)
                if vs.get('key') and '1' in ss:
                    fs=translate(ss['1'],1,vs['out_mask']);pairs.append(dict(vertex=vs.get('key'),fragment=fs.get('key')))
            elif '1' in ss:failures.append(dict(bnsh=p['bnsh_sha256'],index=p['index'],error='Fragment without paired vertex'))
            if '5' in ss:
                cs=translate(ss['5'],5);pairs.append(dict(compute=cs.get('key')))
            unsupported=sorted(set(ss)-{'0','1','5'})
            if unsupported:failures.append(dict(bnsh=p['bnsh_sha256'],index=p['index'],error='Unsupported stages',stages=unsupported))
            references.append(dict(bnsh=p['bnsh_sha256'],index=p['index'],pairs=pairs))
            if time.monotonic()-last>15:
                print(json.dumps(dict(variations=index+1,total=len(programs),unique_sources=len(sources),translation_requests=len(memo),failures=len(failures))),flush=True);last=time.monotonic()
        report=dict(schema=1,complete=True,expanded=a.expand,source_manifest=a.manifest,build_id='b1f12fd919eae86ab8a978317677e64bce443d1f',
            sources=list(sources.values()),references=references,
            failures=[x for x in memo.values() if 'error' in x]+[x for x in failures if 'signature' not in x],
            counts=dict(variations=len(programs),translation_requests=len(memo),unique_sources=len(sources),
                previous_keys=sum(x['previous_key'] for x in sources.values()),new_keys=sum(not x['previous_key'] for x in sources.values()),
                recorded_source_matches=sum(x['matches_recorded_source'] for x in sources.values()),recorded_sources_available=len(known)),
            elapsed_seconds=round(time.monotonic()-start,1),
            constraints=dict(gmem_base='7676b00000',gmem_size='c9500000',vulkan='1.3',float_vertex_attributes=True,
                float_render_targets=True,stencil_slots=0,sint_slots=0,xfb=False,flip_x=False),
            limits=['Sources are candidates until compiled and spirv-val validated.',
                'Dynamic integer textures/targets, integer vertex inputs and transform feedback variants are not exhaustively enumerated.',
                'SPIR-V compilation does not prebuild PS5 driver pipelines.'])
        target=evidence/'translation.json';tmp=target.with_suffix('.new');tmp.write_text(json.dumps(report,indent=2));tmp.replace(target)
        print(json.dumps(dict(counts=report['counts'],failures=len(report['failures']),seconds=report['elapsed_seconds']),indent=2))
    finally:jf.close()


if __name__=='__main__':main()
