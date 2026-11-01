#ifndef ZA_HEBREW_TRIAL_H
#define ZA_HEBREW_TRIAL_H
#include <stdbool.h>
#ifdef __cplusplus
extern "C" {
#endif
/* First status call initializes; subsequent calls are atomic cache reads only. */
int za_hebrew_trial_status(void); /* 1 enabled, 0 disabled, -1 unavailable/conflict */
/* Call at initialization/menu entry, never in a per-frame render loop. */
int za_hebrew_trial_refresh(void);
/* Read-only validation, then queue opposite mode; 1 queued, 0 pending, -1 rejected. */
int za_hebrew_trial_request(void);
void __wrap_backend_reset(void);
bool __wrap_za_observer_menu(const char *active_run);
#ifdef ZA_HEBREW_TRIAL_HOST_TEST
void za_hebrew_trial_test_reset(void);
#endif
#ifdef __cplusplus
}
#endif
#endif
