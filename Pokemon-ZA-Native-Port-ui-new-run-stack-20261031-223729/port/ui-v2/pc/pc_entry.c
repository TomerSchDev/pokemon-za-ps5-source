/* ui-v2 PC proof: what the PS5 title objects provide on the console and the desktop runtime's UI (runtime/ui/*.mm,
 * not linked here) provided on the PC - the stubs title_entry-r26p.c has, plus stand-ins for the console-only helpers
 * the overlay talks to (r16 performance, the Hebrew trial, the observer). The launcher (launcher_run) and the overlay
 * (menu_*) are the real ui-v2 modules; za_items / za_money are the real r28/r27 helpers (the hooked game DLL imports
 * za_items_pump / za_cheat_money_component from this exe). */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

const char *rt_version(void) { return "v0.1.4-local202-pc-ui-v2"; }

void menu_notice(const char *text, int seconds) { (void)seconds; fprintf(stderr, "[pc-ui-v2] notice: %s\n", text); }
void launcher_prompts_kick(const char *root) { (void)root; }
int menu_keyboard_run(const char *initial, int max_len, char *out, int cap) {
    (void)initial; (void)max_len;
    if (cap > 0) out[0] = 0;
    fprintf(stderr, "[pc-ui-v2] text input unavailable; request cancelled\n");
    return 0;
}
void input_note_rstick(int32_t ry) { (void)ry; }
void save_editor_frame(uint64_t frame) { (void)frame; }
void save_editor_file_read(const char *path, uint64_t addr, int64_t off, int64_t size) { (void)path; (void)addr; (void)off; (void)size; }
void shader_tour_tick(uint64_t frame) { (void)frame; }
uint64_t chaos_dgnmap_obj(void) { return 0; }
int inventory_items_cursor(void) { return -1; }

/* r16 performance (port/performance-r16, console only): the PC runs at the game's own pace; the trial row logs */
static int pc_performance_status;
int za_performance_status(void) { return pc_performance_status; }
void za_performance_request(int trial) {
    pc_performance_status = trial ? 1 : 0;
    fprintf(stderr, "[pc-ui-v2] za_performance_request(%d): status now %d (PC stand-in; no frame-mode change)\n", trial, pc_performance_status);
}
/* Hebrew trial (port/perf-r28/src/hebrew_trial.cpp, console only): the pack is not available on the PC */
int za_hebrew_trial_status(void) { return -1; }
int za_hebrew_trial_refresh(void) { return -1; }
int za_hebrew_trial_request(void) { fprintf(stderr, "[pc-ui-v2] za_hebrew_trial_request: pack not available on the PC\n"); return -1; }
/* observer (port/observer-r17, console only): never asks to continue a run */
bool za_observer_menu(const char *active_run) { (void)active_run; return false; }
/* the r28 PC game DLL's diagnostic hooks (port/cheats-r28/test/pc_command.c): not used by the ui-v2 proof */
void za_items_pc_batch(void *cpu) { (void)cpu; }
void za_money_pc_start(void) {}
/* klog on the console; stderr here */
int sceKernelDebugOutText(int channel, const char *text) { (void)channel; fputs(text, stderr); fflush(stderr); return 0; }
