"""Exact runtime helper and control-defined XFB source generation (no game execution).

Writes only audit-extra files under shader-prewarm-research and audit-prefixed evidence.
Root controller may merge these source records after inspecting their provenance.
"""
from pathlib import Path
import ctypes, hashlib, json, subprocess, time
from forecast import ROOT
from translate_all import cache_hash

RUNTIME=Path('/home/tomer/ps5-za-native/title-r1-20261027/source')
WORK=Path('/home/tomer/ps5-za-native/shader-prewarm-research/audit-extra')

BRIDGE=r'''
char *audit_xfb(const unsigned char *code, size_t size, const unsigned char *count,
                const unsigned short *stride, unsigned *out_mask, char *error, size_t cap) {
    ShaderKey key = {0}; key.glsl = 1;
    for (int i=0;i<4;i++) { key.xfb_count[i]=count[i];key.xfb_stride[i]=stride[i]; }
    maxwell_gmem_base=0x7676b00000ull;maxwell_gmem_size=0xc9500000ull;
    ShaderInfo *info=maxwell_translate(code,size,STAGE_VERTEX,&key);
    if (!info) { snprintf(error,cap,"Translator allocation failed");return NULL; }
    *out_mask=info->out_mask;
    char *source=info->msl;
    if (!source) snprintf(error,cap,"%s",info->error);
    info->msl=NULL;maxwell_free(info);return source;
}
const char *audit_builtin(const char *name,int *stage) { return builtin_src(name,stage); }
char *audit_empty(void) {
    ShaderInfo *i=maxwell_empty_fragment();
    if (!i)return NULL;
    char *source=i->msl;i->msl=NULL;maxwell_free(i);return source;
}
void audit_free(char *p) { free(p); }
'''


def main():
    WORK.mkdir(exist_ok=True);sources=WORK/'sources';sources.mkdir(exist_ok=True)
    ev=ROOT/'evidence/offline-shaders-20261028'
    original=(RUNTIME/'runtime/nvn/vulkan/shaders.c').read_text()
    function=original[original.index('static const char *builtin_src('):original.index('\nVkShaderModule vk_builtin_shader(')]
    includes='#include "shader.h"\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n'
    includes+='const char smaa_hlsl_src[]=\n#include "smaa_hlsl.inc"\n;\n'
    c=WORK/'bridge.c';c.write_text(includes+function+BRIDGE)
    libpath=WORK/'libaudit.so'
    subprocess.run(['/usr/bin/clang-21','-O2','-fPIC','-shared','-Wall','-Wextra','-Werror','-Wno-unused-parameter',
                    '-I'+str(RUNTIME/'runtime/nvn/maxwell'),'-I'+str(RUNTIME/'build/ps5/inc'),str(c),
                    str(RUNTIME/'runtime/nvn/maxwell/translate.c'),'-lm','-o',str(libpath)],check=True)
    lib=ctypes.CDLL(str(libpath));u=ctypes.c_uint;sz=ctypes.c_size_t
    lib.audit_builtin.argtypes=[ctypes.c_char_p,ctypes.POINTER(ctypes.c_int)];lib.audit_builtin.restype=ctypes.c_void_p
    lib.audit_empty.restype=ctypes.c_void_p;lib.audit_free.argtypes=[ctypes.c_void_p]
    lib.audit_xfb.argtypes=[ctypes.c_char_p,sz,ctypes.POINTER(ctypes.c_ubyte),ctypes.POINTER(ctypes.c_ushort),
                             ctypes.POINTER(u),ctypes.c_char_p,sz];lib.audit_xfb.restype=ctypes.c_void_p
    known={}
    for folder in list((ROOT/'evidence').glob('randomizer-shaders-*'))+list((ROOT/'evidence').glob('title-r11-shaders-*')):
        for ext in ('vert','frag','comp'):
            for p in folder.glob('*.'+ext):known[p.stem]=hashlib.sha256(p.read_bytes()).hexdigest()
    existing={p.stem for p in (ROOT/'artifacts/randomizer-r15/PPSA91762/cache/spirv').glob('*.spv')}
    for x in json.loads((ROOT/'evidence/randomizer-shaders-20261028-041124Z/manifest.json').read_bytes()):
        existing.add(x['source'].split('.')[0])
    records=[];failures=[]
    def save(data,stage,signature,origin):
        key=cache_hash(data,stage);sha=hashlib.sha256(data).hexdigest();ext={0:'vert',1:'frag',5:'comp'}[stage]
        if key in known:assert known[key]==sha
        dest=sources/(key+'.'+ext)
        if dest.exists():assert dest.read_bytes()==data
        else:dest.write_bytes(data)
        records.append(dict(key=key,ext=ext,stage=stage,signature=signature,source_sha256=sha,bytes=len(data),
            previous_key=key in existing,matches_recorded_source=key in known,origin=origin,source_path=str(dest)))
    names=['present.vert','present.frag','texcopy.frag','depthcopy.frag','post.vert',
           'smaa_edge.frag','smaa_weight.frag','smaa_blend.frag','easu.frag','rcas.frag','clear.vert']
    names += ['clear.frag.'+kind+str(i) for kind in 'fiu' for i in range(8)]
    names += ['clear.frag.none']
    for name in names:
        stage=ctypes.c_int();ptr=lib.audit_builtin(name.encode(),ctypes.byref(stage));assert ptr
        save(ctypes.string_at(ptr),stage.value,['builtin',name,stage.value],dict(kind='builtin',name=name))
    ptr=lib.audit_empty();assert ptr
    save(ctypes.string_at(ptr),1,['empty_fragment',1],dict(kind='empty_fragment'));lib.audit_free(ptr)
    (ev/'audit-extra-helpers.json').write_text(json.dumps(records,indent=2))
    print(json.dumps(dict(helper_names=len(names)+1,helper_unique_sources=len({r['key'] for r in records}),
                         helper_new_keys=len({r['key'] for r in records if not r['previous_key']}))),flush=True)
    inputs=json.loads((ev/'audit-xfb-inputs.json').read_bytes())
    raw=ROOT/'private-data/offline-shaders-20261028/programs';last=time.monotonic()
    for index,s in enumerate(inputs):
        code=(raw/(s['code_sha256']+'.bin')).read_bytes();assert hashlib.sha256(code).hexdigest()==s['code_sha256']
        counts=(ctypes.c_ubyte*4)(*s['xfb_count']);strides=(ctypes.c_ushort*4)(*s['xfb_stride'])
        mask=u();err=ctypes.create_string_buffer(1024)
        ptr=lib.audit_xfb(code,s['const_offset'],counts,strides,ctypes.byref(mask),err,len(err))
        if ptr:
            sig=[0,s['code_sha256'],s['const_offset'],0,0,0,0,0,*s['xfb_count'],*s['xfb_stride']]
            save(ctypes.string_at(ptr),0,sig,dict(kind='xfb',control_sha256=s['control_sha256'],
                    counts=s['xfb_count'],strides=s['xfb_stride'],out_mask=mask.value));lib.audit_free(ptr)
        else:failures.append(dict(input=s,error=err.value.decode(errors='replace')))
        if time.monotonic()-last>15:
            print(json.dumps(dict(xfb=index+1,total=len(inputs),failures=len(failures))),flush=True);last=time.monotonic()
    report=dict(complete=True,records=records,failures=failures,counts=dict(helper_requests=len(names)+1,
        xfb_requests=len(inputs),unique_sources=len({r['key'] for r in records}),
        new_keys=len({r['key'] for r in records if not r['previous_key']})),
        provenance={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [RUNTIME/'runtime/nvn/vulkan/shaders.c',
            RUNTIME/'runtime/nvn/maxwell/translate.c',RUNTIME/'runtime/nvn/maxwell/shader.h',RUNTIME/'build/ps5/inc/smaa_hlsl.inc',c,libpath]},
        constraints=dict(gmem_base='7676b00000',gmem_size='c9500000',float_vertex_attributes=True,flip_y=False,
                         depth_minus_one=False,flip_x=False,stencil_slots=0,sint_slots=0))
    (ev/'audit-extra-sources.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(dict(counts=report['counts'],failures=len(failures)),indent=2),flush=True)


if __name__=='__main__':main()
