#define _POSIX_C_SOURCE 200809L
#include "worker.h"
#include <shaderc/shaderc.h>
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
extern uint64_t za_shaderc_cache_hash(const char *,size_t,int,uint32_t);
struct input { const char *name; const char *base; const char *out; };
static char *read_text(const char *path) {
    FILE*f=fopen(path,"rb");assert(f);assert(!fseek(f,0,SEEK_END));long n=ftell(f);assert(n>0);
    rewind(f);char *s=malloc((size_t)n+1);assert(s);assert(fread(s,1,(size_t)n,f)==(size_t)n);fclose(f);s[n]=0;return s;
}
static void *compile_input(void *arg) {
    struct input *in=arg;char path[2048];snprintf(path,sizeof path,"%s/%s",in->base,in->name);
    char *source=read_text(path);int stage=strstr(in->name,".vert")?0:1;
    shaderc_compiler_t c=shaderc_compiler_initialize();
    for(int i=0;i<3;i++) {
        shaderc_compilation_result_t r=shaderc_compile_into_spv(c,source,strlen(source),
            stage==0?shaderc_vertex_shader:shaderc_fragment_shader,in->name,"main",NULL);
        if(shaderc_result_get_compilation_status(r))fprintf(stderr,"%s\n",shaderc_result_get_error_message(r));
        assert(shaderc_result_get_compilation_status(r)==shaderc_compilation_status_success);
        snprintf(path,sizeof path,"%s/%02d-%s.spv",in->out,i,in->name);FILE*f=fopen(path,"wb");assert(f);
        size_t n=shaderc_result_get_length(r);assert(fwrite(shaderc_result_get_bytes(r),1,n,f)==n);assert(!fclose(f));
        shaderc_result_release(r);
    }
    shaderc_compiler_release(c);free(source);return NULL;
}
int main(int argc,char **argv) {
    assert(argc==3);assert(!mkdir(argv[2],0755));
    const char *names[]={"f120ba848ee181dc.vert","3198145b25b05558.frag","a1ef9d4227fc9202.vert","a2c55b2c0d2b389c.vert",
        "1ec6b1959cac7285.frag","e0988fdfe87fc048.vert","adce547ac7e3f484.frag","5deb7d0d2467a9be.vert",
        "67281a0d557ad6e9.vert","7362f8f494e987bf.vert","90d68f4f7edf55bc.frag","1fad545410e2cf35.vert"};
    struct input in[12];pthread_t threads[12];
    for(int i=0;i<12;i++){in[i]=(struct input){names[i],argv[1],argv[2]};assert(!pthread_create(&threads[i],NULL,compile_input,&in[i]));}
    for(int i=0;i<12;i++)pthread_join(threads[i],NULL);
    struct za_local_stats stats;za_local_compiler_stats(&stats);assert(stats.completed==36&&stats.slots_used==0&&stats.high_water<=8);
    const char *bad="#version 450\nthis is not GLSL\n";
    shaderc_compiler_t c=shaderc_compiler_initialize();
    shaderc_compilation_result_t r=shaderc_compile_into_spv(c,bad,strlen(bad),shaderc_fragment_shader,"bad","main",NULL);
    assert(shaderc_result_get_compilation_status(r)!=shaderc_compilation_status_success);shaderc_result_release(r);
    const char *compute="#version 450\nlayout(local_size_x=1) in; void main(){}\n";
    shaderc_compile_options_t o=shaderc_compile_options_initialize();
    shaderc_compile_options_set_target_env(o,shaderc_target_env_vulkan,shaderc_env_version_vulkan_1_2);
    r=shaderc_compile_into_spv(c,compute,strlen(compute),shaderc_compute_shader,"compute12","main",o);
    assert(shaderc_result_get_compilation_status(r)==shaderc_compilation_status_success);
    uint32_t version;memcpy(&version,shaderc_result_get_bytes(r)+4,4);assert(version==0x10500);
    char path[2048];snprintf(path,sizeof path,"%s/compute-vulkan12.spv",argv[2]);FILE *f=fopen(path,"wb");assert(f);
    size_t n=shaderc_result_get_length(r);assert(fwrite(shaderc_result_get_bytes(r),1,n,f)==n);fclose(f);
    shaderc_result_release(r);shaderc_compile_options_release(o);
    za_local_compiler_shutdown();
    printf("real adapter: 36 concurrent captured compiles, failure recovery, Vulkan 1.2/compute stage mapping passed\n");
    return 0;
}
