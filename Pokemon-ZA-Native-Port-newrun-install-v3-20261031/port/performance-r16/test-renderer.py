"""Compile tests of the actual changed helpers, comparing to r15 operations.
Vulkan handles/device capabilities are host mocks; no GPU validation is claimed.
"""
from pathlib import Path
import subprocess, sys
root=Path(__file__).resolve().parents[2]
work=Path(sys.argv[1]); out=work/'host-tests';out.mkdir(exist_ok=True)
old=(work/'exec-r15-original.c').read_text()
new=(work/'source/runtime/nvn/vulkan/exec.c').read_text()
def func(text,signature):
    a=text.index(signature); b=text.index('{',a); n=1;i=b+1
    while n:
        n+=(text[i]=='{')-(text[i]=='}');i+=1
    return text[a:i]+'\n'
def typedef(text,name):
    b=text.index('} '+name+';')+len('} '+name+';')
    a=text.rindex('typedef struct {',0,b)
    return text[a:b]+'\n'
common='''#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <stdatomic.h>
#include <vulkan/vulkan.h>
#define ENV getenv
static uint64_t rng=0x1642f8a94fa33ull;
static uint32_t rand32(void) { rng^=rng<<13; rng^=rng>>7; rng^=rng<<17; return (uint32_t)rng; }
'''

# Exact original key calculation vs the actual r16 dependency capture.
code=common+'''
typedef struct { uint32_t attr_mask,out_mask; } ShaderInfo;
typedef struct { ShaderInfo *vi,*fi; } Prog;
typedef struct { uint32_t format; } Tex;
static struct { bool no_eds1,no_eds2; } g_vkc;
static struct { bool divisor; } g_vk;
static struct {
    uint32_t attrib[16],stream[16][2],channel_mask;
    int nattrib,nstream;
    struct { Tex *color[8]; } rt;
    uint8_t color_state[4],blend[8][8],ms[24],poly[4],depth_clamp;
    bool prim_restart;
} st;
static VkFormat pass_color[8],pass_depth,pass_stencil;
static uint32_t pass_ncolor,pass_samples;
static uint64_t za_key_generation=1;
static VkFormat vertex_format(uint32_t f) { return (VkFormat)(100+f); }
static VkFormat vertex_format_supported(VkFormat f) { return f; }
#define ZERO_BINDING 16
'''
code+=typedef(old,'FixedState')+typedef(old,'PipeKey')+typedef(new,'ZaPipeInput')
code+=func(old,'static int rt_kind(')+func(new,'static void za_pipe_input(')
a=old.index('    PipeKey k;',old.index('    // ---- pipeline\n'))
b=old.index('    uint64_t ph =',a)
body=old[a:b].replace('    FixedState fx;\n    fixed_state(&fx, vkey.flip_x, vkey.flip_y, native, topo);\n','')
code+='static PipeKey reference(Prog *pr,uint8_t cls,bool native,uint32_t mode,FixedState fx) {\n'+body+'\nreturn k;\n}\n'
code+='''
static void randomize(Tex *rt) {
    for(unsigned i=0;i<sizeof st;i++) ((unsigned char*)&st)[i]=(unsigned char)rand32();
    st.nattrib=rand32()%17; st.nstream=rand32()%17;
    for(int i=0;i<8;i++) { rt[i].format=rand32()%64;st.rt.color[i]=rand32()%2?&rt[i]:NULL;pass_color[i]=(VkFormat)(rand32()%127); }
    pass_ncolor=rand32()%9;pass_samples=1u<<(rand32()%4);pass_depth=(VkFormat)(rand32()%127);pass_stencil=(VkFormat)(rand32()%127);
    st.prim_restart=(rand32()&1)!=0;
    g_vkc.no_eds1=(rand32()&1)!=0;g_vkc.no_eds2=(rand32()&1)!=0;g_vk.divisor=true;
}
int main(void) {
    ShaderInfo vi={0xffff,0},fi={0,0xffffffff};Prog pr={&vi,&fi};Tex rt[8];
    unsigned hits=0,misses=0;
    for(int iter=0;iter<40000;iter++) {
        randomize(rt);FixedState fx;for(unsigned i=0;i<sizeof fx;i++)((uint8_t*)&fx)[i]=(uint8_t)rand32();
        uint8_t cls=rand32()%3;bool native=(rand32()&1)!=0;uint32_t mode=rand32()%10;
        ZaPipeInput a,b;za_pipe_input(&a,&pr,cls,native,mode,&fx);PipeKey before=reference(&pr,cls,native,mode,fx);
        switch(iter%16) {
        case 0: break;
        case 1: st.attrib[rand32()%16]^=1u<<(rand32()%32);break;
        case 2: st.stream[rand32()%16][rand32()%2]^=1;break;
        case 3: st.channel_mask^=1u<<(rand32()%32);break;
        case 4: st.blend[rand32()%8][rand32()%8]^=1;break;
        case 5: st.rt.color[rand32()%8]=NULL;break;
        case 6: rt[rand32()%8].format^=1;break;
        case 7: pass_color[rand32()%8]=(VkFormat)rand32();break;
        case 8: pass_depth=(VkFormat)rand32();pass_stencil=(VkFormat)rand32();break;
        case 9: st.poly[2]^=1;st.ms[12]^=1;break;
        case 10: st.depth_clamp^=1;st.prim_restart=!st.prim_restart;break;
        case 11: st.nattrib=rand32()%17;st.nstream=rand32()%17;break;
        case 12: cls=rand32()%3;mode=rand32()%10;break;
        case 13: ((uint8_t*)&fx)[rand32()%sizeof fx]^=1;break;
        case 14: ++za_key_generation;break;
        case 15: pass_samples=1u<<(rand32()%4);pass_ncolor=rand32()%9;break;
        }
        za_pipe_input(&b,&pr,cls,native,mode,&fx);PipeKey after=reference(&pr,cls,native,mode,fx);
        if(!memcmp(&a,&b,sizeof a)){assert(!memcmp(&before,&after,sizeof before));hits++;}else misses++;
    }
    assert(hits>1000&&misses>10000);
    printf("PASS pipeline dependencies: 40000 randomized original-key comparisons; hits=%u invalidations=%u\\n",hits,misses);
}
'''
(out/'pipeline-equivalence.c').write_text(code)

# Preserve the original bytewise shader-key hashing contract, including padding.
key_header=(work/'source/runtime/nvn/maxwell/shader.h').read_text()
code=common+typedef(key_header,'ShaderKey')+'''
typedef struct { struct { uint64_t code_addr; } stages[2]; } NvnProgram;
static uint64_t za_key_generation=1,za_prog_memo_hits;
static int za_memo_on(void) { return 1; }
'''
a=old.index('    uint64_t h =',old.index('static Prog *get_program('))
b=old.index('    uint32_t slot =',a)
code+='static uint64_t original_hash(NvnProgram *np,ShaderKey *vkey,ShaderKey *fkey) {\n'+old[a:b]+'return h;\n}\n'
a=new.index('    struct ZaProgramInput',new.index('static Prog *get_program('))
b=new.index('    Prog *p =',a)
code+='static uint64_t memo_hash(NvnProgram *np,ShaderKey *vkey,ShaderKey *fkey) {\n'+new[a:b]+'return h;\n}\n'
code+='''
int main(void) {
    NvnProgram np;ShaderKey v,f;
    for(int iter=0;iter<20000;iter++) {
        for(unsigned i=0;i<sizeof v;i++)((uint8_t*)&v)[i]=(uint8_t)rand32();
        for(unsigned i=0;i<sizeof f;i++)((uint8_t*)&f)[i]=(uint8_t)rand32();
        np.stages[0].code_addr=rand32();np.stages[1].code_addr=rand32();
        assert(original_hash(&np,&v,&f)==memo_hash(&np,&v,&f));
        assert(original_hash(&np,&v,&f)==memo_hash(&np,&v,&f));
        ((uint8_t*)&v)[iter%sizeof v]^=1;
        assert(original_hash(&np,&v,&f)==memo_hash(&np,&v,&f));
        f.sint_slots^=1;
        assert(original_hash(&np,&v,&f)==memo_hash(&np,&v,&f));
    }
    assert(za_prog_memo_hits>=20000);
    puts("PASS program hash: 80000 byte-exact comparisons against r15, padding mutations, repeated inputs and signed texture masks");
}
'''
(out/'program-equivalence.c').write_text(code)

# Graphics constant copies: every possible byte length, including partial rows,
# padding, both graphics stages, changed sources, submission and reboot lifetime.
code=common+'''
typedef struct { uint64_t addr,size; } Range;
typedef struct { uintptr_t buf; uint64_t off; void *ptr; } VkSpan;
static struct { Range sbuf[6][16]; } st;
static uint64_t za_key_generation=1,za_lean_hits,za_lean_copies,seq=1;
static uint8_t memory[0x800];static unsigned allocated;
static uint64_t vk_pending_seq(void){return seq;}
static VkSpan vk_transient_copy(const void* p,uint64_t size,uint64_t align){(void)align;memcpy(memory,p,size);++allocated;return (VkSpan){allocated,0,memory};}
'''+func(new,'static VkSpan za_driver_constants(')+'''
int main(void) {
    for(int stage=0;stage<2;stage++) for(uint64_t size=1;size<=2048;size++) {
        ++seq;for(int i=0;i<16;i++)st.sbuf[stage][i]=(Range){((uint64_t)rand32()<<32)|rand32(),rand32()};
        uint32_t original[512]={0};unsigned base=0x110+0x100*(stage==1?4:0);
        for(int i=0;i<16;i++){uint32_t *e=&original[(base+16*i)/4];e[0]=(uint32_t)st.sbuf[stage][i].addr;e[1]=(uint32_t)(st.sbuf[stage][i].addr>>32);e[2]=(uint32_t)st.sbuf[stage][i].size;}
        VkSpan a=za_driver_constants(stage,size);assert(!memcmp(a.ptr,original,size));
        VkSpan b=za_driver_constants(stage,size);assert(a.buf==b.buf);
        ++seq;b=za_driver_constants(stage,size);assert(a.buf!=b.buf);a=b;
        ++za_key_generation;b=za_driver_constants(stage,size);assert(a.buf!=b.buf);
    }
    assert(za_lean_hits==4096&&za_lean_copies==12288);
    puts("PASS driver constants: 4096 exact byte comparisons, partial rows, reuse, submission and reboot invalidation");
}
'''
(out/'constant-equivalence.c').write_text(code)

code=common.replace('static uint64_t rng=0x1642f8a94fa33ull;\nstatic uint32_t rand32(void) { rng^=rng<<13; rng^=rng>>7; rng^=rng<<17; return (uint32_t)rng; }\n','')
code+='static struct { bool no_eds1,no_eds2; } g_vkc;\n'
a=new.index('static const VkDynamicState DYN[]');b=new.index('// Fixed-function state',a)
code+=new[a:b]
a=new.index('static _Atomic uint64_t za_build_activity;');b=new.index('typedef struct Job',a)
code+=new[a:b]
code+='''
static void *stress(void *arg) {
    (void)arg;for(int i=0;i<10000;i++) {
        uint32_t n=0;const VkDynamicState *d=dyn_states(&n);
        assert(n==17u-(g_vkc.no_eds1?8u:0u)-(g_vkc.no_eds2?2u:0u));
        unsigned at=0;for(unsigned j=0;j<17;j++) if(!(g_vkc.no_eds1&&j>=7&&j<=14)&&!(g_vkc.no_eds2&&j>=15))assert(d[at++]==DYN[j]);
        za_build_begin();assert((uint32_t)za_renderer_build_activity()>0);za_build_end();
    }return NULL;
}
int main(void) {
    for(int cap=0;cap<4;cap++) {
        g_vkc.no_eds1=(cap&1)!=0;g_vkc.no_eds2=(cap&2)!=0;
        pthread_t t[16];for(int i=0;i<16;i++)assert(!pthread_create(&t[i],NULL,stress,NULL));
        for(int i=0;i<16;i++)assert(!pthread_join(t[i],NULL));
    }
    uint64_t a=za_renderer_build_activity();assert((uint32_t)a==0&&(a>>32)==640000);
    puts("PASS concurrency: 64 worker threads, 640000 dynamic-state reads and atomic queued-work completions, four capability combinations");
}
'''
(out/'thread-safety.c').write_text(code)

commands=[]
for name,path in [('policy',root/'port/performance-r16/test-policy.c'),('cache',root/'port/performance-r16/test-cache.c'),('api',root/'port/performance-r16/test-api.c'),
                  ('pipeline-equivalence',out/'pipeline-equivalence.c'),('program-equivalence',out/'program-equivalence.c'),('constant-equivalence',out/'constant-equivalence.c'),('thread-safety',out/'thread-safety.c')]:
    cmd=['clang-21','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread',
         '-I/home/tomer/ps5-za-native/PS5_Mesa/include','-I'+str(root/'port/performance-r16'),str(path),'-o',str(out/name)]
    subprocess.run(cmd,check=True)
    result=subprocess.run([str(out/name)],check=True,text=True,capture_output=True,timeout=60,cwd=out)
    print(result.stdout,end='');commands.append(result.stdout)
(root/'evidence/performance-r16/host-tests.txt').write_text(''.join(commands)+'Compiled -Wall -Wextra -Werror; AddressSanitizer and UndefinedBehaviorSanitizer enabled.\n')
