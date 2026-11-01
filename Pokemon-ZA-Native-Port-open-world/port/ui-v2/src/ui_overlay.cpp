#include "ui_overlay.h"

#include <algorithm>
#include <cctype>
#include <cstdio>

#include "ui_theme.h"

namespace ui::overlay {
using namespace theme;

static const Rect kPanel{200, 92, 1520, 896};

static std::string u2s(unsigned v) {
    char b[16];
    std::snprintf(b, sizeof b, "%u", v);
    return b;
}

static std::string readoutLine(const State& s) {
    return u2s((s.readout.fpsX10 + 5) / 10) + " FPS   " + u2s(s.readout.msX10 / 10) + "." + u2s(s.readout.msX10 % 10) + " ms   " + s.readout.mode;
}

Rect readoutRect(const Fonts& f, const State& s) {
    float w = f.bold.measure(readoutLine(s), 20) + 40;
    return Rect{1920 - 24 - w, 20, w, 40};
}

static void readoutAt(Canvas& c, const Fonts& f, const State& s, Rect r) {
    c.fillRoundRect(r, 12, rgb(0x0C1726, 200));
    c.strokeRoundRect(r, 12, 1, rgb(0x2E4360, 180));
    c.textInRect(f.bold, r, 20, readoutLine(s), s.readout.mode == "FALLBACK" ? Warn : Accent, Align::Center);
}

static void readout(Canvas& c, const Fonts& f, const State& s) {
    if (!s.fpsCounter) return;
    readoutAt(c, f, s, readoutRect(f, s));
}

// The readout alone, at the top-left of a small canvas (the title's readout layer).
void drawReadoutOnly(Canvas& c, const Fonts& f, const State& s) {
    Rect r = readoutRect(f, s);
    readoutAt(c, f, s, Rect{0, 0, r.w, r.h});
}

Rect panelRect() { return kPanel; }

static void tabs(Canvas& c, const Fonts& f, const State& s, Rect bar) {
    drawPadGlyph(c, f, PadGlyph::L1, bar.x + 22, bar.y + bar.h * 0.5f, 26, Text3);
    float x = bar.x + 60;
    for (int t = 0; t < 1 + items::TabCount; t++) {
        std::string name = t == TabCheats ? "Cheats" : items::tabName(t - TabItemsFirst);
        bool on = t == s.tab;
        float w = pillWidth(f, name, 22, true, 22);
        if (t - TabItemsFirst == items::TabFavourites) w += 26;
        Rect pill{x, bar.y + (bar.h - 44) * 0.5f, w, 44};
        if (on) c.fillRoundRect(pill, 22, Accent);
        float tx = pill.x + 22;
        if (t - TabItemsFirst == items::TabFavourites) {
            drawStar(c, tx + 8, pill.y + 22, 9, on ? AccentInk : Warn, true);
            tx += 26;
        }
        c.text(f.bold, tx, pill.y + (44 - (f.bold.ascent(22) - f.bold.descent(22))) * 0.5f, 22, name, on ? AccentInk : Text2);
        x += w + 10;
    }
    drawPadGlyph(c, f, PadGlyph::R1, x + 22, bar.y + bar.h * 0.5f, 26, Text3);
}

static std::string moneyValue(const CheatState& cs) {
    const char* m[] = {"Normal", "+10,000", "+100,000", "+1,000,000"};
    return m[std::clamp(cs.moneyChoice, 0, 3)];
}

static void cheatsTab(Canvas& c, const Fonts& f, const State& s, Rect body) {
    const auto& rows = model::cheatRows();
    const CheatState& cs = s.cheats;
    float rowH = 88, y = body.y;
    for (size_t i = 0; i < rows.size(); i++) {
        const model::RowDef& r = rows[i];
        bool focused = int(i) == s.row;
        Rect row{body.x, y, body.w, rowH};
        c.fillRoundRect(row, RowRadius, focused ? RowFocus : rgb(0x152536, 230));
        if (focused) {
            c.strokeRoundRect(row, RowRadius, 1.5f, withAlpha(Accent, 120));
            c.fillRoundRect(Rect{row.x, row.y + 14, 5, row.h - 28}, 2.5f, Accent);
        }
        float labelX = row.x + 30, right = row.right() - 28, cy = row.y + 32;
        c.text(f.bold, labelX, row.y + 12, RowSize, r.label, focused ? Text : mix(Text, Text2, 0.25f));
        std::string desc = r.desc, value, badge;
        Color badgeColor = Accent;
        if (r.id == std::string("shiny") || r.id == std::string("capture")) {
            int v = r.id == std::string("shiny") ? cs.shiny : cs.capture;
            v = std::clamp(v, 0, int(r.options.size()) - 1);
            value = r.options[size_t(v)].label;
            desc = r.options[size_t(v)].desc;
        } else if (r.id == std::string("money")) {
            value = cs.moneyAvailable ? moneyValue(cs) : "Not available";
            desc = cs.moneyAvailable ? r.options[size_t(std::clamp(cs.moneyChoice, 0, 3))].desc : "The money hook is not in this build.";
            if (cs.moneyAvailable && !cs.moneyStatus.empty()) {
                badge = cs.moneyStatus;
                badgeColor = badge.rfind("ADDED", 0) == 0 ? Accent : badge.rfind("QUEUED", 0) == 0 ? Warn : Err;
            }
        } else if (r.id == std::string("fps_counter")) {
            value = cs.fpsCounter ? "On" : "Off";
        } else if (r.id == std::string("fps_trial")) {
            value = cs.fpsMode == -1 ? "Controlled by config" : cs.fpsMode == 1 ? "60 (auto)" : cs.fpsMode == 2 ? "30 fallback" : "30";
            badge = cs.fpsMode == 1 ? "CROSS: STOP" : cs.fpsMode == 2 ? "CROSS: RETRY 60" : cs.fpsMode == 0 ? "CROSS: START 60" : "";
            badgeColor = cs.fpsMode == 2 ? Warn : Accent;
        } else if (r.id == std::string("hebrew")) {
            value = cs.hebrewMode == 1 ? "On" : cs.hebrewMode == 0 ? "Off" : "Pack not available";
            badge = cs.hebrewMode == 1 ? "CROSS: SWITCH OFF" : cs.hebrewMode == 0 ? "CROSS: SWITCH ON" : "";
            badgeColor = Warn;
        }
        // value control
        if (r.kind == model::Kind::Toggle) {
            drawSwitch(c, right - 56, cy, cs.fpsCounter, focused ? Accent : AccentDim, rgb(0x2A3C55), Text);
            float lw = f.bold.measure(value, ValueSize), lineH = f.bold.ascent(ValueSize) - f.bold.descent(ValueSize);
            c.text(f.bold, right - 56 - 18 - lw, cy - lineH * 0.5f, ValueSize, value, focused ? Accent : Text);
        } else if (r.kind == model::Kind::Level) {
            float w = pillWidth(f, value, ValueSize, true, 22), x = right - 26 - w;
            drawChevron(c, right - 12, cy, 16, false, focused ? Accent : Text3);
            drawPill(c, f, x, cy, value, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text, ValueSize, true, 22, PillH);
            drawChevron(c, x - 14, cy, 16, true, focused ? Accent : Text3);
            float dotsW = 16.0f * float(r.options.size());
            int idx = r.id == std::string("shiny") ? cs.shiny : r.id == std::string("capture") ? cs.capture : cs.moneyChoice;
            drawLevelDots(c, right - dotsW, cy + 34, int(r.options.size()), idx, focused ? Accent : AccentDim, rgb(0x33475F));
            if (!badge.empty()) drawBadge(c, f, x - 30, cy, badge, badgeColor, Align::Right);
        } else if (r.kind == model::Kind::Action && !value.empty()) {
            float w = pillWidth(f, value, ValueSize, true, 22);
            drawPill(c, f, right - w, cy, value, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text, ValueSize, true, 22, PillH);
            if (!badge.empty()) drawBadge(c, f, right - w - 16, cy, badge, badgeColor, Align::Right);
        } else if (r.kind == model::Kind::Action) {
            drawPill(c, f, right, cy, "Reset", focused ? Accent : rgb(0x223650), focused ? AccentInk : Text2, ValueSize, true, 24, PillH, Align::Right);
        }
        c.text(f.regular, labelX, row.y + 50, DescSize, f.regular.fit(desc, DescSize, row.w * 0.6f), focused ? Text2 : Text3);
        y += rowH + 6;
    }
}

static void itemsTab(Canvas& c, const Fonts& f, const State& s, Rect body) {
    const items::Picker& p = s.picker;
    const auto& items = items::catalog();
    const auto& vis = p.visible();
    Rect list{body.x, body.y + 44, body.w - 110, ListRowH * ListVisible};
    // column header
    c.text(f.bold, list.x + 30, body.y + 6, SmallSize, "ITEM", Text3);
    c.text(f.bold, list.x + list.w * 0.56f, body.y + 6, SmallSize, "POCKET", Text3);
    c.text(f.bold, list.right() - 206, body.y + 6, SmallSize, "AMOUNT", Text3);
    c.text(f.bold, list.right() - 30, body.y + 6, SmallSize, "CAP", Text3, Align::Right);
    if (vis.empty()) {
        c.text(f.regular, list.x + 30, list.y + 20, RowSize - 2, p.tab() == items::TabFavourites ? "No favourites yet. Square marks an item; added items appear here too." : "Nothing here.", Text3);
    }
    for (int k = 0; k < ListVisible && p.first() + k < int(vis.size()); k++) {
        int idx = p.first() + k;
        unsigned itemIndex = vis[size_t(idx)];
        const items::Item& it = items[itemIndex];
        bool focused = idx == p.cursor();
        Rect row{list.x, list.y + k * ListRowH, list.w, ListRowH - 4};
        c.fillRoundRect(row, 10, focused ? RowFocus : rgb(0x152536, 215));
        if (focused) {
            c.strokeRoundRect(row, 10, 1.5f, withAlpha(Accent, 120));
            c.fillRoundRect(Rect{row.x, row.y + 10, 5, row.h - 20}, 2.5f, Accent);
        }
        float cy = row.y + row.h * 0.5f;
        if (p.isFavourite(itemIndex)) drawStar(c, row.x + 32, cy, 9, Warn, true);
        else if (focused) drawStar(c, row.x + 32, cy, 9, Text3, false);
        float lineH = f.bold.ascent(ValueSize) - f.bold.descent(ValueSize);
        c.text(focused ? f.bold : f.regular, row.x + 56, cy - lineH * 0.5f, ValueSize, it.name, focused ? Text : mix(Text, Text2, 0.2f));
        c.text(f.regular, row.x + row.w * 0.56f, cy - lineH * 0.5f + 2, DescSize, items::pocketName(it.pocket), Text3);
        // amount pill with chevrons (TMs are ×1 only)
        std::string amt = "\xC3\x97" + u2s(p.amount(itemIndex));  // ×
        float aw = pillWidth(f, amt, ValueSize - 2, true, 16), ax = row.right() - 120 - aw * 0.5f;
        bool adjustable = it.cap > 1;
        if (adjustable && focused) drawChevron(c, ax - aw * 0.5f - 14, cy, 14, true, Accent);
        drawPill(c, f, ax, cy, amt, focused ? withAlpha(Accent, 36) : rgb(0x223650), focused ? Accent : Text2, ValueSize - 2, true, 16, 36, Align::Center);
        if (adjustable && focused) drawChevron(c, ax + aw * 0.5f + 14, cy, 14, false, Accent);
        c.text(f.regular, row.right() - 30, cy - lineH * 0.5f + 2, DescSize, u2s(it.cap), Text3, Align::Right);
    }
    // scrollbar
    drawScrollbar(c, Rect{list.right() + 14, list.y, 8, list.h}, int(vis.size()), p.first(), ListVisible, rgb(0x1E2F45), AccentDim);
    // alphabet strip (TMs: tens)
    float stripX = list.right() + 54;
    if (p.tab() == items::TabTMs) {
        int groups = (int(vis.size()) + 9) / 10;
        float gh = list.h / std::max(groups, 1);
        for (int g = 0; g < groups; g++) {
            bool on = p.cursor() / 10 == g;
            std::string label = u2s(unsigned(g * 10 + 1));
            float cy = list.y + gh * g + gh * 0.5f;
            if (on) c.fillRoundRect(Rect{stripX - 4, cy - 12, 44, 24}, 8, withAlpha(Accent, 40));
            c.text(f.bold, stripX + 18, cy - 9, SmallSize - 1, label, on ? Accent : Text3, Align::Center);
        }
    } else {
        std::string present = p.letters();
        char cur = p.currentLetter();
        float lh = list.h / 26.0f;
        for (int i = 0; i < 26; i++) {
            char ch = char('A' + i);
            bool has = present.find(ch) != std::string::npos, on = ch == cur;
            float cy = list.y + lh * i + lh * 0.5f;
            if (on) c.fillCircle(stripX + 18, cy, 12, Accent);
            c.text(f.bold, stripX + 18, cy - 9, SmallSize - 1, std::string(1, ch), on ? AccentInk : has ? Text2 : rgb(0x3A4B62), Align::Center);
        }
    }
    // status line
    float sy = list.bottom() + 22;
    Color statusColor = s.itemStatus.rfind("ADDED", 0) == 0 ? Accent : s.itemStatus.rfind("QUEUED", 0) == 0 ? Warn : s.itemStatus == "READY" ? Text2 : Err;
    drawBadge(c, f, list.x, sy + 12, s.itemStatus, statusColor);
    std::string note = s.itemsAdded ? u2s(s.itemsAdded) + " added this session  ·  save in the game to keep them" : "Open the satchel once in the game to enable adding";
    c.text(f.regular, list.x + f.bold.measure(s.itemStatus, SmallSize - 2) + 40, sy + 2, DescSize, note, Text3);
    c.text(f.regular, list.right(), sy + 2, DescSize, u2s(unsigned(vis.size())) + " items", Text3, Align::Right);
}

static void panel(Canvas& c, const Fonts& f, const State& s) {
    c.fillRect(Rect{0, 0, float(c.width()), float(c.height())}, Scrim);
    c.shadowRoundRect(kPanel, 26, 24, rgb(0x000000, 140));
    c.fillRoundRect(kPanel, 26, OverlayBg);
    c.strokeRoundRect(kPanel, 26, 1.5f, OverlayEdge);
    c.fillRoundRect(Rect{kPanel.x + 40, kPanel.y, kPanel.w - 80, 4}, 2, Accent);
    // header
    c.text(f.bold, kPanel.x + 40, kPanel.y + 26, SmallSize, "Z-A RANDOMIZER", Accent);
    c.text(f.bold, kPanel.x + 40, kPanel.y + 46, H1Size, s.tab == TabCheats ? "Cheats" : "Items", Text);
    tabs(c, f, s, Rect{kPanel.x + 420, kPanel.y + 42, kPanel.w - 460, 52});
    Rect body{kPanel.x + 40, kPanel.y + 122, kPanel.w - 80, kPanel.h - 122 - 92};
    if (s.tab == TabCheats) cheatsTab(c, f, s, body);
    else itemsTab(c, f, s, body);
    // footer
    float fy = kPanel.bottom() - 70;
    c.fillRect(Rect{kPanel.x + 40, fy - 10, kPanel.w - 80, 1}, OverlayEdge);
    std::vector<Hint> hints;
    if (s.tab == TabCheats)
        hints = {{PadGlyph::DpadUpDown, "Select"}, {PadGlyph::DpadLeftRight, "Change"}, {PadGlyph::Cross, "Apply"}, {PadGlyph::L1, "Tab"}, {PadGlyph::Circle, "Close"}, {PadGlyph::L3R3, "Toggle menu"}};
    else
        hints = {{PadGlyph::DpadUpDown, "Move"}, {PadGlyph::L2, "Page"}, {PadGlyph::Triangle, "Next letter"}, {PadGlyph::DpadLeftRight, "Amount"}, {PadGlyph::Square, "Favourite"}, {PadGlyph::Cross, "Add"}, {PadGlyph::Circle, "Close"}};
    drawHints(c, f, kPanel.x + 40, fy + 24, hints, Text2, Text, HintSize);
    std::string right = s.tab == TabCheats ? (s.cheats.settingsSaved ? "Settings saved for this run" : "Could not save - settings apply this session") : "Items follow the game's limits  ·  requests are never replayed";
    float lineH = f.regular.ascent(SmallSize) - f.regular.descent(SmallSize);
    c.text(f.regular, kPanel.right() - 40, fy + 24 - lineH * 0.5f, SmallSize, right, Text3, Align::Right);
}

void draw(Canvas& c, const Fonts& f, const State& s) {
    if (s.drawReadout) readout(c, f, s);
    if (s.open && s.drawPanel) panel(c, f, s);
    if (s.toastVisible && s.drawToast) drawToast(c, f, s.toast, c.width() * 0.5f, float(c.height()) - 36);
}

Rect toastRect(const Fonts& f, const Toast& t, int canvasW, int canvasH) {
    // (the geometry of ui_widgets drawToast, with its shadow margin)
    float px = 24, h = t.detail.empty() ? 64 : 84;
    float textW = std::max(f.bold.measure(t.text, px), t.detail.empty() ? 0.0f : f.regular.measure(t.detail, 18));
    float w = textW + 64 + 56;
    float cx = canvasW * 0.5f, bottomY = float(canvasH) - 36;
    return Rect{cx - w * 0.5f - 20, bottomY - h - 20, w + 40, h + 40};
}

// The toast alone, placed as drawToast would within a canvas of the toastRect size (the title's toast layer).
void drawToastOnly(Canvas& c, const Fonts& f, const Toast& t) {
    float h = t.detail.empty() ? 64 : 84;
    drawToast(c, f, t, c.width() * 0.5f, 20 + h);
}

Action press(State& s, items::Button b) {
    using B = items::Button;
    Action a;
    if (b == B::Circle) { s.open = false; a.kind = Action::Close; return a; }
    const int tabCount = 1 + items::TabCount;
    if (b == B::L1 || b == B::R1) {
        s.tab = (s.tab + (b == B::L1 ? -1 : 1) + tabCount) % tabCount;
        if (s.tab != TabCheats) s.picker.setTab(s.tab - TabItemsFirst);
        s.row = 0;
        return a;
    }
    if (s.tab != TabCheats) {
        items::Request req = s.picker.press(b);
        if (req.issued) { a.kind = Action::ItemRequest; a.index = req.index; a.amount = req.amount; }
        else if (b == B::Square && s.picker.current()) a.kind = Action::FavouritesChanged;
        return a;
    }
    const auto& rows = model::cheatRows();
    int n = int(rows.size());
    if (b == B::Up) { s.row = (s.row + n - 1) % n; return a; }
    if (b == B::Down) { s.row = (s.row + 1) % n; return a; }
    const model::RowDef& r = rows[size_t(std::clamp(s.row, 0, n - 1))];
    int dir = b == B::Left ? -1 : 1;
    CheatState& cs = s.cheats;
    if (b != B::Left && b != B::Right && b != B::Cross) return a;
    if (r.id == std::string("shiny")) { cs.shiny = (cs.shiny + 5 + dir) % 5; a.kind = Action::SettingsChanged; return a; }
    if (r.id == std::string("capture")) { cs.capture = (cs.capture + 5 + dir) % 5; a.kind = Action::SettingsChanged; return a; }
    if (r.id == std::string("fps_counter")) { cs.fpsCounter = !cs.fpsCounter; s.fpsCounter = cs.fpsCounter; a.kind = Action::SettingsChanged; return a; }
    if (r.id == std::string("money")) {
        if (!cs.moneyAvailable) return a;
        if (b == B::Cross) {
            static const unsigned amounts[4] = {0, 10000, 100000, 1000000};
            unsigned amount = amounts[std::clamp(cs.moneyChoice, 0, 3)];
            if (!amount) { a.kind = Action::MoneyCancel; return a; }
            a.kind = Action::MoneyQueue;
            a.amount = amount;
            return a;
        }
        cs.moneyChoice = (cs.moneyChoice + 4 + dir) % 4;
        a.kind = Action::MoneyCancel;  // changing the amount cancels a not-yet-consumed request (as before)
        return a;
    }
    if (r.id == std::string("fps_trial") && b == B::Cross) { a.kind = Action::FpsTrial; return a; }
    if (r.id == std::string("hebrew") && b == B::Cross) { a.kind = Action::Hebrew; return a; }
    if (r.id == std::string("reset") && b == B::Cross) { cs.shiny = cs.capture = 0; a.kind = Action::Reset; return a; }
    return a;
}

std::string simulate(State& s, const Action& a) {
    CheatState& cs = s.cheats;
    switch (a.kind) {
        case Action::None: case Action::Close: case Action::SettingsChanged: case Action::FavouritesChanged: return "";
        case Action::MoneyQueue:
            cs.moneyStatus = "QUEUED - SAVE IN GAME";
            return moneyValue(cs) + " queued - save in the game to apply";
        case Action::MoneyCancel:
            if (!cs.moneyStatus.empty()) { cs.moneyStatus.clear(); return "Money request cancelled"; }
            return "";
        case Action::FpsTrial:
            if (cs.fpsMode == -1) return "FPS is controlled by the config file";
            cs.fpsMode = cs.fpsMode == 1 ? 0 : 1;
            return cs.fpsMode == 1 ? "60 FPS trial started - returns to 30 automatically" : "Back to 30 FPS";
        case Action::Hebrew:
            if (cs.hebrewMode < 0) return "Hebrew pack not available";
            cs.hebrewMode = cs.hebrewMode ? 0 : 1;
            s.open = false;
            return cs.hebrewMode ? "Hebrew trial on - reloading the last save" : "Hebrew trial off - reloading the last save";
        case Action::Reset: return "Shiny and capture back to normal";
        case Action::ItemRequest: {
            const items::Item& it = items::catalog()[a.index];
            // The real build calls za_items_request(index, amount) here and reads za_items_status().
            s.picker.noteAdded(a.index);
            s.itemsAdded++;
            s.itemStatus = "QUEUED - OPEN BAG";
            return std::string(it.name) + " \xC3\x97" + std::to_string(a.amount) + " queued";
        }
    }
    return "";
}

}  // namespace ui::overlay
