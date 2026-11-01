#include "ui_canvas.h"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <unordered_map>

#define STBTT_STATIC
#define STB_TRUETYPE_IMPLEMENTATION
#include <imstb_truetype.h>

namespace ui {

// ------------------------------------------------------------------------------------------------------ colours
Color mix(Color a, Color b, float t) {
    t = std::clamp(t, 0.0f, 1.0f);
    auto l = [&](uint8_t p, uint8_t q) { return uint8_t(std::lround(p + (q - p) * t)); };
    return Color{l(a.r, b.r), l(a.g, b.g), l(a.b, b.b), l(a.a, b.a)};
}

uint32_t decodeUtf8(const std::string& s, size_t& i) {
    unsigned char c = (unsigned char)s[i++];
    if (c < 0x80) return c;
    int extra = c >= 0xF0 ? 3 : c >= 0xE0 ? 2 : c >= 0xC0 ? 1 : 0;
    uint32_t cp = extra == 3 ? (c & 0x07) : extra == 2 ? (c & 0x0F) : (c & 0x1F);
    for (int k = 0; k < extra && i < s.size(); k++) cp = (cp << 6) | ((unsigned char)s[i++] & 0x3F);
    return cp;
}

// ------------------------------------------------------------------------------------------------------ font
struct GlyphBitmap {
    int w = 0, h = 0, x0 = 0, y0 = 0;
    std::vector<uint8_t> coverage;
};

struct Font::Impl {
    stbtt_fontinfo font{};
    int ascent = 0, descent = 0, lineGap = 0;
    // key: pixel size * 4 (quarter pixels) << 24 | glyph << 2 | shift (0..2 thirds of a pixel)
    std::unordered_map<uint64_t, GlyphBitmap> cache;
    std::unordered_map<uint32_t, int> glyphIndex;

    float scale(float px) const { return stbtt_ScaleForMappingEmToPixels(&font, px); }
    int index(uint32_t cp) {
        auto it = glyphIndex.find(cp);
        if (it != glyphIndex.end()) return it->second;
        int g = stbtt_FindGlyphIndex(&font, (int)cp);
        if (!g && cp != '?') g = stbtt_FindGlyphIndex(&font, '?');
        glyphIndex.emplace(cp, g);
        return g;
    }
    const GlyphBitmap& bitmap(float px, int g, int shift) {
        uint64_t key = (uint64_t(std::lround(px * 4)) << 24) | (uint64_t(g) << 2) | uint64_t(shift);
        auto it = cache.find(key);
        if (it != cache.end()) return it->second;
        GlyphBitmap bm;
        float s = scale(px), sx = shift / 3.0f;
        int x0, y0, x1, y1;
        stbtt_GetGlyphBitmapBoxSubpixel(&font, g, s, s, sx, 0, &x0, &y0, &x1, &y1);
        bm.w = x1 - x0;
        bm.h = y1 - y0;
        bm.x0 = x0;
        bm.y0 = y0;
        if (bm.w > 0 && bm.h > 0) {
            bm.coverage.assign(size_t(bm.w) * bm.h, 0);
            stbtt_MakeGlyphBitmapSubpixel(&font, bm.coverage.data(), bm.w, bm.h, bm.w, s, s, sx, 0, g);
        }
        return cache.emplace(key, std::move(bm)).first->second;
    }
};

Font::Font() = default;
Font::~Font() { delete info_; }

bool Font::load(const uint8_t* data, size_t size) {
    delete info_;
    info_ = nullptr;
    if (!data || size < 12) return false;
    auto* impl = new Impl();
    int offset = stbtt_GetFontOffsetForIndex(data, 0);
    if (offset < 0 || !stbtt_InitFont(&impl->font, data, offset)) {
        delete impl;
        return false;
    }
    stbtt_GetFontVMetrics(&impl->font, &impl->ascent, &impl->descent, &impl->lineGap);
    info_ = impl;
    return true;
}

float Font::ascent(float px) const { return info_ ? info_->ascent * info_->scale(px) : px * 0.8f; }
float Font::descent(float px) const { return info_ ? info_->descent * info_->scale(px) : -px * 0.2f; }
float Font::lineHeight(float px) const {
    return info_ ? (info_->ascent - info_->descent + info_->lineGap) * info_->scale(px) : px * 1.2f;
}

float Font::measure(const std::string& utf8, float px) const {
    if (!info_) return 0;
    float s = info_->scale(px), x = 0;
    int prev = 0;
    for (size_t i = 0; i < utf8.size();) {
        uint32_t cp = decodeUtf8(utf8, i);
        int g = info_->index(cp);
        int adv, lsb;
        stbtt_GetGlyphHMetrics(&info_->font, g, &adv, &lsb);
        if (prev) x += stbtt_GetGlyphKernAdvance(&info_->font, prev, g) * s;
        x += adv * s;
        prev = g;
    }
    return x;
}

std::string Font::fit(const std::string& utf8, float px, float maxWidth) const {
    if (measure(utf8, px) <= maxWidth) return utf8;
    const std::string ellipsis = "\xE2\x80\xA6";  // U+2026
    std::string out;
    size_t i = 0;
    while (i < utf8.size()) {
        size_t next = i;
        decodeUtf8(utf8, next);
        std::string candidate = utf8.substr(0, next) + ellipsis;
        if (measure(candidate, px) > maxWidth) break;
        out = candidate;
        i = next;
    }
    return out.empty() ? ellipsis : out;
}

// ------------------------------------------------------------------------------------------------------ canvas
Canvas::Canvas(int width, int height) : w_(width), h_(height), px_(size_t(width) * height * 4, 0) {
    resetClip();
}

void Canvas::clear(Color c) {
    uint8_t a = c.a;
    uint8_t p[4] = {uint8_t(c.r * a / 255), uint8_t(c.g * a / 255), uint8_t(c.b * a / 255), a};
    for (size_t i = 0; i < px_.size(); i += 4) std::memcpy(&px_[i], p, 4);
}

void Canvas::setClip(Rect r) {
    Rect full{0, 0, float(w_), float(h_)};
    float x0 = std::max(r.x, full.x), y0 = std::max(r.y, full.y);
    float x1 = std::min(r.right(), full.right()), y1 = std::min(r.bottom(), full.bottom());
    clip_ = Rect{x0, y0, std::max(0.0f, x1 - x0), std::max(0.0f, y1 - y0)};
}
void Canvas::resetClip() { clip_ = Rect{0, 0, float(w_), float(h_)}; }

// Integer source-over of a straight colour with an effective 8-bit alpha onto the premultiplied canvas.
static inline void blendBytes(uint8_t* p, Color c, unsigned a8) {
    if (a8 >= 255) {
        p[0] = c.r; p[1] = c.g; p[2] = c.b; p[3] = 255;
        return;
    }
    unsigned ia = 255 - a8;
    p[0] = uint8_t((c.r * a8 + p[0] * ia + 127) / 255);
    p[1] = uint8_t((c.g * a8 + p[1] * ia + 127) / 255);
    p[2] = uint8_t((c.b * a8 + p[2] * ia + 127) / 255);
    p[3] = uint8_t((255 * a8 + p[3] * ia + 127) / 255);
}

inline void Canvas::blendPixel(int x, int y, Color c, float coverage) {
    if (coverage <= 0.0f) return;
    unsigned a8 = unsigned(c.a * std::min(coverage, 1.0f) + 0.5f);
    if (!a8) return;
    blendBytes(&px_[(size_t(y) * w_ + x) * 4], c, a8);
}

// A horizontal run [x0, x1) of one colour at one effective alpha (clipped by the caller).
inline void Canvas::blendSpan(int y, int x0, int x1, Color c, unsigned a8) {
    if (!a8 || x1 <= x0) return;
    uint8_t* p = &px_[(size_t(y) * w_ + x0) * 4];
    if (a8 >= 255) {
        for (int x = x0; x < x1; x++, p += 4) { p[0] = c.r; p[1] = c.g; p[2] = c.b; p[3] = 255; }
    } else {
        // premultiplied constant for pixels that are still transparent (a scrim over a cleared overlay canvas)
        uint8_t pre[4] = {uint8_t((c.r * a8 + 127) / 255), uint8_t((c.g * a8 + 127) / 255), uint8_t((c.b * a8 + 127) / 255), uint8_t(a8)};
        for (int x = x0; x < x1; x++, p += 4) {
            if (p[3] == 0) std::memcpy(p, pre, 4);
            else blendBytes(p, c, a8);
        }
    }
}

// One row of an axis-aligned rectangle [fx0, fx1) with exact area coverage at the fractional edges; `rowCov` is the
// row's vertical coverage (1 inside, fractional on the top/bottom rows).
inline void Canvas::spanWithEdges(int y, float fx0, float fx1, Color c, float rowCov) {
    fx0 = std::max(fx0, clip_.x);
    fx1 = std::min(fx1, clip_.right());
    if (fx1 <= fx0 || rowCov <= 0.0f) return;
    int px0 = int(std::floor(fx0)), px1 = int(std::ceil(fx1));
    float alpha = c.a * rowCov;
    if (px1 - px0 == 1) {
        blendPixel(px0, y, c, (fx1 - fx0) * rowCov);
        return;
    }
    float left = (px0 + 1) - fx0, right = fx1 - (px1 - 1);
    blendPixel(px0, y, c, left * rowCov);
    blendSpan(y, px0 + 1, px1 - 1, c, unsigned(alpha + 0.5f));
    blendPixel(px1 - 1, y, c, right * rowCov);
}

// Distance -> coverage over `feather` pixels (1 px = anti-aliasing of a hard edge).
static inline float coverageOf(float d, float feather) {
    if (feather <= 0.0f) return d < 0 ? 1.0f : 0.0f;
    return std::clamp(0.5f - d / feather, 0.0f, 1.0f);
}

template <class Distance, class Shade>
void Canvas::fillSDFShade(Rect bounds, float feather, Distance d, Shade shade) {
    int x0 = int(std::floor(std::max(bounds.x - feather, clip_.x)));
    int y0 = int(std::floor(std::max(bounds.y - feather, clip_.y)));
    int x1 = int(std::ceil(std::min(bounds.right() + feather, clip_.right())));
    int y1 = int(std::ceil(std::min(bounds.bottom() + feather, clip_.bottom())));
    for (int y = y0; y < y1; y++) {
        for (int x = x0; x < x1; x++) {
            float cov = coverageOf(d(x + 0.5f, y + 0.5f), feather);
            if (cov > 0.0f) blendPixel(x, y, shade(x + 0.5f, y + 0.5f), cov);
        }
    }
}
template <class Distance>
void Canvas::fillSDF(Rect bounds, Color c, float feather, Distance d) {
    fillSDFShade(bounds, feather, d, [c](float, float) { return c; });
}

static inline float roundRectDistance(float px, float py, Rect r, float radius) {
    float hw = r.w * 0.5f, hh = r.h * 0.5f;
    radius = std::min(radius, std::min(hw, hh));
    float qx = std::fabs(px - (r.x + hw)) - (hw - radius);
    float qy = std::fabs(py - (r.y + hh)) - (hh - radius);
    float ox = std::max(qx, 0.0f), oy = std::max(qy, 0.0f);
    return std::sqrt(ox * ox + oy * oy) + std::min(std::max(qx, qy), 0.0f) - radius;
}

// Rounded rectangles row by row: straight rows are spans with exact edge coverage; only the corner cells (radius
// wide) are evaluated through the distance function. A 1920x1080 fill costs one span per row.
template <class Shade>
void Canvas::roundRectRows(Rect r, float radius, Shade shade) {
    if (r.w <= 0 || r.h <= 0) return;
    radius = std::clamp(radius, 0.0f, std::min(r.w, r.h) * 0.5f);
    int y0 = int(std::floor(std::max(r.y, clip_.y))), y1 = int(std::ceil(std::min(r.bottom(), clip_.bottom())));
    for (int y = y0; y < y1; y++) {
        float rowCov = std::min(r.bottom(), float(y + 1)) - std::max(r.y, float(y));
        if (rowCov <= 0.0f) continue;
        float yc = y + 0.5f;
        Color c = shade(yc);
        bool corner = radius > 0.5f && (yc < r.y + radius || yc > r.bottom() - radius);
        if (!corner) {
            spanWithEdges(y, r.x, r.right(), c, rowCov);
            continue;
        }
        float leftEnd = r.x + radius + 1, rightStart = r.right() - radius - 1;
        int lx0 = int(std::floor(std::max(r.x, clip_.x))), lx1 = int(std::ceil(std::min(leftEnd, clip_.right())));
        for (int x = lx0; x < lx1; x++) blendPixel(x, y, c, coverageOf(roundRectDistance(x + 0.5f, yc, r, radius), 1.0f));
        if (rightStart > leftEnd) spanWithEdges(y, leftEnd, rightStart, c, rowCov);
        int rx0 = int(std::floor(std::max(std::max(rightStart, leftEnd), clip_.x))), rx1 = int(std::ceil(std::min(r.right(), clip_.right())));
        for (int x = rx0; x < rx1; x++) blendPixel(x, y, c, coverageOf(roundRectDistance(x + 0.5f, yc, r, radius), 1.0f));
    }
}

void Canvas::fillRect(Rect r, Color c) {
    roundRectRows(r, 0.0f, [c](float) { return c; });
}

void Canvas::fillRoundRect(Rect r, float radius, Color c) {
    roundRectRows(r, radius, [c](float) { return c; });
}

void Canvas::fillRoundRectGradient(Rect r, float radius, Color top, Color bottom) {
    float h = std::max(r.h, 1.0f);
    roundRectRows(r, radius, [&](float yc) { return mix(top, bottom, (yc - r.y) / h); });
}

// Outline and shadow: the distance function is evaluated only in the bands around the edge (`band` pixels wide,
// the whole width in the top/bottom bands); for the shadow the interior is a plain span.
template <class Distance>
void Canvas::edgeBands(Rect outer, float band, float feather, Color c, Distance d, bool fillInterior) {
    int y0 = int(std::floor(std::max(outer.y, clip_.y))), y1 = int(std::ceil(std::min(outer.bottom(), clip_.bottom())));
    int ox0 = int(std::floor(std::max(outer.x, clip_.x))), ox1 = int(std::ceil(std::min(outer.right(), clip_.right())));
    for (int y = y0; y < y1; y++) {
        float yc = y + 0.5f;
        bool full = yc < outer.y + band || yc > outer.bottom() - band;
        auto evaluate = [&](int xa, int xb) {
            for (int x = xa; x < xb; x++) blendPixel(x, y, c, coverageOf(d(x + 0.5f, yc), feather));
        };
        if (full) {
            evaluate(ox0, ox1);
            continue;
        }
        int lx1 = int(std::ceil(std::min(outer.x + band, clip_.right())));
        int rx0 = int(std::floor(std::max(outer.right() - band, clip_.x)));
        evaluate(ox0, std::min(lx1, ox1));
        if (fillInterior && rx0 > lx1) blendSpan(y, std::max(lx1, ox0), std::min(rx0, ox1), c, c.a);
        evaluate(std::max(rx0, ox0), ox1);
    }
}

void Canvas::strokeRoundRect(Rect r, float radius, float thickness, Color c) {
    float half = thickness * 0.5f;
    radius = std::clamp(radius, 0.0f, std::min(r.w, r.h) * 0.5f);
    edgeBands(r.inset(-half - 1, -half - 1), radius + half + 2, 1.0f, c,
              [r, radius, half](float px, float py) { return std::fabs(roundRectDistance(px, py, r, radius)) - half; }, false);
}

void Canvas::shadowRoundRect(Rect r, float radius, float blur, Color c) {
    // Only the halo around the rectangle is drawn: the caller paints the rectangle itself over the inside.
    radius = std::clamp(radius, 0.0f, std::min(r.w, r.h) * 0.5f);
    edgeBands(r.inset(-blur, -blur), radius + 2 * blur + 1, 2.0f * blur, c,
              [r, radius](float px, float py) { return roundRectDistance(px, py, r, radius); }, false);
}

void Canvas::fillCircle(float cx, float cy, float radius, Color c) {
    Rect b{cx - radius, cy - radius, 2 * radius, 2 * radius};
    fillSDF(b, c, 1.0f, [cx, cy, radius](float px, float py) { return std::hypot(px - cx, py - cy) - radius; });
}

void Canvas::strokeCircle(float cx, float cy, float radius, float thickness, Color c) {
    float half = thickness * 0.5f;
    Rect b{cx - radius - half, cy - radius - half, 2 * (radius + half), 2 * (radius + half)};
    fillSDF(b, c, 1.0f, [cx, cy, radius, half](float px, float py) {
        return std::fabs(std::hypot(px - cx, py - cy) - radius) - half;
    });
}

void Canvas::line(float x0, float y0, float x1, float y1, float thickness, Color c) {
    float half = thickness * 0.5f;
    Rect b{std::min(x0, x1) - half, std::min(y0, y1) - half, std::fabs(x1 - x0) + thickness, std::fabs(y1 - y0) + thickness};
    float dx = x1 - x0, dy = y1 - y0, len2 = std::max(dx * dx + dy * dy, 1e-6f);
    fillSDF(b, c, 1.0f, [=](float px, float py) {
        float t = std::clamp(((px - x0) * dx + (py - y0) * dy) / len2, 0.0f, 1.0f);
        return std::hypot(px - (x0 + t * dx), py - (y0 + t * dy)) - half;
    });
}

void Canvas::fillTriangle(float x0, float y0, float x1, float y1, float x2, float y2, Color c) {
    Rect b{std::min({x0, x1, x2}), std::min({y0, y1, y2}), 0, 0};
    b.w = std::max({x0, x1, x2}) - b.x;
    b.h = std::max({y0, y1, y2}) - b.y;
    auto segment = [](float px, float py, float ax, float ay, float bx, float by) {
        float ex = bx - ax, ey = by - ay, wx = px - ax, wy = py - ay;
        float t = std::clamp((wx * ex + wy * ey) / std::max(ex * ex + ey * ey, 1e-6f), 0.0f, 1.0f);
        return std::hypot(wx - ex * t, wy - ey * t);
    };
    // Signed distance: negative inside (consistent winding handled by the sign of the doubled area).
    float area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0);
    fillSDF(b, c, 1.0f, [=](float px, float py) {
        float d = std::min({segment(px, py, x0, y0, x1, y1), segment(px, py, x1, y1, x2, y2), segment(px, py, x2, y2, x0, y0)});
        float s0 = (x1 - x0) * (py - y0) - (px - x0) * (y1 - y0);
        float s1 = (x2 - x1) * (py - y1) - (px - x1) * (y2 - y1);
        float s2 = (x0 - x2) * (py - y2) - (px - x2) * (y0 - y2);
        bool inside = area >= 0 ? (s0 >= 0 && s1 >= 0 && s2 >= 0) : (s0 <= 0 && s1 <= 0 && s2 <= 0);
        return inside ? -d : d;
    });
}

void Canvas::glyph(const Font& f, float px, int g, float x, float baseline, Color c) {
    float xf = std::floor(x);
    int shift = int((x - xf) * 3.0f) % 3;
    const GlyphBitmap& bm = f.info_->bitmap(px, g, shift);
    if (bm.w <= 0 || bm.h <= 0) return;
    int ox = int(xf) + bm.x0, oy = int(std::lround(baseline)) + bm.y0;
    int cx0 = int(clip_.x), cy0 = int(clip_.y), cx1 = int(clip_.right()), cy1 = int(clip_.bottom());
    for (int yy = 0; yy < bm.h; yy++) {
        int y = oy + yy;
        if (y < cy0 || y >= cy1) continue;
        for (int xx = 0; xx < bm.w; xx++) {
            int xpos = ox + xx;
            if (xpos < cx0 || xpos >= cx1) continue;
            uint8_t cov = bm.coverage[size_t(yy) * bm.w + xx];
            if (cov) blendPixel(xpos, y, c, cov / 255.0f);
        }
    }
}

float Canvas::text(const Font& f, float x, float y, float px, const std::string& utf8, Color c, Align align) {
    if (!f.info_) return 0;
    float width = f.measure(utf8, px);
    if (align == Align::Center) x -= width * 0.5f;
    else if (align == Align::Right) x -= width;
    float s = f.info_->scale(px), baseline = y + f.ascent(px), penX = x;
    int prev = 0;
    for (size_t i = 0; i < utf8.size();) {
        uint32_t cp = decodeUtf8(utf8, i);
        int g = f.info_->index(cp);
        if (prev) penX += stbtt_GetGlyphKernAdvance(&f.info_->font, prev, g) * s;
        glyph(f, px, g, penX, baseline, c);
        int adv, lsb;
        stbtt_GetGlyphHMetrics(&f.info_->font, g, &adv, &lsb);
        penX += adv * s;
        prev = g;
    }
    return width;
}

float Canvas::textInRect(const Font& f, Rect r, float px, const std::string& utf8, Color c, Align align, float padX) {
    float lineH = f.ascent(px) - f.descent(px);
    float y = r.y + (r.h - lineH) * 0.5f;
    float x = align == Align::Left ? r.x + padX : align == Align::Right ? r.right() - padX : r.x + r.w * 0.5f;
    return text(f, x, y, px, utf8, c, align);
}

void Canvas::blit(const Canvas& src, int x, int y) {
    for (int sy = 0; sy < src.h_; sy++) {
        int dy = y + sy;
        if (dy < int(clip_.y) || dy >= int(clip_.bottom())) continue;
        for (int sx = 0; sx < src.w_; sx++) {
            int dx = x + sx;
            if (dx < int(clip_.x) || dx >= int(clip_.right())) continue;
            const uint8_t* s = &src.px_[(size_t(sy) * src.w_ + sx) * 4];
            uint8_t* d = &px_[(size_t(dy) * w_ + dx) * 4];
            float ia = 1.0f - s[3] / 255.0f;
            for (int k = 0; k < 4; k++) d[k] = uint8_t(std::min(255L, std::lround(s[k] + d[k] * ia)));
        }
    }
}

void Canvas::blitStraight(const uint8_t* rgba, int sw, int sh, int x, int y, float alpha) {
    for (int sy = 0; sy < sh; sy++) {
        int dy = y + sy;
        if (dy < int(clip_.y) || dy >= int(clip_.bottom())) continue;
        for (int sx = 0; sx < sw; sx++) {
            int dx = x + sx;
            if (dx < int(clip_.x) || dx >= int(clip_.right())) continue;
            const uint8_t* s = &rgba[(size_t(sy) * sw + sx) * 4];
            blendPixel(dx, dy, Color{s[0], s[1], s[2], s[3]}, alpha);
        }
    }
}

void Canvas::drawScaled(const Canvas& src) {
    // Box filter when shrinking, nearest when enlarging. Straight copy of premultiplied values.
    for (int y = 0; y < h_; y++) {
        int sy0 = y * src.h_ / h_, sy1 = std::max(sy0 + 1, (y + 1) * src.h_ / h_);
        for (int x = 0; x < w_; x++) {
            int sx0 = x * src.w_ / w_, sx1 = std::max(sx0 + 1, (x + 1) * src.w_ / w_);
            unsigned sum[4] = {0, 0, 0, 0}, n = 0;
            for (int sy = sy0; sy < sy1; sy++)
                for (int sx = sx0; sx < sx1; sx++, n++)
                    for (int k = 0; k < 4; k++) sum[k] += src.px_[(size_t(sy) * src.w_ + sx) * 4 + k];
            uint8_t* d = &px_[(size_t(y) * w_ + x) * 4];
            for (int k = 0; k < 4; k++) d[k] = uint8_t(sum[k] / std::max(n, 1u));
        }
    }
}

std::vector<uint8_t> Canvas::toStraightRGBA() const {
    std::vector<uint8_t> out(px_.size());
    for (size_t i = 0; i < px_.size(); i += 4) {
        uint8_t a = px_[i + 3];
        if (a == 0) {
            out[i] = out[i + 1] = out[i + 2] = 0;
        } else {
            for (int k = 0; k < 3; k++) out[i + k] = uint8_t(std::min(255, int(px_[i + k]) * 255 / a));
        }
        out[i + 3] = a;
    }
    return out;
}

}  // namespace ui
