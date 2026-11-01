/* Existing linked RADV function, also used by VK_EXT_memory_budget. No new
 * kernel import, driver modification, or query during measurement is needed. */
extern void radv_ps5_winsys_heap_usage(uint64_t*,uint64_t*,uint64_t*);
static uint64_t za_slots_completed_checked(void) {
    uint64_t done=0;
    VkResult result=vkGetSemaphoreCounterValue(g_vk.dev,g_vk.timeline,&done);
    if(result!=VK_SUCCESS)FATAL("[za-r23-slots] completion query failed: %d\n",result);
    return done;
}
/* Called under za_sq_lock after successful driver submission. */
static void za_slots_physical_submit(const VkSubmitInfo2 *si) {
    uint64_t seq=0;
    for(uint32_t i=0;i<si->signalSemaphoreInfoCount;i++)
        if(si->pSignalSemaphoreInfos[i].semaphore==g_vk.timeline)seq=si->pSignalSemaphoreInfos[i].value;
    if(!za_slots_physical_push(&za_slot_physical,seq))
        FATAL("[za-r23-slots] invalid physical sequence ledger\n");
}
static uint64_t za_slots_before_wait(uint64_t target) {
    uint64_t done=za_slots_completed_checked();
    pthread_mutex_lock(&za_sq_lock);
    za_slots_physical_retire(&za_slot_physical,done);
    uint64_t logical=submit_seq>done?submit_seq-done:0;
    uint64_t physical=za_slot_physical.count,held=za_sq.lists;
    pthread_mutex_unlock(&za_sq_lock);
    ++za_slot_stats.samples;
    za_slot_stats.logical_sum+=logical;za_slot_stats.physical_sum+=physical;za_slot_stats.held_sum+=held;
    if(logical>za_slot_stats.logical_high)za_slot_stats.logical_high=logical;
    if(physical>za_slot_stats.physical_high)za_slot_stats.physical_high=physical;
    if(held>za_slot_stats.held_high)za_slot_stats.held_high=held;
    if(target && done<target)++za_slot_stats.incomplete;else ++za_slot_stats.ready;
    return done;
}
static void za_slots_after_wait(uint64_t target,uint64_t before,uint64_t elapsed) {
    /* vk_wait_seq historically only logs timeout. Never reset/rebegin/reuse a
     * slot if completion is unproven, including after that timeout path. */
    uint64_t done=za_slots_completed_checked();
    if(done<target)FATAL("[za-r23-slots] refusing unfinished slot: target=%llu completed=%llu\n",
        (unsigned long long)target,(unsigned long long)done);
    pthread_mutex_lock(&za_sq_lock);za_slots_physical_retire(&za_slot_physical,done);pthread_mutex_unlock(&za_sq_lock);
    za_slot_stats.wait_ns+=elapsed;
    if(target && before<target)za_slot_stats.incomplete_ns+=elapsed;else za_slot_stats.ready_ns+=elapsed;
    if(elapsed>za_slot_stats.max_wait_ns)za_slot_stats.max_wait_ns=elapsed;
}
static void za_slots_resource_counts(ZaSlotDepthStatus *s) {
    s->transient_capacity_bytes=s->descriptor_pools=s->command_buffers=s->counter_query_pools=0;
    for(int i=0;i<nchunks;i++)s->transient_capacity_bytes+=chunks[i].size;
    if(s->transient_capacity_bytes>za_slot_chunk_high)za_slot_chunk_high=s->transient_capacity_bytes;
    for(unsigned i=0;i<SUBS;i++) {
        s->descriptor_pools+=(uint64_t)subs[i].npools;
        s->command_buffers+=(subs[i].main!=VK_NULL_HANDLE)+(subs[i].upload!=VK_NULL_HANDLE);
        s->counter_query_pools+=cq[i].pool!=VK_NULL_HANDLE;
    }
}
static void za_slots_budget(ZaSlotDepthStatus *s) {
    s->pool_bytes=s->largest_free_extent=s->driver_bytes=0;
    radv_ps5_winsys_heap_usage(&s->pool_bytes,&s->largest_free_extent,&s->driver_bytes);
    s->budget_valid=za_slots_budget_valid(s->pool_bytes,s->largest_free_extent,s->driver_bytes)?1u:0u;
    s->required_headroom_bytes=ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES;
}
static void za_slots_report(void) {
    ZaSlotDepthStatus resources={0};za_slots_resource_counts(&resources);
    LOG("[za-r23-slots] active=%u capacity=%u samples=%llu incomplete_on_entry=%llu ready_on_entry=%llu wait_ns=%llu incomplete_ns=%llu ready_ns=%llu max_wait_ns=%llu logical_sum=%llu physical_sum=%llu held_sum=%llu logical_high=%llu physical_high=%llu held_high=%llu chunks=%d transient_capacity=%llu transient_high=%llu descriptor_pools=%llu command_buffers=%llu counter_query_pools=%llu preparation=%u immutable=%u\n",
        za_slot_active,SUBS,(unsigned long long)za_slot_stats.samples,(unsigned long long)za_slot_stats.incomplete,
        (unsigned long long)za_slot_stats.ready,(unsigned long long)za_slot_stats.wait_ns,
        (unsigned long long)za_slot_stats.incomplete_ns,(unsigned long long)za_slot_stats.ready_ns,
        (unsigned long long)za_slot_stats.max_wait_ns,(unsigned long long)za_slot_stats.logical_sum,
        (unsigned long long)za_slot_stats.physical_sum,(unsigned long long)za_slot_stats.held_sum,
        (unsigned long long)za_slot_stats.logical_high,(unsigned long long)za_slot_stats.physical_high,
        (unsigned long long)za_slot_stats.held_high,nchunks,(unsigned long long)resources.transient_capacity_bytes,
        (unsigned long long)za_slot_chunk_high,(unsigned long long)resources.descriptor_pools,
        (unsigned long long)resources.command_buffers,(unsigned long long)resources.counter_query_pools,
        za_preparation_profile_flags(),za_immutable_enabled?1u:0u);
    memset(&za_slot_stats,0,sizeof za_slot_stats);
}
/* Used only after a proved all-slot drain. Dormant pool/CB/query resources are
 * reclaimed on 16->8 and failed admission. Transient chunks remain in the
 * existing recyclable ring; this does not promise full memory reclamation. */
static void za_slots_release_extra(void) {
    for(unsigned i=8;i<SUBS;i++) {
        for(int j=0;j<subs[i].npools;j++)vkDestroyDescriptorPool(g_vk.dev,subs[i].pools[j],NULL);
        if(subs[i].main)vkFreeCommandBuffers(g_vk.dev,g_vk.pool,1,&subs[i].main);
        if(subs[i].upload)vkFreeCommandBuffers(g_vk.dev,g_vk.pool,1,&subs[i].upload);
        pthread_mutex_lock(&cq_lock);
        if(cq[i].pool)vkDestroyQueryPool(g_vk.dev,cq[i].pool,NULL);
        memset(&cq[i],0,sizeof cq[i]);
        pthread_mutex_unlock(&cq_lock);
        memset(&subs[i],0,sizeof subs[i]);
    }
}
static VkResult za_slots_create_pool(VkDescriptorPool *out) {
    VkDescriptorPoolSize sizes[]={{VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER,32768},{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER,4096},
        {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER,32768},{VK_DESCRIPTOR_TYPE_SAMPLED_IMAGE,1024},{VK_DESCRIPTOR_TYPE_SAMPLER,1024}};
    VkDescriptorPoolCreateInfo info={.sType=VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO,.maxSets=8192,.poolSizeCount=5,.pPoolSizes=sizes};
    return vkCreateDescriptorPool(g_vk.dev,&info,NULL,out);
}
static bool za_slots_preflight(void) {
    int pools=1;
    for(unsigned i=0;i<8;i++)if(subs[i].npools>pools)pools=subs[i].npools;
    if(pools>16)return false;
    for(unsigned i=8;i<SUBS;i++) {
        while(subs[i].npools<pools) {
            VkDescriptorPool created=VK_NULL_HANDLE;
            if(za_slots_create_pool(&created)!=VK_SUCCESS)return false;
            subs[i].pools[subs[i].npools++]=created;
        }
        VkCommandBuffer *buffers[]={&subs[i].main,&subs[i].upload};
        for(unsigned j=0;j<2;j++)if(!*buffers[j]) {
            VkCommandBufferAllocateInfo info={.sType=VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,.commandPool=g_vk.pool,
                .level=VK_COMMAND_BUFFER_LEVEL_PRIMARY,.commandBufferCount=1};
            VkCommandBuffer created=VK_NULL_HANDLE;
            if(vkAllocateCommandBuffers(g_vk.dev,&info,&created)!=VK_SUCCESS)return false;
            *buffers[j]=created;
        }
        pthread_mutex_lock(&cq_lock);
        if(!cq[i].pool) {
            VkQueryPoolCreateInfo info={.sType=VK_STRUCTURE_TYPE_QUERY_POOL_CREATE_INFO,.queryType=VK_QUERY_TYPE_TIMESTAMP,.queryCount=CQ_MAX};
            VkQueryPool created=VK_NULL_HANDLE;
            VkResult result=vkCreateQueryPool(g_vk.dev,&info,NULL,&created);
            if(result!=VK_SUCCESS) {pthread_mutex_unlock(&cq_lock);return false;}
            cq[i].pool=created;
        }
        pthread_mutex_unlock(&cq_lock);
    }
    return true;
}
void backend_slot_depth_status(ZaSlotDepthStatus *out) {
    *out=za_slot_status;out->abi_version=ZA_SLOT_DEPTH_ABI;out->capacity_slots=SUBS;out->active_slots=za_slot_active;
}
int backend_slot_depth_switch(const char *text,uint64_t frame) {
    unsigned wanted=za_slots_parse(text),previous=za_slot_active;
    ZaSlotDepthStatus s={.abi_version=ZA_SLOT_DEPTH_ABI,.active_slots=previous,.capacity_slots=SUBS,
        .requested_slots=wanted,.previous_slots=previous,.frame=frame,.result=-1};
    if(!wanted)goto done;
    s.result=-3;
    if(!frame || za_submit_defer || in_pass)goto done;
    za_submission_configure();
    if(wanted==16 && (za_batch_limit!=4 || za_preparation_profile_flags()!=0 || za_immutable_enabled)) {s.result=-5;goto done;}
    ZaSubmitReason saved=za_submit_reason;za_submit_reason=ZA_SUB_SWITCH;
    renderer_flush();za_submission_flush_to(UINT64_MAX,ZA_SUB_SWITCH);za_submit_reason=saved;
    s.drained_seq=renderer_fence_seq();
    VkResult completion=vkGetSemaphoreCounterValue(g_vk.dev,g_vk.timeline,&s.completed_seq);
    if(completion!=VK_SUCCESS || s.completed_seq<s.drained_seq)goto done;
    pthread_mutex_lock(&za_sq_lock);
    bool pending=za_sq.ncbs || za_sq.lists;
    za_slots_physical_retire(&za_slot_physical,s.completed_seq);
    pending=pending || za_slot_physical.count!=0;
    pthread_mutex_unlock(&za_sq_lock);
    if(pending)goto done;
    for(unsigned i=0;i<SUBS;i++) {
        if((subs[i].main_begun||subs[i].upload_begun) && subs[i].seq>s.completed_seq)goto done;
    }
    pthread_mutex_lock(&cq_lock);
    bool queries_pending=false;
    for(unsigned i=0;i<SUBS;i++)if(cq[i].n && cq[i].seq>s.completed_seq)queries_pending=true;
    pthread_mutex_unlock(&cq_lock);
    if(queries_pending)goto done;
    cq_resolve_done(s.completed_seq);
    for(unsigned i=0;i<SUBS;i++)if(subs[i].ts) {
        uint64_t t[2];
        if(vkGetQueryPoolResults(g_vk.dev,prof_qp,i*2,2,sizeof t,t,8,VK_QUERY_RESULT_64_BIT)==VK_SUCCESS && t[1]>t[0])
            prof_gpu+=(uint64_t)((double)(t[1]-t[0])*g_vk.props.limits.timestampPeriod);
        subs[i].ts=false;
    }
    za_slots_budget(&s);
    if(wanted==16) {
        if(!za_slots_budget_admit(s.pool_bytes,s.largest_free_extent,s.driver_bytes)) {s.result=-4;goto done;}
        if(!za_slots_preflight()) {
            if(previous==8)za_slots_release_extra();
            s.result=-6;goto done;
        }
        za_slots_budget(&s);
        if(!za_slots_budget_admit(s.pool_bytes,s.largest_free_extent,s.driver_bytes)) {
            if(previous==8)za_slots_release_extra();
            s.result=-4;goto done;
        }
    }
    za_slots_report(); /* close old telemetry interval before changing rotation */
    pthread_mutex_lock(&seq_lock);
    for(unsigned i=0;i<SUBS;i++)subs[i].main_begun=subs[i].upload_begun=false;
    cur_sub=0;za_slot_active=wanted;
    pthread_mutex_unlock(&seq_lock);
    if(wanted==8)za_slots_release_extra();
    s.active_slots=wanted;s.result=(int)wanted;
done:
    za_slots_resource_counts(&s);za_slot_status=s;
    LOG("[za-r23-slots] switch frame=%llu requested=%u active=%u previous=%u result=%d drained_seq=%llu completed_seq=%llu budget_valid=%u pool=%llu largest_free_extent=%llu driver=%llu required=%llu\n",
        (unsigned long long)frame,wanted,za_slot_active,previous,s.result,(unsigned long long)s.drained_seq,
        (unsigned long long)s.completed_seq,s.budget_valid,(unsigned long long)s.pool_bytes,
        (unsigned long long)s.largest_free_extent,(unsigned long long)s.driver_bytes,(unsigned long long)s.required_headroom_bytes);
    return s.result;
}
