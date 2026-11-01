/* Native direct-boot harness. The desktop launcher/ImGui overlay are not part
 * of this first hardware test. Keep absence explicit, especially text input. */
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
int main(int argc, char **argv) {
    (void)argc; (void)argv;
    sceKernelDebugOutText(0, "[za-title-" ZA_TITLE_REV "] main reached; starting native runtime\n");
    setenv("LARECOMP_NO_LAUNCHER", "1", 1);
    setenv("LARECOMP_PS5_STDERR", "klog", 1);
    setenv("ZA_SHADERC_CACHE_DIRS", "cache/spirv:/app0/cache/spirv", 0);
    setenv("LARECOMP_FONT", "/app0/fonts/DejaVuSans.ttf", 0);
    setenv("ZA_SHADERC_HOST_WAIT_MS", "120000", 0); /* development host bridge */
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
