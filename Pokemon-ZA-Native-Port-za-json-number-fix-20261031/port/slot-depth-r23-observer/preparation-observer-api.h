#ifndef ZA_PREPARATION_OBSERVER_API_H
#define ZA_PREPARATION_OBSERVER_API_H
#include <stdint.h>

/* Startup: baseline. One explicit observer command, at a successful,
 * non-represented post-present boundary, requests a change. The runtime owns
 * exec_lock serialization and drains old GPU work before changing flags.
 * No calls to switch are permitted during settling or measurement.
 * Return flags + 1 only after application, -1 invalid profile, -3 unsafe
 * boundary/drain failure. Failure leaves the prior profile unchanged.
 * Getters return the actual current state, never the queued request. */
enum {
    ZA_PREPARATION_PLAN = 1u,
    ZA_PREPARATION_LAZY = 2u,
    ZA_PREPARATION_ALL = ZA_PREPARATION_PLAN | ZA_PREPARATION_LAZY
};
int za_preparation_switch_profile(const char *profile, uint64_t frame);
const char *za_preparation_profile_name(void);
uint32_t za_preparation_profile_flags(void);

#endif
