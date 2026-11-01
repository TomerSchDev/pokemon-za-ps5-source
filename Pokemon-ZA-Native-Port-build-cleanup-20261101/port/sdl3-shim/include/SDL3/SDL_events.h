/*
 * SDL3 shim (PS5): SDL_events.h - subset of SDL 3.4.18.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * The event type values are the complete SDL list (they are the ABI); of the event
 * records only those the runtime reads or writes are in the union, each laid out
 * exactly as SDL 3.4.18 lays it out. The union is 128 bytes, as in SDL.
 */
#ifndef SDL_events_h_
#define SDL_events_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_gamepad.h>
#include <SDL3/SDL_joystick.h>
#include <SDL3/SDL_keyboard.h>
#include <SDL3/SDL_keycode.h>
#include <SDL3/SDL_mouse.h>
#include <SDL3/SDL_scancode.h>
#include <SDL3/SDL_video.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum SDL_EventType {
    SDL_EVENT_FIRST = 0,
    SDL_EVENT_QUIT = 0x100,
    SDL_EVENT_TERMINATING,
    SDL_EVENT_LOW_MEMORY,
    SDL_EVENT_WILL_ENTER_BACKGROUND,
    SDL_EVENT_DID_ENTER_BACKGROUND,
    SDL_EVENT_WILL_ENTER_FOREGROUND,
    SDL_EVENT_DID_ENTER_FOREGROUND,
    SDL_EVENT_LOCALE_CHANGED,
    SDL_EVENT_SYSTEM_THEME_CHANGED,
    SDL_EVENT_DISPLAY_ORIENTATION = 0x151,
    SDL_EVENT_DISPLAY_ADDED,
    SDL_EVENT_DISPLAY_REMOVED,
    SDL_EVENT_DISPLAY_MOVED,
    SDL_EVENT_DISPLAY_DESKTOP_MODE_CHANGED,
    SDL_EVENT_DISPLAY_CURRENT_MODE_CHANGED,
    SDL_EVENT_DISPLAY_CONTENT_SCALE_CHANGED,
    SDL_EVENT_DISPLAY_USABLE_BOUNDS_CHANGED,
    SDL_EVENT_DISPLAY_FIRST = SDL_EVENT_DISPLAY_ORIENTATION,
    SDL_EVENT_DISPLAY_LAST = SDL_EVENT_DISPLAY_USABLE_BOUNDS_CHANGED,
    SDL_EVENT_WINDOW_SHOWN = 0x202,
    SDL_EVENT_WINDOW_HIDDEN,
    SDL_EVENT_WINDOW_EXPOSED,
    SDL_EVENT_WINDOW_MOVED,
    SDL_EVENT_WINDOW_RESIZED,
    SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED,
    SDL_EVENT_WINDOW_METAL_VIEW_RESIZED,
    SDL_EVENT_WINDOW_MINIMIZED,
    SDL_EVENT_WINDOW_MAXIMIZED,
    SDL_EVENT_WINDOW_RESTORED,
    SDL_EVENT_WINDOW_MOUSE_ENTER,
    SDL_EVENT_WINDOW_MOUSE_LEAVE,
    SDL_EVENT_WINDOW_FOCUS_GAINED,
    SDL_EVENT_WINDOW_FOCUS_LOST,
    SDL_EVENT_WINDOW_CLOSE_REQUESTED,
    SDL_EVENT_WINDOW_HIT_TEST,
    SDL_EVENT_WINDOW_ICCPROF_CHANGED,
    SDL_EVENT_WINDOW_DISPLAY_CHANGED,
    SDL_EVENT_WINDOW_DISPLAY_SCALE_CHANGED,
    SDL_EVENT_WINDOW_SAFE_AREA_CHANGED,
    SDL_EVENT_WINDOW_OCCLUDED,
    SDL_EVENT_WINDOW_ENTER_FULLSCREEN,
    SDL_EVENT_WINDOW_LEAVE_FULLSCREEN,
    SDL_EVENT_WINDOW_DESTROYED,
    SDL_EVENT_WINDOW_HDR_STATE_CHANGED,
    SDL_EVENT_WINDOW_FIRST = SDL_EVENT_WINDOW_SHOWN,
    SDL_EVENT_WINDOW_LAST = SDL_EVENT_WINDOW_HDR_STATE_CHANGED,
    SDL_EVENT_KEY_DOWN = 0x300,
    SDL_EVENT_KEY_UP,
    SDL_EVENT_TEXT_EDITING,
    SDL_EVENT_TEXT_INPUT,
    SDL_EVENT_KEYMAP_CHANGED,
    SDL_EVENT_KEYBOARD_ADDED,
    SDL_EVENT_KEYBOARD_REMOVED,
    SDL_EVENT_TEXT_EDITING_CANDIDATES,
    SDL_EVENT_SCREEN_KEYBOARD_SHOWN,
    SDL_EVENT_SCREEN_KEYBOARD_HIDDEN,
    SDL_EVENT_MOUSE_MOTION = 0x400,
    SDL_EVENT_MOUSE_BUTTON_DOWN,
    SDL_EVENT_MOUSE_BUTTON_UP,
    SDL_EVENT_MOUSE_WHEEL,
    SDL_EVENT_MOUSE_ADDED,
    SDL_EVENT_MOUSE_REMOVED,
    SDL_EVENT_JOYSTICK_AXIS_MOTION = 0x600,
    SDL_EVENT_JOYSTICK_BALL_MOTION,
    SDL_EVENT_JOYSTICK_HAT_MOTION,
    SDL_EVENT_JOYSTICK_BUTTON_DOWN,
    SDL_EVENT_JOYSTICK_BUTTON_UP,
    SDL_EVENT_JOYSTICK_ADDED,
    SDL_EVENT_JOYSTICK_REMOVED,
    SDL_EVENT_JOYSTICK_BATTERY_UPDATED,
    SDL_EVENT_JOYSTICK_UPDATE_COMPLETE,
    SDL_EVENT_GAMEPAD_AXIS_MOTION = 0x650,
    SDL_EVENT_GAMEPAD_BUTTON_DOWN,
    SDL_EVENT_GAMEPAD_BUTTON_UP,
    SDL_EVENT_GAMEPAD_ADDED,
    SDL_EVENT_GAMEPAD_REMOVED,
    SDL_EVENT_GAMEPAD_REMAPPED,
    SDL_EVENT_GAMEPAD_TOUCHPAD_DOWN,
    SDL_EVENT_GAMEPAD_TOUCHPAD_MOTION,
    SDL_EVENT_GAMEPAD_TOUCHPAD_UP,
    SDL_EVENT_GAMEPAD_SENSOR_UPDATE,
    SDL_EVENT_GAMEPAD_UPDATE_COMPLETE,
    SDL_EVENT_GAMEPAD_STEAM_HANDLE_UPDATED,
    SDL_EVENT_FINGER_DOWN = 0x700,
    SDL_EVENT_FINGER_UP,
    SDL_EVENT_FINGER_MOTION,
    SDL_EVENT_FINGER_CANCELED,
    SDL_EVENT_PINCH_BEGIN = 0x710,
    SDL_EVENT_PINCH_UPDATE,
    SDL_EVENT_PINCH_END,
    SDL_EVENT_CLIPBOARD_UPDATE = 0x900,
    SDL_EVENT_DROP_FILE = 0x1000,
    SDL_EVENT_DROP_TEXT,
    SDL_EVENT_DROP_BEGIN,
    SDL_EVENT_DROP_COMPLETE,
    SDL_EVENT_DROP_POSITION,
    SDL_EVENT_AUDIO_DEVICE_ADDED = 0x1100,
    SDL_EVENT_AUDIO_DEVICE_REMOVED,
    SDL_EVENT_AUDIO_DEVICE_FORMAT_CHANGED,
    SDL_EVENT_SENSOR_UPDATE = 0x1200,
    SDL_EVENT_PEN_PROXIMITY_IN = 0x1300,
    SDL_EVENT_PEN_PROXIMITY_OUT,
    SDL_EVENT_PEN_DOWN,
    SDL_EVENT_PEN_UP,
    SDL_EVENT_PEN_BUTTON_DOWN,
    SDL_EVENT_PEN_BUTTON_UP,
    SDL_EVENT_PEN_MOTION,
    SDL_EVENT_PEN_AXIS,
    SDL_EVENT_CAMERA_DEVICE_ADDED = 0x1400,
    SDL_EVENT_CAMERA_DEVICE_REMOVED,
    SDL_EVENT_CAMERA_DEVICE_APPROVED,
    SDL_EVENT_CAMERA_DEVICE_DENIED,
    SDL_EVENT_RENDER_TARGETS_RESET = 0x2000,
    SDL_EVENT_RENDER_DEVICE_RESET,
    SDL_EVENT_RENDER_DEVICE_LOST,
    SDL_EVENT_PRIVATE0 = 0x4000,
    SDL_EVENT_PRIVATE1,
    SDL_EVENT_PRIVATE2,
    SDL_EVENT_PRIVATE3,
    SDL_EVENT_POLL_SENTINEL = 0x7F00,
    SDL_EVENT_USER = 0x8000,
    SDL_EVENT_LAST = 0xFFFF,
    SDL_EVENT_ENUM_PADDING = 0x7FFFFFFF
} SDL_EventType;

typedef struct SDL_CommonEvent {
    Uint32 type;
    Uint32 reserved;
    Uint64 timestamp; /**< In nanoseconds, populated using SDL_GetTicksNS() */
} SDL_CommonEvent;

typedef struct SDL_WindowEvent {
    SDL_EventType type;
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    Sint32 data1;
    Sint32 data2;
} SDL_WindowEvent;

typedef struct SDL_KeyboardEvent {
    SDL_EventType type; /**< SDL_EVENT_KEY_DOWN or SDL_EVENT_KEY_UP */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    SDL_KeyboardID which;
    SDL_Scancode scancode;
    SDL_Keycode key;
    SDL_Keymod mod;
    Uint16 raw;
    bool down;
    bool repeat;
} SDL_KeyboardEvent;

typedef struct SDL_TextEditingEvent {
    SDL_EventType type; /**< SDL_EVENT_TEXT_EDITING */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    const char *text;
    Sint32 start;
    Sint32 length;
} SDL_TextEditingEvent;

typedef struct SDL_TextInputEvent {
    SDL_EventType type; /**< SDL_EVENT_TEXT_INPUT */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    const char *text;
} SDL_TextInputEvent;

typedef struct SDL_MouseMotionEvent {
    SDL_EventType type; /**< SDL_EVENT_MOUSE_MOTION */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    SDL_MouseID which;
    SDL_MouseButtonFlags state;
    float x;
    float y;
    float xrel;
    float yrel;
} SDL_MouseMotionEvent;

typedef struct SDL_MouseButtonEvent {
    SDL_EventType type; /**< SDL_EVENT_MOUSE_BUTTON_DOWN or SDL_EVENT_MOUSE_BUTTON_UP */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    SDL_MouseID which;
    Uint8 button;
    bool down;
    Uint8 clicks;
    Uint8 padding;
    float x;
    float y;
} SDL_MouseButtonEvent;

typedef struct SDL_MouseWheelEvent {
    SDL_EventType type; /**< SDL_EVENT_MOUSE_WHEEL */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    SDL_MouseID which;
    float x;
    float y;
    SDL_MouseWheelDirection direction;
    float mouse_x;
    float mouse_y;
    Sint32 integer_x;
    Sint32 integer_y;
} SDL_MouseWheelEvent;

typedef struct SDL_JoyAxisEvent {
    SDL_EventType type; /**< SDL_EVENT_JOYSTICK_AXIS_MOTION */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
    Uint8 axis;
    Uint8 padding1;
    Uint8 padding2;
    Uint8 padding3;
    Sint16 value;
    Uint16 padding4;
} SDL_JoyAxisEvent;

typedef struct SDL_JoyButtonEvent {
    SDL_EventType type; /**< SDL_EVENT_JOYSTICK_BUTTON_DOWN or SDL_EVENT_JOYSTICK_BUTTON_UP */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
    Uint8 button;
    bool down;
    Uint8 padding1;
    Uint8 padding2;
} SDL_JoyButtonEvent;

typedef struct SDL_JoyDeviceEvent {
    SDL_EventType type; /**< SDL_EVENT_JOYSTICK_ADDED or SDL_EVENT_JOYSTICK_REMOVED */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
} SDL_JoyDeviceEvent;

typedef struct SDL_GamepadAxisEvent {
    SDL_EventType type; /**< SDL_EVENT_GAMEPAD_AXIS_MOTION */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
    Uint8 axis; /**< SDL_GamepadAxis */
    Uint8 padding1;
    Uint8 padding2;
    Uint8 padding3;
    Sint16 value;
    Uint16 padding4;
} SDL_GamepadAxisEvent;

typedef struct SDL_GamepadButtonEvent {
    SDL_EventType type; /**< SDL_EVENT_GAMEPAD_BUTTON_DOWN or SDL_EVENT_GAMEPAD_BUTTON_UP */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
    Uint8 button; /**< SDL_GamepadButton */
    bool down;
    Uint8 padding1;
    Uint8 padding2;
} SDL_GamepadButtonEvent;

typedef struct SDL_GamepadDeviceEvent {
    SDL_EventType type; /**< SDL_EVENT_GAMEPAD_ADDED, SDL_EVENT_GAMEPAD_REMOVED, ... */
    Uint32 reserved;
    Uint64 timestamp;
    SDL_JoystickID which;
} SDL_GamepadDeviceEvent;

typedef struct SDL_QuitEvent {
    SDL_EventType type; /**< SDL_EVENT_QUIT */
    Uint32 reserved;
    Uint64 timestamp;
} SDL_QuitEvent;

typedef struct SDL_UserEvent {
    Uint32 type;
    Uint32 reserved;
    Uint64 timestamp;
    SDL_WindowID windowID;
    Sint32 code;
    void *data1;
    void *data2;
} SDL_UserEvent;

/* The members the runtime touches; every SDL member starts at offset 0 and the size is the padding. */
typedef union SDL_Event {
    Uint32 type;
    SDL_CommonEvent common;
    SDL_WindowEvent window;
    SDL_KeyboardEvent key;
    SDL_TextEditingEvent edit;
    SDL_TextInputEvent text;
    SDL_MouseMotionEvent motion;
    SDL_MouseButtonEvent button;
    SDL_MouseWheelEvent wheel;
    SDL_JoyDeviceEvent jdevice;
    SDL_JoyAxisEvent jaxis;
    SDL_JoyButtonEvent jbutton;
    SDL_GamepadDeviceEvent gdevice;
    SDL_GamepadAxisEvent gaxis;
    SDL_GamepadButtonEvent gbutton;
    SDL_QuitEvent quit;
    SDL_UserEvent user;
    Uint8 padding[128];
} SDL_Event;

SDL_COMPILE_TIME_ASSERT(SDL_Event, sizeof(SDL_Event) == 128);

/* Reads the pad once (scePadReadState) and turns the changes into gamepad events; checks the quit trigger. */
extern SDL_DECLSPEC void SDLCALL SDL_PumpEvents(void);
extern SDL_DECLSPEC bool SDLCALL SDL_PollEvent(SDL_Event *event);
extern SDL_DECLSPEC bool SDLCALL SDL_WaitEvent(SDL_Event *event);
extern SDL_DECLSPEC bool SDLCALL SDL_WaitEventTimeout(SDL_Event *event, Sint32 timeoutMS);
extern SDL_DECLSPEC bool SDLCALL SDL_PushEvent(SDL_Event *event);

#ifdef __cplusplus
}
#endif

#endif /* SDL_events_h_ */
