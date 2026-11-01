#include "ui_pad.h"

#include <algorithm>
#include <cctype>
#include <cstdlib>
#include <cstring>

#include "items_picker.h"

namespace ui::pad {

static uint32_t bit(Button b) { return 1u << unsigned(b); }
static const uint32_t kDpad = bit(Button::Up) | bit(Button::Down) | bit(Button::Left) | bit(Button::Right);

bool fromSdlButton(int sdlButton, Button& out) {
    switch (sdlButton) {
        case SdlSouth: out = Button::Cross; return true;
        case SdlEast: out = Button::Circle; return true;
        case SdlWest: out = Button::Square; return true;
        case SdlNorth: out = Button::Triangle; return true;
        case SdlLeftShoulder: out = Button::L1; return true;
        case SdlRightShoulder: out = Button::R1; return true;
        case SdlDpadUp: out = Button::Up; return true;
        case SdlDpadDown: out = Button::Down; return true;
        case SdlDpadLeft: out = Button::Left; return true;
        case SdlDpadRight: out = Button::Right; return true;
        default: return false;
    }
}

static const struct { const char* name; Button b; } kNames[] = {
    {"UP", Button::Up}, {"DOWN", Button::Down}, {"LEFT", Button::Left}, {"RIGHT", Button::Right},
    {"CROSS", Button::Cross}, {"CIRCLE", Button::Circle}, {"TRIANGLE", Button::Triangle}, {"SQUARE", Button::Square},
    {"L1", Button::L1}, {"R1", Button::R1}, {"L2", Button::L2}, {"R2", Button::R2},
    {"A", Button::Cross}, {"B", Button::Circle}, {"X", Button::Square}, {"Y", Button::Triangle},
};

bool parseButton(const std::string& name, Button& out) {
    std::string u;
    for (char c : name) u += char(std::toupper((unsigned char)c));
    for (const auto& n : kNames)
        if (u == n.name) { out = n.b; return true; }
    return false;
}

const char* buttonName(Button b) {
    for (const auto& n : kNames)
        if (n.b == b) return n.name;
    return "?";
}

bool buttonEvent(State& s, Button b, bool down, uint64_t nowMs, Button& pressed) {
    uint32_t m = bit(b);
    if (!down) {
        s.held &= ~m;
        if (s.repeating & m) { s.repeating = 0; s.repeatAtMs = 0; }
        return false;
    }
    if (s.held & m) return false;  // already down (the shim never repeats, but a script might)
    s.held |= m;
    if (m & kDpad) {
        s.repeating = m;  // the latest direction repeats; a second one replaces it
        s.heldSinceMs = nowMs;
        s.repeatAtMs = nowMs + items::repeatDelayMs(0);
    }
    pressed = b;
    return true;
}

bool triggerEvent(State& s, int sdlAxis, int value, uint64_t nowMs, Button& pressed) {
    (void)nowMs;
    bool* flag = sdlAxis == SdlLeftTrigger ? &s.l2 : sdlAxis == SdlRightTrigger ? &s.r2 : nullptr;
    if (!flag) return false;
    bool down = value >= 16384;  // half travel
    if (down == *flag) return false;
    *flag = down;
    if (!down) return false;
    pressed = sdlAxis == SdlLeftTrigger ? Button::L2 : Button::R2;
    return true;
}

bool repeat(State& s, uint64_t nowMs, Button& pressed) {
    if (!s.repeating || !(s.held & s.repeating) || nowMs < s.repeatAtMs) return false;
    unsigned heldMs = unsigned(std::min<uint64_t>(nowMs - s.heldSinceMs, 1u << 30));
    s.repeatAtMs = nowMs + items::repeatDelayMs(heldMs);
    for (int i = 0; i < 12; i++)
        if (s.repeating & (1u << i)) { pressed = Button(i); return true; }
    return false;
}

void clear(State& s) { s = State{}; }

bool Script::parse(const char* text) {
    steps.clear();
    next = 0;
    if (!text || !*text) return true;
    std::string s = text;
    size_t at = 0;
    while (at < s.size()) {
        size_t comma = s.find(',', at);
        std::string item = s.substr(at, comma == std::string::npos ? std::string::npos : comma - at);
        at = comma == std::string::npos ? s.size() : comma + 1;
        if (item.empty()) continue;
        size_t colon = item.find(':');
        if (colon == std::string::npos) { steps.clear(); return false; }
        char* end = nullptr;
        unsigned long long frame = std::strtoull(item.c_str(), &end, 10);
        if (end != item.c_str() + colon) { steps.clear(); return false; }
        Button b;
        // "frame:NAME:count" (the runtime's LARECOMP_INPUT shape) is accepted: the count is ignored
        std::string name = item.substr(colon + 1);
        size_t colon2 = name.find(':');
        if (colon2 != std::string::npos) name = name.substr(0, colon2);
        if (!parseButton(name, b)) { steps.clear(); return false; }
        steps.push_back({frame, b});
    }
    std::stable_sort(steps.begin(), steps.end(), [](const Step& a, const Step& b) { return a.frame < b.frame; });
    return true;
}

void Script::due(uint64_t frame, std::vector<Button>& out) {
    while (next < steps.size() && steps[next].frame <= frame) out.push_back(steps[next++].button);
}

}  // namespace ui::pad
