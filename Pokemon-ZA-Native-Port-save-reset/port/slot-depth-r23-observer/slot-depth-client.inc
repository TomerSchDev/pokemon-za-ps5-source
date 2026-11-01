def canonical_slot_depth(value):
    if type(value) is int and value in (8,16):return value
    if type(value) is str and value in ('8','16'):return int(value)
    raise ValueError('Slot depth must be exactly 8 or 16')

def validate_slot_depth_ack(ack,expected_depth):
    expected=canonical_slot_depth(expected_depth)
    if ack.get('op')!='slot_depth' or type(ack.get('requested_slots')) is not int or ack['requested_slots']!=expected:
        raise ValueError('Slot depth receipt differs from the intended command')
    if ack.get('file')!='':raise ValueError('Slot depth receipt must not name a file')
    result=ack.get('result')
    negative={'rejected_depth':-1,'drain_failed':-3,'memory_gate':-4,'incompatible_profile':-5,'preflight_failed':-6}
    if result not in {'applied','rejected_boundary','rejected_in_menu','receipt_mismatch',*negative}:
        raise ValueError('Unknown slot depth result')
    u32=('status_abi_version','active_slots','capacity_slots','status_requested_slots','previous_slots','budget_valid','status_reserved')
    u64=('frame','cost_ns','status_frame','drained_seq','completed_seq','pool_bytes','largest_free_extent','driver_bytes',
         'required_headroom_bytes','transient_capacity_bytes','descriptor_pools','command_buffers','counter_query_pools')
    for names,limit in ((u32,2**32),(u64,2**64)):
        for key in names:
            if type(ack.get(key)) is not int or not 0<=ack[key]<limit:raise ValueError('Invalid slot depth diagnostic '+key)
    for key in ('runtime_result','status_result'):
        if type(ack.get(key)) is not int or not -(2**31)<=ack[key]<2**31:raise ValueError('Invalid slot depth return '+key)
    valid=(ack['status_abi_version']==1 and ack['capacity_slots']==16 and ack['active_slots'] in (8,16)
        and ack['status_requested_slots'] in (0,8,16) and ack['previous_slots'] in (0,8,16)
        and ack['budget_valid'] in (0,1) and ack['status_reserved']==0 and ack['status_result'] in (0,8,16,-1,-3,-4,-5,-6))
    if type(ack.get('status_valid')) is not bool or ack['status_valid']!=valid:
        raise ValueError('Incorrect slot depth snapshot validity flag')
    if not valid and result!='receipt_mismatch':raise ValueError('Invalid runtime snapshot cannot claim an outcome')
    code=ack['runtime_result']
    if result=='receipt_mismatch':return # Retain diagnostics, never treat this as application.
    if result in ('rejected_boundary','rejected_in_menu'):
        if code!=0 or ack['cost_ns']!=0 or (result=='rejected_in_menu' and ack['frame']!=0):
            raise ValueError('Invalid slot depth observer rejection context')
        return # status_frame can be old; no runtime switch was called.
    if not ack['frame'] or ack['status_frame']!=ack['frame'] or ack['status_requested_slots']!=expected or ack['status_result']!=code or ack['previous_slots'] not in (8,16):
        raise ValueError('Slot depth last-switch snapshot does not match this call')
    if result=='applied':
        if code!=expected or ack['active_slots']!=expected or ack['completed_seq']<ack['drained_seq']:
            raise ValueError('Slot depth was not confirmed applied after a completed drain')
        if expected==16 and (ack['budget_valid']!=1 or not 0<ack['pool_bytes']<=64<<30 or
            not 0<ack['largest_free_extent']<=ack['pool_bytes'] or ack['driver_bytes']>ack['pool_bytes'] or
            ack['required_headroom_bytes']<2**30 or ack['largest_free_extent']<ack['required_headroom_bytes']):
            raise ValueError('Sixteen slots require a checked free contiguous extent and headroom')
    elif code!=negative[result] or ack['active_slots']!=ack['previous_slots']:
        raise ValueError('Rejected slot depth switch reports an incorrect code or state change')

