#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <pthread.h>
#include <vulkan/vulkan.h>
#define MAX_BIND 96
#define GMAP_BUFFER_INDEX 20
#define GFAST_BUFFER_INDEX 21
#define XFB_BUFFER_INDEX 22
#define TEXTYPE_2D 1
typedef struct { uint32_t set, binding; VkDescriptorType type; } VkBindingInfo;
#include "preparation.h"
static void test_log(const char *fmt, ...) { (void)fmt; }
#define LOG test_log
#include "counters.inc"
typedef struct { int ntex; } ShaderInfo;
typedef struct { VkBindingInfo binds[MAX_BIND]; int nbinds; ZaPrepRecipe prep; } Prog;
typedef struct { VkBuffer buf; VkDeviceSize off; void *ptr; } VkSpan;
static struct { VkDevice dev; } g_vk;
static float tex_sc[2][64][2], g_mirror_w;
static uint32_t tex_wh[2][64][2], gmap_tab[65][4];
static bool xfb_on, xm_draw;
static uint64_t xfb_addr[4], xfb_size[4], gwin_base, gwin_max, gmem_lo, xm_lo;
static VkBuffer xm_buf;
#define XM_SIZE 0x400000u
enum { DEDUPE_RSCALE_V, DEDUPE_RSCALE_F, DEDUPE_TINT };
typedef struct { uint32_t binding, type; uint64_t a, b, c; } Norm;
typedef struct { int slot; uint64_t size, align; uint8_t bytes[2048]; } Copy;
typedef struct { int what, stage, index; uint32_t x,y,z; } Event;
typedef struct {
    unsigned allocs, updates, n, ncopies, nevents;
    Norm writes[96]; Copy copies[96]; Event events[256];
    float scales[2][64][2]; uint32_t wh[2][64][2];
} Record;
static Record record;
static void event(int what,int stage,int index,uint32_t x,uint32_t y,uint32_t z) {
    assert(record.nevents < 256);
    record.events[record.nevents++] = (Event){what,stage,index,x,y,z};
}
static VkDescriptorSet vk_alloc_set(VkDescriptorSetLayout layout) {
    (void)layout; ++record.allocs; return (VkDescriptorSet)(uintptr_t)0x1234;
}
VKAPI_ATTR void VKAPI_CALL vkUpdateDescriptorSets(VkDevice dev,uint32_t n,const VkWriteDescriptorSet *w,uint32_t copies,const VkCopyDescriptorSet *c) {
    (void)dev; assert(!copies && !c); ++record.updates; record.n=n;
    assert(n<=96);
    for(uint32_t i=0;i<n;i++) {
        assert(w[i].sType==VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET && !w[i].pNext);
        assert(w[i].dstSet==(VkDescriptorSet)(uintptr_t)0x1234 && w[i].descriptorCount==1);
        assert(w[i].dstArrayElement==0 && !w[i].pTexelBufferView);
        Norm *v=&record.writes[i]; v->binding=w[i].dstBinding; v->type=w[i].descriptorType;
        if(w[i].pImageInfo) {
            assert(!w[i].pBufferInfo);
            v->a=(uint64_t)(uintptr_t)w[i].pImageInfo->sampler;
            v->b=(uint64_t)(uintptr_t)w[i].pImageInfo->imageView;
            v->c=w[i].pImageInfo->imageLayout;
        } else {
            assert(w[i].pBufferInfo);
            v->a=(uint64_t)(uintptr_t)w[i].pBufferInfo->buffer;
            v->b=w[i].pBufferInfo->offset;v->c=w[i].pBufferInfo->range;
        }
    }
}
static VkSampler vk_default_sampler(bool linear) { event(1,linear,0,0,0,0); return (VkSampler)(uintptr_t)(10+linear); }
static VkImageView vk_dummy_view(int type) { event(2,0,type,0,0,0); return (VkImageView)(uintptr_t)(100+type); }
static void texture_info(int stage,ShaderInfo *si,int i,VkDescriptorImageInfo *out,float sc[2],uint32_t wh[2]) {
    (void)si;event(3,stage,i,0,0,0);
    *out=(VkDescriptorImageInfo){(VkSampler)(uintptr_t)(200+i),(VkImageView)(uintptr_t)(400+stage*80+i),VK_IMAGE_LAYOUT_GENERAL};
    sc[0]=(float)(i+1)/2;sc[1]=(float)(stage+1)/3;wh[0]=64u+(unsigned)i;wh[1]=48u+(unsigned)stage;
}
static VkDescriptorBufferInfo cbuf_info(int stage,ShaderInfo *si,int k,uint32_t x,uint32_t y,uint32_t z) {
    (void)si;event(4,stage,k,x,y,z);
    return (VkDescriptorBufferInfo){(VkBuffer)(uintptr_t)(1000+stage),(uint64_t)(k*256),16u+x+3u*y+7u*z};
}
static VkDescriptorBufferInfo gfast_info(void) {event(5,0,0,0,0,0);return (VkDescriptorBufferInfo){(VkBuffer)(uintptr_t)71,24,65536};}
static VkDescriptorBufferInfo gmem_info(void) {event(6,0,0,0,0,0);return (VkDescriptorBufferInfo){(VkBuffer)(uintptr_t)72,48,131072};}
static VkSpan copy_span(int slot,const void *data,uint64_t size,uint64_t align) {
    assert(record.ncopies<96 && size<=2048);
    Copy *c=&record.copies[record.ncopies++];c->slot=slot;c->size=size;c->align=align;
    memcpy(c->bytes,data,(size_t)size);
    return (VkSpan){(VkBuffer)(uintptr_t)0x9876,record.ncopies*2048u,NULL};
}
static VkSpan copy_dedupe(int slot,const void *data,uint64_t size,uint64_t align) {return copy_span(slot,data,size,align);}
static VkSpan vk_transient_copy(const void *data,uint64_t size,uint64_t align) {return copy_span(99,data,size,align);}
static VkDescriptorBufferInfo ubo_span(VkSpan s,uint64_t size) {return (VkDescriptorBufferInfo){s.buf,s.off,size};}
