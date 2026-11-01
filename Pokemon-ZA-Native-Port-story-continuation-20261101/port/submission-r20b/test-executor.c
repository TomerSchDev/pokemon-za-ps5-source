#define _POSIX_C_SOURCE 200809L
/* Actual queue.inc/executor.inc, with a deterministic mock Vulkan driver.
 * This checks CPU scheduling and captured submits, not GPU raster correctness. */
#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include "submission.h"

static struct { VkQueue queue; VkSemaphore timeline; } g_vk = {
    (VkQueue)(uintptr_t)1, (VkSemaphore)(uintptr_t)2
};
static uint64_t clock_ns = 1, cum_draws, cum_exec, prof_exec, prof_submit, logical_seq;
static int prof = 1;
static uint64_t SDL_GetTicksNS(void) { return clock_ns; }
#define ENV getenv
static char log_line[2048];
#define LOG(...) ((void)snprintf(log_line, sizeof log_line, __VA_ARGS__))
#define PROF_T0() uint64_t prof_t0_ = prof ? SDL_GetTicksNS() : 0
#define PROF_ADD(v) do { if (prof) (v) += SDL_GetTicksNS() - prof_t0_; } while (0)
#define VK_CHECK(v) assert((v) == VK_SUCCESS)
static void vk_devlost_dump(void) { assert(!"device loss"); }

typedef struct {
    uint32_t n, waits, signals;
    uintptr_t cb[ZA_BATCH_CBS + 4];
    uint64_t timeline_value;
} Captured;
static Captured captured[4096];
static unsigned captured_n;
static uint64_t signaled;
VKAPI_ATTR VkResult VKAPI_CALL vkQueueSubmit2(VkQueue queue, uint32_t n,
        const VkSubmitInfo2 *infos, VkFence fence) {
    assert(queue == g_vk.queue && fence == VK_NULL_HANDLE && n == 1);
    assert(captured_n < sizeof captured / sizeof captured[0]);
    const VkSubmitInfo2 *in = infos;
    Captured *out = &captured[captured_n++];
    memset(out, 0, sizeof *out);
    out->n = in->commandBufferInfoCount;
    out->waits = in->waitSemaphoreInfoCount;
    out->signals = in->signalSemaphoreInfoCount;
    assert(out->n <= ZA_BATCH_CBS + 4);
    for (uint32_t i = 0; i < out->n; ++i) out->cb[i] = (uintptr_t)in->pCommandBufferInfos[i].commandBuffer;
    unsigned timelines = 0;
    for (uint32_t i = 0; i < out->signals; ++i) {
        if (in->pSignalSemaphoreInfos[i].semaphore != g_vk.timeline) continue;
        ++timelines;
        out->timeline_value = in->pSignalSemaphoreInfos[i].value;
        assert(out->timeline_value > signaled);
        signaled = out->timeline_value;
    }
    assert(timelines == 1);  /* no duplicate signal of the same timeline */
    return VK_SUCCESS;
}
#include "queue.inc"

typedef enum { EMPTY, NORMAL, FENCED, EMPTY_FENCED, READBACK, COPYBACK, SLOW, MANY_DRAWS, MANY_CMDS } Kind;
static Kind scripts[128];
static uintptr_t pending_cb[2];
static unsigned pending_n;
static uint64_t next_token, wait_count, fence_seq, copied_before_submit;
static uint64_t slots[8];
static unsigned slot;
static void renderer_submit(void);
static void renderer_flush(void) {
    renderer_submit();
    za_submission_flush_to(logical_seq, ZA_SUB_WAIT);
    assert(logical_seq <= signaled);
    ++wait_count;
}
static void renderer_submit(void) {
    if (!pending_n) return;  /* exact empty-list behavior at issue */
    za_submission_flush_to(slots[slot], ZA_SUB_WAIT);
    assert(slots[slot] <= signaled); /* cannot recycle a held slot */
    VkCommandBufferSubmitInfo cb[2];
    memset(cb, 0, sizeof cb);
    for (unsigned i = 0; i < pending_n; ++i) {
        cb[i].sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO;
        cb[i].commandBuffer = (VkCommandBuffer)pending_cb[i];
    }
    VkSemaphoreSubmitInfo sig = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO,
        .semaphore = g_vk.timeline, .value = logical_seq + 1, .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT};
    VkSubmitInfo2 si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
        .commandBufferInfoCount = pending_n, .pCommandBufferInfos = cb,
        .signalSemaphoreInfoCount = 1, .pSignalSemaphoreInfos = &sig};
    za_submission_accept(&si);
    ++logical_seq;
    slots[slot] = logical_seq;
    slot = (slot + 1) % 8;
    /* Deliberately overwrite the stack descriptors: accept must own copies. */
    memset(cb, 0xa5, sizeof cb);
    pending_n = 0;
}
static void exec_list(uint64_t handle, int depth) {
    assert(depth == 0 && handle < sizeof scripts / sizeof scripts[0]);
    Kind kind = scripts[handle];
    za_command_count += kind == MANY_CMDS ? ZA_BATCH_COMMANDS : 20;
    if (kind == EMPTY_FENCED) { za_list_fenced = true; fence_seq = logical_seq; return; }
    if (kind == EMPTY) return;
    pending_cb[0] = ++next_token; /* upload */
    pending_cb[1] = ++next_token; /* main, with XFB copyback before finalization */
    pending_n = 2;
    if (kind == COPYBACK) ++copied_before_submit;
    if (kind == READBACK) {
        renderer_flush();
        assert(logical_seq <= signaled); /* CPU may read now */
        clock_ns += ZA_BATCH_NS;
        pending_cb[0] = ++next_token;
        pending_cb[1] = ++next_token;
        pending_n = 2;
    }
    cum_draws += kind == MANY_DRAWS ? ZA_BATCH_DRAWS : 1;
    if (kind == FENCED) { za_list_fenced = true; fence_seq = logical_seq + 1; }
    if (kind == SLOW) clock_ns += ZA_BATCH_NS;
}
#include "executor.inc"
static uint64_t renderer_fence_seq(void) { return logical_seq; }
static bool force_incomplete;
static uint64_t vk_completed_seq(void) { return force_incomplete ? 0 : signaled; }
#include "boundary.inc"

static void reset(bool batch) {
    assert(!za_sq.ncbs && !pending_n);
    memset(&za_sq, 0, sizeof za_sq);
    memset(captured, 0, sizeof captured);
    memset(scripts, 0, sizeof scripts);
    memset(slots, 0, sizeof slots);
    captured_n = slot = 0;
    signaled = logical_seq = next_token = wait_count = fence_seq = copied_before_submit = 0;
    cum_draws = cum_exec = prof_exec = prof_submit = za_command_count = 0;
    clock_ns = 1;
    za_batch_on = batch; za_batch_limit = batch ? 8 : 1;
    za_submit_defer = za_list_fenced = false;
    za_submit_reason = ZA_SUB_INTERNAL;
}
static void run(unsigned n) {
    uint64_t handles[128];
    for (unsigned i = 0; i < n; ++i) handles[i] = i;
    backend_execute_batch(handles, (int)n);
    assert(!za_sq.ncbs && logical_seq == signaled);
    uintptr_t expected = 1;
    for (unsigned i = 0; i < captured_n; ++i)
        for (uint32_t j = 0; j < captured[i].n; ++j) assert(captured[i].cb[j] == expected++);
    assert(expected == next_token + 1); /* exact upload/main order, no omission */
}
static void normal(unsigned n) { for (unsigned i = 0; i < n; ++i) scripts[i] = NORMAL; }
static void manual_signal(bool binary, bool empty) {
    VkCommandBufferSubmitInfo cb = {.sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_SUBMIT_INFO,
        .commandBuffer = (VkCommandBuffer)(uintptr_t)99};
    VkSemaphoreSubmitInfo sig[2] = {
        {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = g_vk.timeline,
         .value = logical_seq + 1, .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT},
        {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO, .semaphore = (VkSemaphore)(uintptr_t)3,
         .stageMask = VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT}
    };
    VkSemaphoreSubmitInfo wait = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_SUBMIT_INFO,
        .semaphore = (VkSemaphore)(uintptr_t)4, .stageMask = VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT};
    VkSubmitInfo2 si = {.sType = VK_STRUCTURE_TYPE_SUBMIT_INFO_2,
        .commandBufferInfoCount = empty ? 0 : 1, .pCommandBufferInfos = &cb,
        .signalSemaphoreInfoCount = binary ? 2 : 1, .pSignalSemaphoreInfos = sig,
        .waitSemaphoreInfoCount = binary ? 1 : 0, .pWaitSemaphoreInfos = &wait};
    za_submission_accept(&si);
    logical_seq++;
}
int main(void) {
    assert(za_submission_parse_profile("batch4\n") == 4);
    assert(za_submission_parse_profile(" \tbatch2\r\n") == 2);
    assert(za_submission_parse_profile("batch8") == 8);
    assert(!za_submission_parse_profile(NULL));
    assert(za_submission_parse_profile("each\n") == 1);
    assert(!za_submission_parse_profile("batch"));
    assert(!za_submission_parse_profile("batchx"));
    assert(!za_submission_parse_profile("batch\nextra"));
    /* Consume real once-only configuration before each case selects its mode. */
    za_submission_configure();
    reset(false); normal(7); run(7);
    assert(captured_n == 7 && za_sq.merged == 0 && za_sq.reasons[ZA_SUB_EACH] == 7);
    reset(true); normal(7); scripts[2] = COPYBACK; run(7);
    assert(captured_n == 1 && captured[0].n == 14 && captured[0].timeline_value == 7);
    assert(copied_before_submit == 1 && za_sq.merged == 6 && za_sq.batch_hist[6] == 1);
    assert(za_sq.nvn_hist[3] == 1 && za_sq.nvn_lists == 7);
    reset(true); normal(32); run(32);
    assert(captured_n == 4 && za_sq.reasons[ZA_SUB_LISTS] == 3);
    assert(za_sq.nvn_hist[4] == 1 && za_sq.max_nvn == 32);
    reset(true); normal(3); scripts[1] = FENCED; run(3);
    assert(captured_n == 2 && captured[0].timeline_value == fence_seq && fence_seq == 2);
    assert(za_sq.reasons[ZA_SUB_FENCE] == 1);
    reset(true); normal(3); scripts[1] = EMPTY_FENCED; run(3);
    assert(captured_n == 2 && captured[0].timeline_value == 1 && fence_seq == 1);
    assert(za_sq.reasons[ZA_SUB_FENCE] == 1);
    reset(true); scripts[0] = NORMAL; run(2); /* empty final list */
    assert(captured_n == 1 && captured[0].timeline_value == 1);
    reset(true); normal(3); scripts[1] = READBACK; run(3);
    assert(wait_count == 1 && captured_n == 2 && captured[0].timeline_value == 2);
    assert(captured[1].timeline_value == 4 && za_sq.reasons[ZA_SUB_INTERNAL] == 1);
    reset(true); normal(3); scripts[1] = SLOW; run(3);
    assert(captured_n == 2 && za_sq.reasons[ZA_SUB_AGE] == 1);
    reset(true); normal(3); scripts[1] = MANY_DRAWS; run(3);
    assert(captured_n == 2 && za_sq.reasons[ZA_SUB_DRAWS] == 1);
    reset(true); normal(3); scripts[1] = MANY_CMDS; run(3);
    assert(captured_n == 2 && za_sq.reasons[ZA_SUB_COMMANDS] == 1);
    reset(true); scripts[0] = READBACK;
    za_execute_one(0, false);
    assert(za_sq.lists == 1 && za_sq.started_ns == clock_ns); /* rearmed after internal flush */
    clock_ns += ZA_BATCH_NS;
    scripts[1] = NORMAL; za_execute_one(1, false);
    assert(!za_sq.ncbs && za_sq.reasons[ZA_SUB_AGE] == 1);
    reset(true); scripts[0] = NORMAL; za_execute_one(0, false);
    assert(captured_n == 0 && za_sq.ncbs == 2);
    manual_signal(true, false);
    assert(captured_n == 2 && captured[0].waits == 0 && captured[1].waits == 1);
    assert(captured[0].signals == 1 && captured[1].signals == 2);
    reset(true); scripts[0] = NORMAL; za_execute_one(0, false);
    manual_signal(false, true); /* standalone timeline signal cannot disappear */
    assert(captured_n == 2 && captured[1].n == 0 && signaled == 2 && !za_sq.ncbs);
    reset(true); scripts[0] = NORMAL; za_execute_one(0, false);
    za_submission_flush_to(1, ZA_SUB_WAIT);
    assert(signaled == 1 && za_sq.reasons[ZA_SUB_WAIT] == 1);
    reset(true); scripts[0] = NORMAL; backend_execute(0);
    assert(captured_n == 1 && za_sq.nvn_hist[1] == 1);
    reset(true); run(0);
    assert(captured_n == 0 && za_sq.nvn_hist[0] == 1);
    reset(true); normal(8); za_batch_limit = 4; run(8);
    assert(captured_n == 2 && za_sq.batch_hist[3] == 2);
    reset(true); normal(8); za_batch_limit = 2; run(8);
    assert(captured_n == 4 && za_sq.batch_hist[1] == 4);
    reset(true); scripts[0] = NORMAL; za_execute_one(0, false);
    assert(za_sq.ncbs && !signaled);
    assert(backend_submission_switch_profile("batch4", 99) == 4);
    assert(!za_sq.ncbs && signaled == logical_seq && za_batch_limit == 4);
    assert(backend_submission_switch_profile("batch2", 100) == 2);
    assert(backend_submission_switch_profile("each", 101) == 1 && !za_batch_on);
    assert(backend_submission_switch_profile("batch", 102) == -1 && za_batch_limit == 1);
    assert(!setenv("LARECOMP_VK_SUBMIT_EACH", "1", 1));
    assert(backend_submission_switch_profile("batch4", 103) == -2 && za_batch_limit == 1);
    assert(!unsetenv("LARECOMP_VK_SUBMIT_EACH"));
    assert(!setenv("LARECOMP_SYNC_SUBMIT", "1", 1));
    assert(backend_submission_switch_profile("batch2", 104) == -2 && za_batch_limit == 1);
    assert(!unsetenv("LARECOMP_SYNC_SUBMIT"));
    force_incomplete = true;
    assert(backend_submission_switch_profile("batch4", 105) == -3 && za_batch_limit == 1);
    force_incomplete = false;
    za_submission_report();
    puts("PASS: actual queue/executor, strict profiles, exact CB ordering, one timeline signal, copied descriptors, 8-slot reuse, nested-list fence flag, empty fence/end, internal readback, age reset, draw/command/list bounds, binary boundaries, standalone signal, waits, NVN histogram.");
    return 0;
}
