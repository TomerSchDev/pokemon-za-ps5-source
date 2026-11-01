/* PC diagnostic test controller for the dex-count proof. Linked ONLY into the isolated PC game library built by
 * test/build-pc.py; never part of the PS5 build. Same mechanism as the earlier lab_control.c: the runtime's own
 * SDL test-device key events (which = 0x7E57, accepted while LARECOMP_NO_USER_INPUT blocks the user's input) and
 * its window-shot request. No Windows input APIs, no game memory access.
 *
 * Command file (ZA_DEXCOUNT_PC_CONTROL, replaced atomically by the driver):
 *   line 1: sequence number (executed once, when larger than the last one)
 *   then one step per line: <hold_ms> <key_mask> [shot]   (hold_ms <= 20000, at most 64 steps)
 * Key mask bits (default bindings, runtime/hle/bindings.c):
 *   0 K=A  1 J=B  2 L=X  3 I=Y  4 Q=L  5 E=R  6 1=ZL  7 3=ZR  8 Return=Plus  9 Backspace=Minus
 *   10 W  11 S  12 A  13 D (left stick)  14 KP8  15 KP5  16 KP4  17 KP6 (right stick)
 *   18 Left 19 Up 20 Right 21 Down (d-pad)  22 F=LS click  23 KP0=RS click
 * Keys are pressed/released at step boundaries (a key held in two consecutive steps stays down) and all keys are
 * released after the last step. "shot" saves the window to build/c<seq>_<step>.png 300 ms after the step.
 * Each completed command appends to control.log in the run folder.
 */
#include <SDL3/SDL.h>
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define TEST_DEVICE 0x7E57u
static bool (*push_event)(SDL_Event *);
static bool (*on_main)(SDL_MainThreadCallback, void *, bool);
static char *shot_request;  /* runtime's g_window_shot_request[256] */
static char shot_name[128];

static const SDL_Scancode k_keys[24] = {
    SDL_SCANCODE_K, SDL_SCANCODE_J, SDL_SCANCODE_L, SDL_SCANCODE_I, SDL_SCANCODE_Q, SDL_SCANCODE_E,
    SDL_SCANCODE_1, SDL_SCANCODE_3, SDL_SCANCODE_RETURN, SDL_SCANCODE_BACKSPACE,
    SDL_SCANCODE_W, SDL_SCANCODE_S, SDL_SCANCODE_A, SDL_SCANCODE_D,
    SDL_SCANCODE_KP_8, SDL_SCANCODE_KP_5, SDL_SCANCODE_KP_4, SDL_SCANCODE_KP_6,
    SDL_SCANCODE_LEFT, SDL_SCANCODE_UP, SDL_SCANCODE_RIGHT, SDL_SCANCODE_DOWN,
    SDL_SCANCODE_F, SDL_SCANCODE_KP_0};

static void key(SDL_Scancode sc, bool down) {
    SDL_Event e;
    memset(&e, 0, sizeof e);
    e.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
    e.key.which = TEST_DEVICE;
    e.key.scancode = sc;
    e.key.down = down;
    push_event(&e);
}

static void apply(unsigned long from, unsigned long to) {
    for (unsigned i = 0; i < 24; ++i) {
        unsigned long bit = 1ul << i;
        if ((from & bit) && !(to & bit)) key(k_keys[i], false);
    }
    for (unsigned i = 0; i < 24; ++i) {
        unsigned long bit = 1ul << i;
        if (!(from & bit) && (to & bit)) key(k_keys[i], true);
    }
}

static void request_shot(void *unused) {
    (void)unused;
    if (shot_request) snprintf(shot_request, 256, "build/%s.png", shot_name);
}

static void log_line(const char *fmt, unsigned long a, unsigned long b, unsigned long c) {
    FILE *f = fopen("control.log", "a");
    if (!f) return;
    fprintf(f, fmt, a, b, c);
    fprintf(f, " tick=%llu\n", (unsigned long long)GetTickCount64());
    fclose(f);
}

static DWORD WINAPI control_thread(void *unused) {
    (void)unused;
    const char *path = getenv("ZA_DEXCOUNT_PC_CONTROL");
    HMODULE sdl = GetModuleHandleA("SDL3.dll");
    if (!path || !*path || !sdl) return 0;
    push_event = (bool (*)(SDL_Event *))(void *)GetProcAddress(sdl, "SDL_PushEvent");
    on_main = (bool (*)(SDL_MainThreadCallback, void *, bool))(void *)GetProcAddress(sdl, "SDL_RunOnMainThread");
    shot_request = (char *)(void *)GetProcAddress(GetModuleHandleA(NULL), "g_window_shot_request");
    if (!push_event || !on_main) return 0;
    log_line("controller ready %lu %lu %lu", 0, 0, 0);
    unsigned long last = 0;
    for (;;) {
        Sleep(50);
        FILE *f = fopen(path, "r");
        if (!f) continue;
        unsigned long seq = 0, ms[64], mask[64], shot[64];
        int steps = 0;
        char line[256];
        if (fgets(line, sizeof line, f)) seq = strtoul(line, NULL, 10);
        while (steps < 64 && fgets(line, sizeof line, f)) {
            unsigned long m = 0, k = 0, s = 0;
            int n = sscanf(line, "%lu %lu %lu", &m, &k, &s);
            if (n < 2 || m > 20000 || k >= (1ul << 24) || s > 1) continue;
            ms[steps] = m, mask[steps] = k, shot[steps] = n == 3 ? s : 0;
            steps++;
        }
        fclose(f);
        if (seq <= last) continue;
        last = seq;
        unsigned long held = 0;
        for (int i = 0; i < steps; ++i) {
            apply(held, mask[i]);
            held = mask[i];
            Sleep(ms[i]);
            if (shot[i]) {
                apply(held, 0);
                held = 0;
                Sleep(300);
                snprintf(shot_name, sizeof shot_name, "c%04lu_%02d", seq, i);
                on_main(request_shot, NULL, true);
                Sleep(200);
            }
        }
        apply(held, 0);
        log_line("done seq=%lu steps=%lu last_mask=%lu", seq, (unsigned long)steps, steps ? mask[steps - 1] : 0);
    }
}

void za_dexcount_pc_control_start(void) {
    static int started;
    if (!started++ && getenv("ZA_DEXCOUNT_PC_CONTROL")) {
        HANDLE thread = CreateThread(NULL, 0, control_thread, NULL, 0, NULL);
        if (thread) CloseHandle(thread);
    }
}
