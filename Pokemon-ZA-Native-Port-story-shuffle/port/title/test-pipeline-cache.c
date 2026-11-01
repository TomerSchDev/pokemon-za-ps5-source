#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdatomic.h>
#include <sys/stat.h>
#include <unistd.h>
#define VK_UUID_SIZE 16
#define VK_PIPELINE_CACHE_HEADER_VERSION_ONE 1
#define VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO 17
#define VK_SUCCESS 0
#define VK_INCOMPLETE 5
typedef int VkResult;
typedef struct { int sType;size_t initialDataSize;const void *pInitialData; } VkPipelineCacheCreateInfo;
static struct { int dev,pcache;struct {uint32_t vendorID,deviceID;unsigned char pipelineCacheUUID[16];} props; } g_vk;
static unsigned char blob[64];
static uint64_t SDL_GetTicks(void) { return 0; }
#define LOG(...) printf(__VA_ARGS__)
#define VK_CHECK(x) assert((x)==VK_SUCCESS)
static int vkCreatePipelineCache(int d,const VkPipelineCacheCreateInfo *ci,const void *a,int *p) {
    (void)d;(void)a;*p=1;assert(ci->initialDataSize==0||ci->initialDataSize==sizeof blob);return VK_SUCCESS;
}
static int vkGetPipelineCacheData(int d,int p,size_t *size,void *data) {
    (void)d;(void)p;if(!data){*size=sizeof blob;return VK_SUCCESS;}
    assert(*size>=sizeof blob);memcpy(data,blob,sizeof blob);*size=sizeof blob;return VK_SUCCESS;
}
#include "pipeline_cache.h"
int main(void) {
    char dir[]="/tmp/za-cache-test-XXXXXX";assert(mkdtemp(dir));assert(!chdir(dir));
    g_vk.props.vendorID=0x1002;g_vk.props.deviceID=0x1234;
    for(int i=0;i<16;i++) g_vk.props.pipelineCacheUUID[i]=(unsigned char)i;
    uint32_t h[]={32,1,0x1002,0x1234};memcpy(blob,h,sizeof h);memcpy(blob+16,g_vk.props.pipelineCacheUUID,16);
    assert(za_cache_compatible(blob,sizeof blob));assert(!za_cache_compatible(blob,31));
    blob[8]^=1;assert(!za_cache_compatible(blob,sizeof blob));blob[8]^=1;
    blob[16]^=1;assert(!za_cache_compatible(blob,sizeof blob));blob[16]^=1;
    za_pipeline_cache_init();assert(za_pcache_size==0);
    za_pipeline_cache_checkpoint();assert(za_pcache_size==sizeof blob);
    FILE *f=fopen(ZA_PCACHE_FILE,"rb");unsigned char got[64];assert(f && fread(got,1,sizeof got,f)==sizeof got);fclose(f);
    assert(!memcmp(got,blob,sizeof blob));
    za_pipeline_cache_init();assert(za_pcache_size==sizeof blob);
    assert(!mkdir(ZA_PCACHE_TMP,0700));blob[63]=1;za_pipeline_cache_checkpoint();
    f=fopen(ZA_PCACHE_FILE,"rb");assert(f && fread(got,1,sizeof got,f)==sizeof got);fclose(f);assert(got[63]==0);
    assert(!rmdir(ZA_PCACHE_TMP));za_pipeline_cache_checkpoint();
    f=fopen(ZA_PCACHE_FILE,"rb");assert(f && fread(got,1,sizeof got,f)==sizeof got);fclose(f);assert(got[63]==1);
    za_pipeline_cache_start();za_pipeline_cache_shutdown();
    unlink(ZA_PCACHE_FILE);rmdir("cache");chdir("/");rmdir(dir);
    puts("PASS: device/UUID validation, first checkpoint, reload, failed-write preservation, atomic replacement, worker stop");
}
