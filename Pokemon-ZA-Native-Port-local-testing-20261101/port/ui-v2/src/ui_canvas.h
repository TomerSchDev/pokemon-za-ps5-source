// ui-v2: CPU rasterizer for the launcher and the in-game overlay.
//
// One RGBA8 canvas (premultiplied alpha), anti-aliased primitives evaluated as signed-distance coverage (rounded
// rectangles, circles, capsule lines, soft shadows), and TrueType text through stb_truetype (public domain; the
// vendored copy is third_party/stb/imstb_truetype.h). Everything is plain C++17 without exceptions or RTTI, so the
// same code builds for the host harness (clang++-21) and for the title (prospero-clang18). No threads, no files
// other than the font bytes handed in by the caller.
//
// Coordinates are canvas pixels (the launcher and the overlay both use a 1920x1080 canvas). Colours are given as
// straight (non-premultiplied) RGBA and converted on the way in.
#pragma once
#include <cstdint>
#include <cstddef>
#include <string>
#include <vector>

namespace ui {

struct Color {
    uint8_t r = 0, g = 0, b = 0, a = 255;
};
// 0xRRGGBB plus an alpha (255 = opaque).
constexpr Color rgb(uint32_t hex, uint8_t alpha = 255) {
    return Color{uint8_t(hex >> 16), uint8_t(hex >> 8), uint8_t(hex), alpha};
}
constexpr Color withAlpha(Color c, uint8_t alpha) { return Color{c.r, c.g, c.b, alpha}; }
// Linear blend of two colours (t = 0 -> a, 1 -> b).
Color mix(Color a, Color b, float t);

struct Rect {
    float x = 0, y = 0, w = 0, h = 0;
    float right() const { return x + w; }
    float bottom() const { return y + h; }
    Rect inset(float dx, float dy) const { return Rect{x + dx, y + dy, w - 2 * dx, h - 2 * dy}; }
    bool contains(float px, float py) const { return px >= x && py >= y && px < x + w && py < y + h; }
};

// A loaded TrueType face. Glyphs are rasterized on demand per (pixel size, glyph, 1/3-pixel shift) and cached.
class Font {
public:
    Font();
    ~Font();
    Font(const Font&) = delete;
    Font& operator=(const Font&) = delete;
    // The bytes must outlive the Font (the title embeds them as a const array; the host reads the file once).
    bool load(const uint8_t* data, size_t size);
    bool ok() const { return info_ != nullptr; }
    // Vertical metrics in pixels for an em size (CSS font-size semantics: 1 em = `px` pixels).
    float ascent(float px) const;
    float descent(float px) const;   // negative
    float lineHeight(float px) const;
    // Advance width of a UTF-8 string, with kerning.
    float measure(const std::string& utf8, float px) const;
    // Longest prefix of `utf8` that fits in `maxWidth`, with an ellipsis appended when it was cut.
    std::string fit(const std::string& utf8, float px, float maxWidth) const;

private:
    friend class Canvas;
    struct Impl;
    Impl* info_ = nullptr;
};

enum class Align { Left, Center, Right };

class Canvas {
public:
    Canvas(int width, int height);
    int width() const { return w_; }
    int height() const { return h_; }
    // Premultiplied RGBA8, row-major, width*4 bytes a row.
    const uint8_t* data() const { return px_.data(); }
    uint8_t* data() { return px_.data(); }
    size_t bytes() const { return px_.size(); }

    void clear(Color c);
    // Drawing is clipped to this rectangle (the whole canvas by default).
    void setClip(Rect r);
    void resetClip();
    Rect clip() const { return clip_; }

    void fillRect(Rect r, Color c);
    void fillRoundRect(Rect r, float radius, Color c);
    // Vertical gradient from `top` to `bottom`.
    void fillRoundRectGradient(Rect r, float radius, Color top, Color bottom);
    void strokeRoundRect(Rect r, float radius, float thickness, Color c);
    // Soft drop shadow: the rounded rectangle's edge faded over `blur` pixels on both sides.
    void shadowRoundRect(Rect r, float radius, float blur, Color c);
    void fillCircle(float cx, float cy, float radius, Color c);
    void strokeCircle(float cx, float cy, float radius, float thickness, Color c);
    // A line with round caps.
    void line(float x0, float y0, float x1, float y1, float thickness, Color c);
    // A filled triangle (anti-aliased).
    void fillTriangle(float x0, float y0, float x1, float y1, float x2, float y2, Color c);

    // Text. `y` is the top of the line box; the baseline sits at y + ascent(px). Returns the advance width.
    float text(const Font& f, float x, float y, float px, const std::string& utf8, Color c, Align align = Align::Left);
    // Text whose baseline is centred vertically in `r`.
    float textInRect(const Font& f, Rect r, float px, const std::string& utf8, Color c, Align align, float padX = 0);

    // Composite another premultiplied canvas over this one at (x, y).
    void blit(const Canvas& src, int x, int y);
    // Composite a straight-alpha RGBA8 image (e.g. a decoded PNG) over this canvas, scaled by `alpha`.
    void blitStraight(const uint8_t* rgba, int sw, int sh, int x, int y, float alpha = 1.0f);
    // Nearest-neighbour / box downscale of another canvas into this one's full area (used by the legacy look).
    void drawScaled(const Canvas& src);

    // Straight-alpha RGBA8 copy (for PNG output).
    std::vector<uint8_t> toStraightRGBA() const;

private:
    void blendPixel(int x, int y, Color c, float coverage);
    void blendSpan(int y, int x0, int x1, Color c, unsigned a8);
    void spanWithEdges(int y, float fx0, float fx1, Color c, float rowCov);
    template <class Shade> void roundRectRows(Rect r, float radius, Shade shade);
    template <class Distance> void edgeBands(Rect outer, float band, float feather, Color c, Distance d, bool fillInterior);
    template <class Distance> void fillSDF(Rect bounds, Color c, float feather, Distance d);
    template <class Distance, class Shade> void fillSDFShade(Rect bounds, float feather, Distance d, Shade shade);
    void glyph(const Font& f, float px, int glyphIndex, float x, float baseline, Color c);

    int w_, h_;
    std::vector<uint8_t> px_;
    Rect clip_;
};

// UTF-8 decoding shared by the font and the widgets (returns the code point and advances `i`).
uint32_t decodeUtf8(const std::string& s, size_t& i);

}  // namespace ui
