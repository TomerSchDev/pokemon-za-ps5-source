// pc_entry_stub.c - the symbols the no-UI Windows runtime build (pc-runtime.mk) needs from "the UI", as no-ops.
// Upstream they come from runtime/ui/*.mm + Dear ImGui, which this build leaves out; the PS5 title supplies the same
// set (port/perf-r26/title_entry-r26p.c). Replace this file with the real entry / overlay modules
// (build-pc-runtime.sh link YOUR_ENTRY.c ...): every function below must then be defined by them.
//
// Also here: the two symbols the relinked game DLL (lasgame-uiv2.dll, port/ui-v2/pc/relink-game-dll.sh) imports from
// the exe that are PC-diagnostic hooks of the r28 proof (port/cheats-r28/test/pc_command.c), as no-ops:
// za_items_pc_batch (called by the hook units main_097/220/339 right after za_items_pump) and za_money_pc_start
// (called by the DLL's lasgame_tables entry). Leaving either undefined makes LoadLibrary of the DLL fail (error 127).
#include <stdint.h>
#include <stdio.h>

#include "ui/menu.h"  // runtime/ui/menu.h: the exact signatures of menu_handle_event & co.

#ifndef PC_RT_VERSION
#define PC_RT_VERSION "dev-uiv2"
#endif

// runtime/main.c log_system: the version at the top of the log (upstream: LARECOMP_VERSION in runtime/ui/launcher.mm)
const char *rt_version(void) { return PC_RT_VERSION "+uiv2-stub"; }

// ---- runtime/ui/menu.mm (the in-game overlay menu): nothing is open, nothing captures input, nothing is drawn
bool menu_handle_event(const SDL_Event *e) { (void)e; return false; }
bool menu_is_open(void) { return false; }
bool menu_input_captured(void) { return false; }
void menu_apply_window_requests(void *sdl_window) { (void)sdl_window; }
void menu_render(void *cmd, uint32_t target_w, uint32_t target_h) { (void)cmd; (void)target_w; (void)target_h; }
void menu_test_open(void) { fprintf(stderr, "[pc-stub] overlay menu unavailable (no-UI build)\n"); }
void menu_notice(const char *text, int seconds) { (void)seconds; fprintf(stderr, "[pc-stub] notice: %s\n", text); }
// runtime/hle/swkbd.c: the game's text entry; 0 = cancelled (out emptied)
int menu_keyboard_run(const char *initial, int max_len, char *out, int cap) {
    (void)initial; (void)max_len;
    if (cap > 0) out[0] = 0;
    fprintf(stderr, "[pc-stub] text input unavailable (no-UI build); request cancelled\n");
    return 0;
}

// ---- runtime/ui/launcher.mm (the start screen): never shown; main() boots the game directly (--play / LARECOMP_INPUT)
void launcher_prompts_kick(const char *root) { (void)root; }
void launcher_run(const char *root) {
    (void)root;
    fprintf(stderr, "[pc-stub] start screen unavailable (no-UI build); booting the game\n");
}

// ---- Link's Awakening overlays / editor / debug hooks (runtime/ui/tracker_overlay.mm, save_editor.mm, shader_tour.mm,
// chaos_overlay.mm, inventory_overlay.mm): they read that game's fixed addresses and do nothing for Z-A
void input_note_rstick(int32_t ry) { (void)ry; }
void save_editor_frame(uint64_t frame) { (void)frame; }
void save_editor_file_read(const char *path, uint64_t addr, int64_t off, int64_t size) {
    (void)path; (void)addr; (void)off; (void)size;
}
void shader_tour_tick(uint64_t frame) { (void)frame; }
uint64_t chaos_dgnmap_obj(void) { return 0; }
int inventory_items_cursor(void) { return -1; }

// ---- imported by lasgame-uiv2.dll (see the header comment): the r28 PC diagnostics, off
void za_items_pc_batch(void *cpu) { (void)cpu; }
void za_money_pc_start(void) {}
