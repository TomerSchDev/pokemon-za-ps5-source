#include "za_immutable_control_r22.h"
/* Only the objects.c wrappers below may call these backend functions. Both
 * getters and setters share the existing executor lock. Normal draw execution
 * performs no control-file reads, locking or draining for this experiment. */
uint32_t backend_immutable_spans_flags(void) { return za_immutable_enabled ? 1u : 0u; }
int backend_immutable_spans_switch(const char *mode, uint64_t frame) {
    int wanted = !mode ? -1 : !strcmp(mode,"off") ? 0 : !strcmp(mode,"on") ? 1 : -1;
    if (wanted < 0) return -1;
    if (!frame || za_submit_defer || in_pass) return -3;
    za_submission_configure();
    ZaSubmitReason saved_reason = za_submit_reason;
    za_submit_reason = ZA_SUB_SWITCH;
    renderer_flush();
    za_submission_flush_to(UINT64_MAX, ZA_SUB_SWITCH);
    za_submit_reason = saved_reason;
    uint64_t drained = renderer_fence_seq();
    if (vk_completed_seq() < drained) return -3;
    pthread_mutex_lock(&za_sq_lock);
    if (za_sq.ncbs || za_sq.lists) { pthread_mutex_unlock(&za_sq_lock); return -3; }
    unsigned previous = backend_immutable_spans_flags();
    /* Close the old mode's counter interval before switching. This explicit
     * command lies outside settling/measurement; report work cannot pollute it. */
    za_immutable_spans_report();
    za_immutable_spans_set_enabled(wanted != 0);
    pthread_mutex_unlock(&za_sq_lock);
    LOG("[za-r22-immutable] applied frame=%llu mode=%s flags=%u previous=%u drained_seq=%llu\n",
        (unsigned long long)frame, wanted ? "on" : "off", (unsigned)wanted,
        previous, (unsigned long long)drained);
    return wanted + 1;
}
