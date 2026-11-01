#ifndef ZA_IMMUTABLE_SPANS_R22_H
#define ZA_IMMUTABLE_SPANS_R22_H
#include <stdbool.h>
/* Executor-owner only, under the established execution lock. This changes no
 * observer/protocol profile. Baseline is false; a future controlled integration
 * may call this after the same safe drain used for preparation profiles. */
void za_immutable_spans_set_enabled(bool enabled);
#endif
