static ZaSlotDepthStatus slot_status={.abi_version=1,.active_slots=8,.capacity_slots=16};
static unsigned slot_calls,slot_status_calls;
static int slot_force=INT_MIN,slot_bad_status;
static bool slot_budget_unavailable;
int za_slot_depth_switch(const char *depth,uint64_t at_frame) {
    unsigned wanted=slot_depth_value(depth);assert(wanted && at_frame);
    ++slot_calls;clock_ns+=NS/8;
    unsigned previous=slot_status.active_slots;
    slot_status=(ZaSlotDepthStatus){.abi_version=1,.active_slots=previous,.capacity_slots=16,
        .requested_slots=wanted,.previous_slots=previous,.budget_valid=slot_budget_unavailable?0:1,
        .result=slot_force==INT_MIN ? (int)wanted : slot_force,.frame=at_frame,
        .drained_seq=100,.completed_seq=100,.pool_bytes=UINT64_C(8)<<30,
        .largest_free_extent=slot_budget_unavailable?0:UINT64_C(3)<<30,.driver_bytes=UINT64_C(2)<<30,
        .required_headroom_bytes=UINT64_C(1)<<30,.transient_capacity_bytes=UINT64_C(512)<<20,
        .descriptor_pools=32,.command_buffers=32,.counter_query_pools=16};
    if(slot_force==INT_MIN)slot_status.active_slots=wanted;
    if(slot_force==-4)slot_status.largest_free_extent=UINT64_C(512)<<20;
    return slot_status.result;
}
void za_slot_depth_status(ZaSlotDepthStatus *out) {
    ++slot_status_calls;*out=slot_status;
    switch(slot_bad_status) {
    case 1:out->abi_version=2;break;
    case 2:out->frame++;break;
    case 3:out->completed_seq=out->drained_seq-1;break;
    case 4:out->budget_valid=0;break;
    case 5:out->largest_free_extent=out->required_headroom_bytes-1;break;
    case 6:out->required_headroom_bytes=0;break;
    case 7:out->requested_slots=8;break;
    case 8:out->result=8;break;
    case 9:out->reserved=1;break;
    case 10:out->active_slots=7;break;
    case 11:out->pool_bytes=0;break;
    case 12:out->pool_bytes=ZA_SLOT_DEPTH_MAX_POOL_BYTES+1;break;
    case 13:out->largest_free_extent=out->pool_bytes+1;break;
    case 14:out->driver_bytes=out->pool_bytes+1;break;
    default:break;
    }
}
