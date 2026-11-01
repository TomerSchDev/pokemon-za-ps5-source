// ui-v2 shared widgets: pad glyphs, value pills, hint footer, toasts, scrollbars, level dots.
#pragma once
#include <string>
#include <vector>

#include "ui_canvas.h"

namespace ui {

struct Fonts {
    Font regular, bold;
};

enum class PadGlyph { Cross, Circle, Triangle, Square, L1, R1, L2, R2, L3R3, DpadUpDown, DpadLeftRight, Dpad, Options };

// Draws a PlayStation button glyph centred at (cx, cy); `size` is the diameter. Returns the width used.
float drawPadGlyph(Canvas& c, const Fonts& f, PadGlyph g, float cx, float cy, float size, Color color);

struct Hint {
    PadGlyph glyph;
    std::string label;
};
// A row of "glyph label" pairs; returns the total width.
float drawHints(Canvas& c, const Fonts& f, float x, float cy, const std::vector<Hint>& hints, Color glyphColor, Color textColor,
                float px, Align align = Align::Left);

// A rounded pill with text. Returns its width.
float drawPill(Canvas& c, const Fonts& f, float x, float cy, const std::string& text, Color bg, Color fg, float px, bool bold = false,
               float padX = 18, float h = 40, Align align = Align::Left);
float pillWidth(const Fonts& f, const std::string& text, float px, bool bold = false, float padX = 18);

// Chevrons (‹ ›) for value pills.
void drawChevron(Canvas& c, float cx, float cy, float size, bool pointsLeft, Color color);
// Level position dots (filled up to `index`).
void drawLevelDots(Canvas& c, float x, float cy, int count, int index, Color on, Color off);
// Vector icons (Noto Sans has no stars, checks or triangles).
void drawStar(Canvas& c, float cx, float cy, float r, Color color, bool filled);
void drawCheck(Canvas& c, float cx, float cy, float size, Color color);
void drawWarningTriangle(Canvas& c, float cx, float cy, float size, Color color);
void drawLock(Canvas& c, float cx, float cy, float size, Color color);

struct Toast {
    enum Kind { Ok, Info, Warn, Err } kind = Ok;
    std::string text;
    std::string detail;  // optional second line (smaller)
};
// Bottom-centred toast pill above `bottomY`.
void drawToast(Canvas& c, const Fonts& f, const Toast& t, float cx, float bottomY);

// A vertical scrollbar for a list of `total` entries showing `visible` from `first`.
void drawScrollbar(Canvas& c, Rect track, int total, int first, int visible, Color trackColor, Color thumbColor);

// A small status badge ("QUEUED", "PHASE 2"). Returns the width.
float drawBadge(Canvas& c, const Fonts& f, float x, float cy, const std::string& text, Color color, Align align = Align::Left);

// Switch widget for Toggle rows.
void drawSwitch(Canvas& c, float x, float cy, bool on, Color onColor, Color offColor, Color knob);

}  // namespace ui
