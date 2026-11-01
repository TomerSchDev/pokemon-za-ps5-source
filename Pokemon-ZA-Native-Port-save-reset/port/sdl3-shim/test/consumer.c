/*
 * SDL3 shim for the PS5 port: a consumer that includes the shim headers the way
 * the recomp runtime does and uses every SDL call, type, enum and event field the
 * runtime's C files use, with the same shapes (so a mismatch fails to compile).
 * Compile-only (build-check.sh, as C11 and as C++20); never run.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <SDL3/SDL.h>        /* runtime/nvn/vulkan/device.c, main.c, paths.c, hle/input.c, services/audio.c */
#include <SDL3/SDL_vulkan.h> /* device.c: before vk.h, which brings vulkan.h */
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <SDL3/SDL_cpuinfo.h>    /* exec.c */
#include <SDL3/SDL_timer.h>      /* exec.c, textures.c */
#include <SDL3/SDL_filesystem.h> /* textures.c */
#include <SDL3/SDL_surface.h>    /* textures.c */
#include <SDL3/SDL_events.h>     /* nvn/renderer.h */
#include <SDL3/SDL_gamepad.h>    /* hle/pl.c */

#include <ctype.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#ifdef __cplusplus
#define ATOMIC_I32 int32_t /* the sysroot's <stdatomic.h> is C only; the runtime's atomics live in its C files */
#else
#include <stdatomic.h>
#define ATOMIC_I32 _Atomic int32_t
#endif

/* runtime/input_bind.h and runtime/ui/menu.h forward-declare the event union this way */
typedef union SDL_Event SDL_Event;

/* runtime/input_bind.h: the trigger pseudo-buttons follow SDL's buttons */
enum { PADB_LTRIGGER = 26, PADB_RTRIGGER, PADB_HOST_COUNT };
_Static_assert((int)PADB_LTRIGGER == (int)SDL_GAMEPAD_BUTTON_COUNT, "trigger pseudo-buttons follow SDL's buttons");

/* device.c: the PNG writer thread */
typedef struct ShotJob {
    uint32_t w, h;
    char path[256];
    uint8_t *px;
} ShotJob;
static int shot_thread(void *data)
{
    ShotJob *j = (ShotJob *)data;
    free(j->px);
    free(j);
    return 0;
}

/* ---- device.c: ui_window_init, create_instance, create_swapchain, vk_frame_begin, vk_save_png ---- */
static SDL_Window *window;
static void window_and_vulkan(void)
{
    SDL_SetHint(SDL_HINT_JOYSTICK_ALLOW_BACKGROUND_EVENTS, "1");
    if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_GAMEPAD))
        fprintf(stderr, "SDL_Init: %s\n", SDL_GetError());
    int win_w = 1280, win_h = 720;
    SDL_WindowFlags wflags = SDL_WINDOW_VULKAN | SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY;
    if (getenv("LARECOMP_HIDDEN"))
        wflags |= SDL_WINDOW_HIDDEN;
    SDL_SetHint(SDL_HINT_WINDOW_ACTIVATE_WHEN_SHOWN, "0");
    window = SDL_CreateWindow("ZA Recomp", win_w, win_h, wflags);
    if (!window)
        fprintf(stderr, "SDL_CreateWindow: %s\n", SDL_GetError());
    SDL_SetWindowFullscreen(window, true);

    Uint32 n_sdl = 0;
    const char *const *sdl_ext = SDL_Vulkan_GetInstanceExtensions(&n_sdl);
    const char *ext[16];
    uint32_t n_ext = 0;
    for (Uint32 i = 0; i < n_sdl && n_ext < 14; i++)
        ext[n_ext++] = sdl_ext[i];
    VkInstanceCreateInfo ci = {VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO, NULL, 0, NULL, 0, NULL, n_ext, ext};
    (void)ci;

    VkInstance inst = VK_NULL_HANDLE;
    VkSurfaceKHR surface = VK_NULL_HANDLE;
    if (!SDL_Vulkan_CreateSurface(window, inst, NULL, &surface))
        fprintf(stderr, "SDL_Vulkan_CreateSurface: %s\n", SDL_GetError());
    PFN_vkGetInstanceProcAddr gipa = (PFN_vkGetInstanceProcAddr)SDL_Vulkan_GetVkGetInstanceProcAddr();
    (void)gipa;

    int w, h;
    SDL_GetWindowSizeInPixels(window, &w, &h);
    VkExtent2D extent = {(uint32_t)w, (uint32_t)h};
    (void)extent;

    /* input.c input_mouse_update */
    bool want = (SDL_GetWindowFlags(window) & SDL_WINDOW_INPUT_FOCUS) != 0;
    SDL_SetWindowRelativeMouseMode(window, want);

    /* paths.c rt_window_icon + rt_fatal */
    SDL_Surface *icon = SDL_LoadPNG("icon.png");
    if (icon)
        SDL_SetWindowIcon(window, icon), SDL_DestroySurface(icon);
    SDL_ShowSimpleMessageBox(SDL_MESSAGEBOX_ERROR, "ZA Recomp", "message", NULL);

    /* device.c: screenshots */
    ShotJob *j = (ShotJob *)malloc(sizeof *j);
    j->w = (uint32_t)w, j->h = (uint32_t)h;
    snprintf(j->path, sizeof j->path, "%s", "shot.png");
    j->px = (uint8_t *)malloc((size_t)j->w * j->h * 4);
    SDL_Thread *t = SDL_CreateThread(shot_thread, "png", j);
    if (t)
        SDL_DetachThread(t);
    else
        shot_thread(j);
    const uint8_t *rgba = NULL;
    SDL_Surface *s = SDL_CreateSurfaceFrom((int)w, (int)h, SDL_PIXELFORMAT_ABGR8888, (void *)rgba, (int)w * 4);
    if (!s || !SDL_SavePNG(s, "shot.png"))
        fprintf(stderr, "saving failed: %s\n", SDL_GetError());
    SDL_DestroySurface(s);

    /* textures.c: HD packs */
    SDL_CreateDirectory("textures");
    SDL_CreateDirectory("textures/dump");
    SDL_Surface *s0 = SDL_LoadPNG("pack/tex.png");
    if (s0) {
        SDL_Surface *c = SDL_ConvertSurface(s0, SDL_PIXELFORMAT_ABGR8888);
        SDL_DestroySurface(s0);
        if (c) {
            const uint8_t *row = (const uint8_t *)c->pixels + c->pitch;
            (void)row;
            printf("%dx%d\n", c->w, c->h);
            SDL_DestroySurface(c);
        }
    }
    uint64_t t0 = SDL_GetTicksNS();
    (void)t0;
}

/* ---- device.c ui_run / main.c reboot_idle: the event loop and the handlers of input.c and bindings.c ---- */
static uint8_t keys_down[SDL_SCANCODE_COUNT];
static SDL_Gamepad *pad;
static ATOMIC_I32 pad_lx, pad_ly, pad_rx, pad_ry;
static int mouse_down[5];

static void recompute_pad(void)
{
    uint32_t host = 0;
    if (pad) {
        for (int i = 0; i < SDL_GAMEPAD_BUTTON_COUNT; i++)
            if (SDL_GetGamepadButton(pad, (SDL_GamepadButton)i))
                host |= 1u << i;
        if (SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFT_TRIGGER) > 16000)
            host |= 1u << PADB_LTRIGGER;
        if (SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) > 16000)
            host |= 1u << PADB_RTRIGGER;
    }
    (void)host;
    pad_lx = SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTX);
    pad_ly = -SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTY);
    pad_rx = SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_RIGHTX);
    pad_ry = -SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_RIGHTY);
}

static int note_family(void)
{
    int f = 0;
    if (pad)
        switch (SDL_GetGamepadType(pad)) {
        case SDL_GAMEPAD_TYPE_XBOX360: case SDL_GAMEPAD_TYPE_XBOXONE: f = 1; break;
        case SDL_GAMEPAD_TYPE_PS3: case SDL_GAMEPAD_TYPE_PS4: case SDL_GAMEPAD_TYPE_PS5: f = 2; break;
        default: break;
        }
    return f;
}

static int bind_mouse_from_sdl(int b)
{
    switch (b) {
    case SDL_BUTTON_LEFT: return 0;
    case SDL_BUTTON_RIGHT: return 1;
    case SDL_BUTTON_MIDDLE: return 2;
    case SDL_BUTTON_X1: return 3;
    case SDL_BUTTON_X2: return 4;
    }
    return -1;
}

/* bindings.c bind_capture_event + input.c input_user_blocked / test_event */
static bool handle(const SDL_Event *e)
{
    switch (e->type) {
    case SDL_EVENT_KEY_DOWN: case SDL_EVENT_KEY_UP:
        if (e->key.which == 0x7e57 || e->key.scancode == SDL_SCANCODE_ESCAPE || e->key.scancode == SDL_SCANCODE_F1 ||
            e->key.scancode == SDL_SCANCODE_F9 || e->key.scancode == SDL_SCANCODE_F11 || e->key.scancode >= SDL_SCANCODE_COUNT)
            return true;
        if (e->type == SDL_EVENT_KEY_DOWN && e->key.scancode == SDL_SCANCODE_F9 && !e->key.repeat)
            return true;
        if (e->key.scancode < SDL_SCANCODE_COUNT)
            keys_down[e->key.scancode] = e->type == SDL_EVENT_KEY_DOWN;
        return e->key.down;
    case SDL_EVENT_TEXT_INPUT: case SDL_EVENT_TEXT_EDITING:
        return e->text.windowID == 0x7e57 || e->text.text[0] == 0;
    case SDL_EVENT_MOUSE_MOTION:
        return (e->motion.state & SDL_BUTTON_RMASK) && e->motion.xrel * 16 > 0 && e->motion.yrel != 0;
    case SDL_EVENT_MOUSE_BUTTON_DOWN: case SDL_EVENT_MOUSE_BUTTON_UP: {
        int m = bind_mouse_from_sdl(e->button.button);
        if (m < 0)
            break;
        if (e->type == SDL_EVENT_MOUSE_BUTTON_UP)
            mouse_down[m] = 0;
        return e->button.down;
    }
    case SDL_EVENT_MOUSE_WHEEL:
        return e->wheel.y > 0;
    case SDL_EVENT_GAMEPAD_ADDED:
        if (!pad) {
            pad = SDL_OpenGamepad(e->gdevice.which);
            printf("[input] gamepad: %s\n", SDL_GetGamepadName(pad));
            note_family();
        }
        break;
    case SDL_EVENT_GAMEPAD_REMOVED:
        if (pad && SDL_GetGamepadID(pad) == e->gdevice.which) {
            SDL_CloseGamepad(pad);
            pad = NULL;
        }
        recompute_pad();
        break;
    case SDL_EVENT_GAMEPAD_BUTTON_DOWN:
        if (e->gbutton.which == 0x7e57 || e->gbutton.button == SDL_GAMEPAD_BUTTON_GUIDE ||
            e->gbutton.button >= SDL_GAMEPAD_BUTTON_COUNT)
            return true;
        recompute_pad();
        break;
    case SDL_EVENT_GAMEPAD_BUTTON_UP: case SDL_EVENT_GAMEPAD_AXIS_MOTION:
        if (e->type == SDL_EVENT_GAMEPAD_AXIS_MOTION && e->gaxis.value > 16000 &&
            (e->gaxis.axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER || e->gaxis.axis == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER))
            return true;
        recompute_pad();
        break;
    case SDL_EVENT_JOYSTICK_ADDED: case SDL_EVENT_JOYSTICK_AXIS_MOTION: case SDL_EVENT_JOYSTICK_BUTTON_DOWN:
    case SDL_EVENT_JOYSTICK_BUTTON_UP:
        return true;
    }
    return false;
}

/* input.c push_key / scripted events, with SDL_PushEvent */
static void push_key(SDL_Scancode sc, SDL_Keymod mod, bool down)
{
    SDL_Event e;
    memset(&e, 0, sizeof e);
    e.type = down ? SDL_EVENT_KEY_DOWN : SDL_EVENT_KEY_UP;
    e.key.which = 0x7e57;
    e.key.scancode = sc;
    e.key.key = SDL_GetKeyFromScancode(sc, mod, false);
    e.key.mod = mod;
    e.key.down = down;
    SDL_PushEvent(&e);
}

static void scripted(const char *name, const char *text)
{
    SDL_Event e;
    memset(&e, 0, sizeof e);
    push_key(SDL_GetScancodeFromName(name), SDL_KMOD_NONE, true);
    SDL_Keymod mod = SDL_KMOD_NONE;
    SDL_Scancode sc = SDL_GetScancodeFromKey((SDL_Keycode)tolower((unsigned char)*text), &mod);
    if (isupper((unsigned char)*text))
        mod |= SDL_KMOD_LSHIFT;
    push_key(sc, mod, false);
    e.type = SDL_EVENT_TEXT_INPUT, e.text.windowID = 0x7e57, e.text.text = text;
    SDL_PushEvent(&e);
    e.type = SDL_EVENT_GAMEPAD_BUTTON_DOWN;
    e.gbutton.which = 0x7e57;
    e.gbutton.button = SDL_GAMEPAD_BUTTON_SOUTH;
    SDL_PushEvent(&e);
    e.type = SDL_EVENT_GAMEPAD_AXIS_MOTION;
    e.gaxis.axis = SDL_GAMEPAD_AXIS_LEFT_TRIGGER;
    e.gaxis.value = 32767;
    SDL_PushEvent(&e);
    e.type = SDL_EVENT_KEY_DOWN;
    e.key.scancode = !strcmp(name, "esc") ? SDL_SCANCODE_ESCAPE : SDL_GetScancodeFromName(name);
    SDL_PushEvent(&e);
}

static void event_loops(void)
{
    /* input.c: pads present at startup; bindings.c bind_label_family */
    int n = 0;
    SDL_JoystickID *ids = SDL_GetGamepads(&n);
    if (n > 0 && !pad)
        pad = SDL_OpenGamepad(ids[0]);
    int t = 0;
    if (ids && n > 0)
        t = SDL_GetGamepadTypeForID(ids[0]);
    SDL_free(ids);
    int fam = t == SDL_GAMEPAD_TYPE_XBOX360 || t == SDL_GAMEPAD_TYPE_XBOXONE ? 1
            : t == SDL_GAMEPAD_TYPE_PS3 || t == SDL_GAMEPAD_TYPE_PS4 || t == SDL_GAMEPAD_TYPE_PS5 ? 2 : 0;
    (void)fam;
    bool has = SDL_HasGamepad(); /* pl.c */
    (void)has;

    /* bindings.c: names, capture deadline */
    const char *kn = SDL_GetScancodeName((SDL_Scancode)SDL_SCANCODE_KP_0);
    SDL_Scancode sc = strcmp("none", "none") ? SDL_GetScancodeFromName("Keypad 0") : SDL_SCANCODE_UNKNOWN;
    (void)kn;
    (void)sc;
    static const int16_t k_def_key[] = {SDL_SCANCODE_K, SDL_SCANCODE_J, SDL_SCANCODE_L, SDL_SCANCODE_I, SDL_SCANCODE_F,
                                        SDL_SCANCODE_KP_0, SDL_SCANCODE_Q, SDL_SCANCODE_E, SDL_SCANCODE_1, SDL_SCANCODE_3,
                                        SDL_SCANCODE_RETURN, SDL_SCANCODE_BACKSPACE, SDL_SCANCODE_LEFT, SDL_SCANCODE_UP,
                                        SDL_SCANCODE_RIGHT, SDL_SCANCODE_DOWN, SDL_SCANCODE_W, SDL_SCANCODE_S, SDL_SCANCODE_A,
                                        SDL_SCANCODE_D, SDL_SCANCODE_KP_8, SDL_SCANCODE_KP_5, SDL_SCANCODE_KP_4, SDL_SCANCODE_KP_6};
    static const int16_t k_def_pad[] = {SDL_GAMEPAD_BUTTON_EAST, SDL_GAMEPAD_BUTTON_SOUTH, SDL_GAMEPAD_BUTTON_NORTH,
                                        SDL_GAMEPAD_BUTTON_WEST, SDL_GAMEPAD_BUTTON_LEFT_STICK, SDL_GAMEPAD_BUTTON_RIGHT_STICK,
                                        SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, PADB_LTRIGGER,
                                        PADB_RTRIGGER, SDL_GAMEPAD_BUTTON_START, SDL_GAMEPAD_BUTTON_BACK,
                                        SDL_GAMEPAD_BUTTON_DPAD_LEFT, SDL_GAMEPAD_BUTTON_DPAD_UP, SDL_GAMEPAD_BUTTON_DPAD_RIGHT,
                                        SDL_GAMEPAD_BUTTON_DPAD_DOWN};
    (void)k_def_key;
    (void)k_def_pad;
    uint64_t cap_deadline = SDL_GetTicks() + 5000;
    if (SDL_GetTicks() >= cap_deadline)
        return;

    scripted("Escape", "Zz");

    /* ui_run */
    for (int i = 0; i < 2; i++) {
        SDL_Event e;
        while (SDL_WaitEventTimeout(&e, 16)) {
            if (e.type == SDL_EVENT_QUIT) {
                printf("window closed\n");
                return;
            }
            if (handle(&e))
                continue;
        }
    }
    /* main.c reboot_idle */
    SDL_Event e;
    while (SDL_PollEvent(&e))
        if (e.type == SDL_EVENT_QUIT)
            return;
}

/* ---- services/audio.c: the renderer (F32 stereo) and audout (S16, 1/2/6 channels) streams ---- */
static void apply_gain(SDL_AudioStream *st, float g)
{
    if (st && SDL_GetAudioStreamGain(st) != g)
        SDL_SetAudioStreamGain(st, g);
}

static void audio_streams(void)
{
    uint32_t sample_rate = 48000, sample_count = 240, channels = 2;
    if (!SDL_InitSubSystem(SDL_INIT_AUDIO)) {
        printf("[audren] SDL audio init failed: %s\n", SDL_GetError());
        return;
    }
    SDL_AudioSpec spec = {SDL_AUDIO_F32, 2, (int)sample_rate};
    SDL_AudioStream *stream = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec, NULL, NULL);
    if (!stream) {
        printf("[audren] SDL audio open failed: %s\n", SDL_GetError());
        return;
    }
    if (getenv("LARECOMP_AUDIO_GAIN"))
        SDL_SetAudioStreamGain(stream, (float)atof(getenv("LARECOMP_AUDIO_GAIN")));
    SDL_ResumeAudioStreamDevice(stream);

    /* renderer_tick */
    float out[2 * 4096];
    uint32_t N = sample_count > 4096 ? 4096 : sample_count;
    int frame_bytes = (int)(N * 2 * sizeof(float));
    int target = 4 * frame_bytes;
    SDL_AudioSpec dev;
    int dev_frames = 0;
    if (SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(stream), &dev, &dev_frames) && dev_frames > 0) {
        int tt = (2 * dev_frames * (int)sample_rate / (dev.freq ? dev.freq : 48000) + (int)N) * 2 * (int)sizeof(float);
        if (tt > target)
            target = tt;
    }
    while (SDL_GetAudioStreamQueued(stream) >= target)
        break;
    memset(out, 0, (size_t)frame_bytes);
    apply_gain(stream, 1.0f);
    SDL_PutAudioStreamData(stream, out, frame_bytes);

    /* audout */
    SDL_AudioSpec spec16 = {SDL_AUDIO_S16, (int)channels, (int)sample_rate};
    SDL_AudioStream *a = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK, &spec16, NULL, NULL);
    if (a) {
        SDL_ResumeAudioStreamDevice(a);
        if (!SDL_GetAudioDeviceFormat(SDL_GetAudioStreamDevice(a), &dev, &dev_frames) || dev_frames <= 0)
            dev_frames = 1024;
        int target16 = 2 * dev_frames * 2 * (int)channels;
        uint64_t data = 0, size = 0, frames = 480;
        if (data)
            SDL_PutAudioStreamData(a, (const void *)(uintptr_t)data, (int)size);
        uint64_t limit = SDL_GetTicksNS() + 4 * frames * 1000000000ull / sample_rate + 100000000ull;
        while (SDL_GetAudioStreamQueued(a) > target16) {
            if (SDL_GetTicksNS() > limit) {
                printf("[audout] device stalled (%d bytes queued)\n", SDL_GetAudioStreamQueued(a));
                SDL_ClearAudioStream(a);
                break;
            }
            break;
        }
        SDL_DestroyAudioStream(a);
    }
    SDL_DestroyAudioStream(stream);
}

/* ---- main.c, exec.c: system queries, delays ---- */
static void system_queries(void)
{
    printf("%d cores, %d GB\n", SDL_GetNumLogicalCPUCores(), (SDL_GetSystemRAM() + 512) / 1024);
    int workers = SDL_GetNumLogicalCPUCores() - 4;
    if (workers < 4)
        workers = 4;
    SDL_CreateDirectory("logs");
    uint64_t t0 = SDL_GetTicksNS();
    while (SDL_GetTicksNS() - t0 < 100000ull)
        SDL_DelayPrecise(100000);
    SDL_Delay(1);
    SDL_Delay((Uint32)16);
    SDL_DelayPrecise((Uint64)(1.5 * 1e6));
}

int main(void)
{
    window_and_vulkan();
    event_loops();
    audio_streams();
    system_queries();
    SDL_Quit();
    return 0;
}
