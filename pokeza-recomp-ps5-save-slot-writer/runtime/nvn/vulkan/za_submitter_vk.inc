// ================================================================== r25: the submitter thread (port/perf-r25)
// Included by exec.c right before za_submission_queue_r20.inc (apply-runtime-r25.py).
//
// submit=thread (ZA_PERF_SUBMIT=thread, read at vk_exec_init): the game's render thread still records, ends and
// batches its command buffers exactly as before (vk_submit_extra, the r20b batch4 queue, the r23 slot ring), but the
// vkQueueSubmit2 of each driver submission and the vkQueuePresentKHR of each frame are handed, in order, to one
// worker thread (za_submitter.h) and the render thread returns. Mesa's own submit thread is not usable here: the PS5
// winsys's sync has no VK_SYNC_FEATURE_TIMELINE (radv_ps5_sync.c), so Mesa runs the timeline emulated (DEFERRED
// submits) and MESA_VK_ENABLE_SUBMIT_THREAD applies only to ASSISTED mode (vk_device.c).
//
// What stays exactly as before, and why:
//  - order: one worker, FIFO; items are pushed under za_sq_lock in the order the inline code would have submitted;
//  - timeline values: unchanged (the submitted VkSubmitInfo2 is a copy); submit_seq still counts logical submissions;
//  - waits: vk_wait_seq first makes the CPU-held batch reach the queue (r20b), then za_r25_wait_submitted waits until
//    the worker has made the driver submission carrying that value, then waits on the timeline as before - so
//    QueueFinish, fences, ring-slot reuse, counter and XFB readbacks all wait for work handed to the worker too;
//  - ring slots: a slot is reset only after its submission completed (sub() -> vk_wait_seq), hence was submitted;
//  - bookkeeping: the r23 physical ledger, r24's driver-submission ring and the r20 counters are updated when an item
//    is queued (same order as submission), on the render thread under za_sq_lock; the worker never takes
//    za_sq_lock, seq_lock or cq_lock, so queueing may block on a full queue while holding za_sq_lock (back-pressure);
//  - presents: the present's own submission (acquire wait, done-semaphore signal) is queued before the present;
//    vkQueuePresentKHR and vkAcquireNextImageKHR both need the swapchain externally synchronized, so both take
//    za_r25_sc_lock; the acquire waits at most 2 ms under it and retries, so the worker's present is never held off
//    for long (the VideoOut WSI's acquire waits for a flip, not for our present);
//  - the present's result reaches the game one frame late (the latest finished present): OUT_OF_DATE / SUBOPTIMAL
//    seen by the worker makes the next present report OUT_OF_DATE once, so device.c recreates the swapchain;
//  - vkDeviceWaitIdle (swapchain recreation, exit, in-place reboot) needs every queue externally synchronized: those
//    callers quiesce the submitter (drain + keep it out) around it;
//  - device loss: the worker makes the failing call, dumps (LARECOMP_VK_DEVLOST_TRACE) and FATALs, as inline.
// submit=inline (or absent): the same calls on the render thread as r24-clock; only TSC timers around them are added.
#include "za_submitter.h"

uint64_t sceKernelReadTsc(void);
uint64_t sceKernelGetTscFrequency(void);

#define ZA_R25_QUEUE 64u  // items (driver submissions + presents): about two frames at 22 + 2 a frame
static ZaSubq za_r25_q;
static int za_r25_mode;      // 0 inline, 1 thread (vk_exec_init)
static uint64_t za_r25_hz;   // TSC frequency (vk_exec_init)
static pthread_mutex_t za_r25_sc_lock = PTHREAD_MUTEX_INITIALIZER;  // the swapchain: acquire (game) / present (worker)
static int za_r25_present_result = VK_NOT_READY;  // (__atomic) the latest finished present's result
static int za_r25_present_recreate;               // (__atomic) the worker saw OUT_OF_DATE / SUBOPTIMAL, not handled yet
static uint64_t za_r25_exec_ns, za_r25_rsub_ns, za_r25_acquire_ns, za_r25_acquires;  // (__atomic) window totals

typedef struct {
    VkSubmitInfo2 si;
    VkCommandBufferSubmitInfo cbs[ZA_BATCH_CBS];
    VkSemaphoreSubmitInfo sig[2], wait[1];
} ZaR25Submit;
typedef struct { VkSwapchainKHR swapchain; uint32_t image; VkSemaphore wait; } ZaR25Present;
_Static_assert(sizeof(ZaR25Submit) <= ZA_SUBQ_PAYLOAD, "a driver submission must fit an item");

static uint64_t za_r25_now(void) {  // ns from the TSC (sceKernelReadTsc, ~12 ns); SDL ticks before init
    return za_r25_hz ? (uint64_t)(((unsigned __int128)sceKernelReadTsc() * 1000000000ull) / za_r25_hz) : SDL_GetTicksNS();
}

static void za_r25_exec(void *ctx, ZaSubqItem *item) {  // (the worker)
    (void)ctx;
    if (item->kind == ZA_SUBQ_SUBMIT) {
        ZaR25Submit *s = (ZaR25Submit *)item->payload;
        s->si.pCommandBufferInfos = s->cbs;
        s->si.pSignalSemaphoreInfos = s->sig;
        s->si.pWaitSemaphoreInfos = s->wait;
        VkResult sr = vkQueueSubmit2(g_vk.queue, 1, &s->si, VK_NULL_HANDLE);
        if (sr == VK_ERROR_DEVICE_LOST) vk_devlost_dump();
        VK_CHECK(sr);
    } else if (item->kind == ZA_SUBQ_PRESENT) {
        const ZaR25Present *p = (const ZaR25Present *)item->payload;
        VkPresentInfoKHR pi = {.sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR, .waitSemaphoreCount = 1, .pWaitSemaphores = &p->wait,
                               .swapchainCount = 1, .pSwapchains = &p->swapchain, .pImageIndices = &p->image};
        pthread_mutex_lock(&za_r25_sc_lock);
        VkResult r = vkQueuePresentKHR(g_vk.queue, &pi);
        pthread_mutex_unlock(&za_r25_sc_lock);
        __atomic_store_n(&za_r25_present_result, (int)r, __ATOMIC_RELEASE);
        if (r == VK_ERROR_OUT_OF_DATE_KHR || r == VK_SUBOPTIMAL_KHR) __atomic_store_n(&za_r25_present_recreate, 1, __ATOMIC_RELEASE);
        if (r == VK_ERROR_DEVICE_LOST) { vk_devlost_dump(); FATAL("[za-r25] vkQueuePresentKHR: device lost\n"); }
    }
}

// vk_exec_init: the mode, and the worker for submit=thread
static void za_r25_init(void) {
    za_r25_hz = sceKernelGetTscFrequency();
    const char *e = ENV("ZA_PERF_SUBMIT");
    za_r25_mode = e && !strcmp(e, "thread") ? 1 : 0;
    if (za_r25_mode) {
        int r = za_subq_init(&za_r25_q, ZA_R25_QUEUE, za_r25_exec, NULL, za_r25_now);
        if (r) {
            LOG("[za-r25] submitter thread failed to start (%d): submitting inline\n", r);
            za_r25_mode = 0;
        }
    }
    LOG("[za-r25] submission: %s (queue %u items, TSC %llu Hz; Mesa's own submit thread does not apply: emulated "
        "timelines)\n", za_r25_mode ? "thread - vkQueueSubmit2 and vkQueuePresentKHR on the submitter" : "inline",
        ZA_R25_QUEUE, (unsigned long long)za_r25_hz);
}

// za_submission_driver (za_submission_queue_r20.inc, under za_sq_lock), submit=thread: the driver submission, copied
static void za_r25_push_submit(const VkSubmitInfo2 *si) {
    if (si->pNext || si->flags || si->commandBufferInfoCount > ZA_BATCH_CBS || si->signalSemaphoreInfoCount > 2 ||
        si->waitSemaphoreInfoCount > 1)
        FATAL("[za-r25] a driver submission outside the submitter's item: cbs %u signals %u waits %u next %p flags %#x\n",
              si->commandBufferInfoCount, si->signalSemaphoreInfoCount, si->waitSemaphoreInfoCount, si->pNext, si->flags);
    ZaR25Submit s;
    memset(&s, 0, sizeof s);
    s.si = *si;
    memcpy(s.cbs, si->pCommandBufferInfos, si->commandBufferInfoCount * sizeof s.cbs[0]);
    memcpy(s.sig, si->pSignalSemaphoreInfos, si->signalSemaphoreInfoCount * sizeof s.sig[0]);
    memcpy(s.wait, si->pWaitSemaphoreInfos, si->waitSemaphoreInfoCount * sizeof s.wait[0]);
    uint64_t seq = 0;
    for (uint32_t i = 0; i < si->signalSemaphoreInfoCount; i++)
        if (si->pSignalSemaphoreInfos[i].semaphore == g_vk.timeline) seq = si->pSignalSemaphoreInfos[i].value;
    int r = za_subq_push(&za_r25_q, ZA_SUBQ_SUBMIT, seq, &s, sizeof s);
    if (r) FATAL("[za-r25] driver submission %llu out of order (%d)\n", (unsigned long long)seq, r);
}

// vk_wait_seq, after the CPU-held batch reached the queue: until the worker handed that value to the driver
static void za_r25_wait_submitted(uint64_t seq) {
    if (za_r25_mode) za_subq_wait_submitted(&za_r25_q, seq);
}

// device.c vk_frame_begin
VkResult za_r25_acquire(VkSwapchainKHR swapchain, VkSemaphore semaphore, uint32_t *image) {
    const uint64_t t0 = za_r25_now();
    VkResult r;
    if (!za_r25_mode) {
        r = vkAcquireNextImageKHR(g_vk.dev, swapchain, UINT64_MAX, semaphore, VK_NULL_HANDLE, image);
    } else {
        for (;;) {
            pthread_mutex_lock(&za_r25_sc_lock);
            r = vkAcquireNextImageKHR(g_vk.dev, swapchain, 2000000ull, semaphore, VK_NULL_HANDLE, image);
            pthread_mutex_unlock(&za_r25_sc_lock);
            if (r != VK_TIMEOUT && r != VK_NOT_READY) break;
        }
    }
    __atomic_add_fetch(&za_r25_acquire_ns, za_r25_now() - t0, __ATOMIC_RELAXED);
    __atomic_add_fetch(&za_r25_acquires, 1, __ATOMIC_RELAXED);
    return r;
}

// device.c vk_frame_end: inline, vkQueuePresentKHR; thread, queued after the frame's submission
VkResult za_r25_present(const VkPresentInfoKHR *info) {
    if (!za_r25_mode) return vkQueuePresentKHR(g_vk.queue, info);
    if (info->pNext || info->pResults || info->swapchainCount != 1 || info->waitSemaphoreCount != 1)
        FATAL("[za-r25] a present outside the submitter's item\n");
    ZaR25Present p = {info->pSwapchains[0], info->pImageIndices[0], info->pWaitSemaphores[0]};
    if (za_subq_push(&za_r25_q, ZA_SUBQ_PRESENT, 0, &p, sizeof p)) FATAL("[za-r25] present not queued\n");
    if (__atomic_exchange_n(&za_r25_present_recreate, 0, __ATOMIC_ACQ_REL)) return VK_ERROR_OUT_OF_DATE_KHR;
    const VkResult last = (VkResult)__atomic_load_n(&za_r25_present_result, __ATOMIC_ACQUIRE);
    return last == VK_ERROR_OUT_OF_DATE_KHR || last == VK_SUBOPTIMAL_KHR ? VK_SUCCESS : last;  // (handled above, once)
}

// device.c around vkDeviceWaitIdle: every queued item made, the worker kept out until the end
void za_r25_quiesce_begin(void) { if (za_r25_mode) za_subq_quiesce_begin(&za_r25_q); }
void za_r25_quiesce_end(void) { if (za_r25_mode) za_subq_quiesce_end(&za_r25_q); }

// za_r24_stats: r25's keys on the [za-r24-perf] line (window totals; logic / present are the line's own)
//   submit=inline|thread exec_ns rsub_ns acquire_ns acquires render_busy_ns (= exec + rsub + logic + present)
//   sub_items sub_presents sub_busy_ns sub_pushes sub_push_waits sub_push_wait_ns sub_depth_sum sub_depth_max sub_lag
static size_t za_r25_report(char *out, size_t cap, uint64_t logic_ns, uint64_t present_ns) {
    const uint64_t exec = __atomic_exchange_n(&za_r25_exec_ns, 0, __ATOMIC_RELAXED);
    const uint64_t rsub = __atomic_exchange_n(&za_r25_rsub_ns, 0, __ATOMIC_RELAXED);
    const uint64_t acq = __atomic_exchange_n(&za_r25_acquire_ns, 0, __ATOMIC_RELAXED);
    const uint64_t acqn = __atomic_exchange_n(&za_r25_acquires, 0, __ATOMIC_RELAXED);
    ZaSubqStats st;
    memset(&st, 0, sizeof st);
    uint64_t lag = 0;
    if (za_r25_mode) {
        za_subq_take_stats(&za_r25_q, &st);
        pthread_mutex_lock(&seq_lock);
        const uint64_t logical = submit_seq;
        pthread_mutex_unlock(&seq_lock);
        const uint64_t done = za_subq_submitted(&za_r25_q);
        lag = logical > done ? logical - done : 0;  // logical submissions not yet handed to the driver (held + queued)
    }
    int n = snprintf(out, cap,
                     " submit=%s exec_ns=%llu rsub_ns=%llu acquire_ns=%llu acquires=%llu render_busy_ns=%llu sub_items=%llu"
                     " sub_presents=%llu sub_busy_ns=%llu sub_pushes=%llu sub_push_waits=%llu sub_push_wait_ns=%llu"
                     " sub_depth_sum=%llu sub_depth_max=%llu sub_lag=%llu",
                     za_r25_mode ? "thread" : "inline", (unsigned long long)exec, (unsigned long long)rsub,
                     (unsigned long long)acq, (unsigned long long)acqn,
                     (unsigned long long)(exec + rsub + logic_ns + present_ns), (unsigned long long)st.items,
                     (unsigned long long)st.presents, (unsigned long long)st.busy_ns, (unsigned long long)st.pushes,
                     (unsigned long long)st.push_waits, (unsigned long long)st.push_wait_ns,
                     (unsigned long long)st.depth_sum, (unsigned long long)st.depth_max, (unsigned long long)lag);
    return n < 0 ? 0 : (size_t)n < cap ? (size_t)n : cap - 1;
}
