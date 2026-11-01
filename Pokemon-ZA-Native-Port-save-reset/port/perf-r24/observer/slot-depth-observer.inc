/* r24: depths 8, 16, 32 and 64 (r23c: 8 and 16). Every depth above 8 has the same memory receipt. */
static bool slot_depth_is(unsigned v) { return v==8 || v==16 || v==32 || v==64; }
static unsigned slot_depth_value(const char *depth) {
    return !depth ? 0u : !strcmp(depth,"8") ? 8u : !strcmp(depth,"16") ? 16u : !strcmp(depth,"32") ? 32u : !strcmp(depth,"64") ? 64u : 0u;
}
static bool slot_depth_known_result(int result) {
    return result==0 || (result>0 && slot_depth_is((unsigned)result)) || result==-1 || result==-3 || result==-4 || result==-5 || result==-6;
}
static bool slot_depth_status_valid(const ZaSlotDepthStatus *s) {
    return s->abi_version==ZA_SLOT_DEPTH_ABI && s->capacity_slots==ZA_SLOT_DEPTH_CAPACITY &&
        slot_depth_is(s->active_slots) &&
        (s->requested_slots==0 || slot_depth_is(s->requested_slots)) &&
        (s->previous_slots==0 || slot_depth_is(s->previous_slots)) &&
        s->budget_valid<=1 && !s->reserved && slot_depth_known_result(s->result);
}
static const char *slot_depth_result(int result) {
    return result>0 && slot_depth_is((unsigned)result) ? "applied" : result==-1 ? "rejected_depth" : result==-3 ? "drain_failed" :
        result==-4 ? "memory_gate" : result==-5 ? "incompatible_profile" : result==-6 ? "preflight_failed" : "receipt_mismatch";
}
static void ack_slot_depth(const Command *c,const char *result,int applied,uint64_t frame,uint64_t cost) {
    ZaSlotDepthStatus s={0};za_slot_depth_status(&s);
    unsigned requested=slot_depth_value(c->arg);bool valid=slot_depth_status_valid(&s);
    bool called=strcmp(result,"rejected_in_menu") && strcmp(result,"rejected_boundary");
    bool call_matches=s.frame==frame && s.requested_slots==requested && s.result==applied && slot_depth_is(s.previous_slots);
    bool applied_matches=applied>0 && slot_depth_is((unsigned)applied) && s.active_slots==requested && (unsigned)applied==requested &&
        s.completed_seq>=s.drained_seq && (requested==8 || (s.budget_valid==1 &&
        s.pool_bytes && s.pool_bytes<=ZA_SLOT_DEPTH_MAX_POOL_BYTES && s.largest_free_extent &&
        s.largest_free_extent<=s.pool_bytes && s.driver_bytes<=s.pool_bytes &&
        s.required_headroom_bytes>=ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES && s.largest_free_extent>=s.required_headroom_bytes));
    if (!valid || (called && (!call_matches || (!strcmp(result,"applied") ? !applied_matches :
        (applied<0 && s.active_slots!=s.previous_slots))))) result="receipt_mismatch";
    char path[320],text[2400];
    snprintf(path,sizeof path,"%s/ack_%" PRIu64 ".json",session_dir,c->seq);
    snprintf(text,sizeof text,
        "{\"session\":\"%016" PRIx64 "\",\"seq\":%" PRIu64 ",\"op\":\"slot_depth\",\"result\":\"%s\",\"file\":\"\","
        "\"frame\":%" PRIu64 ",\"cost_ns\":%" PRIu64 ",\"runtime_result\":%d,\"requested_slots\":%u,"
        "\"status_valid\":%s,\"status_abi_version\":%u,\"active_slots\":%u,\"capacity_slots\":%u,"
        "\"status_requested_slots\":%u,\"previous_slots\":%u,\"budget_valid\":%u,\"status_result\":%d,\"status_reserved\":%u,"
        "\"status_frame\":%" PRIu64 ",\"drained_seq\":%" PRIu64 ",\"completed_seq\":%" PRIu64 ","
        "\"pool_bytes\":%" PRIu64 ",\"largest_free_extent\":%" PRIu64 ",\"driver_bytes\":%" PRIu64 ","
        "\"required_headroom_bytes\":%" PRIu64 ",\"transient_capacity_bytes\":%" PRIu64 ","
        "\"descriptor_pools\":%" PRIu64 ",\"command_buffers\":%" PRIu64 ",\"counter_query_pools\":%" PRIu64 "}\n",
        session,c->seq,result,frame,cost,applied,requested,valid?"true":"false",s.abi_version,s.active_slots,s.capacity_slots,
        s.requested_slots,s.previous_slots,s.budget_valid,s.result,s.reserved,s.frame,s.drained_seq,s.completed_seq,
        s.pool_bytes,s.largest_free_extent,s.driver_bytes,s.required_headroom_bytes,s.transient_capacity_bytes,
        s.descriptor_pools,s.command_buffers,s.counter_query_pools);
    if(!write_text(path,text))sceKernelDebugOutText(0,"[za-observer] slot depth acknowledgement write failed\n");
}
