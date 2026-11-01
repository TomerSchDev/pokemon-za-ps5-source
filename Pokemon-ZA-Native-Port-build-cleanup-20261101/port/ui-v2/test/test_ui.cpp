// ui-v2 host tests: model navigation, option availability, JSON round trip, the item picker's state machine, the
// rasterizer's blending and text metrics, render determinism and the PNG round trip. Usage: test_ui <fonts dir>
#include <chrono>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "items_picker.h"
#include "png_write.h"
#include "ui_canvas.h"
#include "ui_launcher.h"
#include "ui_model.h"
#include "ui_overlay.h"
#include "ui_widgets.h"

using namespace ui;

static int failures = 0;
#define CHECK(cond)                                                                        \
    do {                                                                                   \
        if (!(cond)) {                                                                     \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond);          \
            failures++;                                                                    \
        }                                                                                  \
    } while (0)

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

static void testModel() {
    using namespace model;
    const auto& pages = launcherPages();
    CHECK(pages.size() == 10);  // Play, Wild, Trainers, Species, Starter, Research, Music, Player, Cheat defaults, Saved runs
    // ids are unique across all pages; every Level/Toggle has a valid default; shipped rows have a shipped default
    std::vector<std::string> ids;
    for (const auto& p : pages)
        for (const auto& r : p.rows) {
            for (const auto& id : ids) CHECK(id != r.id);
            ids.push_back(r.id);
            if (r.kind == Kind::Level || r.kind == Kind::Toggle) {
                CHECK(!r.options.empty());
                CHECK(r.def >= 0 && r.def < int(r.options.size()));
                if (r.avail == Avail::Now) CHECK(r.options[size_t(r.def)].avail == Avail::Now);
                for (const auto& o : r.options) CHECK(std::strlen(o.desc) > 0);
            }
        }
    // today's defaults: wild/trainers fully random, megas, DLC, research on, music off, random starter
    Values v = defaults();
    CHECK(valueText(*findRow("wild_mode"), v) == "Fully random");
    CHECK(valueText(*findRow("trainers_mode"), v) == "Fully random");
    CHECK(v.get("mega_trainers") == 1 && v.get("dlc_rematches") == 1 && v.get("research_rewards") == 1);
    CHECK(v.get("music") == 0 && v.get("starter_mode") == 2);
    CHECK(summary(v) == "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Starter: Random by seed · Research: Randomized · Music: Off");
    // the title (allowPhase2 = false) can never select a phase-2 option; the mockups (true) can
    Nav nav{1, 0};
    Event e = handle(nav, v, Button::Right, false);  // Fully random -> next shipped option: Off (wraps past Chaos)
    CHECK(e.type == Event::Changed && v.get("wild_mode") == 0);
    e = handle(nav, v, Button::Left, false);
    CHECK(v.get("wild_mode") == 3);
    e = handle(nav, v, Button::Right, true);
    CHECK(v.get("wild_mode") == 4);  // Chaos is reachable in the design harness
    nav.row = 1;                      // wild_levels: a row with nothing shipped -> toast, no change
    e = handle(nav, v, Button::Right, false);
    CHECK(e.type == Event::Toast && v.get("wild_levels") == 0);
    // page switching wraps, Circle returns to Play
    nav = Nav{0, 0};
    handle(nav, v, Button::L1);
    CHECK(nav.page == pageCount() - 1);
    handle(nav, v, Button::R1);
    CHECK(nav.page == 0);
    nav.page = pageIndexOf("starter");
    e = handle(nav, v, Button::Circle);
    CHECK(e.type == Event::BackToPlay && nav.page == 0);
    // Play page actions
    nav = Nav{0, 0};
    CHECK(handle(nav, v, Button::Cross).type == Event::Continue);
    nav.row = 1;
    CHECK(handle(nav, v, Button::Cross).type == Event::StartNewRun);
    nav.row = 2;
    CHECK(handle(nav, v, Button::Cross).type == Event::OpenSeed);
    CHECK(handle(nav, v, Button::Triangle).type == Event::RandomSeed);
    nav.row = 3;
    CHECK(handle(nav, v, Button::Cross).type == Event::OpenSavedRuns);
    // starter pick follows the mode
    v.set("starter_mode", 1);
    v.set("starter_pick", 8);
    CHECK(valueText(*findRow("starter_pick"), v) == "Froakie");
    v.set("starter_mode", 2);
    CHECK(valueText(*findRow("starter_pick"), v) == "Decided by the seed");
    // JSON round trip keeps every value, stores option ids not indices
    v = defaults();
    v.set("wild_mode", 4);
    v.set("trainer_levels", 2);
    v.set("starter_mode", 1);
    v.set("starter_pick", 6);
    v.setText("player_name", "Tomer \"Z\"");
    std::string json = toJson(v);
    CHECK(json.find("\"wild_mode\": \"chaos\"") != std::string::npos);
    CHECK(json.find("\"starter_pick\": 650") != std::string::npos);
    CHECK(json.find("\"player_name\": \"Tomer \\\"Z\\\"\"") != std::string::npos);
    Values back;
    CHECK(fromJson(json, back));
    CHECK(back.get("wild_mode") == 4 && back.get("trainer_levels") == 2 && back.get("starter_pick") == 6);
    CHECK(back.text("player_name") == "Tomer \"Z\"");
    CHECK(toJson(back) == json);
    // unknown ids survive (an older binary must not drop a newer run's settings)
    Values unknown;
    CHECK(fromJson("{\"schema\": 2, \"values\": {\"future_row\": \"x\", \"wild_mode\": \"off\"}}", unknown));
    CHECK(unknown.text("future_row") == "x" && unknown.get("wild_mode") == 0);
    // the overlay's cheat rows
    CHECK(cheatRows().size() == 7);
}

static void testPicker() {
    using namespace items;
    const auto& cat = catalog();
    CHECK(cat.size() == 199);
    Picker p;
    CHECK(p.tab() == TabAll && p.visible().size() == 199);
    int counts[TabCount] = {0};
    for (const auto& it : cat) counts[tabOfPocket(it.pocket)]++;
    CHECK(counts[TabMedicine] == 2 && counts[TabBalls] == 2 && counts[TabOther] == 35 && counts[TabTMs] == 160);
    p.setTab(TabOther);
    CHECK(p.visible().size() == 35);
    CHECK(std::string(p.current()->name) == "HP Up");
    for (int k = 0; k < 5; k++) p.press(Button::Down);
    CHECK(std::string(p.current()->name) == "Rare Candy");
    // amount presets, capped by the item's cap; TMs stay x1
    unsigned rare = p.visible()[size_t(p.cursor())];
    CHECK(p.amount(rare) == 1);
    p.press(Button::Right);
    p.press(Button::Right);
    CHECK(p.amount(rare) == 99);
    p.press(Button::Right);
    CHECK(p.amount(rare) == 999);
    p.press(Button::Right);
    CHECK(p.amount(rare) == 1);  // wraps
    Request r = p.press(Button::Cross);
    CHECK(r.issued && r.index == rare && r.amount == 1);
    p.setTab(TabTMs);
    CHECK(p.visible().size() == 160);
    unsigned tm = p.visible()[0];
    p.press(Button::Right);
    CHECK(p.amount(tm) == 1 && p.amountIndex(tm) == 0);
    // page jumps clamp; letter jumps move to the next initial
    p.press(Button::R2);
    CHECK(p.cursor() == 10 && p.first() == 1);
    for (int k = 0; k < 40; k++) p.press(Button::R2);
    CHECK(p.cursor() == 159);
    p.press(Button::L2);
    CHECK(p.cursor() == 149);
    p.setTab(TabAll);
    CHECK(p.currentLetter() == 'M');  // Master Ball
    p.press(Button::Triangle);
    CHECK(p.currentLetter() == 'U');  // Ultra Ball
    p.press(Button::Triangle);
    CHECK(p.currentLetter() == 'F');  // Full Restore
    // favourites and recent
    p.press(Button::Square);
    CHECK(p.isFavourite(p.visible()[size_t(p.cursor())]));
    p.noteAdded(9);  // Rare Candy
    p.noteAdded(9);
    CHECK(p.recent().size() == 1 && p.recent()[0] == 9);
    p.setTab(TabFavourites);
    CHECK(p.visible().size() == 2);  // the favourite first, then the recent one
    CHECK(std::string(catalog()[p.visible()[0]].name) == "Full Restore");
    CHECK(std::string(catalog()[p.visible()[1]].name) == "Rare Candy");
    // persistence round trip
    std::string text = p.serialize();
    Picker q;
    CHECK(q.deserialize(text));
    CHECK(q.isFavourite(2) && q.recent().size() == 1 && q.recent()[0] == 9 && q.amount(rare) == 1);
    CHECK(q.serialize() == text);
    CHECK(!q.deserialize("garbage"));
    // repeat acceleration
    CHECK(repeatDelayMs(0) == 400 && repeatDelayMs(500) == 110 && repeatDelayMs(2000) == 45);
}

static void testOverlayLogic() {
    overlay::State s;
    CHECK(s.open && s.tab == overlay::TabCheats);
    overlay::press(s, items::Button::R1);
    CHECK(s.tab == 1 && s.picker.tab() == items::TabAll);
    overlay::press(s, items::Button::L1);
    overlay::press(s, items::Button::L1);
    CHECK(s.tab == overlay::TabItemsFirst + items::TabFavourites);
    overlay::press(s, items::Button::R1);
    CHECK(s.tab == overlay::TabCheats);
    // money: left/right pick, Cross queues, Normal cancels
    s.row = 2;
    overlay::press(s, items::Button::Right);
    CHECK(s.cheats.moneyChoice == 1);
    overlay::Action a = overlay::press(s, items::Button::Cross);
    CHECK(a.kind == overlay::Action::MoneyQueue && a.amount == 10000);
    std::string t = overlay::simulate(s, a);
    CHECK(t.find("queued") != std::string::npos && s.cheats.moneyStatus.rfind("QUEUED", 0) == 0);
    a = overlay::press(s, items::Button::Left);
    CHECK(a.kind == overlay::Action::MoneyCancel && s.cheats.moneyChoice == 0);
    overlay::simulate(s, a);
    CHECK(s.cheats.moneyStatus.empty());
    // Cross on an item queues it and names it in the toast
    overlay::press(s, items::Button::R1);
    s.picker.setTab(items::TabOther);
    for (int k = 0; k < 5; k++) overlay::press(s, items::Button::Down);
    overlay::press(s, items::Button::Right);
    overlay::press(s, items::Button::Right);
    a = overlay::press(s, items::Button::Cross);
    CHECK(a.kind == overlay::Action::ItemRequest && a.index == 9 && a.amount == 99);
    t = overlay::simulate(s, a);
    CHECK(t == "Rare Candy \xC3\x97" "99 queued");
    CHECK(s.itemsAdded == 1 && s.picker.recent().size() == 1);
    // Square marks a favourite and asks the title to persist it
    a = overlay::press(s, items::Button::Square);
    CHECK(a.kind == overlay::Action::FavouritesChanged && s.picker.isFavourite(9));
    // Circle closes
    a = overlay::press(s, items::Button::Circle);
    CHECK(a.kind == overlay::Action::Close && !s.open);
}

static void testCanvas(const Fonts& f) {
    Canvas c(64, 64);
    c.clear(rgb(0x000000));
    c.fillRect(Rect{8, 8, 16, 16}, rgb(0xFF0000));
    const uint8_t* p = c.data();
    auto px = [&](int x, int y) { return &p[(size_t(y) * 64 + x) * 4]; };
    CHECK(px(12, 12)[0] == 255 && px(12, 12)[1] == 0 && px(12, 12)[3] == 255);  // inside: exact colour
    CHECK(px(30, 30)[0] == 0);                                                    // outside: untouched
    CHECK(px(7, 12)[0] == 0 && px(24, 12)[0] == 0);                               // integer edges are crisp
    // translucent over opaque keeps alpha 255 and mixes the colour
    c.fillRect(Rect{8, 8, 16, 16}, rgb(0x0000FF, 128));
    CHECK(px(12, 12)[3] == 255 && px(12, 12)[2] > 100 && px(12, 12)[2] < 160 && px(12, 12)[0] > 100);
    // a transparent canvas holds premultiplied values and un-premultiplies on export
    Canvas t(8, 8);
    t.clear(Color{0, 0, 0, 0});
    t.fillRect(Rect{0, 0, 8, 8}, rgb(0xFFFFFF, 128));
    CHECK(t.data()[0] == 128 && t.data()[3] == 128);
    auto straight = t.toStraightRGBA();
    CHECK(straight[0] == 255 && straight[3] == 128);
    // text metrics
    CHECK(f.regular.ok() && f.bold.ok());
    float w1 = f.regular.measure("Rare Candy", 24), w2 = f.regular.measure("Rare Candy x99", 24);
    CHECK(w1 > 60 && w2 > w1);
    CHECK(f.bold.measure("Rare Candy", 24) > w1 * 0.95f);
    std::string fitted = f.regular.fit("A very long item name that cannot fit", 24, 120);
    CHECK(fitted.size() < 30 && fitted.find("\xE2\x80\xA6") != std::string::npos);
    CHECK(f.regular.fit("Short", 24, 500) == "Short");
    // glyphs actually land on the canvas
    Canvas g(200, 60);
    g.clear(rgb(0x000000));
    g.text(f.bold, 4, 4, 32, "Hello", rgb(0xFFFFFF));
    int lit = 0;
    for (size_t i = 0; i < g.bytes(); i += 4) lit += g.data()[i] > 128;
    CHECK(lit > 200 && lit < 4000);
}

static void testRenderDeterminism(const Fonts& f) {
    overlay::State s;
    s.tab = overlay::TabItemsFirst + items::TabOther;
    s.picker.setTab(items::TabOther);
    s.toastVisible = true;
    s.toast = {Toast::Ok, "Rare Candy ×99 added", ""};
    Canvas a(1920, 1080), b(1920, 1080);
    a.clear(Color{0, 0, 0, 0});
    b.clear(Color{0, 0, 0, 0});
    overlay::draw(a, f, s);
    overlay::draw(b, f, s);
    CHECK(std::memcmp(a.data(), b.data(), a.bytes()) == 0);
    // with the menu closed only the readout and the toast have pixels: the rest of the frame stays transparent
    overlay::State closed;
    closed.open = false;
    closed.fpsCounter = true;
    Canvas t(1920, 1080);
    t.clear(Color{0, 0, 0, 0});
    overlay::draw(t, f, closed);
    CHECK(t.data()[(size_t(540) * 1920 + 960) * 4 + 3] == 0);  // frame centre untouched
    CHECK(t.data()[(size_t(40) * 1920 + 1800) * 4 + 3] > 0);   // readout pill, top right
    // launcher renders fully opaque
    launcher::State ls;
    ls.seed = "123";
    Canvas l(1920, 1080);
    launcher::draw(l, f, ls);
    bool opaque = true;
    for (size_t i = 3; i < l.bytes(); i += 4 * 997) opaque &= l.data()[i] == 255;
    CHECK(opaque);
    // PNG round trip
    auto rgba = a.toStraightRGBA();
    auto png = encodePng(rgba.data(), 1920, 1080);
    CHECK(png.size() > 1000);
    std::string tmp = "/tmp/ui-v2-roundtrip.png";
    CHECK(writePng(tmp, rgba.data(), 1920, 1080));
    std::vector<uint8_t> back;
    int w = 0, h = 0;
    CHECK(readPngRGBA(tmp, back, w, h));
    CHECK(w == 1920 && h == 1080 && back == rgba);
    std::remove(tmp.c_str());
}

int main(int argc, char** argv) {
    if (argc != 2) {
        std::fprintf(stderr, "usage: test_ui <fonts dir>\n");
        return 2;
    }
    std::string fontsDir = argv[1];
    auto regular = readFile(fontsDir + "/NotoSans-Regular-latin.ttf"), bold = readFile(fontsDir + "/NotoSans-Bold-latin.ttf");
    Fonts f;
    if (!f.regular.load(regular.data(), regular.size()) || !f.bold.load(bold.data(), bold.size())) {
        std::fprintf(stderr, "fonts not found in %s\n", fontsDir.c_str());
        return 2;
    }
    testModel();
    testPicker();
    testOverlayLogic();
    testCanvas(f);
    testRenderDeterminism(f);
    {   // CPU cost of a full redraw on this host (informative; the title redraws only on input)
        launcher::State ls;
        ls.seed = "2315984632";
        overlay::State os;
        os.tab = overlay::TabItemsFirst + items::TabOther;
        os.picker.setTab(items::TabOther);
        Canvas l(1920, 1080), o(1920, 1080);
        auto bench = [&](const char* name, auto&& fn) {
            fn();  // warm the glyph cache first
            auto t0 = std::chrono::steady_clock::now();
            for (int i = 0; i < 5; i++) fn();
            double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count() / 5.0;
            std::printf("redraw %-28s %.1f ms (glyph cache warm)\n", name, ms);
        };
        bench("launcher settings page", [&] { launcher::draw(l, f, ls); });
        bench("overlay items tab", [&] { o.clear(Color{0, 0, 0, 0}); overlay::draw(o, f, os); });
        os.open = false;
        bench("overlay closed (readout only)", [&] { o.clear(Color{0, 0, 0, 0}); overlay::draw(o, f, os); });
    }
    if (failures) {
        std::fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    std::puts("PASS: model (9 pages, availability, JSON round trip), picker (tabs, amounts, jumps, favourites, persistence), "
              "overlay input, canvas blending/text, deterministic render, PNG round trip");
    return 0;
}
