/* Native direct-boot harness. The desktop launcher/ImGui overlay are not part
 * of this first hardware test. Keep absence explicit, especially text input.
 * r24-prof: title_entry-r24.c with the option parser in za_r24prof_options.h (r24 keys plus scale, force60
 * and sample*) and za_prof_start (za_prof.c: force60 log, scale log, sampling profiler).
 * r24-clock: title_entry-r24prof.c with za_r24clock_options.h (plus vkprof, ticks, tsc) and, for vkprof=0, the
 * renderer's own CPU profile switched off after r16's za_performance_init has set LARECOMP_VK_PROF.
 * r25: title_entry-r24clock.c with za_r25_options.h (plus submit, clock, radv_threaded) and, for clock=tsc, the
 * cross-core TSC check and switch (za_clock_r25.c) before anything else reads the clock. */
#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "ui/menu.h"
#ifndef ZA_NATIVE_RANDOMIZER
#include "save_import.h"
#endif

extern int za_game_main(int argc, char **argv);
int sceKernelDebugOutText(int channel, const char *text);
#ifndef ZA_TITLE_REV
#define ZA_TITLE_REV "r3"
#endif
const char *rt_version(void) { return "v0.1.4-local202-ps5-title-" ZA_TITLE_REV; }

/* /app0/perf-r24-options.txt (r24's file and keys, plus r24-prof's - za_r24prof_options.h lists them), one
 * key=value a line ('#' starts a comment), read once with open/read/close (r23b's stdio read of its option file
 * failed on the console; r23c's fd read works). A missing file or key keeps the r23c behaviour.
 * Its own file: /app0/performance-options.txt belongs to r16 (za_performance_init), which turns its key memo and
 * cbuf lean off for any content other than "optimized\n" / "shadow\n" / empty. r16 also always sets
 * LARECOMP_VK_PROF=1, so the render-thread profile is on in r23c and here whatever prof says. */
#include "za_r25_options.h"
#define ZA_R24_OPTIONS_FILE "/app0/perf-r24-options.txt"
static void za_perf_log(const char *fmt, const char *a, const char *b) {
    char line[256];
    snprintf(line, sizeof line, fmt, a, b);
    sceKernelDebugOutText(0, line);
}
static void za_perf_options_load(void) {
    char text[1024];
    size_t n = 0;
    errno = 0;
    int fd = open(ZA_R24_OPTIONS_FILE, O_RDONLY | O_NOFOLLOW);
    if (fd < 0) {
        char e[16];
        snprintf(e, sizeof e, "%d", errno);
        za_perf_log("[za-r24-options] no %s (errno %s); r23c behaviour\n", ZA_R24_OPTIONS_FILE, e);
        return;
    }
    za_perf_log("[za-r24-options] reading %s%s\n", ZA_R24_OPTIONS_FILE, "");
    for (int calls = 0; n < sizeof text - 1 && calls < 64; calls++) {
        ssize_t r = read(fd, text + n, sizeof text - 1 - n);
        if (r <= 0) break;
        n += (size_t)r;
    }
    close(fd);
    text[n] = 0;
    za_r25_parse(text, setenv, unsetenv, za_perf_log);
}

int main(int argc, char **argv) {
    (void)argc; (void)argv;
    sceKernelDebugOutText(0, "[za-title-" ZA_TITLE_REV "] main reached; starting native runtime\n");
    za_perf_options_load();  /* (r24: before anything reads the environment) */
    {   /* r25: clock=tsc - the cross-core check and the switch, before the game's threads exist; submit= is read by
         * exec.c at renderer init */
        const char *ck = getenv("ZA_PERF_CLOCK");
        if (ck && !strcmp(ck, "tsc")) {
            extern void za_clock_r25_enable(void);
            za_clock_r25_enable();
        } else {
            sceKernelDebugOutText(0, "[za-r25-clock] clock=real: CLOCK_MONOTONIC is the real call (r24-clock)\n");
        }
        const char *sm = getenv("ZA_PERF_SUBMIT");
        sceKernelDebugOutText(0, sm && !strcmp(sm, "thread") ? "[za-r25] submit=thread requested (exec.c starts the submitter at renderer init)\n"
                                                            : "[za-r25] submit=inline (r24-clock)\n");
        /* radv_threaded=1: RADV_THREADED_RECORDING is in the environment before the game creates its instance and
         * device (RADV reads it at vkCreateDevice, with its own test: set and atoi != 0). Its worker's clock reads go
         * to cg_radv from here on (za_clock_r25.c). */
        const char *rt = getenv("RADV_THREADED_RECORDING");
        if (rt && atoi(rt) != 0) {
            extern void za_clock_r25_radv_threaded(void);
            za_clock_r25_radv_threaded();
            sceKernelDebugOutText(0, "[za-r25] radv_threaded=1: RADV_THREADED_RECORDING=1 set before vkCreateInstance (RADV's "
                                     "recording worker starts at vkCreateDevice; its clock reads are cg_radv)\n");
        } else {
            sceKernelDebugOutText(0, "[za-r25] radv_threaded=0: RADV records on the calling thread (r24-clock)\n");
        }
    }
    extern void za_prof_start(void);
    za_prof_start();  /* (r24-prof: force60 / scale logs; the sampler, before any guest thread exists) */
    extern void za_performance_init(void);
    za_performance_init();
    /* r24-clock vkprof=0: r16 has just set LARECOMP_VK_PROF=1 (unless something set it before); exec.c reads it once
     * at renderer init as "set at all = on", so it must be absent, not "0". */
    if (getenv("ZA_PERF_VKPROF_OFF")) {
        unsetenv("LARECOMP_VK_PROF");
        sceKernelDebugOutText(0, "[za-r24clock] vkprof=0: LARECOMP_VK_PROF unset after r16's init; the renderer's CPU profile is off\n");
    } else {
        sceKernelDebugOutText(0, getenv("LARECOMP_VK_PROF") ? "[za-r24clock] vkprof: LARECOMP_VK_PROF set (r16 default); the renderer's CPU profile is on\n"
                                                           : "[za-r24clock] vkprof: LARECOMP_VK_PROF not set\n");
    }
    extern void za_observer_init(void);
    za_observer_init();
    setenv("LARECOMP_NO_LAUNCHER", "1", 1);
    setenv("LARECOMP_PS5_STDERR", "klog", 1);
    setenv("ZA_SHADERC_CACHE_DIRS", "cache/spirv:/app0/cache/spirv", 0);
    setenv("LARECOMP_FONT", "/app0/fonts/DejaVuSans.ttf", 0);
    extern void za_shaderc_local_boot(void);
    za_shaderc_local_boot(); /* warm worker while in the launcher */
#ifdef ZA_NATIVE_RANDOMIZER
    /* ZA 2.0.2's main physical arena, verified on the same build in r6/r7/r8.
     * First-use auto-selection can latch the temporary 105 MB arena before
     * the 3.2 GB pool appears. Shader code bakes that choice for the session.
     * Pin only this packaged native randomizer build; the platform commit is
     * idempotent and retains pages which the guest has already populated. */
    setenv("LARECOMP_GWIN", "7676b00000:c9500000", 1);
    extern int za_randomizer_boot(void);
    if (za_randomizer_boot() != 0) return 1;
#ifdef ZA_NATIVE_CHEATS
    extern void za_cheats_init(void);
    za_cheats_init();
#endif
#else
    int imported = za_import_save_once(
        "/app0/save-import/city-tepig-f5c64116.main", "/download0/zarecomp/save/save_0",
        "city-tepig-f5c64116", 3186611, UINT64_C(0x9a88d11de47de1c1));
    if (imported < 0) {
        sceKernelDebugOutText(0, "[save-import] REFUSED: incomplete transaction or invalid staged save; game not started\n");
        return 1;
    }
    sceKernelDebugOutText(0, imported ? "[save-import] city Tepig imported and readback verified; old main retained\n"
                                     : "[save-import] no new import; existing progress retained\n");
#endif
    char *args[] = {"/app0/eboot.bin", "--play", "/app0/game", NULL};
    return za_game_main(3, args);
}

#ifndef ZA_NATIVE_CHEATS
bool menu_handle_event(const SDL_Event *e) { (void)e; return false; }
bool menu_is_open(void) { return false; }
bool menu_input_captured(void) { return false; }
void menu_apply_window_requests(void *window) { (void)window; }
void menu_render(void *cmd, uint32_t w, uint32_t h) { (void)cmd; (void)w; (void)h; }
void menu_test_open(void) { fprintf(stderr, "[ps5-title] overlay unavailable in direct-boot test\n"); }
#endif
void menu_notice(const char *text, int seconds) { (void)seconds; fprintf(stderr, "[ps5-title] %s\n", text); }
void launcher_prompts_kick(const char *root) { (void)root; }
void launcher_run(const char *root) {
    (void)root;
    fprintf(stderr, "[ps5-title] desktop launcher unavailable; booting packaged game\n");
}
int menu_keyboard_run(const char *initial, int max_len, char *out, int cap) {
    (void)initial; (void)max_len;
    if (cap > 0) out[0] = 0;
    fprintf(stderr, "[ps5-title] text input unavailable; request cancelled\n");
    return 0;
}

/* Desktop overlays and Link's Awakening-specific editor/debug hooks. These
 * modules use that game's fixed addresses; they do not supply ZA gameplay. */
void input_note_rstick(int32_t ry) { (void)ry; }
void save_editor_frame(uint64_t frame) { (void)frame; }
void save_editor_file_read(const char *path, uint64_t addr, int64_t off, int64_t size) {
    (void)path; (void)addr; (void)off; (void)size;
}
void shader_tour_tick(uint64_t frame) { (void)frame; }
uint64_t chaos_dgnmap_obj(void) { return 0; }
int inventory_items_cursor(void) { return -1; }
