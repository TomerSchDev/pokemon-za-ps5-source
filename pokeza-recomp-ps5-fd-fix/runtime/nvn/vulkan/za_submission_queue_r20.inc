/* Included by exec.c and by the host trace test. No rendering/state changes. */
typedef struct {
    VkCommandBufferSubmitInfo cbs[ZA_BATCH_CBS];
    uint32_t ncbs, lists;
    VkSemaphoreSubmitInfo signal;
    uint64_t first_seq, started_ns, draw_base, command_base;
    uint64_t logical, calls, cb_total, merged, reasons[ZA_SUB_REASONS];
    uint64_t nvn_calls, nvn_lists, nvn_hist[5], max_nvn, batch_hist[ZA_BATCH_LISTS];
} ZaSubmitQueue;
static ZaSubmitQueue za_sq;
static pthread_mutex_t za_sq_lock = PTHREAD_MUTEX_INITIALIZER;
static bool za_batch_on, za_submit_defer;
static unsigned za_batch_limit = 1;
static ZaSubmitReason za_submit_reason = ZA_SUB_INTERNAL;
static uint64_t za_command_count;
static bool za_list_fenced;

static void za_submission_driver(const VkSubmitInfo2 *si) {
    PROF_T0();
    if (za_r25_mode) {  /* r25 submit=thread: the submitter makes this vkQueueSubmit2, in order (za_submitter_vk.inc) */
        za_r25_push_submit(si);
    } else {
        VkResult sr = vkQueueSubmit2(g_vk.queue, 1, si, VK_NULL_HANDLE);
        if (sr == VK_ERROR_DEVICE_LOST) vk_devlost_dump();
        VK_CHECK(sr);
    }
    za_slots_physical_submit(si);
    za_gap_physical(si);  /* r24: which logical submissions this driver submission carried */
    PROF_ADD(prof_submit);
    za_sq.calls++;
    za_sq.cb_total += si->commandBufferInfoCount;
}

/* Lock held. A single signal at the maximum logical sequence satisfies every
 * earlier list's wait and only delays (never advances) its retirement. */
static void za_submission_flush_locked(ZaSubmitReason reason) {
    if (!za_sq.ncbs) return;
    VkSubmitInfo2 si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
        .commandBufferInfoCount = za_sq.ncbs, .pCommandBufferInfos = za_sq.cbs,
        .signalSemaphoreInfoCount = 1, .pSignalSemaphoreInfos = &za_sq.signal};
    za_submission_driver(&si);
    za_sq.reasons[reason]++;
    if (za_sq.lists > 1) za_sq.merged += za_sq.lists - 1;
    if (za_sq.lists && za_sq.lists <= ZA_BATCH_LISTS) za_sq.batch_hist[za_sq.lists - 1]++;
    za_sq.ncbs = za_sq.lists = 0;
    za_sq.first_seq = za_sq.started_ns = 0;
}

static void za_submission_flush_to(uint64_t seq, ZaSubmitReason reason) {
    pthread_mutex_lock(&za_sq_lock);
    if (za_sq.ncbs && seq >= za_sq.first_seq) za_submission_flush_locked(reason);
    pthread_mutex_unlock(&za_sq_lock);
}

static void za_submission_accept(const VkSubmitInfo2 *si) {
    pthread_mutex_lock(&za_sq_lock);
    za_sq.logical++;
    /* Presentation semaphores/extension state retain their own exact submit.
     * In particular, never apply an acquire wait to earlier rendering. */
    if (!si->commandBufferInfoCount || si->waitSemaphoreInfoCount || si->signalSemaphoreInfoCount != 1 || si->pNext || si->flags ||
        si->pSignalSemaphoreInfos[0].semaphore != g_vk.timeline ||
        si->commandBufferInfoCount > ZA_BATCH_CBS) {
        ZaSubmitReason why = si->waitSemaphoreInfoCount || si->signalSemaphoreInfoCount != 1 ? ZA_SUB_PRESENT : ZA_SUB_INTERNAL;
        za_submission_flush_locked(why);
        za_submission_driver(si);
        za_sq.reasons[why]++;
        za_sq.batch_hist[0]++;
    } else {
        if (za_sq.ncbs + si->commandBufferInfoCount > ZA_BATCH_CBS || za_sq.lists == ZA_BATCH_LISTS)
            za_submission_flush_locked(ZA_SUB_CAPACITY);
        if (!za_sq.ncbs) {
            za_sq.first_seq = si->pSignalSemaphoreInfos[0].value;
            if (!za_sq.started_ns) {
                za_sq.started_ns = SDL_GetTicksNS();
                za_sq.draw_base = cum_draws;
                za_sq.command_base = za_command_count;
            }
        }
        memcpy(za_sq.cbs + za_sq.ncbs, si->pCommandBufferInfos,
               si->commandBufferInfoCount * sizeof za_sq.cbs[0]);
        za_sq.ncbs += si->commandBufferInfoCount;
        za_sq.lists++;
        za_sq.signal = si->pSignalSemaphoreInfos[0];
        if (!za_submit_defer) za_submission_flush_locked(za_submit_reason);
    }
    pthread_mutex_unlock(&za_sq_lock);
}

static void za_submission_begin_list(void) {
    pthread_mutex_lock(&za_sq_lock);
    if (!za_sq.lists) {
        za_sq.started_ns = SDL_GetTicksNS();
        za_sq.draw_base = cum_draws;
        za_sq.command_base = za_command_count;
    }
    pthread_mutex_unlock(&za_sq_lock);
}

static bool za_submission_can_defer(bool last, bool sync) {
    bool defer = false;
    pthread_mutex_lock(&za_sq_lock);
    if (!za_batch_on || sync) za_submit_reason = ZA_SUB_EACH;
    else if (za_list_fenced) za_submit_reason = ZA_SUB_FENCE;
    else if (last) za_submit_reason = ZA_SUB_END;
    else if (cum_draws - za_sq.draw_base >= ZA_BATCH_DRAWS) za_submit_reason = ZA_SUB_DRAWS;
    else if (za_sq.lists + 1 >= za_batch_limit) za_submit_reason = ZA_SUB_LISTS;
    else if (za_command_count - za_sq.command_base >= ZA_BATCH_COMMANDS) za_submit_reason = ZA_SUB_COMMANDS;
    else if (za_sq.started_ns && SDL_GetTicksNS() - za_sq.started_ns >= ZA_BATCH_NS) za_submit_reason = ZA_SUB_AGE;
    else defer = true;
    pthread_mutex_unlock(&za_sq_lock);
    return defer;
}

static void za_submission_report(void) {
    pthread_mutex_lock(&za_sq_lock);
    LOG("[za-r20b-submit] profile=%s logical=%llu vk_calls=%llu merged=%llu cbs=%llu nvn_calls=%llu nvn_lists=%llu max_nvn=%llu nvn_hist=",
        za_submission_profile_name(za_batch_limit), (unsigned long long)za_sq.logical,
        (unsigned long long)za_sq.calls, (unsigned long long)za_sq.merged,
        (unsigned long long)za_sq.cb_total, (unsigned long long)za_sq.nvn_calls,
        (unsigned long long)za_sq.nvn_lists, (unsigned long long)za_sq.max_nvn);
    for (int i = 0; i < 5; ++i) LOG("%s%llu", i ? "," : "", (unsigned long long)za_sq.nvn_hist[i]);
    LOG(" batch_hist=");
    for (unsigned i = 0; i < ZA_BATCH_LISTS; ++i) LOG("%s%llu", i ? "," : "", (unsigned long long)za_sq.batch_hist[i]);
    for (int i = 0; i < ZA_SUB_REASONS; ++i)
        LOG(" %s=%llu", za_submit_reason_names[i], (unsigned long long)za_sq.reasons[i]);
    LOG("\n");
    pthread_mutex_unlock(&za_sq_lock);
}

static void za_submission_configure(void) {
    static bool initialized;
    if (initialized) return;
    initialized = true;
    const char *profile = ENV("ZA_SUBMISSION_PROFILE");
    char text[32] = {0};
    if (!profile) {
        FILE *f = fopen("/app0/submission-options.txt", "rb");
        if (f) { size_t n = fread(text, 1, sizeof text - 1, f); fclose(f); if (n < sizeof text - 1) profile = text; }
    }
    za_batch_limit = za_submission_parse_profile(profile);
    if (!za_batch_limit || ENV("LARECOMP_VK_SUBMIT_EACH") || ENV("LARECOMP_SYNC_SUBMIT")) za_batch_limit = 1;
    za_batch_on = za_batch_limit > 1;
    LOG("[za-r20b-submit] startup profile=%s; bounded within one NVN call; lists=%u draws=%llu commands=%llu age_ns=%llu; logical vs vk_calls are distinct\n",
        za_submission_profile_name(za_batch_limit), za_batch_limit, (unsigned long long)ZA_BATCH_DRAWS,
        (unsigned long long)ZA_BATCH_COMMANDS, (unsigned long long)ZA_BATCH_NS);
}
