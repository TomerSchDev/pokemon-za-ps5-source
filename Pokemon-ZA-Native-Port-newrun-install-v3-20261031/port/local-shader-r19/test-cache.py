"""Exercise actual runtime cache/postprocessing code with the real local compiler."""
import hashlib,json,os,subprocess,sys
from pathlib import Path
root=Path(__file__).resolve().parent
project=root.parents[1]
work=Path(sys.argv[1])
glsl=Path('/home/tomer/ps5-za-native/shader-prewarm-research/host-build/glslang')
capture=project/'evidence/randomizer-shaders-20261028-041124Z'
manifest=json.loads((capture/'manifest.json').read_text())
source=(root/'shaders-r19.c').read_text()
source=source[source.index('static shaderc_shader_kind kind_of'):source.index('\nVkShaderModule vk_module')]
preamble='''#define _POSIX_C_SOURCE 200809L
#include "worker.h"
#include <assert.h>
#include <stdbool.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>
#include <shaderc/shaderc.h>
enum {STAGE_VERTEX=0,STAGE_FRAGMENT=1,STAGE_COMPUTE=5};
#define VK_API_VERSION_1_3 4206592u
#define ENV(name) getenv(name)
#define LOG(...) fprintf(stderr,__VA_ARGS__)
static struct {uint32_t api;} g_vkc={VK_API_VERSION_1_3};
'''
main=r'''
static const char *inputs[] = INPUTS;
static const char *base;
static void *request(void *arg) {
    size_t index=(size_t)arg;char path[2048];
    snprintf(path,sizeof path,"%s/%s",base,inputs[index]);FILE*f=fopen(path,"rb");assert(f);
    fseek(f,0,SEEK_END);long len=ftell(f);rewind(f);assert(len>0);
    char *src=malloc((size_t)len+1);assert(src);assert(fread(src,1,(size_t)len,f)==(size_t)len);fclose(f);src[len]=0;
    size_t n=0;int stage=strstr(inputs[index],".vert")?STAGE_VERTEX:STAGE_FRAGMENT;
    uint32_t *spv=vk_glsl_to_spirv(src,stage,inputs[index],&n);assert(spv&&n>5);free(spv);free(src);return NULL;
}
int main(int argc,char **argv) {
    assert(argc==3);base=argv[1];int expected=atoi(argv[2]);
    pthread_t threads[12];
    for(size_t i=0;i<12;i++)assert(!pthread_create(&threads[i],NULL,request,(void*)i));
    for(int i=0;i<12;i++)pthread_join(threads[i],NULL);
    struct za_local_stats s;za_local_compiler_stats(&s);
    assert(s.completed==(uint64_t)expected&&s.failed==0&&s.timed_out==0&&s.slots_used==0);
    for(size_t i=0;i<12;i++)request((void*)i);
    za_local_compiler_stats(&s);assert(s.completed==(uint64_t)expected);
    za_local_compiler_shutdown();
    printf("cache pass: expected=%d actual=%llu repeated cache hits did not compile\n",expected,(unsigned long long)s.completed);
    return 0;
}
'''.replace('INPUTS','{'+','.join(json.dumps(e['source']) for e in manifest)+'}')
fixture=work/'runtime-cache-test.c'
fixture.write_text(preamble+source+main)
flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-function','-Wno-unused-parameter',
       '-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread','-I'+str(root),'-I'+str(project/'port/shaderc-cache/include')]
subprocess.run(['/usr/bin/clang-21',*flags,'-c',str(fixture),'-o',str(work/'runtime-cache-test.o')],check=True)
libs=[glsl/'glslang'/('lib'+name+'.a') for name in ('glslang','MachineIndependent','GenericCodeGen','glslang-default-resource-limits')]
libs.append(glsl/'SPIRV/libSPIRV.a')
subprocess.run(['/usr/bin/clang++-21','-fsanitize=address,undefined','-pthread',
               *map(str,[work/'worker.o',work/'shaderc_cache.o',work/'compiler_adapter.o',work/'runtime-cache-test.o']),
               '-Wl,--start-group',*map(str,libs),'-Wl,--end-group','-o',str(work/'runtime-cache-test')],check=True)
cwd=work/'runtime-flow';cwd.mkdir()
env=dict(os.environ,ZA_SHADERC_CACHE_DIRS=str(cwd/'cache/spirv'),ZA_SHADERC_HOST_WAIT_MS='0',ZA_SHADERC_LOCAL='1',ASAN_OPTIONS='detect_leaks=1:abort_on_error=1')
def run(expected):
    subprocess.run([str(work/'runtime-cache-test'),str(capture),str(expected)],cwd=cwd,env=env,check=True,timeout=120)
def hashes():
    return {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (cwd/'cache/spirv').glob('*.spv')}
run(12)
first=hashes();assert len(first)==12
for p in (cwd/'cache/spirv').glob('*.spv'):
    subprocess.run(['spirv-val','--target-env','vulkan1.3',str(p)],check=True)
run(0);assert hashes()==first
corrupt=cwd/'cache/spirv'/next(iter(first));corrupt.write_bytes(b'broken'+bytes(30))
run(1);assert hashes()==first
assert not [p for p in (cwd/'cache/spirv').iterdir() if p.suffix!='.spv']
verification=dict(concurrent_cold_compiles=12,restarted_compiles=0,corrupt_cache_recompiled=1,
                  postprocessed_spirv_validated=12,cache_content_unchanged_after_repair=True,temporary_files_remaining=0,asan_ubsan=True)
(work/'cache-verification.json').write_text(json.dumps(verification,indent=2)+'\n')
print(json.dumps(verification,indent=2))
