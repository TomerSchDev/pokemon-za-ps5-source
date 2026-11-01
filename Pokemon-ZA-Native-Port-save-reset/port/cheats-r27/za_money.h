#pragma once
#include <stdint.h>
#ifdef __cplusplus
extern "C" {
#endif
/* Session-only, one-shot additions. Enable does not enqueue anything.
 * OFF cancels an unconsumed request. At most one bounded request may be pending.
 * An addition already consumed by the game thread can finish after OFF. */
int za_money_set_enabled(int enabled);
int za_money_request(uint32_t amount); /* 10000/100000/1000000 only; 1 accepted */
uint32_t za_money_pending(void);
int za_money_ready(void);
int za_money_enabled(void);
uint32_t za_money_applied(void); /* counts actual changes, not button presses */
uint32_t za_money_last_value(void);
uint32_t za_money_rejected(void);
/* Exact translated game call sites only; never call with a guessed pointer. */
void za_cheat_money_component(uint64_t component);
void za_money_lifecycle_reset(void);
#ifdef __cplusplus
}
#endif
