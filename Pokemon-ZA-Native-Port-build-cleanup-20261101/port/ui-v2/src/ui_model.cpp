#include "ui_model.h"

#include <algorithm>
#include <cstdio>
#include <cstring>

namespace ui::model {

// --------------------------------------------------------------------------------------------- the pages (data)
// Wording follows the SMO Randomizer mod's settings pages: a value in plain words and one sentence that says what
// the run will actually do. Avail::Phase2 marks options the generator (port/randomizer/core) does not write yet.

const std::vector<PageDef>& launcherPages() {
    static const std::vector<PageDef> pages = {
        {"play", "Play", "Continue a run or start a new one with the settings on the other pages.", {
            {"continue", "Continue current run", "{run}", Kind::Action},
            {"new_run", "Start a new run", "Builds the randomized tables and a separate save for the seed below.", Kind::Action},
            {"seed", "Seed", "The number that decides everything this run randomizes. Share it to replay the same run.", Kind::Link},
            {"saved", "Saved runs", "Every run keeps its own save and settings. Pick one to continue it.", Kind::Link},
        }},
        {"wild", "Wild Pokémon", "What appears in the wild zones. The early Rock route is kept beatable unless Chaos is chosen.", {
            {"wild_mode", "Wild Pokémon", "", Kind::Level, {
                {"off", "Off", "Wild Pokémon are the original ones."},
                {"zones", "Shuffle zones", "Whole wild zones trade their Pokémon: zone 1's species appear in zone 10 and so on. Levels stay with the zone.", Avail::Phase2},
                {"in_zone", "Shuffle within zone", "Each zone keeps its own species, mixed among its spawn slots.", Avail::Phase2},
                {"random", "Fully random", "Any species can appear anywhere. The early Rock route stays beatable."},
                {"chaos", "Chaos", "Fully random, with random forms and wild Megas and no early-route protection. The seed may not be beatable.", Avail::Phase2},
            }, 0, 0, 1, 3, "", Avail::Now, "Wild"},
            {"wild_levels", "Wild levels", "", Kind::Level, {
                {"vanilla", "Vanilla", "Levels as in the original game."},
                {"plus10", "+10 %", "Every wild level raised by a tenth."},
                {"plus25", "+25 %", "Every wild level raised by a quarter."},
                {"range", "Random range", "Each slot draws a level from a range around the original."},
                {"mixed", "Mixed between zones", "Each zone takes another zone's level range."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Levels"},
            {"wild_mega_rate", "Wild Mega rate", "", Kind::Level, {
                {"vanilla", "Vanilla", "Wild Megas appear where the game places them."},
                {"x2", "×2", "Twice as many Mega-capable slots spawn as Megas."},
                {"x5", "×5", "Five times as many Mega-capable slots spawn as Megas."},
                {"all", "Every Mega slot", "Every Mega-capable slot spawns as a Mega."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Megas"},
            {"alpha_rate", "Alpha rate", "", Kind::Level, {
                {"vanilla", "Vanilla", "Alpha chance as in the original spawn tables."},
                {"x2", "×2", "Twice the Alpha chance in every spawn slot."},
                {"x5", "×5", "Five times the Alpha chance in every spawn slot."},
                {"always", "Always", "Every slot that can be an Alpha is one."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Alpha"},
            {"held_items", "Held items", "", Kind::Level, {
                {"vanilla", "Vanilla", "Wild Pokémon hold what they hold in the original game."},
                {"random", "Random", "A random held item that exists in Z-A."},
                {"none", "None", "No wild Pokémon holds an item."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Items"},
            {"forms", "Forms", "", Kind::Level, {
                {"vanilla", "Vanilla", "Species keep their original forms."},
                {"random", "Random form", "Species with several forms get a random one."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Forms"},
        }},
        {"trainers", "Trainers", "Who you battle and what they bring.", {
            {"trainers_mode", "Trainer teams", "", Kind::Level, {
                {"off", "Off", "Trainer teams are the original ones."},
                {"swap", "Swap teams between trainers", "Every trainer keeps a whole team, but it comes from another trainer of similar level.", Avail::Phase2},
                {"strength", "Random species of similar strength", "Each team member becomes a random species with similar base stats, at the same level.", Avail::Phase2},
                {"random", "Fully random", "Any species, with the moves it learns by that level."},
            }, 0, 0, 1, 3, "", Avail::Now, "Trainers"},
            {"mega_trainers", "Mega trainers", "", Kind::Toggle, {
                {"off", "Off", "Mega-evolving trainers keep their original Mega."},
                {"on", "Random Mega", "Mega-evolving trainers get a random Mega-capable Pokémon with the matching stone."},
            }, 0, 0, 1, 1, "", Avail::Now, "Megas"},
            {"dlc_rematches", "Mega Dimension rematches", "", Kind::Toggle, {
                {"off", "Off", "Rematch bosses stay where they are."},
                {"on", "Shuffle", "Mega Dimension rematch bosses trade places with each other."},
            }, 0, 0, 1, 1, "", Avail::Now, "DLC rematches"},
            {"trainer_levels", "Trainer levels", "", Kind::Level, {
                {"vanilla", "Vanilla", "Trainer levels as in the original game."},
                {"plus10", "+10 %", "A harder run: every trainer Pokémon is a tenth higher."},
                {"plus20", "+20 %", "Every trainer Pokémon is a fifth higher."},
                {"plus30", "+30 %", "Every trainer Pokémon is almost a third higher."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Levels"},
            {"trainer_moves", "Trainer moves", "", Kind::Level, {
                {"learnset", "Learnset", "Moves the species learns by that level (today's behaviour)."},
                {"legal", "Random legal", "Random moves the species can learn."},
                {"any", "Any move", "Any implemented move. Battles can be much harder than intended."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Moves"},
            {"trainer_items", "Held items", "", Kind::Level, {
                {"vanilla", "Vanilla", "Trainer Pokémon hold their original items; Mega stones follow the Mega."},
                {"random", "Random", "A random held item that exists in Z-A."},
                {"none", "None", "No trainer Pokémon holds an item."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Items"},
        }},
        // (appended 31.10: the generator's proposed_options in port/rando-v3/capabilities.json; ids as proposed there)
        {"species", "Species", "Numbers behind every Pokémon. Applies to wild and trainer Pokémon alike.", {
            {"base_stats", "Base stats", "", Kind::Level, {
                {"vanilla", "Vanilla", "Every species keeps its original base stats."},
                {"shuffle", "Shuffle", "Each species' six base stats are shuffled among themselves; the total stays."},
                {"random", "Random", "Each species gets random base stats with a similar total."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Stats"},
            {"catch_rate", "Catch rate", "", Kind::Level, {
                {"vanilla", "Vanilla", "The original catch rate of every species."},
                {"x2", "×2", "Every species is twice as easy to catch."},
                {"max", "Max", "Every species has the maximum catch rate."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Catch rate"},
        }},
        {"starter", "Starter", "Your partner at level 7 in Lumiose City.", {
            {"starter_mode", "Starter", "", Kind::Level, {
                {"vanilla", "Vanilla choice", "One of the three partners the game offers: Chikorita, Tepig or Totodile."},
                {"any", "Any starter", "Pick from the Kanto and Kalos starters as well as the three partners."},
                {"random", "Random by seed", "The seed picks one of the 343 validated species. The partner is a surprise."},
            }, 0, 0, 1, 2, "", Avail::Now, "Starter"},
            {"starter_pick", "Partner", "Left and right choose; the run starts with it at level 7.", Kind::Pick, {}, 0, 0, 1, 0, "", Avail::Now, "", "starter_mode"},
            {"starter_level", "Starter level", "Fixed by the starting save for now.", Kind::Number, {}, 5, 50, 1, 7, "", Avail::Phase2},
        }},
        {"research", "Research rewards", "What the research levels hand out.", {
            {"research_rewards", "Research rewards", "", Kind::Toggle, {
                {"off", "Original", "Research level rewards as in the original game."},
                {"on", "Randomized", "Levels 2–49 get 48 distinct items from a 490-item pool; the research TMs stay protected."},
            }, 0, 0, 1, 1, "", Avail::Now, "Research"},
            {"research_requirements", "Research requirements", "", Kind::Level, {
                {"vanilla", "Vanilla", "Research points needed for each level as in the original game."},
                {"easier", "Easier", "Fewer points for every level."},
                {"harder", "Harder", "More points for every level."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Requirements"},
        }},
        {"music", "Music", "Background music of the run, from the game's own BGM bank.", {
            {"music", "Music", "", Kind::Level, {
                {"off", "Off", "The original soundtrack."},
                {"category", "Shuffle by category", "Town, zone, battle and boss songs are shuffled within their category."},
                {"chaos", "Chaos", "Any of the 64 song units can play anywhere. Story scenes and jingles keep their music."},
            }, 0, 0, 1, 0, "", Avail::Now, "Music"},
        }},
        {"player", "Player", "The trainer of a new run.", {
            {"player_name", "Trainer name", "Shown in the game exactly as typed, up to 12 characters. New runs only.", Kind::Text},
            {"starting_money", "Starting money", "", Kind::Level, {
                {"vanilla", "3,000", "The original starting money."},
                {"m50k", "50,000", "A comfortable start."},
                {"m500k", "500,000", "Shopping is never a problem."},
                {"max", "9,999,999", "The game's maximum."},
            }, 0, 0, 1, 0, "", Avail::Phase2, "Money"},
        }},
        // The cheat defaults are written by the LAUNCHER itself into the new run's cheats.txt (not by the generator):
        // shipped in this build whatever capabilities.json says about them (see cheatDefaultsRow).
        {"cheats", "Cheat defaults", "Written to the run's cheats.txt when the run is created. L3+R3 changes them in the game.", {
            {"shiny_default", "Shiny", "", Kind::Level, {
                {"normal", "Normal", "The game's own shiny odds."},
                {"x4", "4× rolls", "Four shiny rolls for every new Pokémon."},
                {"x16", "16× rolls", "Sixteen shiny rolls for every new Pokémon."},
                {"x64", "64× rolls", "Sixty-four shiny rolls for every new Pokémon."},
                {"always", "Always shiny", "Every newly generated Pokémon is shiny."},
            }, 0, 0, 1, 0, "", Avail::Now, "Shiny"},
            {"capture_default", "Capture", "", Kind::Level, {
                {"normal", "Normal", "The game's own capture score."},
                {"x2", "2× score", "Twice the capture score after the eligibility check."},
                {"x4", "4× score", "Four times the capture score."},
                {"x8", "8× score", "Eight times the capture score."},
                {"max", "Max success score", "Every eligible throw succeeds."},
            }, 0, 0, 1, 0, "", Avail::Now, "Capture"},
            {"fps_counter_default", "FPS counter", "", Kind::Toggle, {
                {"off", "Off", "No frame counter at start."},
                {"on", "On", "The frame counter is shown from the first frame."},
            }, 0, 0, 1, 1, "", Avail::Now},
        }},
        {"saved", "Saved runs", "Every run keeps its own save. Continue any of them.", {}, true},
    };
    return pages;
}

const std::vector<RowDef>& cheatRows() {
    static const std::vector<RowDef> rows = {
        {"shiny", "Shiny", "", Kind::Level, {
            {"normal", "Normal", "The game's own shiny odds for newly generated Pokémon."},
            {"x4", "4× rolls", "Four shiny rolls for every newly generated Pokémon."},
            {"x16", "16× rolls", "Sixteen shiny rolls for every newly generated Pokémon."},
            {"x64", "64× rolls", "Sixty-four shiny rolls for every newly generated Pokémon."},
            {"always", "Always shiny", "Every newly generated Pokémon is shiny."},
        }},
        {"capture", "Capture", "", Kind::Level, {
            {"normal", "Normal", "The game's own capture score."},
            {"x2", "2× score", "Twice the capture score; the target eligibility check is kept."},
            {"x4", "4× score", "Four times the capture score; the eligibility check is kept."},
            {"x8", "8× score", "Eight times the capture score; the eligibility check is kept."},
            {"max", "Max success score", "Every eligible throw succeeds."},
        }},
        {"money", "Money", "", Kind::Level, {
            {"normal", "Normal", "No change. Selecting Normal cancels a queued addition."},
            {"p10k", "+10,000", "Cross queues one addition; it lands when the game saves or shows your money."},
            {"p100k", "+100,000", "Cross queues one addition; it lands when the game saves or shows your money."},
            {"p1m", "+1,000,000", "Cross queues one addition; it lands when the game saves or shows your money."},
        }},
        {"fps_counter", "FPS counter", "Live FPS, frame time and frame mode in the top-right corner.", Kind::Toggle, {
            {"off", "Off", "Live FPS, frame time and frame mode in the top-right corner."},
            {"on", "On", "Live FPS, frame time and frame mode in the top-right corner."},
        }},
        {"fps_trial", "FPS trial", "Session only. Returns to 30 automatically when 60 cannot be held.", Kind::Action},
        {"hebrew", "Hebrew trial", "Save first: switching reloads the last saved progress.", Kind::Action},
        {"reset", "Reset shiny and capture", "Both back to Normal. Money, FPS and Hebrew settings are not touched.", Kind::Action},
    };
    return rows;
}

const std::vector<Starter>& starterList(int starterMode) {
    static const std::vector<Starter> vanilla = {{152, "Chikorita"}, {498, "Tepig"}, {158, "Totodile"}};
    // Kanto and Kalos starters plus the three partners. All are species of Z-A; the generator accepts any species
    // of the validated 343-entry city-starter pool, which phase 2 checks at build time (starter-deltas.json).
    static const std::vector<Starter> any = {{1, "Bulbasaur"}, {4, "Charmander"}, {7, "Squirtle"},
                                             {152, "Chikorita"}, {158, "Totodile"}, {498, "Tepig"},
                                             {650, "Chespin"}, {653, "Fennekin"}, {656, "Froakie"}};
    static const std::vector<Starter> none = {};
    return starterMode == 0 ? vanilla : starterMode == 1 ? any : none;
}

// --------------------------------------------------------------------------------------------- capabilities
#include "capabilities_generated.inc"  // kCaps[], kCapsPresent (tools/gen-capabilities.py)

bool capabilitiesPresent() { return kCapsPresent; }

// The launcher writes these itself (cheats.txt of the new run): never gated by the generator's file.
static bool launcherOwnedRow(const RowDef& r) {
    return r.id == std::string("shiny_default") || r.id == std::string("capture_default") || r.id == std::string("fps_counter_default");
}

static bool capHas(const char* row, const char* option) {
    for (const CapEntry* e = kCaps; e->row; e++)
        if (!std::strcmp(e->row, row) && (!std::strcmp(e->option, option) || !std::strcmp(e->option, "*"))) return true;
    return false;
}

bool optionShipped(const RowDef& row, int index) {
    switch (row.kind) {
        case Kind::Text: return true;
        case Kind::Action: case Kind::Link: case Kind::Info: return true;
        case Kind::Pick: return true;  // the list itself follows the Level row it depends on
        case Kind::Number:
            if (launcherOwnedRow(row)) return true;
            return kCapsPresent ? capHas(row.id, "*") : row.avail == Avail::Now;
        case Kind::Level:
        case Kind::Toggle: {
            if (index < 0 || index >= int(row.options.size())) return false;
            if (launcherOwnedRow(row)) return true;
            if (kCapsPresent) return capHas(row.id, row.options[size_t(index)].id);
            return row.avail == Avail::Now && row.options[size_t(index)].avail == Avail::Now;
        }
    }
    return false;
}

bool rowShipped(const RowDef& row) {
    switch (row.kind) {
        case Kind::Text: case Kind::Action: case Kind::Link: case Kind::Info: return true;
        case Kind::Number: return optionShipped(row, 0);
        case Kind::Pick: return true;
        case Kind::Level:
        case Kind::Toggle: {
            int n = 0;
            for (size_t i = 0; i < row.options.size(); i++) n += optionShipped(row, int(i));
            return n >= 2;
        }
    }
    return false;
}

const RowDef* findRow(const std::string& id) {
    for (const auto& p : launcherPages())
        for (const auto& r : p.rows)
            if (id == r.id) return &r;
    return nullptr;
}

int pageIndexOf(const char* id) {
    const auto& pages = launcherPages();
    for (size_t i = 0; i < pages.size(); i++)
        if (!std::strcmp(pages[i].id, id)) return int(i);
    return -1;
}

// --------------------------------------------------------------------------------------------- values
int Values::get(const std::string& id, int def) const {
    auto it = ints.find(id);
    return it == ints.end() ? def : it->second;
}
const std::string& Values::text(const std::string& id) const {
    static const std::string empty;
    auto it = texts.find(id);
    return it == texts.end() ? empty : it->second;
}

Values defaults() {
    Values v;
    for (const auto& p : launcherPages())
        for (const auto& r : p.rows) {
            if (r.kind == Kind::Text) v.setText(r.id, r.id == std::string("player_name") ? "Trainer" : "");
            else if (r.kind != Kind::Action && r.kind != Kind::Link) v.set(r.id, r.def);
        }
    return v;
}

const Option* selectedOption(const RowDef& row, const Values& v) {
    if (row.kind != Kind::Level && row.kind != Kind::Toggle) return nullptr;
    int i = v.get(row.id, row.def);
    if (i < 0 || i >= int(row.options.size())) return nullptr;
    return &row.options[size_t(i)];
}

static std::string withThousands(int n) {
    char buf[32];
    std::snprintf(buf, sizeof buf, "%d", n);
    std::string s = buf, out;
    int count = 0;
    for (int i = int(s.size()) - 1; i >= 0; i--) {
        out.insert(out.begin(), s[size_t(i)]);
        if (++count % 3 == 0 && i > 0 && s[size_t(i - 1)] != '-') out.insert(out.begin(), ',');
    }
    return out;
}

std::string valueText(const RowDef& row, const Values& v) {
    switch (row.kind) {
        case Kind::Level:
        case Kind::Toggle: {
            const Option* o = selectedOption(row, v);
            return o ? o->label : "?";
        }
        case Kind::Number: {
            std::string s = withThousands(v.get(row.id, row.def));
            if (*row.unit) s += std::string(" ") + row.unit;
            return s;
        }
        case Kind::Text: return v.text(row.id);
        case Kind::Pick: {
            const auto& list = starterList(v.get(row.dependsOn, 0));
            if (list.empty()) return "Decided by the seed";
            int i = v.get(row.id, 0);
            if (i < 0 || i >= int(list.size())) i = 0;
            return list[size_t(i)].name;
        }
        default: return "";
    }
}

std::string summary(const Values& v) {
    std::string out;
    for (const auto& p : launcherPages())
        for (const auto& r : p.rows) {
            if (!*r.shortLabel) continue;
            if (r.kind == Kind::Toggle) {
                if (v.get(r.id, r.def) == 0) continue;  // "off" toggles are not worth a mention
                if (!out.empty()) out += " · ";
                out += std::string(r.shortLabel) + ": " + valueText(r, v);
            } else if (r.kind == Kind::Level) {
                int i = v.get(r.id, r.def);
                // a default value is only worth a mention on the four rows that define a run; anything else
                // (levels, items, cheat defaults...) appears when it was changed
                bool core = r.id == std::string("wild_mode") || r.id == std::string("trainers_mode") ||
                            r.id == std::string("starter_mode") || r.id == std::string("music");
                if (i == r.def && (!core || !rowShipped(r))) continue;
                if (!out.empty()) out += " · ";
                out += std::string(r.shortLabel) + ": " + valueText(r, v);
            }
        }
    return out;
}

static std::string jsonString(const std::string& s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') out += '\\', out += char(c);
        else if (c < 0x20) { char b[8]; std::snprintf(b, sizeof b, "\\u%04x", c); out += b; }
        else out += char(c);
    }
    return out + "\"";
}

std::string toJson(const Values& v) {
    // Levels/toggles/picks are stored by option id (stable even if the option order changes); numbers as numbers.
    std::map<std::string, std::string> entries;
    for (const auto& p : launcherPages())
        for (const auto& r : p.rows) {
            if (r.kind == Kind::Level || r.kind == Kind::Toggle) {
                const Option* o = selectedOption(r, v);
                if (o) entries[r.id] = jsonString(o->id);
            } else if (r.kind == Kind::Number) {
                entries[r.id] = std::to_string(v.get(r.id, r.def));
            } else if (r.kind == Kind::Text) {
                entries[r.id] = jsonString(v.text(r.id));
            } else if (r.kind == Kind::Pick) {
                const auto& list = starterList(v.get(r.dependsOn, 0));
                int i = v.get(r.id, 0);
                entries[r.id] = list.empty() ? "null" : std::to_string(list[size_t(std::clamp(i, 0, int(list.size()) - 1))].species);
            }
        }
    std::string out = "{\"schema\": 2, \"values\": {";
    bool first = true;
    for (const auto& [k, val] : entries) {
        if (!first) out += ", ";
        first = false;
        out += jsonString(k) + ": " + val;
    }
    return out + "}}";
}

bool fromJson(const std::string& json, Values& out) {
    // A tiny reader for exactly what toJson writes (the title uses nlohmann::json; this keeps the host tests
    // dependency-free). Unknown ids are stored too.
    size_t at = json.find("\"values\"");
    if (at == std::string::npos) return false;
    at = json.find('{', at);
    if (at == std::string::npos) return false;
    at++;
    auto skipWs = [&] { while (at < json.size() && std::strchr(" \t\r\n,", json[at])) at++; };
    auto readString = [&](std::string& s) {
        if (at >= json.size() || json[at] != '"') return false;
        at++;
        s.clear();
        while (at < json.size() && json[at] != '"') {
            if (json[at] == '\\' && at + 1 < json.size()) at++;
            s += json[at++];
        }
        if (at >= json.size()) return false;
        at++;
        return true;
    };
    const auto& pages = launcherPages();
    for (;;) {
        skipWs();
        if (at >= json.size()) return false;
        if (json[at] == '}') return true;
        std::string key;
        if (!readString(key)) return false;
        skipWs();
        if (at >= json.size() || json[at] != ':') return false;
        at++;
        skipWs();
        if (at >= json.size()) return false;
        const RowDef* row = nullptr;
        for (const auto& p : pages)
            for (const auto& r : p.rows)
                if (key == r.id) row = &r;
        if (json[at] == '"') {
            std::string s;
            if (!readString(s)) return false;
            if (row && (row->kind == Kind::Level || row->kind == Kind::Toggle)) {
                for (size_t i = 0; i < row->options.size(); i++)
                    if (s == row->options[i].id) out.set(key, int(i));
            } else {
                out.setText(key, s);
            }
        } else {
            size_t end = at;
            while (end < json.size() && std::strchr("-0123456789null", json[end])) end++;
            std::string num = json.substr(at, end - at);
            at = end;
            if (num != "null") {
                int n = std::atoi(num.c_str());
                if (row && row->kind == Kind::Pick) {
                    const auto& list = starterList(out.get(row->dependsOn, 0));
                    for (size_t i = 0; i < list.size(); i++)
                        if (list[i].species == n) out.set(key, int(i));
                } else {
                    out.set(key, n);
                }
            }
        }
    }
}

// --------------------------------------------------------------------------------------------- navigation
const PageDef& page(int index) {
    const auto& pages = launcherPages();
    return pages[size_t(std::clamp(index, 0, int(pages.size()) - 1))];
}
int pageCount() { return int(launcherPages().size()); }

static bool optionAllowed(const RowDef& r, int i, bool allowPhase2) { return allowPhase2 || optionShipped(r, i); }

static bool cycle(const RowDef& r, Values& v, int dir, bool allowPhase2) {
    if (r.kind == Kind::Level || r.kind == Kind::Toggle) {
        int n = int(r.options.size());
        if (n == 0) return false;
        int i = v.get(r.id, r.def), start = i;
        for (int step = 0; step < n; step++) {
            i = (i + dir + n) % n;
            if (i == start) return false;  // the only option this build offers is the current one: nothing to change
            if (optionAllowed(r, i, allowPhase2)) { v.set(r.id, i); return true; }
        }
        return false;
    }
    if (r.kind == Kind::Number) {
        if (!allowPhase2 && !optionShipped(r, 0)) return false;
        int x = v.get(r.id, r.def) + dir * r.step;
        if (x < r.min) x = r.max;
        if (x > r.max) x = r.min;
        v.set(r.id, x);
        return true;
    }
    if (r.kind == Kind::Pick) {
        const auto& list = starterList(v.get(r.dependsOn, 0));
        if (list.empty()) return false;
        int n = int(list.size());
        v.set(r.id, (v.get(r.id, 0) + dir + n) % n);
        return true;
    }
    return false;
}

Event handle(Nav& nav, Values& v, Button b, bool allowPhase2) {
    Event e;
    const PageDef& p = page(nav.page);
    int rows = int(p.rows.size());
    auto changed = [&](const RowDef& r) { e.type = Event::Changed; e.text = r.id; return e; };
    switch (b) {
        case Button::L1: nav.page = (nav.page + pageCount() - 1) % pageCount(); nav.row = 0; return e;
        case Button::R1: nav.page = (nav.page + 1) % pageCount(); nav.row = 0; return e;
        case Button::Up: if (rows) nav.row = (nav.row + rows - 1) % rows; return e;
        case Button::Down: if (rows) nav.row = (nav.row + 1) % rows; return e;
        case Button::Circle:
            if (nav.page != 0) { nav.page = 0; nav.row = 0; e.type = Event::BackToPlay; }
            return e;
        default: break;
    }
    if (!rows) return e;
    const RowDef& r = p.rows[size_t(std::clamp(nav.row, 0, rows - 1))];
    if (b == Button::Left || b == Button::Right) {
        if (cycle(r, v, b == Button::Left ? -1 : 1, allowPhase2)) return changed(r);
        if (r.kind == Kind::Level || r.kind == Kind::Toggle || r.kind == Kind::Number) {
            e.type = Event::Toast;
            e.text = "Not in this build yet";
        }
        return e;
    }
    if (b == Button::Cross) {
        if (r.id == std::string("continue")) e.type = Event::Continue;
        else if (r.id == std::string("new_run")) e.type = Event::StartNewRun;
        else if (r.id == std::string("seed")) e.type = Event::OpenSeed;
        else if (r.id == std::string("saved")) e.type = Event::OpenSavedRuns;
        else if (r.kind == Kind::Text) e.type = Event::OpenName;
        else if (cycle(r, v, 1, allowPhase2)) return changed(r);
        return e;
    }
    if (b == Button::Triangle) {
        if (r.id == std::string("seed")) { e.type = Event::RandomSeed; return e; }
        if (nav.page == 0) return e;  // the Play page has nothing to reset
        e.type = Event::Toast;
        e.text = std::string(resetPage(nav.page, v)) + " reset to defaults";
        return e;
    }
    return e;
}

const char* resetPage(int pageIndex, Values& v) {
    const PageDef& p = page(pageIndex);
    Values d = defaults();
    for (const auto& row : p.rows) {
        if (row.kind == Kind::Text) v.setText(row.id, d.text(row.id));
        else if (row.kind != Kind::Action && row.kind != Kind::Link) v.set(row.id, d.get(row.id, row.def));
    }
    return p.title;
}

}  // namespace ui::model
