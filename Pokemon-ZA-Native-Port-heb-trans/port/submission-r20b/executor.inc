/* This exact executor is compiled both in the PS5 title and the host trace
 * tests. Record each list exactly as r19a: finalize its upload/main buffers,
 * copy transform feedback, rotate slots and advance its logical sequence. */
static void za_execute_one(uint64_t handle, bool last) {
    za_submission_begin_list();
    za_list_fenced = false;
    PROF_T0();
    exec_list(handle, 0);
    PROF_ADD(prof_exec);
    if (prof) cum_exec += SDL_GetTicksNS() - prof_t0_;
    static int sync_submit = -1;
    if (sync_submit < 0) sync_submit = ENV("LARECOMP_SYNC_SUBMIT") ? 1 : 0;
    za_submit_defer = za_submission_can_defer(last, sync_submit != 0);
    bool defer = za_submit_defer;
    ZaSubmitReason reason = za_submit_reason;
    if (sync_submit) renderer_flush();
    else renderer_submit();
    za_submit_defer = false;
    za_submit_reason = ZA_SUB_INTERNAL;
    za_list_fenced = false;
    /* A fenced/last list may be empty, so renderer_submit may have returned
     * early. Earlier completed lists still must reach the queue now. */
    if (!defer) za_submission_flush_to(UINT64_MAX, reason);
}

void backend_execute_batch(const uint64_t *handles, int n) {
    za_submission_configure();
    pthread_mutex_lock(&za_sq_lock);
    za_sq.nvn_calls++;
    if (n > 0) za_sq.nvn_lists += (uint64_t)n;
    if (n > 0 && (uint64_t)n > za_sq.max_nvn) za_sq.max_nvn = (uint64_t)n;
    za_sq.nvn_hist[n <= 0 ? 0 : n == 1 ? 1 : n <= 4 ? 2 : n <= 8 ? 3 : 4]++;
    pthread_mutex_unlock(&za_sq_lock);
    for (int i = 0; i < n; ++i) za_execute_one(handles[i], i == n - 1);
}

void backend_execute(uint64_t handle) { backend_execute_batch(&handle, 1); }
