/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: events, the gamepad
 * (libScePad), and the keyboard/mouse that are never pressed.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The DualSense is read once per SDL_PumpEvents with scePadReadState (the cached
 * state, as the probe's poll_pad), its changes become SDL_EVENT_GAMEPAD_* events
 * and a snapshot that SDL_GetGamepadButton / SDL_GetGamepadAxis read from any
 * thread. SDL_EVENT_QUIT is never generated on its own; the one trigger is a stop
 * file (SDL3_PS5_QUIT_FILE, default /download0/za-sdl3.quit, checked once a
 * second), besides SDL_PushEvent from the title itself.
 */
#include "sdl3_ps5_internal.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <sys/stat.h>

/* ------------------------------------------------------------- event queue */

#define QUEUE_CAPACITY 1024

static struct {
    SDL_Event events[QUEUE_CAPACITY];
    unsigned head, count;
    pthread_mutex_t lock;
    bool quit_sent;
    uint64_t last_quit_check_ns;
} queue = {.lock = PTHREAD_MUTEX_INITIALIZER};

void sdl3_ps5_events_init(void)
{
    pthread_mutex_lock(&queue.lock);
    queue.head = queue.count = 0;
    queue.quit_sent = false;
    pthread_mutex_unlock(&queue.lock);
}

void sdl3_ps5_events_quit(void)
{
    sdl3_ps5_events_init();
}

bool sdl3_ps5_queue_event(const SDL_Event *event)
{
    pthread_mutex_lock(&queue.lock);
    if (queue.count == QUEUE_CAPACITY) {
        pthread_mutex_unlock(&queue.lock);
        return SDL_SetError("the event queue is full (%u events)", (unsigned)QUEUE_CAPACITY);
    }
    queue.events[(queue.head + queue.count) % QUEUE_CAPACITY] = *event;
    queue.count++;
    pthread_mutex_unlock(&queue.lock);
    return true;
}

static bool dequeue(SDL_Event *out, bool remove)
{
    pthread_mutex_lock(&queue.lock);
    if (queue.count == 0) {
        pthread_mutex_unlock(&queue.lock);
        return false;
    }
    if (out)
        *out = queue.events[queue.head];
    if (remove) {
        queue.head = (queue.head + 1) % QUEUE_CAPACITY;
        queue.count--;
    }
    pthread_mutex_unlock(&queue.lock);
    return true;
}

bool SDL_PushEvent(SDL_Event *event)
{
    if (!event)
        return SDL_SetError("SDL_PushEvent: NULL event");
    if (event->common.timestamp == 0)
        event->common.timestamp = SDL_GetTicksNS();
    return sdl3_ps5_queue_event(event);
}

static void check_quit_trigger(void)
{
    if (queue.quit_sent)
        return;
    const uint64_t now = SDL_GetTicksNS();
    if (queue.last_quit_check_ns && now - queue.last_quit_check_ns < 1000000000ull)
        return;
    queue.last_quit_check_ns = now;
    const char *path = getenv("SDL3_PS5_QUIT_FILE");
    if (path && !*path)
        return; /* set empty: no file trigger */
    if (!path)
        path = "/download0/za-sdl3.quit";
    struct stat st;
    if (stat(path, &st) != 0)
        return;
    SDL_Event e;
    memset(&e, 0, sizeof(e));
    e.quit.type = SDL_EVENT_QUIT;
    e.quit.timestamp = now;
    if (sdl3_ps5_queue_event(&e)) {
        queue.quit_sent = true;
        sdl3_ps5_log("quit: %s exists; SDL_EVENT_QUIT queued", path);
    }
}

void SDL_PumpEvents(void)
{
    sdl3_ps5_pad_pump();
    check_quit_trigger();
}

bool SDL_PollEvent(SDL_Event *event)
{
    /* The pad is read when the queue runs dry, so a poll loop reads it once (twice at most) per pass. */
    if (dequeue(event, event != NULL))
        return true;
    SDL_PumpEvents();
    return dequeue(event, event != NULL);
}

bool SDL_WaitEventTimeout(SDL_Event *event, Sint32 timeoutMS)
{
    const uint64_t start = SDL_GetTicksNS();
    for (;;) {
        if (SDL_PollEvent(event))
            return true;
        if (timeoutMS == 0)
            return false;
        if (timeoutMS > 0 && SDL_GetTicksNS() - start >= (uint64_t)timeoutMS * 1000000ull)
            return false;
        SDL_DelayNS(1000000ull); /* the pad is polled, not signalled: a millisecond between reads */
    }
}

bool SDL_WaitEvent(SDL_Event *event)
{
    return SDL_WaitEventTimeout(event, -1);
}

/* --------------------------------------------------------------------- pad */

#define PAD_INSTANCE_ID ((SDL_JoystickID)1)
#define PAD_NAME "DualSense Wireless Controller"

struct SDL_Gamepad {
    SDL_JoystickID id;
};
static struct SDL_Gamepad the_gamepad = {PAD_INSTANCE_ID};

static struct {
    bool initialized, opened;
    int user_id, init_rc, open_rc, handle;
    int touchpad_button; /* SDL_GAMEPAD_BUTTON_TOUCHPAD, or BACK with SDL3_PS5_TOUCHPAD_BUTTON=back */
    pthread_mutex_t lock; /* the snapshot below */
    bool connected;
    uint32_t raw_buttons;
    uint32_t buttons; /* bit b = SDL_GamepadButton b held */
    Sint16 axes[SDL_GAMEPAD_AXIS_COUNT];
    int open_refs;
    uint32_t reads, read_failures, intercepted;
} pad = {.user_id = -1, .handle = -1, .touchpad_button = SDL_GAMEPAD_BUTTON_TOUCHPAD, .lock = PTHREAD_MUTEX_INITIALIZER};

/* DualSense bits -> SDL buttons, as SDL's own PS5 mapping (a:b0 Cross ... start:b6 Options, back:b4 Create). */
static const struct {
    uint32_t bit;
    SDL_GamepadButton button;
} button_map[] = {
    {PS5_PAD_BUTTON_CREATE, SDL_GAMEPAD_BUTTON_BACK},
    {PS5_PAD_BUTTON_L3, SDL_GAMEPAD_BUTTON_LEFT_STICK},
    {PS5_PAD_BUTTON_R3, SDL_GAMEPAD_BUTTON_RIGHT_STICK},
    {PS5_PAD_BUTTON_OPTIONS, SDL_GAMEPAD_BUTTON_START},
    {PS5_PAD_BUTTON_UP, SDL_GAMEPAD_BUTTON_DPAD_UP},
    {PS5_PAD_BUTTON_RIGHT, SDL_GAMEPAD_BUTTON_DPAD_RIGHT},
    {PS5_PAD_BUTTON_DOWN, SDL_GAMEPAD_BUTTON_DPAD_DOWN},
    {PS5_PAD_BUTTON_LEFT, SDL_GAMEPAD_BUTTON_DPAD_LEFT},
    {PS5_PAD_BUTTON_L1, SDL_GAMEPAD_BUTTON_LEFT_SHOULDER},
    {PS5_PAD_BUTTON_R1, SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER},
    {PS5_PAD_BUTTON_TRIANGLE, SDL_GAMEPAD_BUTTON_NORTH},
    {PS5_PAD_BUTTON_CIRCLE, SDL_GAMEPAD_BUTTON_EAST},
    {PS5_PAD_BUTTON_CROSS, SDL_GAMEPAD_BUTTON_SOUTH},
    {PS5_PAD_BUTTON_SQUARE, SDL_GAMEPAD_BUTTON_WEST},
};

static uint32_t map_buttons(uint32_t raw)
{
    uint32_t mask = 0;
    for (size_t i = 0; i < sizeof(button_map) / sizeof(button_map[0]); i++) {
        if (raw & button_map[i].bit)
            mask |= 1u << button_map[i].button;
    }
    if (raw & PS5_PAD_BUTTON_TOUCH_PAD)
        mask |= 1u << pad.touchpad_button;
    return mask;
}

/* SDL's HIDAPI PS5 driver: a stick byte becomes value * 257 - 32768 (0 up / left); a trigger byte 0..32767. */
static Sint16 stick_axis(uint8_t value)
{
    return (Sint16)((int)value * 257 - 32768);
}

static Sint16 trigger_axis(uint8_t value)
{
    return (Sint16)(((int)value * 32767) / 255);
}

bool sdl3_ps5_pad_init(void)
{
    if (pad.initialized)
        return pad.opened;
    pad.initialized = true;
    const char *touchpad = sdl3_ps5_env("SDL3_PS5_TOUCHPAD_BUTTON");
    pad.touchpad_button = touchpad && strcasecmp(touchpad, "back") == 0 ? SDL_GAMEPAD_BUTTON_BACK : SDL_GAMEPAD_BUTTON_TOUCHPAD;
    pad.user_id = sdl3_ps5_user_id();
    if (pad.user_id < 0) {
        sdl3_ps5_log("pad: no user id from User Service; no gamepad");
        return false;
    }
    /* As the probe: scePadInit, scePadOpen on the standard port, a handle the process already holds as the fallback. */
    pad.init_rc = scePadInit();
    pad.open_rc = scePadOpen(pad.user_id, PS5_PAD_PORT_TYPE_STANDARD, 0, NULL);
    pad.handle = pad.open_rc;
    if (pad.handle < 0)
        pad.handle = scePadGetHandle(pad.user_id, PS5_PAD_PORT_TYPE_STANDARD, 0);
    sdl3_ps5_log("pad: scePadInit rc=0x%08x, scePadOpen rc=0x%08x, handle %d, touchpad click -> SDL button %d",
                 (unsigned)pad.init_rc, (unsigned)pad.open_rc, pad.handle, pad.touchpad_button);
    if (pad.handle < 0)
        return false;
    pad.opened = true;
    /* The first SDL_PumpEvents reads the pad; a pad present then is announced with SDL_EVENT_GAMEPAD_ADDED. */
    return true;
}

void sdl3_ps5_pad_quit(void)
{
    if (pad.opened) {
        const int rc = scePadClose(pad.handle);
        sdl3_ps5_log("pad: scePadClose rc=0x%08x after %u reads (%u failed, %u intercepted)", (unsigned)rc, pad.reads,
                     pad.read_failures, pad.intercepted);
    }
    pthread_mutex_lock(&pad.lock);
    pad.opened = false;
    pad.initialized = false;
    pad.handle = -1;
    pad.connected = false;
    pad.buttons = pad.raw_buttons = 0;
    memset(pad.axes, 0, sizeof(pad.axes));
    pad.open_refs = 0;
    pthread_mutex_unlock(&pad.lock);
}

static void push_pad_event(SDL_Event *e)
{
    e->common.timestamp = SDL_GetTicksNS();
    sdl3_ps5_queue_event(e);
}

static void push_device_event(SDL_EventType type)
{
    SDL_Event e;
    memset(&e, 0, sizeof(e));
    e.gdevice.type = type;
    e.gdevice.which = PAD_INSTANCE_ID;
    push_pad_event(&e);
}

static void push_button_event(int button, bool down)
{
    SDL_Event e;
    memset(&e, 0, sizeof(e));
    e.gbutton.type = down ? SDL_EVENT_GAMEPAD_BUTTON_DOWN : SDL_EVENT_GAMEPAD_BUTTON_UP;
    e.gbutton.which = PAD_INSTANCE_ID;
    e.gbutton.button = (Uint8)button;
    e.gbutton.down = down;
    push_pad_event(&e);
}

static void push_axis_event(int axis, Sint16 value)
{
    SDL_Event e;
    memset(&e, 0, sizeof(e));
    e.gaxis.type = SDL_EVENT_GAMEPAD_AXIS_MOTION;
    e.gaxis.which = PAD_INSTANCE_ID;
    e.gaxis.axis = (Uint8)axis;
    e.gaxis.value = value;
    push_pad_event(&e);
}

void sdl3_ps5_pad_pump(void)
{
    if (!pad.opened)
        return;
    union {
        struct ps5_pad_record record;
        uint8_t raw[256]; /* twice the record, as the probe reads it */
    } data;
    memset(&data, 0, sizeof(data));
    const int rc = scePadReadState(pad.handle, &data);
    pad.reads++;
    if (rc != 0) {
        pad.read_failures++;
        if (pad.read_failures <= 3 || pad.read_failures % 1000 == 0)
            sdl3_ps5_log("pad: scePadReadState rc=0x%08x (%u failures)", (unsigned)rc, pad.read_failures);
        return; /* the last snapshot stands */
    }
    const bool connected = data.record.connected != 0;
    uint32_t raw = data.record.buttons;
    if (raw & PS5_PAD_BUTTON_INTERCEPTED) {
        raw = 0; /* the system has the input (the PS button's menu): everything released */
        pad.intercepted++;
    }
    const uint32_t buttons = connected ? map_buttons(raw) : 0;
    Sint16 axes[SDL_GAMEPAD_AXIS_COUNT] = {0, 0, 0, 0, 0, 0};
    if (connected) {
        axes[SDL_GAMEPAD_AXIS_LEFTX] = stick_axis(data.record.left_x);
        axes[SDL_GAMEPAD_AXIS_LEFTY] = stick_axis(data.record.left_y);
        axes[SDL_GAMEPAD_AXIS_RIGHTX] = stick_axis(data.record.right_x);
        axes[SDL_GAMEPAD_AXIS_RIGHTY] = stick_axis(data.record.right_y);
        axes[SDL_GAMEPAD_AXIS_LEFT_TRIGGER] = trigger_axis(data.record.l2);
        axes[SDL_GAMEPAD_AXIS_RIGHT_TRIGGER] = trigger_axis(data.record.r2);
    }

    pthread_mutex_lock(&pad.lock);
    const bool was_connected = pad.connected;
    const uint32_t old_buttons = pad.buttons;
    Sint16 old_axes[SDL_GAMEPAD_AXIS_COUNT];
    memcpy(old_axes, pad.axes, sizeof(old_axes));
    pad.connected = connected;
    pad.raw_buttons = raw;
    pad.buttons = buttons;
    memcpy(pad.axes, axes, sizeof(pad.axes));
    pthread_mutex_unlock(&pad.lock);

    if (connected && !was_connected) {
        sdl3_ps5_log("pad: connected (" PAD_NAME ", instance %u)", (unsigned)PAD_INSTANCE_ID);
        push_device_event(SDL_EVENT_GAMEPAD_ADDED);
    } else if (!connected && was_connected) {
        sdl3_ps5_log("pad: disconnected");
        push_device_event(SDL_EVENT_GAMEPAD_REMOVED);
    }
    if (!connected)
        return;
    for (int b = 0; b < SDL_GAMEPAD_BUTTON_COUNT; b++) {
        const uint32_t bit = 1u << b;
        if ((buttons ^ old_buttons) & bit)
            push_button_event(b, (buttons & bit) != 0);
    }
    for (int a = 0; a < SDL_GAMEPAD_AXIS_COUNT; a++) {
        if (axes[a] != old_axes[a])
            push_axis_event(a, axes[a]);
    }
}

static bool pad_connected(void)
{
    pthread_mutex_lock(&pad.lock);
    const bool connected = pad.opened && pad.connected;
    pthread_mutex_unlock(&pad.lock);
    return connected;
}

/* ----------------------------------------------------------- gamepad API */

bool SDL_HasGamepad(void)
{
    return pad_connected();
}

SDL_JoystickID *SDL_GetGamepads(int *count)
{
    SDL_JoystickID *ids = SDL_malloc(2 * sizeof(*ids));
    if (!ids) {
        if (count)
            *count = 0;
        SDL_SetError("SDL_GetGamepads: out of memory");
        return NULL;
    }
    int n = 0;
    if (pad_connected())
        ids[n++] = PAD_INSTANCE_ID;
    ids[n] = 0;
    if (count)
        *count = n;
    return ids;
}

const char *SDL_GetGamepadNameForID(SDL_JoystickID instance_id)
{
    if (instance_id != PAD_INSTANCE_ID || !pad.opened) {
        SDL_SetError("SDL_GetGamepadNameForID: no gamepad %u", (unsigned)instance_id);
        return NULL;
    }
    return PAD_NAME;
}

SDL_GamepadType SDL_GetGamepadTypeForID(SDL_JoystickID instance_id)
{
    return instance_id == PAD_INSTANCE_ID && pad.opened ? SDL_GAMEPAD_TYPE_PS5 : SDL_GAMEPAD_TYPE_UNKNOWN;
}

SDL_Gamepad *SDL_OpenGamepad(SDL_JoystickID instance_id)
{
    if (instance_id != PAD_INSTANCE_ID || !pad_connected()) {
        SDL_SetError("SDL_OpenGamepad: gamepad %u is not connected", (unsigned)instance_id);
        return NULL;
    }
    pthread_mutex_lock(&pad.lock);
    pad.open_refs++;
    pthread_mutex_unlock(&pad.lock);
    return &the_gamepad;
}

void SDL_CloseGamepad(SDL_Gamepad *gamepad)
{
    if (gamepad != &the_gamepad)
        return;
    pthread_mutex_lock(&pad.lock);
    if (pad.open_refs > 0)
        pad.open_refs--;
    pthread_mutex_unlock(&pad.lock);
}

SDL_JoystickID SDL_GetGamepadID(SDL_Gamepad *gamepad)
{
    return gamepad == &the_gamepad ? PAD_INSTANCE_ID : 0;
}

const char *SDL_GetGamepadName(SDL_Gamepad *gamepad)
{
    if (gamepad != &the_gamepad) {
        SDL_SetError("SDL_GetGamepadName: invalid gamepad");
        return NULL;
    }
    return PAD_NAME;
}

SDL_GamepadType SDL_GetGamepadType(SDL_Gamepad *gamepad)
{
    return gamepad == &the_gamepad ? SDL_GAMEPAD_TYPE_PS5 : SDL_GAMEPAD_TYPE_UNKNOWN;
}

Sint16 SDL_GetGamepadAxis(SDL_Gamepad *gamepad, SDL_GamepadAxis axis)
{
    if (gamepad != &the_gamepad || axis < 0 || axis >= SDL_GAMEPAD_AXIS_COUNT)
        return 0;
    pthread_mutex_lock(&pad.lock);
    const Sint16 value = pad.axes[axis];
    pthread_mutex_unlock(&pad.lock);
    return value;
}

bool SDL_GetGamepadButton(SDL_Gamepad *gamepad, SDL_GamepadButton button)
{
    if (gamepad != &the_gamepad || button < 0 || button >= SDL_GAMEPAD_BUTTON_COUNT)
        return false;
    pthread_mutex_lock(&pad.lock);
    const bool down = (pad.buttons >> button) & 1u;
    pthread_mutex_unlock(&pad.lock);
    return down;
}

/* ---------------------------------------------------- keyboard and mouse */

/* The SDL names of the scancodes the shim knows (SDL_scancode.h subset), with the US-layout key they produce. */
#define K(scancode, name, key, shifted) {scancode, name, key, shifted}
static const struct {
    SDL_Scancode scancode;
    const char *name;
    char key, shifted;
} keys[] = {
    K(SDL_SCANCODE_A, "A", 'a', 0),           K(SDL_SCANCODE_B, "B", 'b', 0),
    K(SDL_SCANCODE_C, "C", 'c', 0),           K(SDL_SCANCODE_D, "D", 'd', 0),
    K(SDL_SCANCODE_E, "E", 'e', 0),           K(SDL_SCANCODE_F, "F", 'f', 0),
    K(SDL_SCANCODE_G, "G", 'g', 0),           K(SDL_SCANCODE_H, "H", 'h', 0),
    K(SDL_SCANCODE_I, "I", 'i', 0),           K(SDL_SCANCODE_J, "J", 'j', 0),
    K(SDL_SCANCODE_K, "K", 'k', 0),           K(SDL_SCANCODE_L, "L", 'l', 0),
    K(SDL_SCANCODE_M, "M", 'm', 0),           K(SDL_SCANCODE_N, "N", 'n', 0),
    K(SDL_SCANCODE_O, "O", 'o', 0),           K(SDL_SCANCODE_P, "P", 'p', 0),
    K(SDL_SCANCODE_Q, "Q", 'q', 0),           K(SDL_SCANCODE_R, "R", 'r', 0),
    K(SDL_SCANCODE_S, "S", 's', 0),           K(SDL_SCANCODE_T, "T", 't', 0),
    K(SDL_SCANCODE_U, "U", 'u', 0),           K(SDL_SCANCODE_V, "V", 'v', 0),
    K(SDL_SCANCODE_W, "W", 'w', 0),           K(SDL_SCANCODE_X, "X", 'x', 0),
    K(SDL_SCANCODE_Y, "Y", 'y', 0),           K(SDL_SCANCODE_Z, "Z", 'z', 0),
    K(SDL_SCANCODE_1, "1", '1', '!'),         K(SDL_SCANCODE_2, "2", '2', '@'),
    K(SDL_SCANCODE_3, "3", '3', '#'),         K(SDL_SCANCODE_4, "4", '4', '$'),
    K(SDL_SCANCODE_5, "5", '5', '%'),         K(SDL_SCANCODE_6, "6", '6', '^'),
    K(SDL_SCANCODE_7, "7", '7', '&'),         K(SDL_SCANCODE_8, "8", '8', '*'),
    K(SDL_SCANCODE_9, "9", '9', '('),         K(SDL_SCANCODE_0, "0", '0', ')'),
    K(SDL_SCANCODE_RETURN, "Return", '\r', 0), K(SDL_SCANCODE_ESCAPE, "Escape", 0x1b, 0),
    K(SDL_SCANCODE_BACKSPACE, "Backspace", '\b', 0), K(SDL_SCANCODE_TAB, "Tab", '\t', 0),
    K(SDL_SCANCODE_SPACE, "Space", ' ', 0),   K(SDL_SCANCODE_MINUS, "-", '-', '_'),
    K(SDL_SCANCODE_EQUALS, "=", '=', '+'),    K(SDL_SCANCODE_LEFTBRACKET, "[", '[', '{'),
    K(SDL_SCANCODE_RIGHTBRACKET, "]", ']', '}'), K(SDL_SCANCODE_BACKSLASH, "\\", '\\', '|'),
    K(SDL_SCANCODE_SEMICOLON, ";", ';', ':'), K(SDL_SCANCODE_APOSTROPHE, "'", '\'', '"'),
    K(SDL_SCANCODE_GRAVE, "`", '`', '~'),     K(SDL_SCANCODE_COMMA, ",", ',', '<'),
    K(SDL_SCANCODE_PERIOD, ".", '.', '>'),    K(SDL_SCANCODE_SLASH, "/", '/', '?'),
    K(SDL_SCANCODE_CAPSLOCK, "CapsLock", 0, 0),
    K(SDL_SCANCODE_F1, "F1", 0, 0),           K(SDL_SCANCODE_F2, "F2", 0, 0),
    K(SDL_SCANCODE_F3, "F3", 0, 0),           K(SDL_SCANCODE_F4, "F4", 0, 0),
    K(SDL_SCANCODE_F5, "F5", 0, 0),           K(SDL_SCANCODE_F6, "F6", 0, 0),
    K(SDL_SCANCODE_F7, "F7", 0, 0),           K(SDL_SCANCODE_F8, "F8", 0, 0),
    K(SDL_SCANCODE_F9, "F9", 0, 0),           K(SDL_SCANCODE_F10, "F10", 0, 0),
    K(SDL_SCANCODE_F11, "F11", 0, 0),         K(SDL_SCANCODE_F12, "F12", 0, 0),
    K(SDL_SCANCODE_PRINTSCREEN, "PrintScreen", 0, 0), K(SDL_SCANCODE_SCROLLLOCK, "ScrollLock", 0, 0),
    K(SDL_SCANCODE_PAUSE, "Pause", 0, 0),     K(SDL_SCANCODE_INSERT, "Insert", 0, 0),
    K(SDL_SCANCODE_HOME, "Home", 0, 0),       K(SDL_SCANCODE_PAGEUP, "PageUp", 0, 0),
    K(SDL_SCANCODE_DELETE, "Delete", 0x7f, 0), K(SDL_SCANCODE_END, "End", 0, 0),
    K(SDL_SCANCODE_PAGEDOWN, "PageDown", 0, 0), K(SDL_SCANCODE_RIGHT, "Right", 0, 0),
    K(SDL_SCANCODE_LEFT, "Left", 0, 0),       K(SDL_SCANCODE_DOWN, "Down", 0, 0),
    K(SDL_SCANCODE_UP, "Up", 0, 0),           K(SDL_SCANCODE_NUMLOCKCLEAR, "Numlock", 0, 0),
    K(SDL_SCANCODE_KP_DIVIDE, "Keypad /", '/', 0), K(SDL_SCANCODE_KP_MULTIPLY, "Keypad *", '*', 0),
    K(SDL_SCANCODE_KP_MINUS, "Keypad -", '-', 0), K(SDL_SCANCODE_KP_PLUS, "Keypad +", '+', 0),
    K(SDL_SCANCODE_KP_ENTER, "Keypad Enter", 0, 0),
    K(SDL_SCANCODE_KP_1, "Keypad 1", 0, 0),   K(SDL_SCANCODE_KP_2, "Keypad 2", 0, 0),
    K(SDL_SCANCODE_KP_3, "Keypad 3", 0, 0),   K(SDL_SCANCODE_KP_4, "Keypad 4", 0, 0),
    K(SDL_SCANCODE_KP_5, "Keypad 5", 0, 0),   K(SDL_SCANCODE_KP_6, "Keypad 6", 0, 0),
    K(SDL_SCANCODE_KP_7, "Keypad 7", 0, 0),   K(SDL_SCANCODE_KP_8, "Keypad 8", 0, 0),
    K(SDL_SCANCODE_KP_9, "Keypad 9", 0, 0),   K(SDL_SCANCODE_KP_0, "Keypad 0", 0, 0),
    K(SDL_SCANCODE_KP_PERIOD, "Keypad .", 0, 0),
    K(SDL_SCANCODE_LCTRL, "Left Ctrl", 0, 0), K(SDL_SCANCODE_LSHIFT, "Left Shift", 0, 0),
    K(SDL_SCANCODE_LALT, "Left Alt", 0, 0),   K(SDL_SCANCODE_LGUI, "Left GUI", 0, 0),
    K(SDL_SCANCODE_RCTRL, "Right Ctrl", 0, 0), K(SDL_SCANCODE_RSHIFT, "Right Shift", 0, 0),
    K(SDL_SCANCODE_RALT, "Right Alt", 0, 0),  K(SDL_SCANCODE_RGUI, "Right GUI", 0, 0),
};
#undef K
#define KEY_COUNT (sizeof(keys) / sizeof(keys[0]))

const char *SDL_GetScancodeName(SDL_Scancode scancode)
{
    for (size_t i = 0; i < KEY_COUNT; i++) {
        if (keys[i].scancode == scancode)
            return keys[i].name;
    }
    return ""; /* SDL: an empty string for a scancode without a name */
}

SDL_Scancode SDL_GetScancodeFromName(const char *name)
{
    if (!name || !*name) {
        SDL_SetError("SDL_GetScancodeFromName: invalid name");
        return SDL_SCANCODE_UNKNOWN;
    }
    for (size_t i = 0; i < KEY_COUNT; i++) {
        if (strcasecmp(keys[i].name, name) == 0)
            return keys[i].scancode;
    }
    SDL_SetError("SDL_GetScancodeFromName: scancode \"%s\" not found", name);
    return SDL_SCANCODE_UNKNOWN;
}

SDL_Keycode SDL_GetKeyFromScancode(SDL_Scancode scancode, SDL_Keymod modstate, bool key_event)
{
    (void)key_event;
    for (size_t i = 0; i < KEY_COUNT; i++) {
        if (keys[i].scancode != scancode)
            continue;
        if (!keys[i].key)
            return SDL_SCANCODE_TO_KEYCODE((SDL_Keycode)scancode);
        char c = keys[i].key;
        if (modstate & SDL_KMOD_SHIFT) {
            if (keys[i].shifted)
                c = keys[i].shifted;
            else if (c >= 'a' && c <= 'z')
                c = (char)(c - 'a' + 'A');
        }
        return (SDL_Keycode)(unsigned char)c;
    }
    if (scancode <= SDL_SCANCODE_UNKNOWN || scancode >= SDL_SCANCODE_COUNT)
        return SDLK_UNKNOWN;
    return SDL_SCANCODE_TO_KEYCODE((SDL_Keycode)scancode);
}

SDL_Scancode SDL_GetScancodeFromKey(SDL_Keycode key, SDL_Keymod *modstate)
{
    if (modstate)
        *modstate = SDL_KMOD_NONE;
    if (key & SDLK_SCANCODE_MASK) {
        const SDL_Keycode scancode = key & ~SDLK_SCANCODE_MASK;
        return scancode < SDL_SCANCODE_COUNT ? (SDL_Scancode)scancode : SDL_SCANCODE_UNKNOWN;
    }
    if (key >= 'A' && key <= 'Z') {
        if (modstate)
            *modstate = SDL_KMOD_LSHIFT;
        key = key - 'A' + 'a';
    }
    for (size_t i = 0; i < KEY_COUNT; i++) {
        if (keys[i].key && (SDL_Keycode)(unsigned char)keys[i].key == key)
            return keys[i].scancode;
    }
    for (size_t i = 0; i < KEY_COUNT; i++) {
        if (keys[i].shifted && (SDL_Keycode)(unsigned char)keys[i].shifted == key) {
            if (modstate)
                *modstate = SDL_KMOD_LSHIFT;
            return keys[i].scancode;
        }
    }
    return SDL_SCANCODE_UNKNOWN;
}

bool SDL_SetWindowRelativeMouseMode(SDL_Window *window, bool enabled)
{
    (void)window;
    (void)enabled; /* no mouse to hold */
    return true;
}
