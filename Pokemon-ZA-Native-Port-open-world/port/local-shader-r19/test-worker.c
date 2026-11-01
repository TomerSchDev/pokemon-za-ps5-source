#define _POSIX_C_SOURCE 200809L
#include "worker.h"
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static atomic_int active, peak, init_count, finish_count, slow_entered;
int za_glsl_init(void) { atomic_fetch_add(&init_count,1); return 1; }
void za_glsl_finish(void) { atomic_fetch_add(&finish_count,1); }
int za_glsl_compile_for_api(const char *src,int stage,uint32_t api,uint32_t **words,size_t *count,char *error,size_t size) {
    (void)stage; (void)api;
    int n=atomic_fetch_add(&active,1)+1;
    if(n>atomic_load(&peak))atomic_store(&peak,n);
    if(!strcmp(src,"SLOW"))atomic_store(&slow_entered,1);
    struct timespec delay={!strcmp(src,"SLOW")?1:0,!strcmp(src,"SLOW")?500000000:1000000};
    nanosleep(&delay,NULL);
    atomic_fetch_sub(&active,1);
    if(!strcmp(src,"FAIL")){snprintf(error,size,"expected failure");return 0;}
    *words=calloc(6,4); assert(*words); *count=6;
    (*words)[0]=0x07230203;(*words)[1]=0x10600;(*words)[5]=(uint32_t)src[0];
    return 1;
}
static void *caller(void *unused) {
    (void)unused;
    for(int i=0;i<12;i++) {
        uint32_t *w=NULL;size_t n=0;char e[256];struct za_local_metrics m;
        int ok=za_local_compile("GOOD",4,0,(1u<<22)|(3u<<12),&w,&n,e,sizeof e,&m);
        if(!ok)fprintf(stderr,"concurrent request failed: %s\n",e);
        assert(ok);
        assert(n==6&&w[5]=='G'&&m.compile_ms>=0&&m.queue_ms>=0);free(w);
    }
    return NULL;
}
int main(void) {
    uint32_t *w=NULL;size_t n=0;char e[256];
    assert(!za_local_compile("GOOD",ZA_LOCAL_MAX_SOURCE+1u,0,4206592,&w,&n,e,sizeof e,NULL));
    assert(!w&&!n);
    assert(!za_local_compile("G\0OD",4,0,4206592,&w,&n,e,sizeof e,NULL));
    assert(!za_local_compile("GOOD",4,5,4206592,&w,&n,e,sizeof e,NULL));
    pthread_t t[24];
    for(int i=0;i<24;i++)assert(!pthread_create(&t[i],NULL,caller,NULL));
    for(int i=0;i<24;i++)pthread_join(t[i],NULL);
    assert(atomic_load(&peak)==1&&atomic_load(&init_count)==1);
    assert(!za_local_compile("FAIL",4,0,4206592,&w,&n,e,sizeof e,NULL)&&!w&&!n);
    assert(strstr(e,"expected failure"));
    assert(za_local_compile("GOOD",4,0,4206592,&w,&n,e,sizeof e,NULL));free(w);
    char *slow=malloc(5);assert(slow);memcpy(slow,"SLOW",5);
    assert(!za_local_compile(slow,4,0,4206592,&w,&n,e,sizeof e,NULL));
    free(slow); /* The timed-out worker must own its own source copy. */
    assert(!w&&!n&&atomic_load(&slow_entered));
    struct za_local_stats s;za_local_compiler_stats(&s);
    assert(s.disabled&&s.timed_out==1&&s.high_water<=8&&s.high_water>1);
    assert(!za_local_compile("GOOD",4,0,4206592,&w,&n,e,sizeof e,NULL));
    za_local_compiler_shutdown();za_local_compiler_stats(&s);
    assert(s.slots_used==0&&atomic_load(&finish_count)==1);
    printf("worker concurrency/negative/recovery/abandoned-timeout passed; completed=%llu high_water=%u\n",(unsigned long long)s.completed,s.high_water);
    return 0;
}
