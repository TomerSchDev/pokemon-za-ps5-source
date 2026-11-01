#define _POSIX_C_SOURCE 200809L
#include "worker.h"
#include "../shader-prewarm/compiler.h"
#include <errno.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef ZA_LOCAL_TIMEOUT_MS
#define ZA_LOCAL_TIMEOUT_MS 30000
#endif
#ifndef ZA_LOCAL_SKIP_WARMUP
#define ZA_LOCAL_SKIP_WARMUP 0
#endif
enum { FREE, QUEUED, ACTIVE, DONE };
struct job {
    int state, abandoned, ok, stage;
    uint32_t api;
    char *source;
    uint32_t *words;
    size_t count;
    char error[2048];
    double submitted, started, elapsed;
};
static pthread_once_t once = PTHREAD_ONCE_INIT;
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t changed = PTHREAD_COND_INITIALIZER;
static pthread_t thread;
static int started, stopping;
static struct job jobs[ZA_LOCAL_QUEUE_CAPACITY];
static unsigned queue[ZA_LOCAL_QUEUE_CAPACITY], head, queued;
static struct za_local_stats stats;

static double ms(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec*1000.0+t.tv_nsec/1000000.0;
}
static struct timespec deadline(void) {
    struct timespec t;
    clock_gettime(CLOCK_REALTIME, &t);
    t.tv_sec += ZA_LOCAL_TIMEOUT_MS/1000;
    t.tv_nsec += (ZA_LOCAL_TIMEOUT_MS%1000)*1000000L;
    if (t.tv_nsec >= 1000000000L) { t.tv_sec++; t.tv_nsec -= 1000000000L; }
    return t;
}
static void message(char *out, size_t size, const char *s) {
    if (out && size) snprintf(out, size, "%s", s);
}
static void release_job(struct job *j) {
    free(j->source); free(j->words);
    memset(j, 0, sizeof *j);
    stats.slots_used--;
    pthread_cond_broadcast(&changed);
}
static int warmup(void) {
    const char *sources[] = {
        "#version 450\nvoid main(){gl_Position=vec4(0.0,0.0,0.0,1.0);}\n",
        "#version 450\nlayout(location=0) out vec4 c; void main(){c=vec4(1.0);}\n",
        "#version 450\nlayout(local_size_x=1) in; void main(){}\n"
    };
    for (int stage=0; stage<3; ++stage) {
        uint32_t *words=NULL; size_t n=0; char error[1024];
        int ok=za_glsl_compile_for_api(sources[stage],stage,(1u<<22)|(3u<<12),&words,&n,error,sizeof error);
        free(words);
        if (!ok) { fprintf(stderr,"[shader-local] warmup failed: %s\n",error); return 0; }
    }
    return 1;
}
static void *run(void *unused) {
    (void)unused;
    double t=ms();
    int initialized=za_glsl_init();
    int ready=initialized && (ZA_LOCAL_SKIP_WARMUP || warmup());
    fprintf(stderr,"[shader-local] worker ready=%d init-warmup=%.3fms slots=%d max-source=%u\n",
            ready,ms()-t,ZA_LOCAL_QUEUE_CAPACITY,ZA_LOCAL_MAX_SOURCE);
    pthread_mutex_lock(&lock);
    stats.ready=ready;
    if (!ready) stats.disabled=1;
    pthread_cond_broadcast(&changed);
    for (;;) {
        while (!queued && !stopping) pthread_cond_wait(&changed,&lock);
        if (!queued && stopping) break;
        unsigned slot=queue[head]; head=(head+1)%ZA_LOCAL_QUEUE_CAPACITY; queued--;
        struct job *j=&jobs[slot];
        if (j->abandoned) { release_job(j); continue; }
        if (stats.disabled || stopping) {
            message(j->error,sizeof j->error,"local compiler unavailable");
            j->state=DONE; stats.failed++;
            pthread_cond_broadcast(&changed); continue;
        }
        j->state=ACTIVE; j->started=ms();
        pthread_mutex_unlock(&lock);
        uint32_t *words=NULL; size_t count=0; char error[2048]={0};
        int ok=za_glsl_compile_for_api(j->source,j->stage,j->api,&words,&count,error,sizeof error);
        double elapsed=ms()-j->started;
        if (ok && (!words || count<=5 || count>(16u<<20)/4 || words[0]!=0x07230203u)) {
            ok=0; message(error,sizeof error,"local compiler returned invalid module header/size");
        }
        pthread_mutex_lock(&lock);
        j->ok=ok; j->words=words; j->count=count; j->elapsed=elapsed;
        message(j->error,sizeof j->error,error);
        if (ok) stats.completed++; else stats.failed++;
        j->state=DONE;
        if (j->abandoned) release_job(j);
        pthread_cond_broadcast(&changed);
    }
    pthread_mutex_unlock(&lock);
    if (initialized) za_glsl_finish();
    return NULL;
}
static void start_once(void) {
    pthread_attr_t attr;
    int error=pthread_attr_init(&attr);
    if (!error) {
        error=pthread_attr_setstacksize(&attr,8u<<20);
        if (!error) error=pthread_create(&thread,&attr,run,NULL);
        pthread_attr_destroy(&attr);
    }
    pthread_mutex_lock(&lock);
    started=!error;
    if (error) stats.disabled=1;
    pthread_mutex_unlock(&lock);
}
int za_local_compiler_start(void) {
    pthread_once(&once,start_once);
    pthread_mutex_lock(&lock);
    int ok=started && !stats.disabled && !stopping;
    pthread_mutex_unlock(&lock);
    return ok;
}
int za_local_compile(const char *source,size_t length,int stage,uint32_t api,
                     uint32_t **words,size_t *count,char *error,size_t error_size,
                     struct za_local_metrics *metrics) {
    if (!words || !count) return 0;
    *words=NULL; *count=0;
    if (metrics) memset(metrics,0,sizeof *metrics);
    message(error,error_size,"");
    if (!source || !length || length>ZA_LOCAL_MAX_SOURCE || stage<0 || stage>2 ||
        (api!=((1u<<22)|(3u<<12)) && api!=((1u<<22)|(2u<<12))) || memchr(source,0,length)) {
        message(error,error_size,"unsupported source length, embedded NUL, stage or Vulkan version"); return 0;
    }
    if (!za_local_compiler_start()) { message(error,error_size,"local compiler disabled"); return 0; }
    struct timespec until=deadline();
    pthread_mutex_lock(&lock);
    while (stats.slots_used==ZA_LOCAL_QUEUE_CAPACITY && !stats.disabled && !stopping) {
        int e=pthread_cond_timedwait(&changed,&lock,&until);
        if (e) {
            stats.rejected++; pthread_mutex_unlock(&lock);
            message(error,error_size,"local compiler queue deadline exceeded"); return 0;
        }
    }
    if (stats.disabled || stopping) {
        stats.rejected++; pthread_mutex_unlock(&lock);
        message(error,error_size,"local compiler unavailable"); return 0;
    }
    unsigned slot=0;
    while (slot<ZA_LOCAL_QUEUE_CAPACITY && jobs[slot].state!=FREE) slot++;
    if (slot==ZA_LOCAL_QUEUE_CAPACITY) {
        stats.rejected++; pthread_mutex_unlock(&lock);
        message(error,error_size,"local compiler queue invariant"); return 0;
    }
    struct job *j=&jobs[slot];
    j->source=malloc(length+1);
    if (!j->source) {
        stats.rejected++; pthread_mutex_unlock(&lock);
        message(error,error_size,"local compiler source allocation failed"); return 0;
    }
    memcpy(j->source,source,length); j->source[length]=0;
    j->state=QUEUED; j->stage=stage; j->api=api; j->submitted=ms();
    queue[(head+queued)%ZA_LOCAL_QUEUE_CAPACITY]=slot; queued++;
    stats.submitted++; stats.slots_used++;
    if (stats.slots_used>stats.high_water) stats.high_water=stats.slots_used;
    pthread_cond_broadcast(&changed);
    while (j->state!=DONE) {
        int e=pthread_cond_timedwait(&changed,&lock,&until);
        if (e && j->state!=DONE) {
            /* The worker still owns this source and will free the slot. Do not
             * cancel glslang or free memory it may currently be reading. */
            j->abandoned=1; stats.timed_out++; stats.disabled=1;
            pthread_cond_broadcast(&changed); pthread_mutex_unlock(&lock);
            message(error,error_size,"local compiler deadline exceeded; disabled for this session"); return 0;
        }
    }
    int ok=j->ok;
    if (ok) { *words=j->words; *count=j->count; j->words=NULL; }
    else message(error,error_size,j->error[0]?j->error:"local compiler failed");
    if (metrics) {
        metrics->queue_ms=j->started>0?j->started-j->submitted:ms()-j->submitted;
        metrics->compile_ms=j->elapsed;
    }
    release_job(j);
    pthread_mutex_unlock(&lock);
    return ok;
}
void za_local_compiler_stats(struct za_local_stats *out) {
    pthread_mutex_lock(&lock); *out=stats; pthread_mutex_unlock(&lock);
}
void za_local_compiler_shutdown(void) {
    pthread_mutex_lock(&lock);
    stopping=1; pthread_cond_broadcast(&changed); int join=started;
    pthread_mutex_unlock(&lock);
    if (join) pthread_join(thread,NULL);
}
