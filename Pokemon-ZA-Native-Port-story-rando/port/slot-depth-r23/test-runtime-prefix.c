#define _POSIX_C_SOURCE 200809L
#include <assert.h>
#include <errno.h>
#include <pthread.h>
#include <setjmp.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include "slot-policy.h"
#define SUBS ZA_SLOT_DEPTH_CAPACITY
#define CQ_MAX 64
typedef struct {VkCommandBuffer main,upload;bool main_begun,upload_begun,ts;uint64_t seq;VkDescriptorPool pools[16];int npools,cur_pool;} Sub;
typedef struct {VkQueryPool pool;uint32_t n;uint64_t seq;uint64_t *out[CQ_MAX];} CounterQ;
typedef struct {uint64_t size;} Chunk;
static Sub subs[SUBS];static CounterQ cq[SUBS];static int cur_sub,nchunks;
static Chunk chunks[32];static uint64_t submit_seq,prof_gpu;
static VkQueryPool prof_qp=(VkQueryPool)(uintptr_t)99;
static struct {VkDevice dev;VkCommandPool pool;VkSemaphore timeline;struct {struct {double timestampPeriod;} limits;} props;} g_vk;
static pthread_mutex_t seq_lock=PTHREAD_MUTEX_INITIALIZER,cq_lock=PTHREAD_MUTEX_INITIALIZER,za_sq_lock=PTHREAD_MUTEX_INITIALIZER;
static struct {unsigned lists,ncbs;} za_sq;
typedef enum {ZA_SUB_INTERNAL,ZA_SUB_SWITCH} ZaSubmitReason;
static ZaSubmitReason za_submit_reason;
static bool in_pass,za_submit_defer,za_immutable_enabled;
static unsigned za_batch_limit=4,prep_flags;
static const char *wait_why;
static unsigned query_result_calls,reset_pool_calls,flush_calls,resolve_calls,budget_calls,alloc_calls,fail_alloc;
static unsigned live_pools,live_buffers,live_queries;
static uint64_t next_handle=100,completed=0,clock_ns=1,budget_pool=UINT64_C(12)<<30,budget_extent=UINT64_C(4)<<30,budget_driver=UINT64_C(1)<<30;
static bool fail_completion,fail_drain,fail_wait,fail_second_budget,catch_fatal;
static jmp_buf fatal_jump;
static char last_log[2048];
#define LOG(...) ((void)snprintf(last_log,sizeof last_log,__VA_ARGS__))
#define FATAL(...) do {LOG(__VA_ARGS__);assert(catch_fatal);longjmp(fatal_jump,1);} while(0)
static uint64_t SDL_GetTicksNS(void){return ++clock_ns;}
static unsigned za_preparation_profile_flags(void){return prep_flags;}
static void za_submission_configure(void){}
static void za_submission_flush_to(uint64_t seq,ZaSubmitReason reason){(void)seq;(void)reason;}
static void renderer_flush(void){++flush_calls;if(!fail_drain)completed=submit_seq;}
uint64_t renderer_fence_seq(void);
static void cq_resolve_done(uint64_t done){
    pthread_mutex_lock(&cq_lock);++resolve_calls;
    for(unsigned i=0;i<SUBS;i++)if(cq[i].n && cq[i].seq<=done)cq[i].n=0;
    pthread_mutex_unlock(&cq_lock);
}
static void vk_wait_seq(uint64_t target){if(!fail_wait && completed<target)completed=target;clock_ns+=100;}
VKAPI_ATTR VkResult VKAPI_CALL vkGetSemaphoreCounterValue(VkDevice d,VkSemaphore sem,uint64_t *v){
    (void)d;(void)sem;if(fail_completion)return VK_ERROR_DEVICE_LOST;*v=completed;return VK_SUCCESS;
}
VKAPI_ATTR VkResult VKAPI_CALL vkGetQueryPoolResults(VkDevice d,VkQueryPool q,uint32_t first,uint32_t count,size_t n,void *out,VkDeviceSize stride,VkQueryResultFlags flags){
    (void)d;(void)q;(void)flags;assert(first+count<=SUBS*2 && count==2 && n==16 && stride==8);
    ++query_result_calls;((uint64_t*)out)[0]=10;((uint64_t*)out)[1]=20;return VK_SUCCESS;
}
VKAPI_ATTR VkResult VKAPI_CALL vkResetDescriptorPool(VkDevice d,VkDescriptorPool p,VkDescriptorPoolResetFlags flags){
    (void)d;(void)p;assert(!flags);++reset_pool_calls;return VK_SUCCESS;
}
static bool allocation_failed(void){return ++alloc_calls==fail_alloc;}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateDescriptorPool(VkDevice d,const VkDescriptorPoolCreateInfo *i,const VkAllocationCallbacks *a,VkDescriptorPool *out){
    (void)d;assert(!a && i->maxSets==8192 && i->poolSizeCount==5);assert(i->pPoolSizes[0].descriptorCount==32768);
    if(allocation_failed()){*out=(VkDescriptorPool)(uintptr_t)0xdead;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
    *out=(VkDescriptorPool)(uintptr_t)++next_handle;++live_pools;return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyDescriptorPool(VkDevice d,VkDescriptorPool p,const VkAllocationCallbacks *a){(void)d;assert(p&&!a&&live_pools);--live_pools;}
VKAPI_ATTR VkResult VKAPI_CALL vkAllocateCommandBuffers(VkDevice d,const VkCommandBufferAllocateInfo *i,VkCommandBuffer *out){
    (void)d;assert(i->commandBufferCount==1 && i->level==VK_COMMAND_BUFFER_LEVEL_PRIMARY);
    if(allocation_failed()){*out=(VkCommandBuffer)(uintptr_t)0xdead;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
    *out=(VkCommandBuffer)(uintptr_t)++next_handle;++live_buffers;return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL vkFreeCommandBuffers(VkDevice d,VkCommandPool p,uint32_t n,const VkCommandBuffer *b){(void)d;(void)p;assert(n==1&&*b&&live_buffers);--live_buffers;}
VKAPI_ATTR VkResult VKAPI_CALL vkCreateQueryPool(VkDevice d,const VkQueryPoolCreateInfo *i,const VkAllocationCallbacks *a,VkQueryPool *out){
    (void)d;assert(!a&&i->queryCount==CQ_MAX);assert(pthread_mutex_trylock(&cq_lock)==EBUSY);
    if(allocation_failed()){*out=(VkQueryPool)(uintptr_t)0xdead;return VK_ERROR_OUT_OF_DEVICE_MEMORY;}
    *out=(VkQueryPool)(uintptr_t)++next_handle;++live_queries;return VK_SUCCESS;
}
VKAPI_ATTR void VKAPI_CALL vkDestroyQueryPool(VkDevice d,VkQueryPool p,const VkAllocationCallbacks *a){
    (void)d;assert(p&&!a&&live_queries);assert(pthread_mutex_trylock(&cq_lock)==EBUSY);--live_queries;
}
void radv_ps5_winsys_heap_usage(uint64_t *pool,uint64_t *extent,uint64_t *driver){
    ++budget_calls;*pool=budget_pool;*extent=fail_second_budget&&budget_calls==2?1:budget_extent;*driver=budget_driver;
}
#include "slot-state.inc"
#include "slot-runtime.inc"
/* The test generator appends the actual candidate sub() and fence getter. */
