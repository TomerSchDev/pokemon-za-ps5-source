#pragma once
// Case-preserving text for the randomizer menu. Display::text (menu_display.cpp) upper-cases everything and
// has no glyphs for ! ? ' &, so a typed name would not show as it will appear in the game. These 5x7 glyphs
// (rows top to bottom, bit 4 = left column, the classic HD44780 shapes) cover what the name keyboard offers;
// upper case, digits, space, - and . still come from Display::text.
#include <string>

namespace za::native {
struct ExtraGlyph { char character; unsigned char rows[7]; };
inline constexpr ExtraGlyph extraGlyphs[] = {
    {'a', {0, 0, 14, 1, 15, 17, 15}},   {'b', {16, 16, 22, 25, 17, 17, 30}}, {'c', {0, 0, 14, 16, 16, 17, 14}},
    {'d', {1, 1, 13, 19, 17, 17, 15}},  {'e', {0, 0, 14, 17, 31, 16, 14}},   {'f', {6, 9, 8, 28, 8, 8, 8}},
    {'g', {0, 15, 17, 17, 15, 1, 14}},  {'h', {16, 16, 22, 25, 17, 17, 17}}, {'i', {4, 0, 12, 4, 4, 4, 14}},
    {'j', {2, 0, 6, 2, 2, 18, 12}},     {'k', {16, 16, 18, 20, 24, 20, 18}}, {'l', {12, 4, 4, 4, 4, 4, 14}},
    {'m', {0, 0, 26, 21, 21, 17, 17}},  {'n', {0, 0, 22, 25, 17, 17, 17}},   {'o', {0, 0, 14, 17, 17, 17, 14}},
    {'p', {0, 0, 30, 17, 30, 16, 16}},  {'q', {0, 0, 13, 19, 15, 1, 1}},     {'r', {0, 0, 22, 25, 16, 16, 16}},
    {'s', {0, 0, 14, 16, 14, 1, 30}},   {'t', {8, 8, 28, 8, 8, 9, 6}},       {'u', {0, 0, 17, 17, 17, 19, 13}},
    {'v', {0, 0, 17, 17, 17, 10, 4}},   {'w', {0, 0, 17, 17, 21, 21, 10}},   {'x', {0, 0, 17, 10, 4, 10, 17}},
    {'y', {0, 0, 17, 17, 15, 1, 14}},   {'z', {0, 0, 31, 2, 4, 8, 31}},      {'!', {4, 4, 4, 4, 4, 0, 4}},
    {'?', {14, 17, 1, 2, 4, 0, 4}},     {'\'', {4, 4, 8, 0, 0, 0, 0}},       {'&', {12, 18, 20, 8, 21, 18, 13}},
};

inline const ExtraGlyph* extraGlyph(char c) {
    for (const auto& g : extraGlyphs)
        if (g.character == c) return &g;
    return nullptr;
}

// Draws value as typed. Display: anything with rect(x, y, w, h, color) and text(x, y, string, color, scale).
template <class Display>
inline int drawExact(Display& d, int x, int y, const std::string& value, unsigned color, int scale) {
    for (char c : value) {
        if (const ExtraGlyph* g = extraGlyph(c)) {
            for (int row = 0; row < 7; row++)
                for (int col = 0; col < 5; col++)
                    if (g->rows[row] & (1 << (4 - col))) d.rect(x + col * scale, y + row * scale, scale, scale, color);
        } else {
            d.text(x, y, std::string(1, c), color, scale);
        }
        x += 6 * scale;
    }
    return x;
}
}
