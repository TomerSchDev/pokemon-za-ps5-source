#ifndef ZA_SLOT_POLICY_R23_H
#define ZA_SLOT_POLICY_R23_H
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include "slot-depth-control.h"
static inline unsigned za_slots_parse(const char *text) {  /* r24: also 32 and 64 */
    return !text?0:!strcmp(text,"8")?8:!strcmp(text,"16")?16:!strcmp(text,"32")?32:!strcmp(text,"64")?64:0;
}
static inline bool za_slots_budget_valid(uint64_t pool,uint64_t extent,uint64_t driver) {
    return pool && pool<=(UINT64_C(64)<<30) && extent && extent<=pool && driver<=pool;
}
/* AvailableDirectMemorySize reports the largest contiguous free range. This
 * gate is deliberately conservative; it does not add the driver's UMA heaps. */
static inline bool za_slots_budget_admit(uint64_t pool,uint64_t extent,uint64_t driver) {
    return za_slots_budget_valid(pool,extent,driver) && extent>=ZA_SLOT_DEPTH_MIN_HEADROOM_BYTES;
}
#define ZA_SLOT_PHYSICAL_CAP 256u  /* r24: 64 in r23c; above the 64-slot capacity plus presentation submits */
typedef struct { uint64_t seq[ZA_SLOT_PHYSICAL_CAP]; unsigned first,count; } ZaSlotPhysical;
static inline void za_slots_physical_retire(ZaSlotPhysical *q,uint64_t completed) {
    while(q->count && q->seq[q->first]<=completed) {
        q->first=(q->first+1)%ZA_SLOT_PHYSICAL_CAP;--q->count;
    }
}
static inline bool za_slots_physical_push(ZaSlotPhysical *q,uint64_t seq) {
    if(!seq || q->count==ZA_SLOT_PHYSICAL_CAP)return false;
    if(q->count && q->seq[(q->first+q->count-1)%ZA_SLOT_PHYSICAL_CAP]>=seq)return false;
    q->seq[(q->first+q->count)%ZA_SLOT_PHYSICAL_CAP]=seq;++q->count;return true;
}
#endif
