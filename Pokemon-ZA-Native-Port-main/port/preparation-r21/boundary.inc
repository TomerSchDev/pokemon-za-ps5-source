/* Observer calls only after a successful non-represented present. The objects.c
 * wrapper holds the recursive exec_lock; no profile polling in draws. Failure
 * leaves the previous profile unchanged. The positive result is flags + 1. */
int backend_preparation_switch_profile(const char *profile, uint64_t frame) {
    int wanted = za_prep_parse(profile);
    if (wanted < 0) return -1;
    if (za_submit_defer || in_pass) return -3;
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
    unsigned previous = za_preparation_profile_flags();
    atomic_store_explicit(&za_prep_flags, (unsigned)wanted, memory_order_relaxed);
    pthread_mutex_unlock(&za_sq_lock);
    LOG("[za-r21-prep] applied frame=%llu profile=%s flags=%u previous=%s drained_seq=%llu\n",
        (unsigned long long)frame, za_prep_name((unsigned)wanted), (unsigned)wanted,
        za_prep_name(previous), (unsigned long long)drained);
    return wanted + 1;
}
