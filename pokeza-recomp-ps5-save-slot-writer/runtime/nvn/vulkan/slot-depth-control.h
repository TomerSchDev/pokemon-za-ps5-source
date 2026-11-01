#ifndef ZA_SLOT_DEPTH_CONTROL_R23_H
#define ZA_SLOT_DEPTH_CONTROL_R23_H
#include <stdint.h>
enum {
    ZA_SLOT_DEPTH_ABI = 1,
    ZA_SLOT_DEPTH_CAPACITY = 64,  /* r24: 16 in r23c; 32 and 64 added */
    ZA_SLOT_DEPTH_APPLIED_8 = 8,
    ZA_SLOT_DEPTH_APPLIED_16 = 16,
    ZA_SLOT_DEPTH_APPLIED_32 = 32,
    ZA_SLOT_DEPTH_APPLIED_64 = 64,
    ZA_SLOT_DEPTH_INVALID = -1,
    ZA_SLOT_DEPTH_UNSAFE = -3,
    ZA_SLOT_DEPTH_MEMORY_GATE = -4,
    ZA_SLOT_DEPTH_INCOMPATIBLE = -5,
    ZA_SLOT_DEPTH_PREFLIGHT_FAILED = -6
};
#define ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES (UINT64_C(1) << 30)
#define ZA_SLOT_DEPTH_MAX_POOL_BYTES (UINT64_C(64) << 30)
typedef struct {
    uint32_t abi_version, active_slots, capacity_slots, requested_slots, previous_slots, budget_valid;
    int32_t result;
    uint32_t reserved;
    uint64_t frame, drained_seq, completed_seq, pool_bytes, largest_free_extent, driver_bytes,
        required_headroom_bytes, transient_capacity_bytes, descriptor_pools, command_buffers, counter_query_pools;
} ZaSlotDepthStatus;
/* Observer calls only after a successful non-represented present, outside
 * settling/measurement. Switch and status copy use the existing exec_lock.
 * Startup: active8, capacity64 (r24; 16 in r23c), ABI1. Positive return is actual applied depth;
 * negatives above leave active depth unchanged. Incompatible means any of
 * submission!=batch4, preparation!=baseline or immutable spans!=off.
 * A 16/32/64-slot success requires a valid budget and at least the checked headroom
 * in the largest FREE CONTIGUOUS direct-memory extent, before and after the extra
 * slots' resources are allocated. It is not total free RAM.
 * 8 slots may apply when the budget query is unavailable. Resource allocation
 * failure is distinct from a memory gate refusal. Status is the coherent last
 * switch receipt; active_slots is overwritten with actual current state.
 * A status read performs no memory query, allocation or GPU drain. */
int za_slot_depth_switch(const char *depth, uint64_t frame);
void za_slot_depth_status(ZaSlotDepthStatus *out);
#endif
