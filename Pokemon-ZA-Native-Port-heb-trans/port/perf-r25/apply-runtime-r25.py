"""Apply r25's edits to an r24-clock work copy (r24-prof's and r24-clock's own edits are already in it).

  source/runtime/nvn/vulkan/za_submitter.h, za_submitter_vk.inc   copied from port/perf-r25 (the submitter's core and
                                                                   its Vulkan glue)
  source/runtime/nvn/vulkan/exec.c        include the glue before za_submission_queue_r20.inc; vk_wait_seq also waits
                                          until the submitter handed the value to the driver; za_r25_init at renderer
                                          init; r25's keys on the [za-r24-perf] line
  source/runtime/nvn/vulkan/za_submission_queue_r20.inc   za_submission_driver: submit=thread queues the driver
                                          submission instead of calling vkQueueSubmit2 (bookkeeping unchanged)
  source/runtime/nvn/vulkan/za_submission_executor_r20.inc   TSC timers: the render thread's exec and submit time
  source/runtime/nvn/vulkan/device.c      acquire / present through za_r25_acquire / za_r25_present; the submitter
                                          quiesced around each vkDeviceWaitIdle
  source/runtime/platform/ps5.c           plat_now_ns's clock_gettime -> za_clock_game_gettime (always the real clock)
  source/runtime/services/audio.c         the audio renderer's pacing clock -> za_clock_game_gettime

Exact-text edits; each anchor must occur exactly once, and a tree that already has the edits is left unchanged
(idempotent). Usage: python3 apply-runtime-r25.py <work copy, e.g. /home/tomer/ps5-za-native/perf-r25-20261029>
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
COPIES = {'za_submitter.h': 'source/runtime/nvn/vulkan/za_submitter.h',
          'za_submitter_vk.inc': 'source/runtime/nvn/vulkan/za_submitter_vk.inc'}

EDITS = {
    'source/runtime/nvn/vulkan/exec.c': [
        ('static void cq_resolve_done(uint64_t done);\n\nvoid vk_wait_seq(uint64_t seq) {\n',
         'static void cq_resolve_done(uint64_t done);\n'
         'static void za_r25_wait_submitted(uint64_t seq);  // (r25: za_submitter_vk.inc)\n'
         '\nvoid vk_wait_seq(uint64_t seq) {\n'),
        ('    za_submission_flush_to(seq, ZA_SUB_WAIT);  // never wait for work still held on the CPU\n',
         '    za_submission_flush_to(seq, ZA_SUB_WAIT);  // never wait for work still held on the CPU\n'
         '    za_r25_wait_submitted(seq);  // r25 submit=thread: nor for work the submitter has not handed to the driver yet\n'),
        ('#include "za_submission_queue_r20.inc"\n',
         '#include "za_submitter_vk.inc"  // r25: submit=inline|thread (port/perf-r25)\n'
         '#include "za_submission_queue_r20.inc"\n'),
        ('            (double)g_vk.props.limits.timestampPeriod);\n    }\n    st_defaults();\n}\n',
         '            (double)g_vk.props.limits.timestampPeriod);\n    }\n'
         '    za_r25_init();  // r25: submit=inline|thread\n'
         '    st_defaults();\n}\n'),
        ('        if (n < sizeof line) n += za_clock_report(line + n, sizeof line - n);\n    }\n',
         '        if (n < sizeof line) n += za_clock_report(line + n, sizeof line - n);\n    }\n'
         '    if (n < sizeof line) n += za_r25_report(line + n, sizeof line - n, lns, pns);  // r25: submitter and render-thread keys\n'),
    ],
    'source/runtime/nvn/vulkan/za_submission_queue_r20.inc': [
        ('    PROF_T0();\n'
         '    VkResult sr = vkQueueSubmit2(g_vk.queue, 1, si, VK_NULL_HANDLE);\n'
         '    if (sr == VK_ERROR_DEVICE_LOST) vk_devlost_dump();\n'
         '    VK_CHECK(sr);\n',
         '    PROF_T0();\n'
         '    if (za_r25_mode) {  /* r25 submit=thread: the submitter makes this vkQueueSubmit2, in order (za_submitter_vk.inc) */\n'
         '        za_r25_push_submit(si);\n'
         '    } else {\n'
         '        VkResult sr = vkQueueSubmit2(g_vk.queue, 1, si, VK_NULL_HANDLE);\n'
         '        if (sr == VK_ERROR_DEVICE_LOST) vk_devlost_dump();\n'
         '        VK_CHECK(sr);\n'
         '    }\n'),
    ],
    'source/runtime/nvn/vulkan/za_submission_executor_r20.inc': [
        ('    PROF_T0();\n    exec_list(handle, 0);\n    PROF_ADD(prof_exec);\n',
         '    PROF_T0();\n'
         '    const uint64_t za_r25_t0 = za_r25_now();  /* r25: the render thread\'s own exec / submit time, profile or not */\n'
         '    exec_list(handle, 0);\n'
         '    const uint64_t za_r25_t1 = za_r25_now();\n'
         '    PROF_ADD(prof_exec);\n'),
        ('    if (!defer) za_submission_flush_to(UINT64_MAX, reason);\n}\n',
         '    if (!defer) za_submission_flush_to(UINT64_MAX, reason);\n'
         '    __atomic_add_fetch(&za_r25_exec_ns, za_r25_t1 - za_r25_t0, __ATOMIC_RELAXED);  /* r25 */\n'
         '    __atomic_add_fetch(&za_r25_rsub_ns, za_r25_now() - za_r25_t1, __ATOMIC_RELAXED);\n'
         '}\n'),
    ],
    'source/runtime/nvn/vulkan/device.c': [
        ('static void recreate_swapchain(void) {\n    vkDeviceWaitIdle(g_vk.dev);\n    create_swapchain();\n}\n',
         '// r25 (exec.c, port/perf-r25/za_submitter_vk.inc): with submit=thread the presents go through the submitter, and\n'
         '// vkDeviceWaitIdle needs it quiesced (every queue externally synchronized); inline: the same calls as before\n'
         'VkResult za_r25_acquire(VkSwapchainKHR swapchain, VkSemaphore semaphore, uint32_t *image);\n'
         'VkResult za_r25_present(const VkPresentInfoKHR *info);\n'
         'void za_r25_quiesce_begin(void);\n'
         'void za_r25_quiesce_end(void);\n'
         '\n'
         'static void recreate_swapchain(void) {\n'
         '    za_r25_quiesce_begin();\n'
         '    vkDeviceWaitIdle(g_vk.dev);\n'
         '    create_swapchain();\n'
         '    za_r25_quiesce_end();\n'
         '}\n'),
        ('    VkResult r = vkAcquireNextImageKHR(g_vk.dev, g_vk.swapchain, UINT64_MAX, acquire_sem[slot], VK_NULL_HANDLE, &cur_frame.image);\n'
         '    if (r == VK_ERROR_OUT_OF_DATE_KHR) {\n'
         '        recreate_swapchain();\n'
         '        r = vkAcquireNextImageKHR(g_vk.dev, g_vk.swapchain, UINT64_MAX, acquire_sem[slot], VK_NULL_HANDLE, &cur_frame.image);\n'
         '    }\n',
         '    VkResult r = za_r25_acquire(g_vk.swapchain, acquire_sem[slot], &cur_frame.image);  // r25 (inline: the same call)\n'
         '    if (r == VK_ERROR_OUT_OF_DATE_KHR) {\n'
         '        recreate_swapchain();\n'
         '        r = za_r25_acquire(g_vk.swapchain, acquire_sem[slot], &cur_frame.image);\n'
         '    }\n'),
        ('    VkResult r = vkQueuePresentKHR(g_vk.queue, &pi);\n    za_observer_present_result = r;\n',
         '    VkResult r = za_r25_present(&pi);  // r25: inline vkQueuePresentKHR; thread: queued (the latest finished present\'s result)\n'
         '    za_observer_present_result = r;\n'),
        ('        vkDeviceWaitIdle(g_vk.dev);\n        if (trace) LOG("[vk] exit: saving the pipeline cache\\n");\n',
         '        za_r25_quiesce_begin();  // r25: the submitter drained and held (not released: the process ends)\n'
         '        vkDeviceWaitIdle(g_vk.dev);\n        if (trace) LOG("[vk] exit: saving the pipeline cache\\n");\n'),
        ('    if (!g_vk.dev) return;\n    vkDeviceWaitIdle(g_vk.dev);\n    extern void vk_textures_reset(void);\n',
         '    if (!g_vk.dev) return;\n'
         '    za_r25_quiesce_begin();  // r25\n'
         '    vkDeviceWaitIdle(g_vk.dev);\n'
         '    za_r25_quiesce_end();\n'
         '    extern void vk_textures_reset(void);\n'),
    ],
    'source/runtime/platform/ps5.c': [
        ('static uint64_t g_tsc_hz;\n\nuint64_t plat_now_ns(void) {\n',
         'static uint64_t g_tsc_hz;\n'
         'int za_clock_game_gettime(clockid_t id, struct timespec *ts);  // r25 (port/perf-r25/za_clock_r25.c): always the real clock\n'
         '\nuint64_t plat_now_ns(void) {\n'),
        ('    struct timespec ts;\n    clock_gettime(CLOCK_MONOTONIC, &ts);\n    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;\n}\n',
         '    struct timespec ts;\n'
         '    za_clock_game_gettime(CLOCK_MONOTONIC, &ts);  // r25: the game\'s timing never follows clock=tsc (tsc=1 is its switch)\n'
         '    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;\n}\n'),
    ],
    'source/runtime/services/audio.c': [
        ('#include <time.h>\n',
         '#include <time.h>\n'
         'int za_clock_game_gettime(clockid_t id, struct timespec *ts);  // r25 (port/perf-r25/za_clock_r25.c): always the real clock\n'),
        ('            clock_gettime(CLOCK_MONOTONIC, &now);\n',
         '            za_clock_game_gettime(CLOCK_MONOTONIC, &now);  // r25: the audio renderer\'s pacing stays on the real clock\n'),
    ],
}


def main():
    work = Path(sys.argv[1])
    for name, rel in COPIES.items():
        src = (HERE / name).read_bytes()
        dst = work / rel
        if dst.exists() and dst.read_bytes() == src:
            print(f'{rel}: already current')
        else:
            dst.write_bytes(src)
            print(f'{rel}: copied')
    for rel, edits in EDITS.items():
        path = work / rel
        text = path.read_text(encoding='utf-8')
        changed = False
        for old, new in edits:
            if new in text:
                continue
            count = text.count(old)
            if count != 1:
                raise SystemExit(f'{rel}: anchor found {count} times: {old[:70]!r}')
            text = text.replace(old, new)
            changed = True
        if changed:
            path.write_text(text, encoding='utf-8', newline='\n')
        print(f'{rel}: {"patched" if changed else "already patched"}')


if __name__ == '__main__':
    main()
