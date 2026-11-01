// Isolated C++17 test: link ui_model.cpp + settings_codes.cpp, no game/crypto/JSON dependencies.
// Fixed codes below were calculated independently with Python hashlib.sha256 over the
// byte protocol documented in settings_codes.h, not copied from this C++ implementation.
#include "settings_codes.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <set>
#include <string>

namespace {
#include "settings_words.inc"
}

using ui::codes::SettingsCodes;
using ui::model::Values;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); failures++; } } while (0)

static std::array<std::string, 8> fields(const SettingsCodes& c) {
    return {c.wild, c.trainers, c.starter, c.research, c.music, c.player, c.cheats, c.overall};
}
static bool same(const SettingsCodes& a, const SettingsCodes& b) { return fields(a) == fields(b); }
static void option(Values& v, const char* rowId, const char* optionId) {
    const auto* row = ui::model::findRow(rowId);
    CHECK(row != nullptr);
    if (!row) return;
    for (size_t i = 0; i < row->options.size(); i++) if (std::string(row->options[i].id) == optionId) {
        v.set(rowId, int(i)); return;
    }
    CHECK(false);
}
static void onlyCategory(const SettingsCodes& before, const Values& values, size_t category) {
    const auto after = fields(ui::codes::compute(values));
    const auto prior = fields(before);
    for (size_t i = 0; i < 7; i++) CHECK((after[i] != prior[i]) == (i == category));
    CHECK(after[7] != prior[7]);
}

int main() {
    using namespace ui::codes;
    const Values defaults = ui::model::defaults();
    const auto base = compute(defaults);
    const std::array<std::string, 8> expected = {
        "Birch-Creek-Spring-Nut", "Sloth-Flag-Stream-Creek", "Snail-Date-Chair-Corn", "Clock-Seal-Owl-Gold",
        "Brush-Tent-Bright-Basket", "Grape-Lion-Rock-Lake", "Sweet-Berry-Nest-Thorn", "Reed-Spark-Thorn-Dove"};
    CHECK(fields(base) == expected);
    CHECK(same(base, compute(Values{})));  // absent values resolve to the real explicit defaults
    CHECK(configurationCode(defaults) == base.overall);

    Values v = defaults;
    option(v, "wild_levels", "plus10");
    CHECK(categoryCode("wild", v) == "Sweet-Cocoa-Button-Tree");
    onlyCategory(base, v, 0);
    v = defaults; option(v, "mega_trainers", "off"); onlyCategory(base, v, 1);
    v = defaults; option(v, "starter_mode", "any"); v.set("starter_pick", 8); onlyCategory(base, v, 2);
    v = defaults; option(v, "research_rewards", "off"); onlyCategory(base, v, 3);
    v = defaults; option(v, "music", "category"); onlyCategory(base, v, 4);
    v = defaults; v.setText("player_name", "Tomer"); onlyCategory(base, v, 5);
    CHECK(compute(v).player == "Wolf-Trout-Fox-Bear");
    v.setText("player_name", "tomer");
    CHECK(compute(v).player != "Wolf-Trout-Fox-Bear");  // exact case changes the save's trainer name
    v = defaults; option(v, "shiny_default", "always"); onlyCategory(base, v, 6);

    v = defaults;
    v.set("starter_pick", 8);
    CHECK(same(base, compute(v)));  // hidden previous partner has no effect in Random mode
    v.set("seed", 12345); v.setText("seed", "987654321");
    v.set("future_unused_option", 42); v.setText("unrecognized_display_label", "New translation");
    CHECK(same(base, compute(v)));

    // Reverse insertion order and unknown imported fields cannot change the projection.
    Values reversed;
    for (auto i = defaults.ints.rbegin(); i != defaults.ints.rend(); ++i) reversed.set(i->first, i->second);
    for (auto i = defaults.texts.rbegin(); i != defaults.texts.rend(); ++i) reversed.setText(i->first, i->second);
    CHECK(same(base, compute(reversed)));
    Values imported;
    CHECK(ui::model::fromJson("{\"schema\":2,\"values\":{\"player_name\":\"Trainer\",\"future_key\":\"unused\",\"alpha_rate\":\"vanilla\",\"wild_mode\":\"random\"}}", imported));
    CHECK(same(base, compute(imported)));

    // Versions belong to the digest domain; a cosmetic UI revision is deliberately absent.
    CHECK(configurationCode(defaults, "za202-randomizer-alpha1") == "Still-Red-Earth-Creek");
    CHECK(compute(defaults, CurrentAlgorithm, "different-game-build").overall != base.overall);
    CHECK(compute(defaults, "").overall.empty());
    CHECK(compute(defaults, CurrentAlgorithm, "").overall.empty());
    CHECK(categoryCode("not-a-category", defaults).empty());

    // Independent multi-block SHA vector: 1108 canonical bytes, including a 600-byte
    // exact player string and a 208-byte algorithm ID (deliberately beyond UI limits).
    v = defaults;
    std::string longName;
    for (int i = 0; i < 100; i++) longName += "Abc123";
    v.setText("player_name", longName);
    CHECK(categoryCode("player", v, "za-long-" + std::string(200, 'x')) == "Flag-Mirror-Cap-Earth");

    const std::array<const char*, 7> pages = {"wild", "trainers", "starter", "research", "music", "player", "cheats"};
    for (size_t i = 0; i < pages.size(); i++) CHECK(forPage(base, pages[i]) == expected[i]);
    CHECK(forPage(base, "play") == base.overall && forPage(base, "saved") == base.overall);
    CHECK(forPage(base, "unknown").empty());
    std::set<std::string> words;
    CHECK(sizeof kComparisonWords / sizeof kComparisonWords[0] == 256);
    for (const char* word : kComparisonWords) {
        const std::string text(word);
        CHECK(text.size() >= 3 && text.size() <= 7);
        CHECK(text[0] >= 'A' && text[0] <= 'Z');
        for (size_t i = 1; i < text.size(); i++) CHECK(text[i] >= 'a' && text[i] <= 'z');
        words.insert(text);
    }
    CHECK(words.size() == 256);
    CHECK(std::string(Schema) == "za-settings-words-1");
    CHECK(std::string(WordBankSha256) == "863995c9b345bbe185bac7b65d8de61f4df09aad5b65d4ff62bb0e296d8c9c60");
    for (const auto& code : fields(base)) {
        CHECK(code.size() >= 15 && code.size() <= 31);
        CHECK(std::count(code.begin(), code.end(), '-') == 3);
        size_t begin = 0;
        for (int i = 0; i < 4; i++) {
            const size_t end = code.find('-', begin);
            CHECK(words.count(code.substr(begin, end == std::string::npos ? end : end - begin)) == 1);
            begin = end == std::string::npos ? code.size() : end + 1;
        }
    }
    if (!failures) std::puts("settings words: 256 unique words, pinned bank hash, 12 independent hashlib vectors, category isolation, defaults, ordering, unknown keys, seed exclusion and version domains passed");
    return failures ? 1 : 0;
}
