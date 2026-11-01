#include "performance.h"
#include <stdio.h>
#include <string.h>

extern uint64_t plat_now_ns(void);
extern uint64_t renderer_present_count(void);
int sceKernelDebugOutText(int channel, const char *text);

/* Called from the build-verified 2.0.2 frame configuration instruction only. */
__attribute__((visibility("hidden")))
int32_t za_title_frame_cfg(int32_t original) {
    static bool initialized;
    static ZaPerformance state;
    if (!initialized) {
        initialized = true;
        char profile[32] = {0};
        FILE *f = fopen("/app0/performance-profile.txt", "rb");
        size_t n = f ? fread(profile, 1, sizeof(profile) - 1, f) : 0;
        if (f) fclose(f);
        state.enabled = n == 8 && !memcmp(profile, "60-auto\n", 8);
        sceKernelDebugOutText(0, state.enabled
            ? "[za-performance] static 60 FPS trial enabled; fallback after 5 slow windows (<58.5 FPS), after 5 warmup windows\n"
            : "[za-performance] original 30 FPS mode; optional trial disabled\n");
    }
    if (!state.enabled || state.fell_back) return original;
    bool previous = state.fell_back;
    int32_t mode = za_performance_step(&state, original, plat_now_ns(), renderer_present_count());
    if (!previous && state.fell_back) {
        char msg[192];
        snprintf(msg, sizeof msg, "[za-performance] 60 FPS not sustained (last %.1f FPS); original frame mode restored for this session\n", state.last_fps);
        sceKernelDebugOutText(0, msg);
    }
    return mode;
}
