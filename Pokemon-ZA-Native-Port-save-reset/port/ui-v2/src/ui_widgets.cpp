#include "ui_widgets.h"

#include <algorithm>
#include <cmath>

#include "ui_theme.h"

namespace ui {

static float badgeGlyph(Canvas& c, const Fonts& f, const std::string& label, float cx, float cy, float size, Color color) {
    float w = std::max(size * 1.35f, f.bold.measure(label, size * 0.56f) + size * 0.6f);
    Rect r{cx - w * 0.5f, cy - size * 0.5f, w, size};
    c.strokeRoundRect(r, size * 0.3f, 2.0f, color);
    c.textInRect(f.bold, r, size * 0.56f, label, color, Align::Center);
    return w;
}

float drawPadGlyph(Canvas& c, const Fonts& f, PadGlyph g, float cx, float cy, float size, Color color) {
    float r = size * 0.5f, t = std::max(2.0f, size * 0.085f);
    switch (g) {
        case PadGlyph::Cross:
            c.strokeCircle(cx, cy, r - t * 0.5f, t, color);
            c.line(cx - r * 0.42f, cy - r * 0.42f, cx + r * 0.42f, cy + r * 0.42f, t, color);
            c.line(cx - r * 0.42f, cy + r * 0.42f, cx + r * 0.42f, cy - r * 0.42f, t, color);
            return size;
        case PadGlyph::Circle:
            c.strokeCircle(cx, cy, r - t * 0.5f, t, color);
            c.strokeCircle(cx, cy, r * 0.45f, t, color);
            return size;
        case PadGlyph::Triangle: {
            c.strokeCircle(cx, cy, r - t * 0.5f, t, color);
            float h = r * 0.9f, yTop = cy - h * 0.55f, yBot = cy + h * 0.4f, half = h * 0.52f;
            c.line(cx, yTop, cx - half, yBot, t, color);
            c.line(cx, yTop, cx + half, yBot, t, color);
            c.line(cx - half, yBot, cx + half, yBot, t, color);
            return size;
        }
        case PadGlyph::Square: {
            c.strokeCircle(cx, cy, r - t * 0.5f, t, color);
            float s = r * 0.9f;
            c.strokeRoundRect(Rect{cx - s * 0.5f, cy - s * 0.5f, s, s}, t, t, color);
            return size;
        }
        case PadGlyph::L1: return badgeGlyph(c, f, "L1", cx, cy, size, color);
        case PadGlyph::R1: return badgeGlyph(c, f, "R1", cx, cy, size, color);
        case PadGlyph::L2: return badgeGlyph(c, f, "L2", cx, cy, size, color);
        case PadGlyph::R2: return badgeGlyph(c, f, "R2", cx, cy, size, color);
        case PadGlyph::L3R3: return badgeGlyph(c, f, "L3+R3", cx, cy, size, color);
        case PadGlyph::Options: return badgeGlyph(c, f, "OPT", cx, cy, size, color);
        case PadGlyph::DpadUpDown:
        case PadGlyph::DpadLeftRight:
        case PadGlyph::Dpad: {
            // A plus shape; the arms that matter are filled.
            float arm = r * 0.34f, len = r * 0.95f;
            bool ud = g != PadGlyph::DpadLeftRight, lr = g != PadGlyph::DpadUpDown;
            Color dim = withAlpha(color, uint8_t(color.a / 3));
            c.fillRoundRect(Rect{cx - arm, cy - len, 2 * arm, 2 * len}, arm * 0.5f, ud ? color : dim);
            c.fillRoundRect(Rect{cx - len, cy - arm, 2 * len, 2 * arm}, arm * 0.5f, lr ? color : dim);
            return size;
        }
    }
    return size;
}

float drawHints(Canvas& c, const Fonts& f, float x, float cy, const std::vector<Hint>& hints, Color glyphColor, Color textColor, float px,
                Align align) {
    float glyph = px * 1.35f, gap = px * 0.5f, between = px * 1.6f;
    auto glyphW = [&](PadGlyph g) {
        switch (g) {
            case PadGlyph::L3R3: return glyph * 2.4f;
            case PadGlyph::L1: case PadGlyph::R1: case PadGlyph::L2: case PadGlyph::R2: case PadGlyph::Options: return glyph * 1.35f;
            default: return glyph;
        }
    };
    float total = 0;
    for (size_t i = 0; i < hints.size(); i++) total += glyphW(hints[i].glyph) + gap + f.regular.measure(hints[i].label, px) + (i + 1 < hints.size() ? between : 0);
    float pen = align == Align::Left ? x : align == Align::Right ? x - total : x - total * 0.5f;
    for (size_t i = 0; i < hints.size(); i++) {
        float gw = glyphW(hints[i].glyph);
        drawPadGlyph(c, f, hints[i].glyph, pen + gw * 0.5f, cy, glyph, glyphColor);
        pen += gw + gap;
        float lineH = f.regular.ascent(px) - f.regular.descent(px);
        c.text(f.regular, pen, cy - lineH * 0.5f, px, hints[i].label, textColor);
        pen += f.regular.measure(hints[i].label, px) + between;
    }
    return total;
}

float pillWidth(const Fonts& f, const std::string& text, float px, bool bold, float padX) {
    return (bold ? f.bold : f.regular).measure(text, px) + 2 * padX;
}

float drawPill(Canvas& c, const Fonts& f, float x, float cy, const std::string& text, Color bg, Color fg, float px, bool bold, float padX,
               float h, Align align) {
    float w = pillWidth(f, text, px, bold, padX);
    float left = align == Align::Left ? x : align == Align::Right ? x - w : x - w * 0.5f;
    Rect r{left, cy - h * 0.5f, w, h};
    if (bg.a) c.fillRoundRect(r, h * 0.5f, bg);
    c.textInRect(bold ? f.bold : f.regular, r, px, text, fg, Align::Center);
    return w;
}

void drawChevron(Canvas& c, float cx, float cy, float size, bool pointsLeft, Color color) {
    float h = size * 0.5f, d = pointsLeft ? -1.0f : 1.0f, t = std::max(2.0f, size * 0.16f);
    c.line(cx - d * h * 0.5f, cy - h, cx + d * h * 0.5f, cy, t, color);
    c.line(cx - d * h * 0.5f, cy + h, cx + d * h * 0.5f, cy, t, color);
}

void drawLevelDots(Canvas& c, float x, float cy, int count, int index, Color on, Color off) {
    for (int i = 0; i < count; i++) {
        float cx = x + 7 + i * 16.0f;
        if (i <= index) c.fillCircle(cx, cy, 4.5f, on);
        else c.fillCircle(cx, cy, 3.5f, off);
    }
}

void drawStar(Canvas& c, float cx, float cy, float r, Color color, bool filled) {
    // Five-pointed star from ten triangles around the centre.
    const float pi = 3.14159265f;
    float px[10], py[10];
    for (int i = 0; i < 10; i++) {
        float a = -pi / 2 + i * pi / 5, rr = (i % 2 == 0) ? r : r * 0.45f;
        px[i] = cx + std::cos(a) * rr;
        py[i] = cy + std::sin(a) * rr;
    }
    if (filled) {
        for (int i = 0; i < 10; i++) c.fillTriangle(cx, cy, px[i], py[i], px[(i + 1) % 10], py[(i + 1) % 10], color);
    } else {
        for (int i = 0; i < 10; i++) c.line(px[i], py[i], px[(i + 1) % 10], py[(i + 1) % 10], std::max(1.5f, r * 0.14f), color);
    }
}

void drawCheck(Canvas& c, float cx, float cy, float size, Color color) {
    float t = std::max(2.0f, size * 0.14f);
    c.line(cx - size * 0.38f, cy + size * 0.02f, cx - size * 0.1f, cy + size * 0.3f, t, color);
    c.line(cx - size * 0.1f, cy + size * 0.3f, cx + size * 0.42f, cy - size * 0.3f, t, color);
}

void drawWarningTriangle(Canvas& c, float cx, float cy, float size, Color color) {
    float h = size * 0.5f;
    c.fillTriangle(cx, cy - h, cx - h * 1.05f, cy + h * 0.8f, cx + h * 1.05f, cy + h * 0.8f, color);
    Color ink = theme::Bg0;
    c.line(cx, cy - h * 0.25f, cx, cy + h * 0.25f, std::max(2.0f, size * 0.11f), ink);
    c.fillCircle(cx, cy + h * 0.5f, std::max(1.5f, size * 0.07f), ink);
}

void drawLock(Canvas& c, float cx, float cy, float size, Color color) {
    float bw = size * 0.72f, bh = size * 0.5f, t = std::max(2.0f, size * 0.12f);
    float bodyTop = cy - bh * 0.1f;
    c.fillRoundRect(Rect{cx - bw * 0.5f, bodyTop, bw, bh}, size * 0.12f, color);
    // shackle: the upper half of a ring, clipped at the body's top edge
    float r = size * 0.26f;
    Rect saved = c.clip();
    c.setClip(Rect{cx - r - t, bodyTop - r - t, 2 * (r + t), r + t});
    c.strokeCircle(cx, bodyTop, r, t, color);
    c.setClip(saved);
}

void drawToast(Canvas& c, const Fonts& f, const Toast& t, float cx, float bottomY) {
    float px = 24, h = t.detail.empty() ? 64 : 84;
    float textW = std::max(f.bold.measure(t.text, px), t.detail.empty() ? 0.0f : f.regular.measure(t.detail, 18));
    float w = textW + 64 + 56;
    Rect r{cx - w * 0.5f, bottomY - h, w, h};
    c.shadowRoundRect(r, h * 0.5f, 14, theme::Shadow);
    c.fillRoundRect(r, h * 0.5f, rgb(0x13223A, 245));
    Color accent = t.kind == Toast::Ok ? theme::Ok : t.kind == Toast::Warn ? theme::Warn : t.kind == Toast::Err ? theme::Err : theme::Info;
    c.strokeRoundRect(r, h * 0.5f, 1.5f, withAlpha(accent, 140));
    float icx = r.x + 36, icy = r.y + h * 0.5f;
    c.fillCircle(icx, icy, 16, accent);
    if (t.kind == Toast::Ok) drawCheck(c, icx, icy, 20, theme::AccentInk);
    else if (t.kind == Toast::Warn || t.kind == Toast::Err) {
        c.line(icx, icy - 7, icx, icy + 2, 3, theme::Bg0);
        c.fillCircle(icx, icy + 7, 2, theme::Bg0);
    } else {
        c.fillCircle(icx, icy - 6, 2.2f, theme::Bg0);
        c.line(icx, icy - 1, icx, icy + 7, 3, theme::Bg0);
    }
    float tx = r.x + 64;
    if (t.detail.empty()) {
        c.textInRect(f.bold, Rect{tx, r.y, textW, h}, px, t.text, theme::Text, Align::Left);
    } else {
        c.text(f.bold, tx, r.y + 14, px, t.text, theme::Text);
        c.text(f.regular, tx, r.y + 48, 18, t.detail, theme::Text2);
    }
}

void drawScrollbar(Canvas& c, Rect track, int total, int first, int visible, Color trackColor, Color thumbColor) {
    c.fillRoundRect(track, track.w * 0.5f, trackColor);
    if (total <= visible || total <= 0) {
        c.fillRoundRect(track, track.w * 0.5f, thumbColor);
        return;
    }
    float frac = float(visible) / float(total);
    float thumbH = std::max(track.w * 2, track.h * frac);
    float y = track.y + (track.h - thumbH) * (float(first) / float(total - visible));
    c.fillRoundRect(Rect{track.x, y, track.w, thumbH}, track.w * 0.5f, thumbColor);
}

float drawBadge(Canvas& c, const Fonts& f, float x, float cy, const std::string& text, Color color, Align align) {
    float px = theme::SmallSize - 2, h = 26, w = f.bold.measure(text, px) + 22;
    float left = align == Align::Left ? x : align == Align::Right ? x - w : x - w * 0.5f;
    Rect r{left, cy - h * 0.5f, w, h};
    c.fillRoundRect(r, 7, withAlpha(color, 34));
    c.strokeRoundRect(r, 7, 1.0f, withAlpha(color, 160));
    c.textInRect(f.bold, r, px, text, color, Align::Center);
    return w;
}

void drawSwitch(Canvas& c, float x, float cy, bool on, Color onColor, Color offColor, Color knob) {
    Rect r{x, cy - 15, 56, 30};
    c.fillRoundRect(r, 15, on ? onColor : offColor);
    c.fillCircle(on ? r.right() - 15 : r.x + 15, cy, 11, knob);
}

}  // namespace ui
