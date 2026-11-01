/* Called ONLY by the observer after a successful non-represented present,
 * through objects.c's existing recursive execution lock. No draw-time polling.
 * Positive result is the applied cap, after all old GPU work is complete. */
int backend_submission_switch_profile(const char *profile, uint64_t frame) {
    unsigned wanted = za_submission_parse_profile(profile);
    if (!wanted) return -1;
    if (wanted > 1 && (ENV("LARECOMP_VK_SUBMIT_EACH") || ENV("LARECOMP_SYNC_SUBMIT"))) return -2;
    if (za_submit_defer) return -3; /* not a drained list boundary */
    za_submission_configure();
    ZaSubmitReason saved_reason = za_submit_reason;
    za_submit_reason = ZA_SUB_SWITCH;
    renderer_flush();
    za_submission_flush_to(UINT64_MAX, ZA_SUB_SWITCH);
    za_submit_reason = saved_reason;
    uint64_t drained = renderer_fence_seq();
    if (vk_completed_seq() < drained) return -3; /* timeout never means applied */
    pthread_mutex_lock(&za_sq_lock);
    if (za_sq.ncbs || za_sq.lists) { pthread_mutex_unlock(&za_sq_lock); return -3; }
    unsigned previous = za_batch_limit;
    za_batch_limit = wanted;
    za_batch_on = wanted > 1;
    za_sq.started_ns = 0;
    pthread_mutex_unlock(&za_sq_lock);
    LOG("[za-r20b-submit] applied frame=%llu profile=%s max_lists=%u previous=%s drained_seq=%llu\n",
        (unsigned long long)frame, za_submission_profile_name(wanted), wanted,
        za_submission_profile_name(previous), (unsigned long long)drained);
    return (int)wanted;
}
