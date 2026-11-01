// ui-v2: controller input shared by the launcher and the in-game overlay.
//
// SDL gamepad events (the PS5 SDL3 shim delivers SDL_EVENT_GAMEPAD_BUTTON_DOWN/UP for every DualSense button and
// SDL_EVENT_GAMEPAD_AXIS_MOTION for the triggers) become model::Button presses, with hold-to-accelerate repeats for
// the D-pad (items::repeatDelayMs: 400 ms, then 110 ms, then 45 ms after 1.2 s). L2/R2 are axes in SDL3: a press is
// the trigger crossing half travel. Pure logic (no SDL calls): host-testable, and the scripted test input of the PC
// proof feeds it the same way.
#pragma once
#include <cstdint>
#include <string>
#include <vector>

#include "ui_model.h"

namespace ui::pad {

using Button = model::Button;

// SDL3 gamepad button numbers (SDL_GamepadButton), kept here so the state machine needs no SDL header.
enum SdlButton {
    SdlSouth = 0, SdlEast = 1, SdlWest = 2, SdlNorth = 3, SdlBack = 4, SdlGuide = 5, SdlStart = 6, SdlLeftStick = 7,
    SdlRightStick = 8, SdlLeftShoulder = 9, SdlRightShoulder = 10, SdlDpadUp = 11, SdlDpadDown = 12, SdlDpadLeft = 13,
    SdlDpadRight = 14
};
// SDL3 gamepad axes (SDL_GamepadAxis) for the triggers.
enum SdlAxis { SdlLeftTrigger = 4, SdlRightTrigger = 5 };

// Maps an SDL button number to a Button; returns false for buttons the menus do not use (sticks, guide...).
bool fromSdlButton(int sdlButton, Button& out);
// Parses a button name of the test scripts ("UP", "CROSS", "L1", "R2", ... also "A"/"B"/"X"/"Y" as the runtime's
// LARECOMP_INPUT names: A = Cross, B = Circle, X = Square, Y = Triangle).
bool parseButton(const std::string& name, Button& out);
const char* buttonName(Button b);

struct State {
    uint32_t held = 0;          // bit per Button
    uint32_t repeating = 0;     // the D-pad bits currently repeating
    uint64_t repeatAtMs = 0;    // when the next repeat fires
    uint64_t heldSinceMs = 0;   // when the repeating direction was first pressed
    bool l2 = false, r2 = false;
};

// A button went down (edge) or up. Returns true and sets `pressed` when this is a new press to deliver.
bool buttonEvent(State& s, Button b, bool down, uint64_t nowMs, Button& pressed);
// A trigger axis moved (SDL value -32768..32767; the shim maps L2/R2 to 0..32767). Returns true on a new press.
bool triggerEvent(State& s, int sdlAxis, int value, uint64_t nowMs, Button& pressed);
// Called every frame: emits a repeated D-pad press when a direction is held long enough.
bool repeat(State& s, uint64_t nowMs, Button& pressed);
// Everything released (pad removed, menu closed).
void clear(State& s);

// Scripted input for the PC proof: "frame:NAME[,frame:NAME...]" (frames of the surface that consumes it).
struct Script {
    struct Step { uint64_t frame; Button button; };
    std::vector<Step> steps;
    size_t next = 0;
    bool parse(const char* text);  // false on a malformed entry (nothing is kept)
    // Presses due at `frame` (ascending order; several steps may share a frame).
    void due(uint64_t frame, std::vector<Button>& out);
};

}  // namespace ui::pad
