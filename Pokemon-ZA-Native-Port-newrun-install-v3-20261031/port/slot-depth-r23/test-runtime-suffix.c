static void reset(void) {
    assert(!live_pools&&!live_buffers&&!live_queries);
    memset(subs,0,sizeof subs);memset(cq,0,sizeof cq);memset(&za_sq,0,sizeof za_sq);
    memset(&za_slot_physical,0,sizeof za_slot_physical);memset(&za_slot_stats,0,sizeof za_slot_stats);memset(&za_slot_status,0,sizeof za_slot_status);
    za_slot_active=8;cur_sub=0;submit_seq=20;completed=20;g_vk.props.limits.timestampPeriod=1;
    query_result_calls=reset_pool_calls=flush_calls=resolve_calls=budget_calls=alloc_calls=fail_alloc=0;
    fail_completion=fail_drain=fail_wait=fail_second_budget=catch_fatal=false;in_pass=za_submit_defer=za_immutable_enabled=false;
    za_batch_limit=4;prep_flags=0;budget_pool=UINT64_C(12)<<30;budget_extent=UINT64_C(4)<<30;budget_driver=UINT64_C(1)<<30;
    nchunks=1;chunks[0].size=UINT64_C(64)<<20;
}
static void status(int expected,unsigned active,uint64_t frame) {
    ZaSlotDepthStatus s;backend_slot_depth_status(&s);
    assert(s.abi_version==1&&s.capacity_slots==16&&s.active_slots==active&&s.result==expected&&s.frame==frame);
    assert(s.transient_capacity_bytes==(UINT64_C(64)<<20));
}
int main(void) {
    ZaSlotPhysical cycle={0};
    for(uint64_t i=1;i<=64;i++)assert(za_slots_physical_push(&cycle,i));
    assert(!za_slots_physical_push(&cycle,65));za_slots_physical_retire(&cycle,32);
    for(uint64_t i=65;i<=96;i++)assert(za_slots_physical_push(&cycle,i));
    za_slots_physical_retire(&cycle,96);assert(!cycle.count);
    assert(za_slots_physical_push(&cycle,97)&&!za_slots_physical_push(&cycle,97));
    reset();ZaSlotDepthStatus initial;backend_slot_depth_status(&initial);assert(initial.active_slots==8&&initial.abi_version==1&&initial.capacity_slots==16);
    assert(!za_slots_parse(NULL)&&!za_slots_parse("08")&&!za_slots_parse("16 ")&&!za_slots_parse("32"));
    assert(za_slots_parse("8")==8&&za_slots_parse("16")==16);
    assert(!za_slots_budget_admit(UINT64_C(12)<<30,0,0));
    assert(!za_slots_budget_admit(UINT64_C(12)<<30,UINT64_C(1)<<29,0)); /* fragmentation: lots of total memory, no sufficient extent */
    assert(!za_slots_budget_admit(100,101,0)&&!za_slots_budget_admit(100,10,101));
    assert(!za_slots_budget_admit(UINT64_C(65)<<30,UINT64_C(2)<<30,0));
    assert(backend_slot_depth_switch("bad",1)==-1&&!flush_calls);status(-1,8,1);
    assert(backend_slot_depth_switch("16",0)==-3&&!flush_calls);
    in_pass=true;assert(backend_slot_depth_switch("16",1)==-3);in_pass=false;
    za_submit_defer=true;assert(backend_slot_depth_switch("16",1)==-3);za_submit_defer=false;
    prep_flags=1;assert(backend_slot_depth_switch("16",1)==-5);prep_flags=0;
    za_immutable_enabled=true;assert(backend_slot_depth_switch("16",1)==-5);za_immutable_enabled=false;
    za_batch_limit=8;assert(backend_slot_depth_switch("16",1)==-5);za_batch_limit=4;
    fail_drain=true;completed=19;assert(backend_slot_depth_switch("16",1)==-3);status(-3,8,1);assert(!budget_calls);
    reset();fail_completion=true;assert(backend_slot_depth_switch("16",1)==-3);assert(!budget_calls);
    reset();za_sq.lists=1;assert(backend_slot_depth_switch("16",1)==-3);
    reset();cq[15].n=1;cq[15].seq=21;assert(backend_slot_depth_switch("16",1)==-3&&cq[15].n==1);
    reset();subs[15].main_begun=true;subs[15].seq=21;assert(backend_slot_depth_switch("16",1)==-3);
    reset();budget_extent=0;assert(backend_slot_depth_switch("16",1)==-4&&!alloc_calls);
    assert(backend_slot_depth_switch("8",2)==8);status(8,8,2); /* reverting8 never needs a budget */
    for(unsigned failure=1;failure<=32;failure++) {
        reset();fail_alloc=failure;assert(backend_slot_depth_switch("16",3)==-6);status(-6,8,3);
        assert(!live_pools&&!live_buffers&&!live_queries);assert(submit_seq==20&&cur_sub==0);
    }
    reset();fail_second_budget=true;assert(backend_slot_depth_switch("16",3)==-4);status(-4,8,3);
    assert(!live_pools&&!live_buffers&&!live_queries);
    reset();
    for(unsigned i=0;i<8;i++)subs[i].npools=16; /* observed maximum working set */
    assert(backend_slot_depth_switch("16",3)==16&&live_pools==128&&live_buffers==16&&live_queries==8);
    assert(backend_slot_depth_switch("8",3)==8&&!live_pools&&!live_buffers&&!live_queries);
    reset();cur_sub=12;subs[12].seq=21;
    for(unsigned i=8;i<16;i++){subs[i].ts=true;cq[i].n=1;cq[i].seq=20;}
    assert(backend_slot_depth_switch("16",4)==16);status(16,16,4);
    assert(submit_seq==20&&cur_sub==0&&renderer_fence_seq()==20&&query_result_calls==8);
    assert(live_pools==8&&live_buffers==16&&live_queries==8);
    for(unsigned i=0;i<16;i++)assert(!subs[i].main_begun&&!subs[i].upload_begun&&!subs[i].ts&&!cq[i].n);
    unsigned old_allocs=alloc_calls;assert(backend_slot_depth_switch("16",5)==16&&alloc_calls==old_allocs);
    assert(backend_slot_depth_switch("8",6)==8);status(8,8,6);assert(!live_pools&&!live_buffers&&!live_queries);
    assert(submit_seq==20&&nchunks==1); /* transient retention is unchanged */
    reset();cur_sub=5;subs[5].seq=10;subs[5].npools=1;subs[5].pools[0]=(VkDescriptorPool)(uintptr_t)1;
    completed=9;fail_wait=true;catch_fatal=true;
    if(!setjmp(fatal_jump)){(void)sub();assert(!"unfinished slot must fail closed");}
    assert(!reset_pool_calls&&subs[5].seq==10);
    catch_fatal=false;fail_wait=false;completed=20;(void)sub();
    assert(reset_pool_calls==1&&subs[5].seq==21&&!subs[5].main_begun&&!subs[5].upload_begun);
    (void)sub();assert(reset_pool_calls==1); /* no repeated reset for pending logical sequence */
    reset();catch_fatal=true;fail_completion=true;
    if(!setjmp(fatal_jump)){(void)sub();assert(!"unknown completion must fail closed");}
    assert(!reset_pool_calls);catch_fatal=false;
    reset();VkSemaphoreSubmitInfo sig={.semaphore=g_vk.timeline,.value=4};VkSubmitInfo2 si={.signalSemaphoreInfoCount=1,.pSignalSemaphoreInfos=&sig};
    za_slots_physical_submit(&si);sig.value=8;za_slots_physical_submit(&si);submit_seq=10;completed=4;za_sq.lists=2;
    assert(za_slots_before_wait(5)==4);assert(za_slot_stats.logical_high==6&&za_slot_stats.physical_high==1&&za_slot_stats.held_high==2);
    completed=8;za_slots_after_wait(5,4,100);assert(!za_slot_physical.count&&za_slot_stats.incomplete==1&&za_slot_stats.incomplete_ns==100);
    assert(za_slots_before_wait(5)==8);za_slots_after_wait(5,8,2);assert(za_slot_stats.ready==1&&za_slot_stats.ready_ns==2);
    /* In-process reset does not rewind timeline/depth; idle completion permits
     * later ledger retirement. Process startup alone selects8. */
    reset();assert(backend_slot_depth_switch("16",9)==16);completed=submit_seq;
    assert(za_slot_active==16&&submit_seq==20);assert(backend_slot_depth_switch("8",10)==8);
    assert(za_slot_depth_switch("8",11)==8&&!wrapper_lock);
    za_slot_depth_status(&initial);assert(!wrapper_lock&&initial.result==8&&initial.frame==11);
    za_slot_depth_status(NULL);assert(!wrapper_lock);
    puts("PASS actual slot boundary + actual sub/fence getter: all16 lifetime scan, inactive timestamps, checked timeout/completion, memory fragmentation/zero gate,32 allocation rollback points, no sequence rewind, resource release, distinct logical/physical/held depth and wait-entry classification");
    return 0;
}
