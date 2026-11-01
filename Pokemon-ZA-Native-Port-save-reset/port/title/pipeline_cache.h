/* Included by the isolated PS5 Vulkan device.c after g_vk is defined.
 * Checkpoints survive the PS5 shell terminating a title without C atexit().
 * The Vulkan cache uses internal synchronization (create flags are zero).
 * Our mutex serializes checkpoint I/O with the normal exit checkpoint. */
#include <pthread.h>
#include <errno.h>
#define ZA_PCACHE_FILE "cache/vk_pipelines.bin"
#define ZA_PCACHE_TMP  "cache/vk_pipelines.bin.tmp"
#define ZA_PCACHE_MAX (256u * 1024u * 1024u)
static pthread_mutex_t za_pcache_lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_t za_pcache_thread;
static atomic_bool za_pcache_stop;
static bool za_pcache_started;
static uint64_t za_pcache_hash;
static size_t za_pcache_size;

static uint64_t za_cache_hash(const void *data, size_t size) {
    const unsigned char *p=data; uint64_t h=UINT64_C(0xcbf29ce484222325);
    for(size_t i=0;i<size;i++) h=(h^p[i])*UINT64_C(0x100000001b3);
    return h;
}
static bool za_cache_compatible(const void *data, size_t size) {
    if(size<32 || size>ZA_PCACHE_MAX) return false;
    uint32_t h[4]; memcpy(h,data,sizeof h);
    return h[0]>=32 && h[0]<=size && h[1]==VK_PIPELINE_CACHE_HEADER_VERSION_ONE &&
           h[2]==g_vk.props.vendorID && h[3]==g_vk.props.deviceID &&
           !memcmp((const unsigned char*)data+16,g_vk.props.pipelineCacheUUID,VK_UUID_SIZE);
}
static void za_pipeline_cache_init(void) {
    void *data=NULL; size_t size=0;
    FILE *f=fopen(ZA_PCACHE_FILE,"rb");
    if(f) {
        if(!fseek(f,0,SEEK_END)) {
            long n=ftell(f);
            if(n>=32 && (unsigned long)n<=ZA_PCACHE_MAX && !fseek(f,0,SEEK_SET)) {
                data=malloc((size_t)n);
                if(data && fread(data,1,(size_t)n,f)==(size_t)n && za_cache_compatible(data,(size_t)n)) size=(size_t)n;
            }
        }
        fclose(f);
        if(!size) LOG("[pipeline-cache] existing cache incompatible/incomplete; preserved, starting empty\n");
    }
    VkPipelineCacheCreateInfo ci={.sType=VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO,
        .initialDataSize=size,.pInitialData=size?data:NULL};
    VkResult result=vkCreatePipelineCache(g_vk.dev,&ci,NULL,&g_vk.pcache);
    if(result!=VK_SUCCESS) {
        LOG("[pipeline-cache] initial cache rejected (%d); retrying empty\n",result);
        size=0;ci.initialDataSize=0;ci.pInitialData=NULL;
        VK_CHECK(vkCreatePipelineCache(g_vk.dev,&ci,NULL,&g_vk.pcache));
    }
    za_pcache_hash=size?za_cache_hash(data,size):0;za_pcache_size=size;
    LOG("[pipeline-cache] initialized bytes=%zu fingerprint=%016llx\n",size,(unsigned long long)za_pcache_hash);
    free(data);
}
static void za_pipeline_cache_checkpoint(void) {
    pthread_mutex_lock(&za_pcache_lock);
    uint64_t start=SDL_GetTicks();
    void *data=NULL; size_t size=0; VkResult result=VK_INCOMPLETE;
    for(int retry=0;retry<3 && result==VK_INCOMPLETE;retry++) {
        size_t need=0;
        if(vkGetPipelineCacheData(g_vk.dev,g_vk.pcache,&need,NULL)!=VK_SUCCESS || need<32 || need>ZA_PCACHE_MAX) break;
        free(data);data=malloc(need);if(!data) break;
        size=need;result=vkGetPipelineCacheData(g_vk.dev,g_vk.pcache,&size,data);
    }
    if(result==VK_SUCCESS && za_cache_compatible(data,size)) {
        uint64_t hash=za_cache_hash(data,size);
        if(size!=za_pcache_size || hash!=za_pcache_hash) {
            mkdir("cache",0755);
            FILE *f=fopen(ZA_PCACHE_TMP,"wb");bool ok=false;
            if(f) {
                ok=fwrite(data,1,size,f)==size;
                if(fflush(f)!=0) ok=false;
                if(ok && fsync(fileno(f))!=0) ok=false;
                if(fclose(f)!=0) ok=false;
                if(ok && rename(ZA_PCACHE_TMP,ZA_PCACHE_FILE)!=0) ok=false;
            }
            if(ok) {
                chmod(ZA_PCACHE_FILE,0644);
                za_pcache_size=size;za_pcache_hash=hash;
                LOG("[pipeline-cache] checkpoint bytes=%zu fingerprint=%016llx duration_ms=%llu\n",size,
                    (unsigned long long)hash,(unsigned long long)(SDL_GetTicks()-start));
            } else LOG("[pipeline-cache] checkpoint failed errno=%d; previous cache retained\n",errno);
        }
    } else LOG("[pipeline-cache] snapshot unavailable result=%d bytes=%zu; previous cache retained\n",result,size);
    free(data);pthread_mutex_unlock(&za_pcache_lock);
}
static void *za_pipeline_cache_worker(void *arg) {
    (void)arg;
    while(!atomic_load(&za_pcache_stop)) {
        for(int i=0;i<100 && !atomic_load(&za_pcache_stop);i++) usleep(100000);
        if(!atomic_load(&za_pcache_stop)) za_pipeline_cache_checkpoint();
    }
    return NULL;
}
static void za_pipeline_cache_start(void) {
    int rc=pthread_create(&za_pcache_thread,NULL,za_pipeline_cache_worker,NULL);
    za_pcache_started=rc==0;
    LOG("[pipeline-cache] periodic checkpoint worker rc=%d interval=10s\n",rc);
}
static void za_pipeline_cache_shutdown(void) {
    atomic_store(&za_pcache_stop,true);
    if(za_pcache_started) { pthread_join(za_pcache_thread,NULL);za_pcache_started=false; }
}
