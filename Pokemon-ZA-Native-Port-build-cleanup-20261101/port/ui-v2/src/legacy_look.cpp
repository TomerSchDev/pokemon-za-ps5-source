#include "legacy_look.h"

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <string>
#include <vector>

#include "menu_font.h"    // port/randomizer/menu_font.h (GPL-3.0-or-later glyph table, read by path)
#include "name_glyphs.hpp"  // port/rando-v2/name_glyphs.hpp: drawExact() for the typed trainer name

namespace ui::legacy {

// ---------------------------------------------------------------------------------------- launcher (menu_display.cpp)
class LegacyDisplay {
public:
    static constexpr int width = 1280, height = 720;
    static constexpr int physicalWidth = 1920, physicalHeight = 1080;
    LegacyDisplay() : px(size_t(physicalWidth) * physicalHeight, 0xff000000u) {}

    // Display::rect, verbatim apart from the linear store.
    void rect(int x, int y, int w, int h, uint32_t color) {
        int right = x + w, bottom = y + h;
        if (right > width) right = width;
        if (bottom > height) bottom = height;
        if (x < 0) x = 0;
        if (y < 0) y = 0;
        x = x * 3 / 2; y = y * 3 / 2; right = right * 3 / 2; bottom = bottom * 3 / 2;
        for (int yy = y; yy < bottom; yy++)
            for (int xx = x; xx < right; xx++) px[size_t(yy) * physicalWidth + xx] = color;
    }
    void clear() { rect(0, 0, width, height, 0xff0b1524); rect(0, 0, 12, height, 0xff54e3aa); }
    // Display::text, verbatim.
    void text(int x, int y, const std::string& value, uint32_t color = 0xffedf5fc, int scale = 3) {
        const int origin = x;
        for (unsigned char ch : value) {
            if (ch == '\n') { y += 9 * scale; x = origin; continue; }
            if (ch >= 128) continue;
            char c = char(std::toupper(ch));
            const MenuGlyph* found = nullptr;
            for (const auto& g : glyphs) if (g.character == c) { found = &g; break; }
            if (found) { for (int row = 0; row < 7; row++) for (int col = 0; col < 5; col++) if (found->rows[row] & (1 << (4 - col))) rect(x + col * scale, y + row * scale, scale, scale, color); }
            else if (c == '-') rect(x, y + 3 * scale, 5 * scale, scale, color);
            else if (c == '.') rect(x + 2 * scale, y + 6 * scale, scale, scale, color);
            else if (c == ':') { rect(x + 2 * scale, y + 2 * scale, scale, scale, color); rect(x + 2 * scale, y + 5 * scale, scale, scale, color); }
            else if (c == '/') for (int row = 0; row < 7; row++) rect(x + (4 - row * 4 / 6) * scale, y + row * scale, scale, scale, color);
            x += 6 * scale;
            if (x + 5 * scale >= width) break;
        }
    }
    void toCanvas(Canvas& out) const {
        uint8_t* d = out.data();
        for (size_t i = 0; i < px.size(); i++) {
            uint32_t c = px[i];
            d[i * 4 + 0] = uint8_t(c >> 16); d[i * 4 + 1] = uint8_t(c >> 8); d[i * 4 + 2] = uint8_t(c); d[i * 4 + 3] = 255;
        }
    }
    std::vector<uint32_t> px;
};

static constexpr uint32_t Green = 0xff54e3aa, Muted = 0xff91a5bb, White = 0xffedf5fc;

static void heading(LegacyDisplay& d, const char* subtitle) {
    d.clear(); d.text(56, 36, "POKEMON LEGENDS Z-A", Green, 4); d.text(56, 83, "RANDOMIZER", White, 3);
    d.text(56, 123, subtitle, Muted, 2); d.rect(56, 155, 1168, 2, 0xff293c51);
}

void launcherMain(Canvas& out) {
    LegacyDisplay display;
    // native_menu_music.cpp, page Main (12 rows): sample values, row 1 ("START NEW RUN") focused.
    const int MainRows = 12, row = 1;
    std::string seed = "2315984632", playerName = "Tomer";
    heading(display, "CREATE A NEW RUN OR CONTINUE AN EXISTING SAVE");
    std::string labels[] = {"CONTINUE CURRENT RUN", "START NEW RUN", "SEED  " + seed, "STARTER  RANDOM FROM SEED", "NAME  ",
                            "WILD POKEMON  ON", "TRAINERS  ON", "MEGA TRAINERS  ON", "DLC REMATCHES  ON", "RESEARCH REWARDS  ON",
                            "MUSIC  OFF", "SAVED RUNS  6"};
    for (int i = 0; i < MainRows; i++) {
        int y = 176 + i * 37;
        if (i == row) display.rect(44, y - 7, 1180, 35, 0xff24413e);
        display.text(64, y, labels[i], i == row ? Green : White, 3);
        if (i == 4) za::native::drawExact(display, 64 + int(labels[i].size()) * 18, y, playerName, i == row ? Green : White, 3);
    }
    display.text(56, 633, "D-PAD MOVE / CHANGE    CROSS SELECT    TRIANGLE RANDOM STARTER", Muted, 2);
    display.text(56, 668, "EARLY ROCK GUARD ON. ALL OTHER ORDINARY SPAWNS RANDOM.", Muted, 2);
    display.toCanvas(out);
}

void launcherSeed(Canvas& out) {
    LegacyDisplay display;
    std::string seedInput = "4031";
    int keypad = 4;
    heading(display, "ENTER A SEED USING THE NUMBER KEYPAD - UP TO 16 DIGITS");
    display.rect(280, 185, 720, 68, 0xff192b3d);
    display.text(304, 205, seedInput.empty() ? "ENTER A NUMBER" : seedInput, seedInput.empty() ? Muted : Green, 4);
    const char* keys[] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "CLEAR", "0", "DONE"};
    for (int i = 0; i < 12; i++) {
        int x = 320 + (i % 3) * 216, y = 280 + (i / 3) * 78;
        display.rect(x, y, 200, 64, i == keypad ? 0xff244f43 : 0xff192b3d);
        display.text(x + 100 - int(std::string(keys[i]).size()) * 9, y + 21, keys[i], i == keypad ? Green : White, 3);
    }
    display.text(56, 620, "D-PAD MOVE    CROSS ENTER    SQUARE DELETE", White, 2);
    display.text(56, 663, "TRIANGLE RANDOM SEED    CIRCLE CANCEL", Muted, 2);
    display.toCanvas(out);
}

void launcherSaved(Canvas& out) {
    LegacyDisplay display;
    struct Run { std::string seed, starter, name; };
    std::vector<Run> runs = {{"2315984632", "Tepig", "Tomer"}, {"9376797808", "Pikachu", "Tomer"}, {"6177047620", "Greavard", "Tomer"},
                             {"30081997", "Chingling", "Tomer"}, {"4031C916F62655AE", "Gengar", ""}, {"12345", "Chikorita", "Trainer"}};
    int runIndex = 1;
    heading(display, "SELECT A SAVED RUN TO CONTINUE");
    int start = runIndex / 8 * 8;
    for (int i = start; i < int(runs.size()) && i < start + 8; i++) {
        int y = 190 + (i - start) * 50;
        if (i == runIndex) display.rect(44, y - 9, 1180, 46, 0xff24413e);
        const std::string& name = runs[size_t(i)].name;
        const std::string head = runs[size_t(i)].seed + "  " + runs[size_t(i)].starter + (name.empty() ? "" : "  ");
        display.text(64, y, head, i == runIndex ? Green : White, 2);
        if (!name.empty()) za::native::drawExact(display, 64 + int(head.size()) * 12, y, name, i == runIndex ? Green : White, 2);
    }
    display.text(56, 652, "UP / DOWN SELECT    CROSS CONTINUE    CIRCLE BACK", Muted, 2);
    display.toCanvas(out);
}

// ---------------------------------------------------------------------------------------- overlay (cheats-r28.cpp)
class LegacyVk {
public:
    uint32_t w = 3840, h = 2160;
    std::vector<uint32_t> px;
    explicit LegacyVk(const Canvas& background) : px(size_t(w) * h) {
        Canvas big{int(w), int(h)};
        big.drawScaled(background);
        const uint8_t* d = big.data();
        for (size_t i = 0; i < px.size(); i++) px[i] = (uint32_t(d[i * 4]) << 16) | (uint32_t(d[i * 4 + 1]) << 8) | d[i * 4 + 2];
    }
    // Canvas::rect + draw of cheats-r28.cpp: offsets x*w/1280, extents rw*w/1280, an opaque clear colour.
    void clearRect(int x, int y, int rw, int rh, uint32_t color) {
        int ox = int(int64_t(x) * w / 1280), oy = int(int64_t(y) * h / 720);
        unsigned ew = unsigned(int64_t(rw) * w / 1280), eh = unsigned(int64_t(rh) * h / 720);
        for (unsigned yy = 0; yy < eh; yy++) for (unsigned xx = 0; xx < ew; xx++) {
            unsigned X = unsigned(ox) + xx, Y = unsigned(oy) + yy;
            if (X < w && Y < h) px[size_t(Y) * w + X] = color;
        }
    }
    void box(int x, int y, int rw, int rh, uint32_t color) { clearRect(x, y, rw, rh, color); }
    // Canvas::encode + text: 5x7 cells, 6 advance; '.' one cell on the baseline, 3 wide; unknown advances only.
    void text(int x, int y, const std::string& value, int scale, uint32_t color) {
        for (char c : value) {
            if (c == '.') { clearRect(x + scale, y + 6 * scale, scale, scale, color); x += 3 * scale; continue; }
            const MenuGlyph* found = nullptr;
            for (const auto& g : glyphs) if (g.character == c) { found = &g; break; }
            if (found) for (int yy = 0; yy < 7; yy++) for (int xx = 0; xx < 5; xx++) if (found->rows[yy] & (1u << (4 - xx))) clearRect(x + xx * scale, y + yy * scale, scale, scale, color);
            x += 6 * scale;
        }
    }
    void toCanvas(Canvas& out) const {
        Canvas big{int(w), int(h)};
        uint8_t* d = big.data();
        for (size_t i = 0; i < px.size(); i++) {
            d[i * 4 + 0] = uint8_t(px[i] >> 16); d[i * 4 + 1] = uint8_t(px[i] >> 8); d[i * 4 + 2] = uint8_t(px[i]); d[i * 4 + 3] = 255;
        }
        out.drawScaled(big);
    }
};

static void legacyReadout(LegacyVk& c) {
    // FpsReadout::layout/render for "60 FPS", "16.7 MS", "60 MODE".
    std::string line1 = "60 FPS", line2 = "16.7 MS", line3 = "60 MODE";
    auto textWidth = [](const std::string& v, int scale) { int w = 0; for (char ch : v) w += (ch == '.' ? 3 : 6) * scale; return w > 0 ? w - scale : 0; };
    const int s1 = 3, s2 = 2, right = 1280 - 16, top = 16;
    int w1 = textWidth(line1, s1), w2 = textWidth(line2, s2), w3 = textWidth(line3, s2);
    int wmax = std::max(w1, std::max(w2, w3));
    int y1 = top, y2 = y1 + 7 * s1 + 6, y3 = y2 + 7 * s2 + 4, bottom = y3 + 7 * s2;
    c.box(right - wmax - 8, top - 6, wmax + 16, bottom - top + 12, 0x101e2d);
    c.text(right - w1, y1, line1, s1, 0x54e3aa); c.text(right - w2, y2, line2, s2, 0xedf5fc); c.text(right - w3, y3, line3, s2, 0x91a5bb);
}

void overlayPage1(Canvas& out, const Canvas& background) {
    LegacyVk c(background);
    legacyReadout(c);
    const int kRows = 7, row = 2;
    c.box(100, 104, 1080, 512, 0x101e2d); c.box(100, 104, 1080, 5, 0x54e3aa);
    c.text(136, 140, "Z-A RANDOMIZER - CHEATS", 4, 0x54e3aa);
    std::string money = "MONEY  PLUS 100000  QUEUED - SAVE IN GAME";
    std::string trial = "FPS TRIAL  30 - X START 60";
    std::string hebrew = "HEBREW TRIAL  OFF - X SWITCH ON";
    std::string labels[] = {"SHINY  NORMAL", "CAPTURE  NORMAL", money, "FPS COUNTER  ON", trial, hebrew, "RESET BOTH TO NORMAL"};
    for (int i = 0; i < kRows; i++) { int y = 196 + i * 36; if (i == row) c.box(124, y, 1032, 32, 0x24413e); c.text(144, y + 5, labels[i], 3, i == row ? 0x54e3aa : 0xedf5fc); }
    c.text(136, 462, "SHINY APPLIES TO NEWLY GENERATED POKEMON", 2, 0x91a5bb);
    c.text(136, 486, "CAPTURE BOOST KEEPS THE TARGET ELIGIBILITY CHECK", 2, 0x91a5bb);
    c.text(136, 510, "MONEY  X QUEUES / SAVE IN GAME TO APPLY / NORMAL CANCELS", 2, 0x91a5bb);
    c.text(136, 534, "FPS TRIAL: SESSION ONLY / AUTO RETURN TO 30", 2, 0xffce80);
    c.text(136, 562, "PAGE 1/2 - L1 / R1 PAGE - D-PAD SELECT - CIRCLE CLOSE", 2, 0xedf5fc);
    c.text(136, 586, "SETTINGS SAVED FOR THIS RUN", 2, 0x91a5bb);
    c.toCanvas(out);
}

void overlayPage2(Canvas& out, const Canvas& background) {
    LegacyVk c(background);
    legacyReadout(c);
    const int kRows = 7, row = 0;
    c.box(100, 104, 1080, 512, 0x101e2d); c.box(100, 104, 1080, 5, 0x54e3aa);
    c.text(136, 140, "Z-A RANDOMIZER - CHEATS", 4, 0x54e3aa);
    std::string label[] = {"ITEM 10/199  RARE CANDY", "AMOUNT  99    CAP 999", "ADD ITEM - X  READY", "ALPHA RATE  DISABLED",
                           "EXP MULTIPLIER  DISABLED", "MEGA GAUGE  DISABLED", "ENCOUNTER RATE  DISABLED"};
    for (int i = 0; i < kRows; i++) { int y = 196 + i * 36; if (i == row) c.box(124, y, 1032, 32, 0x24413e); c.text(144, y + 5, label[i], 3, i >= 3 ? 0x91a5bb : i == row ? 0x54e3aa : 0xedf5fc); }
    c.text(136, 462, "ADD: CLOSE THIS MENU AND OPEN SATCHEL TO APPLY", 2, 0xffce80);
    c.text(136, 486, "OPEN SATCHEL ONCE TO ENABLE - SAVE IN GAME AFTER ADDING", 2, 0x91a5bb);
    c.text(136, 510, "LEFT / RIGHT ITEM OR AMOUNT - TRIANGLE JUMPS 10 ITEMS", 2, 0x91a5bb);
    c.text(136, 534, "ONE REQUEST AT A TIME - ITEM LIMITS FOLLOW THE GAME", 2, 0x91a5bb);
    c.text(136, 562, "PAGE 2/2 - L1 / R1 PAGE - CIRCLE CLOSE", 2, 0xedf5fc);
    c.text(136, 586, "R28 ITEMS - SESSION REQUESTS ARE NEVER REPLAYED", 2, 0x91a5bb);
    c.toCanvas(out);
}

}  // namespace ui::legacy
