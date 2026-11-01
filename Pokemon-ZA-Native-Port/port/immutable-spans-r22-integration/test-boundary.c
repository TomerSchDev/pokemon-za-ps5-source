#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <pthread.h>

typedef uintptr_t VkBuffer;
typedef struct { VkBuffer buf; uint64_t off; uint8_t *ptr; } VkSpan;
#define VK_NULL_HANDLE ((VkBuffer)0)
static uint8_t arena[65536];
static uint64_t pending=1,used,allocations;
static uint64_t vk_pending_seq(void){return pending;}
static VkSpan vk_transient_copy(const void *data,uint64_t size,uint64_t align) {
    used=(used+align-1)&~(align-1);assert(used+size<=sizeof arena);
    VkSpan span={1,used,arena+used};memcpy(span.ptr,data,size);used+=size;++allocations;return span;
}
static void test_log(const char *fmt,...){(void)fmt;}
#define LOG(...) test_log(__VA_ARGS__)
#include "runtime/nvn/vulkan/za_immutable_spans_r22.inc"

static pthread_mutex_t exec_lock,za_sq_lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_t owner;
static unsigned depth,lock_calls;
static void owned(void){assert(depth && pthread_equal(owner,pthread_self()));}
static void exec_lock_take(void) {
    pthread_mutex_lock(&exec_lock);
    if(!depth)owner=pthread_self();else assert(pthread_equal(owner,pthread_self()));
    ++depth;++lock_calls;
}
static void exec_lock_give(void){owned();--depth;pthread_mutex_unlock(&exec_lock);}
typedef enum { ZA_SUB_NORMAL,ZA_SUB_SWITCH } ZaSubmitReason;
static ZaSubmitReason za_submit_reason=ZA_SUB_NORMAL;
static bool za_submit_defer,in_pass;
static struct {unsigned ncbs,lists;} za_sq;
static uint64_t completed=10,fenced=10;
static unsigned flushes,step;
static void za_submission_configure(void){owned();step=0;}
static void renderer_flush(void){owned();assert(za_submit_reason==ZA_SUB_SWITCH && step==0);step=1;++flushes;}
static void za_submission_flush_to(uint64_t seq,ZaSubmitReason why){owned();assert(seq==UINT64_MAX && why==ZA_SUB_SWITCH && step==1);step=2;}
static uint64_t renderer_fence_seq(void){owned();assert(za_submit_reason==ZA_SUB_NORMAL && step==2);step=3;return fenced;}
static uint64_t vk_completed_seq(void){owned();assert(step==3);step=4;return completed;}
#include "runtime/nvn/vulkan/za_immutable_boundary_r22.inc"
/* This file is extracted from the modified real objects.c, not a test double. */
#include "extracted-immutable-wrapper.inc"

static void *competing_controls(void *arg) {
    uintptr_t n=(uintptr_t)arg;
    for(unsigned i=0;i<40;++i) {
        assert(za_immutable_spans_switch((i+n)&1 ? "on":"off",100+i)==((i+n)&1 ? 2:1));
        assert(za_immutable_spans_flags()<=1);
    }
    return NULL;
}
int main(void) {
    pthread_mutexattr_t attr;assert(!pthread_mutexattr_init(&attr));
    assert(!pthread_mutexattr_settype(&attr,PTHREAD_MUTEX_RECURSIVE));
    assert(!pthread_mutex_init(&exec_lock,&attr));assert(!pthread_mutexattr_destroy(&attr));
    assert(!za_immutable_spans_flags() && !flushes && !za_immutable_enabled);
    assert(za_immutable_spans_switch(NULL,1)==-1 && za_immutable_spans_switch("ON",1)==-1);
    assert(za_immutable_spans_switch("on",0)==-3 && !flushes);
    za_submit_defer=true;assert(za_immutable_spans_switch("on",1)==-3);za_submit_defer=false;
    in_pass=true;assert(za_immutable_spans_switch("on",1)==-3);in_pass=false;assert(!flushes);
    completed=9;assert(za_immutable_spans_switch("on",1)==-3 && !za_immutable_spans_flags());
    assert(za_submit_reason==ZA_SUB_NORMAL);completed=10;
    za_sq.ncbs=1;assert(za_immutable_spans_switch("on",1)==-3 && !za_immutable_spans_flags());za_sq.ncbs=0;
    za_sq.lists=1;assert(za_immutable_spans_switch("on",1)==-3 && !za_immutable_spans_flags());za_sq.lists=0;
    assert(za_immutable_spans_switch("on",1)==2 && za_immutable_spans_flags()==1);
    static const uint8_t zeros[256];
    exec_lock_take();
    VkSpan a=za_immutable_span_copy(ZA_IMM_VERTEX_ZERO,zeros,256,16);
    VkSpan b=za_immutable_span_copy(ZA_IMM_VERTEX_ZERO,zeros,256,16);assert(a.off==b.off && allocations==1);
    /* Recursive getter under the already-held real executor lock must work. */
    assert(za_immutable_spans_flags()==1);exec_lock_give();
    completed=0;assert(za_immutable_spans_switch("off",2)==-3 && za_immutable_spans_flags()==1);completed=10;
    assert(za_immutable_spans_switch("off",3)==1 && !za_immutable_spans_flags());
    assert(!za_immutable_entries[ZA_IMM_VERTEX_ZERO][0].valid); /* all entries checked below */
    for(unsigned k=0;k<ZA_IMM_KINDS;++k)for(unsigned s=0;s<ZA_IMM_SLOTS;++s)assert(!za_immutable_entries[k][s].valid);
    assert(za_immutable_spans_switch("on",4)==2);
    exec_lock_take();b=za_immutable_span_copy(ZA_IMM_VERTEX_ZERO,zeros,256,16);exec_lock_give();
    assert(b.off!=a.off && allocations==2); /* old sequence number cannot revive a toggle-invalidated entry */
    pthread_t workers[2];unsigned before=flushes;
    assert(!pthread_create(&workers[0],NULL,competing_controls,(void*)(uintptr_t)0));
    assert(!pthread_create(&workers[1],NULL,competing_controls,(void*)(uintptr_t)1));
    for(unsigned i=0;i<2;++i)assert(!pthread_join(workers[i],NULL));
    assert(flushes==before+80 && !depth && lock_calls>=170);
    assert(za_immutable_spans_switch("off",999)==1);
    assert(!pthread_mutex_destroy(&exec_lock));assert(!pthread_mutex_destroy(&za_sq_lock));
    puts("r22 real backend+objects wrappers: default off, parser/frame/defer/pass guards, drain order/completion/queue checks, failed switch retention, toggle invalidation, recursive getter and competing control serialization passed");
}
