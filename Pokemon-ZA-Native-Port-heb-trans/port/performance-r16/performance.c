#include "frame_policy.h"
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifndef ZA_R16_OPTIONS_FILE
#define ZA_R16_OPTIONS_FILE "/app0/performance-options.txt"
#endif
extern uint64_t plat_now_ns(void);
extern uint64_t renderer_present_count(void);
extern uint64_t za_renderer_build_activity(void);
int sceKernelDebugOutText(int, const char *);
static _Atomic uint64_t requested;
static _Atomic int status;
/* Only the guest timing thread owns the policy. The UI sends a generation-
 * tagged request; it never modifies guest state or the policy concurrently. */
void za_performance_request(int trial) {
    uint64_t prev = atomic_load(&requested), next;
    do { next = ((prev & ~UINT64_C(1)) + 2) | (trial ? 1u : 0u); }
    while (!atomic_compare_exchange_weak(&requested, &prev, next));
}
int za_performance_status(void) { return atomic_load(&status); }
void za_performance_init(void) {
    char choice[40] = {0};
    FILE *f = fopen(ZA_R16_OPTIONS_FILE, "rb");
    size_t n = f ? fread(choice, 1, sizeof choice - 1, f) : 0;
    if (f) fclose(f);
    bool optimized = !n || !strcmp(choice, "optimized\n") || !strcmp(choice, "shadow\n");
    bool baseline_pace = !strcmp(choice, "pacing-baseline\n");
    bool shadow = !strcmp(choice, "shadow\n");
    if (optimized) { unsetenv("ZA_R16_NO_KEY_MEMO"); unsetenv("ZA_R16_NO_CBUF_LEAN"); }
    else { setenv("ZA_R16_NO_KEY_MEMO", "1", 1); setenv("ZA_R16_NO_CBUF_LEAN", "1", 1); }
    if (shadow) setenv("ZA_R16_MEMO_SHADOW", "1", 1); else unsetenv("ZA_R16_MEMO_SHADOW");
    setenv("LARECOMP_PACE", baseline_pace ? "1" : "0", 1);
    setenv("LARECOMP_TICK_SCALE", "1", 1);
    setenv("LARECOMP_VK_PROF", "1", 0);
    /* Keep game-identity and GPU-counter/DRS semantics identical to r15.
     * A separate experiment may change them after this comparison. */
    char msg[240];
    snprintf(msg, sizeof msg, "[za-performance-r16] 30 FPS startup; in-game FPS TRIAL arms 60; generic pace=%d memo=%d lean=%d shadow=%d tick_scale=1; GPU counter/DRS policy retained\n",
             baseline_pace, optimized, optimized, shadow);
    sceKernelDebugOutText(0, msg);
}
__attribute__((visibility("hidden")))
int32_t za_title_frame_cfg(int32_t original) {
    static uint64_t applied, log_at;
    static ZaFramePolicy state;
    uint64_t req = atomic_load(&requested);
    if (req != applied) {
        applied = req; za_frame_arm(&state, (req & 1) != 0); log_at = 0;
        sceKernelDebugOutText(0, (req & 1)
            ? "[za-performance-r16] user armed static 60 trial; five clean warmup windows, then five below 58.5 FPS trigger fallback\n"
            : "[za-performance-r16] user restored original frame mode\n");
    }
    uint64_t now = plat_now_ns(), builds = za_renderer_build_activity();
    int before = state.mode;
    int32_t out = za_frame_step(&state, original, now, renderer_present_count(), builds);
    atomic_store(&status, state.mode);
    if (before == ZA_FPS_TRIAL && state.mode == ZA_FPS_FALLBACK)
        sceKernelDebugOutText(0, "[za-performance-r16] sustained slow clean windows; restored original mode (retry available from menu)\n");
    if (state.mode != ZA_FPS_ORIGINAL && now >= log_at) {
        char msg[240];
        snprintf(msg, sizeof msg, "[za-performance-r16] mode=%d fps=%.2f warm=%u slow=%u excluded=%u shader_pending=%u shader_epoch=%llu\n",
                 state.mode, state.last_fps, state.warm, state.slow, state.excluded,
                 (unsigned)(uint32_t)builds, (unsigned long long)(builds >> 32));
        sceKernelDebugOutText(0, msg); log_at = now + UINT64_C(2000000000);
    }
    return out;
}
