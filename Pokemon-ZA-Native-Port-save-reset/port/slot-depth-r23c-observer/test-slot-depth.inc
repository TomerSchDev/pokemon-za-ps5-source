static void test_slot_depth(uint64_t *serial_ptr,uint64_t *frame_ptr) {
    uint64_t serial=*serial_ptr,i=*frame_ptr;
    unsigned prep=preparation_current,spans=immutable_current,prep_calls=preparation_calls,span_calls=immutable_calls;
    assert(!slot_calls && slot_status.active_slots==8);
    send(serial,"slot_depth 16");assert(!za_observer_menu("run"));assert(!slot_calls);
    receipt_has(serial,"\"result\":\"rejected_in_menu\"");receipt_has(serial,"\"active_slots\":8");
    receipt_has(serial++,"\"status_frame\":0");
    const char *bad[]={"slot_depth","slot_depth 08","slot_depth 016","slot_depth 32","slot_depth -8","slot_depth 16 extra","slot_depth ../16"};
    for(unsigned j=0;j<sizeof bad/sizeof bad[0];++j) {
        send(serial,bad[j]);frame(i++,0);assert(!slot_calls);receipt_has(serial++,"\"op\":\"invalid\"");
    }
    send(serial,"slot_depth 16");za_observer_frame(i++,true,true,0,(void*)1,capture);
    assert(!slot_calls);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial,"slot_depth 16");za_observer_frame(i++,false,false,0,(void*)1,capture);
    assert(!slot_calls);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    send(serial,"slot_depth 16");za_observer_frame(0,true,false,0,(void*)1,capture);
    assert(!slot_calls);receipt_has(serial++,"\"result\":\"rejected_boundary\"");
    const unsigned targets[]={8,16,16,8};
    for(unsigned j=0;j<4;++j) {
        char request[32],expected[80];snprintf(request,sizeof request,"slot_depth %u",targets[j]);
        send(serial,request);frame(i++,0);assert(slot_status.active_slots==targets[j] && slot_calls==j+1);
        receipt_has(serial,"\"result\":\"applied\"");receipt_has(serial,"\"status_valid\":true");
        snprintf(expected,sizeof expected,"\"active_slots\":%u",targets[j]);receipt_has(serial,expected);
        snprintf(expected,sizeof expected,"\"status_frame\":%" PRIu64,i-1);receipt_has(serial,expected);
        receipt_has(serial,"\"largest_free_extent\":3221225472");
        receipt_has(serial,"\"required_headroom_bytes\":1073741824");
        receipt_has(serial,"\"descriptor_pools\":32,\"command_buffers\":32,\"counter_query_pools\":16");
        receipt_has(serial++,"\"cost_ns\":125000000");
    }
    send(serial-1,"slot_depth 16");frame(i++,0);assert(slot_calls==4 && slot_status.active_slots==8);
    unsigned calls=slot_calls;
    send(serial++,"measure 1");frame(i++,0);assert(samples && !stop_at);
    uint64_t consumed=sequence,old_poll=poll_after;unsigned statuses=slot_status_calls;
    send(serial,"slot_depth 16");frame(i++,0);
    assert(samples && !stop_at && slot_calls==calls && slot_status_calls==statuses && sequence==consumed && poll_after==old_poll);
    assert(!za_observer_menu("run"));assert(sequence==consumed && poll_after==old_poll);
    clock_ns+=NS;frame(i++,0);assert(stop_at);
    while(samples) {
        clock_ns+=NS/30;frame(i++,0);
        assert(slot_calls==calls && slot_status_calls==statuses && sequence==consumed && poll_after==old_poll);
    }
    clock_ns+=NS;frame(i++,0);assert(slot_calls==calls+1 && slot_status.active_slots==16);
    receipt_has(serial++,"\"result\":\"applied\"");
    /* 8 slots is allowed even when the direct-memory query is unavailable. */
    slot_budget_unavailable=true;send(serial,"slot_depth 8");frame(i++,0);
    receipt_has(serial,"\"result\":\"applied\"");receipt_has(serial++,"\"budget_valid\":0");slot_budget_unavailable=false;
    const int codes[]={-1,-3,-4,-5,-6,0,8,16};
    const char *results[]={"rejected_depth","drain_failed","memory_gate","incompatible_profile","preflight_failed","receipt_mismatch","receipt_mismatch","receipt_mismatch"};
    for(unsigned j=0;j<sizeof codes/sizeof codes[0];++j) {
        slot_force=codes[j];send(serial,"slot_depth 16");frame(i++,0);
        char expected[100];snprintf(expected,sizeof expected,"\"result\":\"%s\"",results[j]);
        receipt_has(serial,expected);receipt_has(serial++,"\"active_slots\":8");
    }
    slot_force=INT_MIN;
    for(int bad_status=1;bad_status<=14;++bad_status) {
        slot_bad_status=bad_status;send(serial,"slot_depth 16");frame(i++,0);
        receipt_has(serial++,"\"result\":\"receipt_mismatch\"");
    }
    slot_bad_status=0;
    /* Rejected menu command retains old status_frame, never labels it this call. */
    uint64_t prior_frame=slot_status.frame;calls=slot_calls;
    send(serial,"slot_depth 8");assert(!za_observer_menu("run"));assert(slot_calls==calls);
    receipt_has(serial,"\"result\":\"rejected_in_menu\"");receipt_has(serial,"\"frame\":0");
    char expected[80];snprintf(expected,sizeof expected,"\"status_frame\":%" PRIu64,prior_frame);receipt_has(serial++,expected);
    statuses=slot_status_calls;
    for(unsigned j=0;j<100;++j){clock_ns+=NS;frame(i++,0);}
    assert(slot_calls==calls && slot_status_calls==statuses);
    assert(preparation_current==prep && immutable_current==spans && preparation_calls==prep_calls && immutable_calls==span_calls);
    *serial_ptr=serial;*frame_ptr=i;
    puts("r23 actual observer: strict8/16, actual coherent status/return/drain/budget diagnostics, all negative codes, stale status distinction, ABI/memory/frame/return mismatch, replay/boundary/menu rejection and no settling/measurement polling passed");
}
