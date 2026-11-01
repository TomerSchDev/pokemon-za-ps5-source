/* SDL3 shim (PS5): SDL_gamepad.h - subset of SDL 3.4.18, backed by libScePad. SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef SDL_gamepad_h_
#define SDL_gamepad_h_

#include <SDL3/SDL_stdinc.h>
#include <SDL3/SDL_error.h>
#include <SDL3/SDL_joystick.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct SDL_Gamepad SDL_Gamepad;

typedef enum SDL_GamepadType {
    SDL_GAMEPAD_TYPE_UNKNOWN = 0,
    SDL_GAMEPAD_TYPE_STANDARD,
    SDL_GAMEPAD_TYPE_XBOX360,
    SDL_GAMEPAD_TYPE_XBOXONE,
    SDL_GAMEPAD_TYPE_PS3,
    SDL_GAMEPAD_TYPE_PS4,
    SDL_GAMEPAD_TYPE_PS5,
    SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_PRO,
    SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_LEFT,
    SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_RIGHT,
    SDL_GAMEPAD_TYPE_NINTENDO_SWITCH_JOYCON_PAIR,
    SDL_GAMEPAD_TYPE_GAMECUBE,
    SDL_GAMEPAD_TYPE_STEAM,
    SDL_GAMEPAD_TYPE_COUNT
} SDL_GamepadType;

typedef enum SDL_GamepadButton {
    SDL_GAMEPAD_BUTTON_INVALID = -1,
    SDL_GAMEPAD_BUTTON_SOUTH,          /**< Cross */
    SDL_GAMEPAD_BUTTON_EAST,           /**< Circle */
    SDL_GAMEPAD_BUTTON_WEST,           /**< Square */
    SDL_GAMEPAD_BUTTON_NORTH,          /**< Triangle */
    SDL_GAMEPAD_BUTTON_BACK,           /**< Create (only if libScePad reports it to the title) */
    SDL_GAMEPAD_BUTTON_GUIDE,          /**< PS (never: the system intercepts it) */
    SDL_GAMEPAD_BUTTON_START,          /**< Options */
    SDL_GAMEPAD_BUTTON_LEFT_STICK,     /**< L3 */
    SDL_GAMEPAD_BUTTON_RIGHT_STICK,    /**< R3 */
    SDL_GAMEPAD_BUTTON_LEFT_SHOULDER,  /**< L1 */
    SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER, /**< R1 */
    SDL_GAMEPAD_BUTTON_DPAD_UP,
    SDL_GAMEPAD_BUTTON_DPAD_DOWN,
    SDL_GAMEPAD_BUTTON_DPAD_LEFT,
    SDL_GAMEPAD_BUTTON_DPAD_RIGHT,
    SDL_GAMEPAD_BUTTON_MISC1,          /**< mute (never) */
    SDL_GAMEPAD_BUTTON_RIGHT_PADDLE1,
    SDL_GAMEPAD_BUTTON_LEFT_PADDLE1,
    SDL_GAMEPAD_BUTTON_RIGHT_PADDLE2,
    SDL_GAMEPAD_BUTTON_LEFT_PADDLE2,
    SDL_GAMEPAD_BUTTON_TOUCHPAD,       /**< touchpad click */
    SDL_GAMEPAD_BUTTON_MISC2,
    SDL_GAMEPAD_BUTTON_MISC3,
    SDL_GAMEPAD_BUTTON_MISC4,
    SDL_GAMEPAD_BUTTON_MISC5,
    SDL_GAMEPAD_BUTTON_MISC6,
    SDL_GAMEPAD_BUTTON_COUNT           /**< 26: the PADB_LTRIGGER of the runtime follows it */
} SDL_GamepadButton;

typedef enum SDL_GamepadAxis {
    SDL_GAMEPAD_AXIS_INVALID = -1,
    SDL_GAMEPAD_AXIS_LEFTX,
    SDL_GAMEPAD_AXIS_LEFTY,         /**< negative = up, as SDL */
    SDL_GAMEPAD_AXIS_RIGHTX,
    SDL_GAMEPAD_AXIS_RIGHTY,
    SDL_GAMEPAD_AXIS_LEFT_TRIGGER,  /**< L2: 0..32767 */
    SDL_GAMEPAD_AXIS_RIGHT_TRIGGER, /**< R2: 0..32767 */
    SDL_GAMEPAD_AXIS_COUNT
} SDL_GamepadAxis;

extern SDL_DECLSPEC bool SDLCALL SDL_HasGamepad(void);
/* A 0-terminated array of instance ids (SDL_malloc: free with SDL_free); *count = how many. */
extern SDL_DECLSPEC SDL_JoystickID *SDLCALL SDL_GetGamepads(int *count);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetGamepadNameForID(SDL_JoystickID instance_id);
extern SDL_DECLSPEC SDL_GamepadType SDLCALL SDL_GetGamepadTypeForID(SDL_JoystickID instance_id);
extern SDL_DECLSPEC SDL_Gamepad *SDLCALL SDL_OpenGamepad(SDL_JoystickID instance_id);
extern SDL_DECLSPEC SDL_JoystickID SDLCALL SDL_GetGamepadID(SDL_Gamepad *gamepad);
extern SDL_DECLSPEC const char *SDLCALL SDL_GetGamepadName(SDL_Gamepad *gamepad);
extern SDL_DECLSPEC SDL_GamepadType SDLCALL SDL_GetGamepadType(SDL_Gamepad *gamepad);
extern SDL_DECLSPEC Sint16 SDLCALL SDL_GetGamepadAxis(SDL_Gamepad *gamepad, SDL_GamepadAxis axis);
extern SDL_DECLSPEC bool SDLCALL SDL_GetGamepadButton(SDL_Gamepad *gamepad, SDL_GamepadButton button);
extern SDL_DECLSPEC void SDLCALL SDL_CloseGamepad(SDL_Gamepad *gamepad);

#ifdef __cplusplus
}
#endif

#endif /* SDL_gamepad_h_ */
