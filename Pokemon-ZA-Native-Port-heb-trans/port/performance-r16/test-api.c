#define _POSIX_C_SOURCE 200809L
#define ZA_R16_OPTIONS_FILE "test-options.txt"
#include "performance.c"
#include <assert.h>
static uint64_t t,p,b;
uint64_t plat_now_ns(void){return t;}
uint64_t renderer_present_count(void){return p;}
uint64_t za_renderer_build_activity(void){return b;}
int sceKernelDebugOutText(int ch,const char *s){(void)ch;(void)s;return 0;}
static void option(const char *v){FILE *f=fopen(ZA_R16_OPTIONS_FILE,"wb");assert(f);assert(fputs(v,f)>=0);assert(!fclose(f));za_performance_init();}
int main(void){
    option("pacing-baseline\n");assert(!strcmp(getenv("LARECOMP_PACE"),"1"));assert(getenv("ZA_R16_NO_KEY_MEMO"));
    option("renderer-baseline\n");assert(!strcmp(getenv("LARECOMP_PACE"),"0"));assert(getenv("ZA_R16_NO_CBUF_LEAN"));
    option("shadow\n");assert(getenv("ZA_R16_MEMO_SHADOW")&&!getenv("ZA_R16_NO_KEY_MEMO"));
    option("optimized\n");assert(!getenv("ZA_R16_MEMO_SHADOW")&&!getenv("ZA_R16_NO_CBUF_LEAN"));
    assert(!strcmp(getenv("LARECOMP_TICK_SCALE"),"1"));
    assert(za_title_frame_cfg(-2)==-2);
    za_performance_request(1);assert(za_title_frame_cfg(1)==0&&za_performance_status()==1);
    for(int i=0;i<600;i++){t+=22222222;++p;za_title_frame_cfg(1);}
    assert(za_performance_status()==2);
    za_performance_request(1);t+=16666667;++p;assert(za_title_frame_cfg(1)==0&&za_performance_status()==1);
    za_performance_request(0);assert(za_title_frame_cfg(-2)==-2&&za_performance_status()==0);
    assert(!remove(ZA_R16_OPTIONS_FILE));
    puts("PASS production timing API: four startup profiles, request/status, fallback, direct retry and restoration");
}
