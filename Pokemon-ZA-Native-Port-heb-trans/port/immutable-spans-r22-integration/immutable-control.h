#ifndef ZA_IMMUTABLE_CONTROL_R22_H
#define ZA_IMMUTABLE_CONTROL_R22_H
#include <stdint.h>
/* Independent of r21 preparation profiles. Startup is off. The observer calls
 * switch only at a successful, non-represented post-present boundary, never
 * while settling/measuring. Objects.c serializes switch AND status with the
 * existing recursive exec_lock; backend switch drains pending GPU work.
 * Return actual flags + 1 (off=1,on=2) after application; -1 invalid mode;
 * -3 unsafe boundary/drain failure. Failure leaves the old state untouched. */
int za_immutable_spans_switch(const char *mode, uint64_t frame);
uint32_t za_immutable_spans_flags(void);
int backend_immutable_spans_switch(const char *mode, uint64_t frame);
uint32_t backend_immutable_spans_flags(void);
#endif
