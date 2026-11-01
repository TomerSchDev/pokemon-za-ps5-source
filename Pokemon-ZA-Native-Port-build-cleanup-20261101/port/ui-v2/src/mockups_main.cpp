// ui-v2 mockups: every PNG in port/ui-v2/mockups is rendered by the real rasterizer (ui_canvas), the real menu model
// (ui_model) and the real screen code (ui_launcher / ui_overlay) on the host. The "current-*" images come from copies
// of the existing drawing code (legacy_look). Usage: mockups <fonts dir> <out dir>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "items_picker.h"
#include "legacy_look.h"
#include "png_write.h"
#include "ui_canvas.h"
#include "ui_launcher.h"
#include "ui_model.h"
#include "ui_overlay.h"
#include "ui_theme.h"
#include "ui_widgets.h"

using namespace ui;

static std::vector<uint8_t> readFile(const std::string& path) {
    std::vector<uint8_t> out;
    FILE* f = std::fopen(path.c_str(), "rb");
    if (!f) return out;
    uint8_t buf[65536];
    size_t n;
    while ((n = std::fread(buf, 1, sizeof buf, f)) > 0) out.insert(out.end(), buf, buf + n);
    std::fclose(f);
    return out;
}

static bool save(const Canvas& c, const std::string& path) {
    auto rgba = c.toStraightRGBA();
    bool ok = writePng(path, rgba.data(), c.width(), c.height());
    std::printf("%s %s (%dx%d)\n", ok ? "wrote" : "FAILED", path.c_str(), c.width(), c.height());
    return ok;
}

// A stand-in for a game frame (no game content leaves the console): sky, a city silhouette, ground and a HUD-like
// corner, enough to show the overlay's translucency and contrast.
static void syntheticGame(Canvas& c) {
    c.fillRoundRectGradient(Rect{0, 0, 1920, 1080}, 0, rgb(0x7FB4E6), rgb(0xDCE9F2));
    c.fillRoundRectGradient(Rect{0, 560, 1920, 520}, 0, rgb(0x6F9B5C), rgb(0x3E5D3A));
    // distant buildings
    unsigned seed = 12345;
    for (int i = 0; i < 46; i++) {
        seed = seed * 1103515245u + 12345u;
        float x = i * 42.0f - 10, h = 120 + float((seed >> 16) % 220), w = 34 + float((seed >> 8) % 30);
        c.fillRect(Rect{x, 560 - h, w, h + 10}, mix(rgb(0x5C6F8E), rgb(0x8A9BB8), float((seed >> 20) % 100) / 100.0f));
    }
    // a tower
    c.fillRect(Rect{1240, 180, 40, 400}, rgb(0x4A5A78));
    c.fillTriangle(1260, 120, 1232, 200, 1288, 200, rgb(0x4A5A78));
    // soft lights
    for (int i = 0; i < 12; i++) {
        seed = seed * 1103515245u + 12345u;
        c.fillCircle(float((seed >> 8) % 1920), 600 + float((seed >> 20) % 400), 40 + float(i * 7), rgb(0xFFF2B0, 40));
    }
    // HUD corner (minimap-like) and a party strip
    c.fillCircle(170, 900, 120, rgb(0x0B1524, 150));
    c.strokeCircle(170, 900, 120, 4, rgb(0xFFFFFF, 160));
    for (int i = 0; i < 3; i++) c.fillRoundRect(Rect{1700, 760 + i * 80.0f, 180, 64}, 16, rgb(0x0B1524, 140));
}

static std::vector<launcher::RunCard> sampleRuns() {
    // The summaries are what model::summary() produces for those settings.
    return {{"r000000006ae46953-8efd14d1", "2315984632", "Tepig", "Tomer", "30 Oct 2026", "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Research: Randomized · Music: Off", true},
            {"r000000006ae35da8-c4c60589", "9376797808", "Pikachu", "Tomer", "29 Oct 2026", "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Research: Randomized · Music: Shuffle by category"},
            {"r000000006ae2a1f0-1b7c0e22", "6177047620", "Greavard", "Tomer", "28 Oct 2026", "Wild: Fully random · Trainers: Off · Megas: Random Mega · Research: Original · Music: Off"},
            {"r000000006ae11048-9b864a3e", "30081997", "Chingling", "Trainer", "27 Oct 2026", "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Music: Off"},
            {"r000000006ae10d06-5a983292", "4031C916F62655AE", "Gengar", "Trainer", "27 Oct 2026", "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Music: Off"},
            {"r000000006ae0f7c2-77d2a0b1", "12345", "Chikorita", "Trainer", "26 Oct 2026", "Wild: Off · Trainers: Off · Starter: Vanilla choice · Music: Off"}};
}

static launcher::State baseLauncher() {
    launcher::State s;
    s.seed = "2315984632";
    s.runs = sampleRuns();
    s.activeRun = 0;
    s.recentSeeds = {"9376797808", "6177047620", "30081997"};
    s.values.setText("player_name", "Tomer");
    s.buildLabel = "ui-v2 design";
    return s;
}

static int pageIndex(const char* id) {
    const auto& pages = model::launcherPages();
    for (size_t i = 0; i < pages.size(); i++)
        if (!std::strcmp(pages[i].id, id)) return int(i);
    return 0;
}

static void caption(Canvas& c, const Fonts& f, Rect r, const std::string& text, Color color) {
    c.textInRect(f.bold, r, 22, f.bold.fit(text, 22, r.w - 16), color, Align::Center);
}

static void sideBySide(Canvas& out, const Fonts& f, const Canvas& left, const Canvas& right, const std::string& leftLabel, const std::string& rightLabel) {
    out.clear(rgb(0x05090F));
    Canvas l(944, 531), r(944, 531);
    l.drawScaled(left);
    r.drawScaled(right);
    const int top = 290;
    out.blit(l, 10, top);
    out.blit(r, 966, top);
    out.strokeRoundRect(Rect{10, float(top), 944, 531}, 0, 1, theme::PanelEdge);
    out.strokeRoundRect(Rect{966, float(top), 944, 531}, 0, 1, theme::PanelEdge);
    caption(out, f, Rect{10, float(top) - 56, 944, 44}, leftLabel, theme::Warn);
    caption(out, f, Rect{966, float(top) - 56, 944, 44}, rightLabel, theme::Accent);
    out.text(f.regular, 960, float(top) + 531 + 36, 20,
             "Both images are rendered on the host at 1920x1080: the left by a copy of the current drawing code, the right by the ui-v2 rasterizer.",
             theme::Text2, Align::Center);
}

int main(int argc, char** argv) {
    if (argc != 3) {
        std::fprintf(stderr, "usage: mockups <fonts dir> <out dir>\n");
        return 2;
    }
    std::string fontsDir = argv[1], out = argv[2];
    auto regular = readFile(fontsDir + "/NotoSans-Regular-latin.ttf"), bold = readFile(fontsDir + "/NotoSans-Bold-latin.ttf");
    Fonts f;
    if (!f.regular.load(regular.data(), regular.size()) || !f.bold.load(bold.data(), bold.size())) {
        std::fprintf(stderr, "fonts not found in %s\n", fontsDir.c_str());
        return 2;
    }
    bool ok = true;
    Canvas c(1920, 1080);

    // ---- launcher
    {
        launcher::State s = baseLauncher();
        s.nav.row = 1;
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-play.png");
    }
    {
        launcher::State s = baseLauncher();
        s.nav.page = pageIndex("wild");
        s.nav.row = 0;
        s.values.set("wild_mode", 1);  // Shuffle zones (phase-2 generator work: the row shows the badge)
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-wild.png");
    }
    {
        launcher::State s = baseLauncher();
        s.nav.page = pageIndex("trainers");
        s.nav.row = 0;
        s.values.set("trainers_mode", 2);  // Random species of similar strength
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-trainers.png");
    }
    {
        launcher::State s = baseLauncher();
        s.nav.page = pageIndex("starter");
        s.nav.row = 1;
        s.values.set("starter_mode", 1);  // Any starter
        s.values.set("starter_pick", 8);  // Froakie
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-starter.png");
    }
    {
        launcher::State s = baseLauncher();
        s.screen = launcher::Screen::Seed;
        s.seedInput = "4031";
        s.keypad = 4;
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-seed.png");
    }
    {
        launcher::State s = baseLauncher();
        s.nav.page = pageIndex("saved");
        s.runIndex = 1;
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-saved-runs.png");
    }
    {
        launcher::State s = baseLauncher();
        s.screen = launcher::Screen::Confirm;
        s.values.set("music", 1);
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-confirm.png");
    }
    {
        launcher::State s = baseLauncher();
        s.screen = launcher::Screen::Generating;
        s.genStage = 2;
        s.genDone = 611;
        s.genTotal = 1700;
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-generating.png");
    }
    {
        launcher::State s = baseLauncher();
        s.nav.page = pageIndex("music");
        s.toastVisible = true;
        s.toast = {Toast::Info, "Music reset to defaults", ""};
        launcher::draw(c, f, s);
        ok &= save(c, out + "/launcher-music-toast.png");
    }

    // ---- overlay over a synthetic game frame
    Canvas game(1920, 1080);
    syntheticGame(game);
    auto composite = [&](const overlay::State& s, const std::string& path) {
        Canvas layer(1920, 1080);
        layer.clear(Color{0, 0, 0, 0});
        overlay::draw(layer, f, s);
        c.blit(game, 0, 0);
        c.blit(layer, 0, 0);
        return save(c, path);
    };
    {
        overlay::State s;
        s.row = 2;
        s.cheats.moneyChoice = 2;
        s.cheats.moneyStatus = "QUEUED - SAVE IN GAME";
        s.cheats.capture = 1;
        ok &= composite(s, out + "/overlay-cheats.png");
    }
    {
        overlay::State s;
        s.tab = overlay::TabItemsFirst + items::TabOther;
        s.picker.setTab(items::TabOther);
        // favourites and a recent addition
        for (int k = 0; k < 5; k++) s.picker.press(items::Button::Down);  // Rare Candy is the 6th "Other" item
        s.picker.press(items::Button::Square);                             // favourite it
        s.picker.press(items::Button::Right);
        s.picker.press(items::Button::Right);                              // ×99
        s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Square);                             // another favourite
        s.picker.press(items::Button::Up);
        s.picker.press(items::Button::Up);
        s.picker.noteAdded(9);
        s.itemsAdded = 2;
        s.itemStatus = "QUEUED - OPEN BAG";
        s.toastVisible = true;
        s.toast = {Toast::Ok, "Rare Candy ×99 queued", "Open the satchel in the game to add it"};
        ok &= composite(s, out + "/overlay-items.png");
    }
    {
        overlay::State s;
        s.tab = overlay::TabItemsFirst + items::TabTMs;
        s.picker.setTab(items::TabTMs);
        for (int k = 0; k < 3; k++) s.picker.press(items::Button::R2);
        s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Down);
        s.itemStatus = "ADDED";
        s.itemsAdded = 3;
        ok &= composite(s, out + "/overlay-items-tms.png");
    }
    {
        overlay::State s;
        s.tab = overlay::TabItemsFirst + items::TabFavourites;
        s.picker.setTab(items::TabAll);
        s.picker.press(items::Button::Square);  // Master Ball favourite
        s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Square);  // Full Restore favourite
        s.picker.noteAdded(9);
        s.picker.noteAdded(13);
        s.picker.setTab(items::TabFavourites);
        s.itemStatus = "READY";
        s.itemsAdded = 4;
        ok &= composite(s, out + "/overlay-items-favourites.png");
    }
    {
        overlay::State s;
        s.open = false;
        s.toastVisible = true;
        s.toast = {Toast::Ok, "Rare Candy ×99 added", "Save in the game to keep it"};
        ok &= composite(s, out + "/overlay-closed-toast.png");
    }

    // ---- the current look, rendered by copies of the real code, and the comparisons
    Canvas cur(1920, 1080);
    legacy::launcherMain(cur);
    ok &= save(cur, out + "/current-launcher-main.png");
    {
        launcher::State s = baseLauncher();
        s.nav.row = 1;
        launcher::draw(c, f, s);
        Canvas cmp(1920, 1080);
        sideBySide(cmp, f, cur, c, "CURRENT  ·  1280x720 canvas, 5x7 bitmap font, scaled 3/2", "UI-V2  ·  1920x1080, Noto Sans, anti-aliased, pages with descriptions");
        ok &= save(cmp, out + "/compare-launcher.png");
    }
    legacy::launcherSeed(cur);
    ok &= save(cur, out + "/current-launcher-seed.png");
    legacy::launcherSaved(cur);
    ok &= save(cur, out + "/current-launcher-saved-runs.png");
    legacy::overlayPage1(cur, game);
    ok &= save(cur, out + "/current-overlay-cheats.png");
    {
        overlay::State s;
        s.row = 2;
        s.cheats.moneyChoice = 2;
        s.cheats.moneyStatus = "QUEUED - SAVE IN GAME";
        Canvas layer(1920, 1080);
        layer.clear(Color{0, 0, 0, 0});
        overlay::draw(layer, f, s);
        c.blit(game, 0, 0);
        c.blit(layer, 0, 0);
        Canvas cmp(1920, 1080);
        sideBySide(cmp, f, cur, c, "CURRENT  ·  vkCmdClearAttachments rectangles, no alpha, 5x7 font", "UI-V2  ·  translucent panel, tabs, descriptions, state badges");
        ok &= save(cmp, out + "/compare-overlay-cheats.png");
    }
    legacy::overlayPage2(cur, game);
    ok &= save(cur, out + "/current-overlay-items.png");
    {
        overlay::State s;
        s.tab = overlay::TabItemsFirst + items::TabOther;
        s.picker.setTab(items::TabOther);
        for (int k = 0; k < 5; k++) s.picker.press(items::Button::Down);
        s.picker.press(items::Button::Right);
        s.picker.press(items::Button::Right);
        Canvas layer(1920, 1080);
        layer.clear(Color{0, 0, 0, 0});
        overlay::draw(layer, f, s);
        c.blit(game, 0, 0);
        c.blit(layer, 0, 0);
        Canvas cmp(1920, 1080);
        sideBySide(cmp, f, cur, c, "CURRENT  ·  ITEM 10/199, one item at a time with left/right", "UI-V2  ·  pocket tabs, 10-row list, scrollbar, letter strip, amount per row");
        ok &= save(cmp, out + "/compare-overlay-items.png");
    }
    return ok ? 0 : 1;
}
