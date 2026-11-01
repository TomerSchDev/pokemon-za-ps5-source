#include "ui_launcher.h"

#include <algorithm>
#include <cmath>

#include "ui_theme.h"
#include "settings_codes.h"

namespace ui::launcher {
using namespace theme;

std::string groupedSeed(const std::string& seed) {
    std::string out;
    int n = int(seed.size());
    for (int i = 0; i < n; i++) {
        out += seed[size_t(i)];
        if ((n - 1 - i) % 3 == 0 && i != n - 1) out += "\xE2\x80\x89";  // U+2009 thin space
    }
    return out;
}

static void background(Canvas& c) {
    c.fillRoundRectGradient(Rect{0, 0, float(c.width()), float(c.height())}, 0, Bg0, Bg1);
    // a faint diagonal band for depth
    for (int i = 0; i < 3; i++) {
        float x = 1180 + i * 170.0f;
        c.fillRoundRect(Rect{x, -80, 110, 1240}, 0, rgb(0xFFFFFF, uint8_t(5 - i)));
    }
}

static void header(Canvas& c, const Fonts& f, const State& s, bool showSeed) {
    float y = Top;
    c.text(f.bold, Margin, y, TitleSize, "POKÉMON LEGENDS Z-A", Accent);
    float w = f.bold.measure("POKÉMON LEGENDS Z-A", TitleSize);
    c.text(f.regular, Margin + w + 14, y, TitleSize, "·  RANDOMIZER", Text2);
    c.text(f.regular, Margin, y + 36, SmallSize, "PS5 native port  ·  build " + s.buildLabel, Text3);
    if (!showSeed) return;
    // Seed chip, top right: the seed is the one fact that matters everywhere.
    std::string seed = groupedSeed(s.seed);
    float sw = f.bold.measure(seed, SeedSize);
    float chipW = std::max(sw + 64, 420.0f), chipH = 92;
    Rect chip{float(c.width()) - Margin - chipW, Top - 10, chipW, chipH};
    c.fillRoundRect(chip, 18, Panel);
    c.strokeRoundRect(chip, 18, 1, PanelEdge);
    c.text(f.bold, chip.x + 24, chip.y + 10, SmallSize, "SEED", Text3);
    c.text(f.bold, chip.right() - 24, chip.y + 30, SeedSize, seed, Text, Align::Right);
    drawHints(c, f, chip.x + 24, chip.bottom() + 20, {{PadGlyph::Triangle, "Random seed"}}, Text3, Text3, SmallSize);
}

static void footer(Canvas& c, const Fonts& f, const std::vector<Hint>& hints, const std::string& rightNote) {
    float y = float(c.height()) - FooterH;
    c.fillRect(Rect{0, y, float(c.width()), FooterH}, rgb(0x000000, 60));
    c.fillRect(Rect{0, y, float(c.width()), 1}, PanelEdge);
    drawHints(c, f, Margin, y + FooterH * 0.5f, hints, Text2, Text, HintSize);
    if (!rightNote.empty()) {
        float lineH = f.regular.ascent(SmallSize) - f.regular.descent(SmallSize);
        c.text(f.regular, float(c.width()) - Margin, y + FooterH * 0.5f - lineH * 0.5f, SmallSize, rightNote, Text3, Align::Right);
    }
}

// ------------------------------------------------------------------------------------------ settings screen
static std::string navSummary(const model::PageDef& p, const State& s) {
    if (p.cards) return std::to_string(s.runs.size()) + (s.runs.size() == 1 ? " run" : " runs");
    if (p.id == std::string("play")) return s.activeRun >= 0 ? "Run ready" : "No run yet";
    // the first Level/Toggle/Text row's value is the page's one-line summary
    for (const auto& r : p.rows)
        if (r.kind == model::Kind::Level || r.kind == model::Kind::Toggle || r.kind == model::Kind::Text)
            return model::valueText(r, s.values);
    return "";
}

static void nav(Canvas& c, const Fonts& f, const State& s, Rect area) {
    const auto& pages = model::launcherPages();
    float itemH = 66, y = area.y + 36;
    drawPadGlyph(c, f, PadGlyph::L1, area.x + 22, area.y + 10, 24, Text3);
    for (size_t i = 0; i < pages.size(); i++) {
        bool on = int(i) == s.nav.page;
        Rect r{area.x, y, area.w, itemH - 6};
        if (on) {
            c.fillRoundRect(r, RowRadius, RowFocus);
            c.fillRoundRect(Rect{r.x, r.y + 10, 5, r.h - 20}, 2.5f, Accent);
        }
        c.text(f.bold, r.x + 26, r.y + 9, NavSize, pages[i].title, on ? Text : Text2);
        std::string sub = navSummary(pages[i], s);
        c.text(f.regular, r.x + 26, r.y + 38, NavSubSize, f.regular.fit(sub, NavSubSize, r.w - 52), on ? Accent : Text3);
        y += itemH;
    }
    drawPadGlyph(c, f, PadGlyph::R1, area.x + 22, y + 10, 24, Text3);
}

static void valueControl(Canvas& c, const Fonts& f, const model::RowDef& r, const State& s, Rect row, bool focused, bool& phase2) {
    float right = row.right() - 28, cy = row.y + 34;
    using model::Kind;
    // "NOT IN THIS BUILD": the row has nothing to choose in this build, or the chosen option is not shipped
    phase2 = !model::rowShipped(r);
    if (r.kind == Kind::Level || r.kind == Kind::Toggle) {
        if (!model::optionShipped(r, s.values.get(r.id, r.def))) phase2 = true;
    }
    switch (r.kind) {
        case Kind::Toggle: {
            bool on = s.values.get(r.id, r.def) != 0;
            std::string label = model::valueText(r, s.values);
            float lw = f.bold.measure(label, ValueSize);
            drawSwitch(c, right - 56, cy, on, focused ? Accent : AccentDim, rgb(0x2A3C55), Text);
            float lineH = f.bold.ascent(ValueSize) - f.bold.descent(ValueSize);
            c.text(f.bold, right - 56 - 18 - lw, cy - lineH * 0.5f, ValueSize, label, on ? (focused ? Accent : Text) : Text2);
            break;
        }
        case Kind::Level:
        case Kind::Number:
        case Kind::Pick: {
            std::string label = model::valueText(r, s.values);
            bool pickable = r.kind != Kind::Pick || !model::starterList(s.values.get(r.dependsOn, 0)).empty();
            float w = pillWidth(f, label, ValueSize, true, 22);
            float x = right - 26 - w;
            if (pickable) drawChevron(c, right - 12, cy, 16, false, focused ? Accent : Text3);
            drawPill(c, f, x, cy, label, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text, ValueSize, true, 22, PillH);
            if (pickable) drawChevron(c, x - 14, cy, 16, true, focused ? Accent : Text3);
            if (r.kind == Kind::Level && r.options.size() > 2) {
                int idx = s.values.get(r.id, r.def);
                float dotsW = 16.0f * float(r.options.size());
                drawLevelDots(c, right - dotsW, cy + 34, int(r.options.size()), idx, focused ? Accent : AccentDim, rgb(0x33475F));
            }
            break;
        }
        case Kind::Text: {
            std::string label = model::valueText(r, s.values);
            float w = pillWidth(f, label, ValueSize, true, 22);
            drawPill(c, f, right - w, cy, label, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text, ValueSize, true, 22, PillH);
            drawHints(c, f, right, cy + 34, {{PadGlyph::Cross, "Edit"}}, Text3, Text3, SmallSize, Align::Right);
            break;
        }
        case Kind::Link: {
            std::string label = r.id == std::string("seed") ? groupedSeed(s.seed) : r.id == std::string("saved") ? std::to_string(s.runs.size()) : "";
            if (!label.empty()) {
                float w = pillWidth(f, label, ValueSize, true, 22);
                drawPill(c, f, right - 26 - w, cy, label, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text, ValueSize, true, 22, PillH);
            }
            drawChevron(c, right - 12, cy, 16, false, focused ? Accent : Text3);
            break;
        }
        case Kind::Action: {
            bool primary = r.id == std::string("new_run") || r.id == std::string("continue");
            drawPill(c, f, right, cy, primary ? "Select" : "Run", focused ? Accent : rgb(0x223650), focused ? AccentInk : Text2, ValueSize, true, 24, PillH,
                     Align::Right);
            break;
        }
        case Kind::Info: {
            std::string label = model::valueText(r, s.values);
            float lineH = f.bold.ascent(ValueSize) - f.bold.descent(ValueSize);
            c.text(f.bold, right, cy - lineH * 0.5f, ValueSize, label, Text2, Align::Right);
            break;
        }
    }
}

static std::string rowDescription(const model::RowDef& r, const State& s) {
    if (r.id == std::string("continue")) {
        if (s.activeRun < 0 || s.activeRun >= int(s.runs.size())) return "No run yet. Start a new one below.";
        const RunCard& run = s.runs[size_t(s.activeRun)];
        return "Seed " + run.seed + "  ·  " + run.starter + "  ·  " + run.trainer + "  ·  " + run.date;
    }
    if (r.kind == model::Kind::Level || r.kind == model::Kind::Toggle) {
        const model::Option* o = model::selectedOption(r, s.values);
        if (o && *o->desc) return o->desc;
    }
    return r.desc;
}

static void rows(Canvas& c, const Fonts& f, const State& s, Rect area) {
    const model::PageDef& p = model::page(s.nav.page);
    c.text(f.bold, area.x, area.y, H1Size, p.title, Text);
    c.text(f.regular, area.x, area.y + 46, DescSize, p.blurb, Text2);
    if (p.id != std::string("play")) {
        const std::string code = codes::categoryCode(p.id, s.values);
        if (!code.empty()) drawPill(c, f, area.right(), area.y + 20, "Compare  " + code, rgb(0x14283F), Accent,
                                   SmallSize, true, 16, 34, Align::Right);
    }
    float y = area.y + 96;
    for (size_t i = 0; i < p.rows.size(); i++) {
        const model::RowDef& r = p.rows[i];
        bool focused = int(i) == s.nav.row;
        Rect row{area.x, y, area.w, RowH};
        c.fillRoundRect(row, RowRadius, focused ? RowFocus : Row);
        if (focused) {
            c.strokeRoundRect(row, RowRadius, 1.5f, withAlpha(Accent, 120));
            c.fillRoundRect(Rect{row.x, row.y + 14, 5, row.h - 28}, 2.5f, Accent);
        }
        bool phase2 = false;
        valueControl(c, f, r, s, row, focused, phase2);
        float labelX = row.x + 30;
        c.text(f.bold, labelX, row.y + 14, RowSize, r.label, focused ? Text : mix(Text, Text2, 0.25f));
        if (phase2) {
            float lw = f.bold.measure(r.label, RowSize);
            drawBadge(c, f, labelX + lw + 16, row.y + 32, "NOT IN THIS BUILD", Warn);
        }
        std::string desc = f.regular.fit(rowDescription(r, s), DescSize, row.w * 0.62f);
        c.text(f.regular, labelX, row.y + 54, DescSize, desc, focused ? Text2 : Text3);
        y += RowH + RowGap;
    }
}

static void cards(Canvas& c, const Fonts& f, const State& s, Rect area) {
    const model::PageDef& p = model::page(s.nav.page);
    c.text(f.bold, area.x, area.y, H1Size, p.title, Text);
    c.text(f.regular, area.x, area.y + 46, DescSize, p.blurb, Text2);
    if (s.runs.empty()) {
        c.text(f.regular, area.x, area.y + 120, RowSize, "No saved runs yet.", Text3);
        return;
    }
    const int cols = 2, perPage = 6;
    float gap = 20, cw = (area.w - gap) / cols, ch = 196;
    int firstCard = s.runIndex / perPage * perPage;
    for (int i = firstCard; i < int(s.runs.size()) && i < firstCard + perPage; i++) {
        const RunCard& run = s.runs[size_t(i)];
        int k = i - firstCard;
        Rect card{area.x + (k % cols) * (cw + gap), area.y + 96 + (k / cols) * (ch + gap), cw, ch};
        bool focused = i == s.runIndex;
        c.fillRoundRect(card, 18, focused ? RowFocus : Panel);
        c.strokeRoundRect(card, 18, focused ? 2.0f : 1.0f, focused ? Accent : PanelEdge);
        c.text(f.bold, card.x + 26, card.y + 18, SmallSize, "SEED", Text3);
        c.text(f.bold, card.x + 26, card.y + 38, 38, groupedSeed(run.seed), focused ? Accent : Text);
        if (run.active) drawBadge(c, f, card.right() - 26, card.y + 34, "ACTIVE", Accent, Align::Right);
        c.text(f.regular, card.x + 26, card.y + 94, DescSize, run.starter + "  ·  " + run.trainer + "  ·  " + run.date, Text2);
        c.text(f.regular, card.x + 26, card.y + 126, SmallSize, f.regular.fit(run.summary, SmallSize, card.w - 52), Text3);
        const std::string code = run.configCode.empty() ? "Phrase unavailable" : run.configCode;
        c.text(f.bold, card.x + 26, card.y + 154, 20, code,
               run.configCode.empty() ? Text3 : focused ? Accent : Text2);
    }
    if (int(s.runs.size()) > perPage) {
        Rect track{area.right() - 8, area.y + 96, 6, 3 * ch + 2 * gap};
        drawScrollbar(c, track, int(s.runs.size()), firstCard, perPage, rgb(0x1E2F45), AccentDim);
    }
    if (s.runIndex >= 0 && s.runIndex < int(s.runs.size())) {
        const RunCard& run = s.runs[size_t(s.runIndex)];
        const std::string detail = "Compare: seed " + groupedSeed(run.seed) + "  ·  " +
                                  (run.configCode.empty() ? "settings phrase unavailable for this older run" : run.configCode);
        c.text(f.regular, area.x, area.bottom() - 46, DescSize, f.regular.fit(detail, DescSize, area.w), Text2);
    }
}

static void settings(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, true);
    Rect navArea{Margin, HeaderH + 48, NavW, float(c.height()) - HeaderH - 48 - FooterH - 24};
    nav(c, f, s, navArea);
    Rect content{Margin + NavW + NavGap, HeaderH + 48, float(c.width()) - 2 * Margin - NavW - NavGap, navArea.h};
    const model::PageDef& p = model::page(s.nav.page);
    if (p.cards) cards(c, f, s, content);
    else rows(c, f, s, content);
    std::vector<Hint> hints = {{PadGlyph::DpadUpDown, "Move"}, {PadGlyph::DpadLeftRight, "Change"}, {PadGlyph::Cross, "Select"},
                               {PadGlyph::L1, "Page"}, {PadGlyph::Triangle, "Reset page"}, {PadGlyph::Circle, "Back to Play"}};
    if (p.cards) hints = {{PadGlyph::DpadUpDown, "Move"}, {PadGlyph::Cross, "Continue this run"}, {PadGlyph::L1, "Page"}, {PadGlyph::Circle, "Back to Play"}};
    footer(c, f, hints, s.statusLine.empty() ? "Early Rock route guard on  ·  all other ordinary spawns follow the settings" : s.statusLine);
}

int savedRunsPage() { return model::pageIndexOf("saved"); }

// ------------------------------------------------------------------------------------------ trainer name screen
static void nameScreen(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, false);
    Rect card{(c.width() - 1120) * 0.5f, 168, 1120, 700};
    c.shadowRoundRect(card, 24, 18, Shadow);
    c.fillRoundRect(card, 24, Panel);
    c.strokeRoundRect(card, 24, 1, PanelEdge);
    c.text(f.bold, card.x + 48, card.y + 36, H1Size, "Choose your trainer name", Text);
    c.text(f.regular, card.x + 48, card.y + 84, DescSize, "Up to 12 characters. It appears in the game exactly as typed. New runs only.", Text2);
    Rect field{card.x + 48, card.y + 132, card.w - 96, 96};
    c.fillRoundRect(field, 18, Bg0);
    c.strokeRoundRect(field, 18, 2, withAlpha(Accent, 140));
    const std::string& t = s.name.text;
    c.textInRect(f.bold, field, 56, t.empty() ? "Type a name" : t, t.empty() ? Text3 : Text, Align::Left, 32);
    float tw = t.empty() ? 0 : f.bold.measure(t, 56);
    c.fillRoundRect(Rect{field.x + 32 + tw + 8, field.y + 22, 4, field.h - 44}, 2, Accent);
    c.text(f.regular, field.right() - 28, field.y - 30, SmallSize, std::to_string(t.size()) + " / 12", Text3, Align::Right);
    // the 10 x 5 grid: 92 px keys, wide action keys span two columns
    float kx = card.x + 48, ky = field.bottom() + 30, kw = 92, kh = 66, kg = 10;
    for (size_t row = 0; row < s.name.labels.size(); row++) {
        float x = kx;
        for (size_t k = 0; k < s.name.labels[row].size(); k++) {
            int width = k < s.name.widths[row].size() ? s.name.widths[row][k] : 1;
            float w = kw * width + kg * (width - 1);
            bool on = int(row) == s.name.row && k == size_t(s.name.column);
            bool action = width > 1;
            Rect key{x, ky + row * (kh + kg), w, kh};
            c.fillRoundRect(key, 14, on ? Accent : action ? rgb(0x223650) : Row);
            if (!on) c.strokeRoundRect(key, 14, 1, PanelEdge);
            c.textInRect(f.bold, key, action ? ValueSize - 2 : 30, s.name.labels[row][k], on ? AccentInk : action ? Text2 : Text, Align::Center);
            x += w + kg;
        }
    }
    if (!s.name.message.empty()) {
        drawWarningTriangle(c, card.x + 60, card.bottom() - 60, 18, Warn);
        c.text(f.regular, card.x + 84, card.bottom() - 72, DescSize, s.name.message, Warn);
    }
    footer(c, f, {{PadGlyph::Dpad, "Move"}, {PadGlyph::Cross, "Type"}, {PadGlyph::Square, "Delete"}, {PadGlyph::Triangle, s.name.lower ? "ABC" : "abc"}, {PadGlyph::Circle, "Cancel"}},
           "Letters, digits, space and  - . ! ? ' &");
}

// ------------------------------------------------------------------------------------------ error screen
static void errorScreen(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, false);
    Rect card{(c.width() - 1120) * 0.5f, 300, 1120, 400};
    c.shadowRoundRect(card, 24, 18, Shadow);
    c.fillRoundRect(card, 24, Panel);
    c.strokeRoundRect(card, 24, 2, withAlpha(Err, 160));
    drawWarningTriangle(c, card.x + 72, card.y + 64, 28, Err);
    c.text(f.bold, card.x + 112, card.y + 44, H1Size, s.fatal ? "The randomizer could not start" : "Could not start this run", Text);
    // the message, wrapped by words into the card
    std::vector<std::string> lines;
    std::string line, word;
    auto flush = [&] { if (!line.empty()) lines.push_back(line); line.clear(); };
    for (size_t i = 0; i <= s.errorText.size(); i++) {
        char ch = i < s.errorText.size() ? s.errorText[i] : ' ';
        if (ch == ' ' || ch == '\n') {
            std::string candidate = line.empty() ? word : line + " " + word;
            if (f.regular.measure(candidate, RowSize - 2) <= card.w - 160 || line.empty()) line = candidate;
            else { flush(); line = word; }
            word.clear();
            if (ch == '\n') flush();
        } else word += ch;
    }
    flush();
    float y = card.y + 120;
    for (size_t i = 0; i < lines.size() && i < 5; i++, y += 38) c.text(f.regular, card.x + 112, y, RowSize - 2, lines[i], Text2);
    c.text(f.regular, card.x + 112, card.bottom() - 70, DescSize,
           s.fatal ? "Please close this app from the PS5 home screen. Your runs and saves were not changed." : "Your runs and saves were not changed.", Text3);
    footer(c, f, s.fatal ? std::vector<Hint>{} : std::vector<Hint>{{PadGlyph::Cross, "Back"}, {PadGlyph::Circle, "Back"}}, "");
}

// ------------------------------------------------------------------------------------------ seed screen
static void seedScreen(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, false);
    Rect card{(c.width() - 1120) * 0.5f, 168, 1120, 700};
    c.shadowRoundRect(card, 24, 18, Shadow);
    c.fillRoundRect(card, 24, Panel);
    c.strokeRoundRect(card, 24, 1, PanelEdge);
    c.text(f.bold, card.x + 48, card.y + 36, H1Size, "Enter a seed number", Text);
    c.text(f.regular, card.x + 48, card.y + 84, DescSize, "Up to 16 digits. The same seed and settings always build the same run.", Text2);
    // the entry field
    Rect field{card.x + 48, card.y + 132, card.w - 96, 110};
    c.fillRoundRect(field, 18, Bg0);
    c.strokeRoundRect(field, 18, 2, withAlpha(Accent, 140));
    std::string shown = s.seedInput.empty() ? "Type a number" : groupedSeed(s.seedInput);
    c.textInRect(f.bold, field, SeedBigSize, shown, s.seedInput.empty() ? Text3 : Text, Align::Left, 32);
    if (!s.seedInput.empty()) {
        float w = f.bold.measure(shown, SeedBigSize);
        c.fillRoundRect(Rect{field.x + 32 + w + 10, field.y + 26, 4, field.h - 52}, 2, Accent);
    }
    c.text(f.regular, field.right() - 28, field.y - 30, SmallSize, std::to_string(s.seedInput.size()) + " / 16", Text3, Align::Right);
    // keypad
    const char* keys[12] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "Clear", "0", "Done"};
    float kx = card.x + 48, ky = field.bottom() + 36, kw = 196, kh = 84, kg = 14;
    for (int i = 0; i < 12; i++) {
        Rect k{kx + (i % 3) * (kw + kg), ky + (i / 3) * (kh + kg), kw, kh};
        bool on = i == s.keypad, action = i == 9 || i == 11;
        Color bg = on ? Accent : action ? rgb(0x223650) : Row;
        c.fillRoundRect(k, 16, bg);
        if (!on) c.strokeRoundRect(k, 16, 1, PanelEdge);
        c.textInRect(f.bold, k, action ? ValueSize : 34, keys[i], on ? AccentInk : action ? Text2 : Text, Align::Center);
    }
    // right column: actions and recent seeds
    float rx = kx + 3 * (kw + kg) + 24, rw = card.right() - 48 - rx;
    c.text(f.bold, rx, ky, SmallSize, "ACTIONS", Text3);
    std::vector<std::pair<PadGlyph, const char*>> actions = {{PadGlyph::Triangle, "Generate a random seed"},
                                                            {PadGlyph::Square, "Delete the last digit"},
                                                            {PadGlyph::Cross, "Type the highlighted key"},
                                                            {PadGlyph::Circle, "Cancel and keep the old seed"}};
    float ay = ky + 34;
    for (auto& a : actions) {
        drawPadGlyph(c, f, a.first, rx + 16, ay + 16, 30, Text2);
        c.text(f.regular, rx + 46, ay + 3, DescSize, a.second, Text2);
        ay += 48;
    }
    c.text(f.bold, rx, ay + 18, SmallSize, "RECENT SEEDS", Text3);
    float sy = ay + 48;
    for (size_t i = 0; i < s.recentSeeds.size() && i < 3; i++) {
        drawPill(c, f, rx, sy + 20, groupedSeed(s.recentSeeds[i]), rgb(0x223650), Text, ValueSize - 2, true, 18, 40);
        sy += 54;
    }
    (void)rw;
    footer(c, f, {{PadGlyph::Dpad, "Move"}, {PadGlyph::Cross, "Enter"}, {PadGlyph::Square, "Delete"}, {PadGlyph::Triangle, "Random seed"}, {PadGlyph::Circle, "Cancel"}},
           "Current seed  " + groupedSeed(s.seed));
}

// ------------------------------------------------------------------------------------------ confirm / generating
static void confirmScreen(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, false);
    Rect card{(c.width() - 1120) * 0.5f, 168, 1120, 780};
    c.shadowRoundRect(card, 24, 18, Shadow);
    c.fillRoundRect(card, 24, Panel);
    c.strokeRoundRect(card, 24, 1, PanelEdge);
    c.text(f.bold, card.x + 48, card.y + 36, H1Size, "Start a new run?", Text);
    c.text(f.bold, card.x + 48, card.y + 104, SmallSize, "SEED", Text3);
    c.text(f.bold, card.x + 48, card.y + 124, SeedBigSize, groupedSeed(s.seed), Accent);
    c.text(f.bold, card.x + 48, card.y + 236, SmallSize, "SETTINGS PHRASE", Text3);
    c.text(f.bold, card.x + 300, card.y + 232, ValueSize, codes::configurationCode(s.values), Accent);
    float y = card.y + 296;
    const auto& pages = model::launcherPages();
    const float textX = card.x + 300, textW = card.w - 348;
    for (const auto& p : pages) {
        if (p.cards || p.id == std::string("play")) continue;
        // "label: value" for every shipped row of the page, packed into at most two lines
        std::vector<std::string> parts;
        for (const auto& r : p.rows) {
            if (r.kind == model::Kind::Action || r.kind == model::Kind::Link) continue;
            if (!model::rowShipped(r)) continue;
            parts.push_back(std::string(r.label) + ": " + model::valueText(r, s.values));
        }
        if (parts.empty()) continue;  // nothing of this page is in the build yet
        std::vector<std::string> lines(1);
        for (const auto& part : parts) {
            std::string candidate = lines.back().empty() ? part : lines.back() + "   ·   " + part;
            if (f.regular.measure(candidate, DescSize) <= textW || lines.back().empty()) lines.back() = candidate;
            else lines.push_back(part);
        }
        c.text(f.bold, card.x + 48, y, SmallSize, std::string(p.title), Text3);
        for (size_t i = 0; i < lines.size() && i < 2; i++) {
            c.text(f.regular, textX, y - 3, DescSize, f.regular.fit(lines[i], DescSize, textW), Text);
            y += 32;
        }
        y += 12;
    }
    c.text(f.regular, card.x + 48, card.bottom() - 110, DescSize, "You start in Lumiose City with a level 7 partner. Your previous runs stay in Saved runs.", Text2);
    c.text(f.regular, card.x + 48, card.bottom() - 78, DescSize, "The early Rock route provider is kept; side quests are not guaranteed.", Text3);
    c.text(f.regular, card.x + 48, card.bottom() - 44, SmallSize, "Same seed + same settings phrase gives the same run.", Text2);
    footer(c, f, {{PadGlyph::Cross, "Create and play"}, {PadGlyph::Circle, "Back"}}, "");
}

static void generatingScreen(Canvas& c, const Fonts& f, const State& s) {
    header(c, f, s, false);
    Rect card{(c.width() - 1120) * 0.5f, 220, 1120, 560};
    c.shadowRoundRect(card, 24, 18, Shadow);
    c.fillRoundRect(card, 24, Panel);
    c.strokeRoundRect(card, 24, 1, PanelEdge);
    c.text(f.bold, card.x + 48, card.y + 36, H1Size, "Creating your run", Text);
    c.text(f.bold, card.x + 48, card.y + 92, SmallSize, "SEED", Text3);
    c.text(f.bold, card.x + 48, card.y + 110, SeedSize, groupedSeed(s.seed), Accent);
    const char* stages[] = {"Preparing species", "Randomizing trainers", "Randomizing wild Pokémon", "Randomizing Mega Dimension", "Preparing the starter save", "Saving the new run"};
    float y = card.y + 196;
    for (int i = 0; i < 6; i++) {
        bool done = i < s.genStage, now = i == s.genStage;
        if (done) drawCheck(c, card.x + 64, y + 14, 22, Accent);
        else c.strokeCircle(card.x + 64, y + 14, 9, 2, now ? Accent : Text3);
        c.text(f.regular, card.x + 96, y, RowSize - 2, stages[i], done ? Text2 : now ? Text : Text3);
        y += 44;
    }
    Rect bar{card.x + 48, card.bottom() - 72, card.w - 96, 14};
    c.fillRoundRect(bar, 7, rgb(0x223650));
    float frac = s.genTotal > 0 ? float(s.genDone) / float(s.genTotal) : 0;
    c.fillRoundRect(Rect{bar.x, bar.y, std::max(14.0f, bar.w * frac), bar.h}, 7, Accent);
    c.text(f.regular, bar.right(), bar.y - 32, SmallSize, std::to_string(s.genDone) + " / " + std::to_string(s.genTotal), Text2, Align::Right);
    footer(c, f, {}, "Preparing data and a separate save for this seed");
}

void draw(Canvas& c, const Fonts& f, const State& s) {
    background(c);
    switch (s.screen) {
        case Screen::Settings: settings(c, f, s); break;
        case Screen::Seed: seedScreen(c, f, s); break;
        case Screen::SavedRuns: settings(c, f, s); break;
        case Screen::Confirm: confirmScreen(c, f, s); break;
        case Screen::Generating: generatingScreen(c, f, s); break;
        case Screen::Name: nameScreen(c, f, s); break;
        case Screen::Error: errorScreen(c, f, s); break;
    }
    if (s.toastVisible) drawToast(c, f, s.toast, c.width() * 0.5f, c.height() - FooterH - 24);
}

}  // namespace ui::launcher
