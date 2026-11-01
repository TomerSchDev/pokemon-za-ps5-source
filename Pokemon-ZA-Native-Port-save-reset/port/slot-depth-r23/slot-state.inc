/* Metadata capacity is fixed16; only ring rotation uses the active count. */
static unsigned za_slot_active=8;
static ZaSlotDepthStatus za_slot_status;
static ZaSlotPhysical za_slot_physical;
typedef struct {
    uint64_t samples,incomplete,ready,wait_ns,incomplete_ns,ready_ns,max_wait_ns;
    uint64_t logical_sum,physical_sum,held_sum,logical_high,physical_high,held_high;
} ZaSlotStats;
static ZaSlotStats za_slot_stats;
static uint64_t za_slot_chunk_high;
static uint64_t za_slots_before_wait(uint64_t target);
static void za_slots_after_wait(uint64_t target,uint64_t before,uint64_t elapsed);
static void za_slots_physical_submit(const VkSubmitInfo2 *si);
static void za_slots_report(void);
