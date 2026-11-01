// Host tests for rando-v3 (built with ASan/UBSan by tools/build-host.sh).
//   test_v3 ASSETS OUT [SEEDS]
// 1. Equivalence: with today's settings the v3 tables and save are byte-identical to the legacy pipeline
//    (core generate -> protectProgression -> randomizeResearchRewards) for SEEDS seeds and every toggle combination.
// 2. Determinism: every option level, one at a time and in combinations, generated twice -> identical bytes + report.
// 3. Invariants per level (levels, Alpha, zones, swap, ...) on the produced tables.
// 4. Negative: unsupported option ids, corrupt chunks, corrupt templates are refused.
// Reports (with table SHA-256s) go to OUT/reports.json for the independent Python oracle (tools/oracle_v3.py).
#include "rando_v3.hpp"
#include "progression.hpp"
#include "research_rewards.hpp"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <set>
using namespace za;
using namespace za::v3;

static bool readFile(const std::string& path, Bytes& out) {
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    out.assign(std::istreambuf_iterator<char>(f), {});
    return true;
}
static Json loadJson(const std::string& path) {
    Bytes b;
    if (!readFile(path, b)) { std::cerr << "missing " << path << "\n"; std::abort(); }
    auto j = Json::parse(b, nullptr, false);
    if (j.is_discarded()) { std::cerr << "bad json " << path << "\n"; std::abort(); }
    return j;
}
static void writeFile(const std::string& path, const Bytes& data) {
    std::ofstream f(path, std::ios::binary);
    f.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
    assert(f.good());
}
static int32_t i32(const Bytes& d, size_t p) { return int32_t(uint32_t(d[p]) | (uint32_t(d[p + 1]) << 8) | (uint32_t(d[p + 2]) << 16) | (uint32_t(d[p + 3]) << 24)); }
static float f32(const Bytes& d, size_t p) { uint32_t u = uint32_t(i32(d, p)); float f; std::memcpy(&f, &u, 4); return f; }
#define CHECK(x) do { if (!(x)) { std::cerr << "CHECK failed: " #x " at line " << __LINE__ << "\n"; std::abort(); } } while (0)

int main(int argc, char** argv) {
    if (argc < 3) { std::cerr << "usage: test_v3 ASSETS OUT [SEEDS]\n"; return 2; }
    const std::string assets = argv[1], out = argv[2];
    const int seeds = argc > 3 ? std::atoi(argv[3]) : 100;
    Assets a{loadJson(assets + "/tables.json"), loadJson(assets + "/starter-deltas.json"), loadJson(assets + "/progression.json"),
             loadJson(assets + "/research-rewards.json"), loadJson(assets + "/v3.json")};
    Reader read = [&](const std::string& name, Bytes& b) { return readFile(assets + "/" + name, b); };
    // Rows for the invariant checks.
    std::vector<Json> wildRows, trainerRows;
    for (const auto& c : a.v3["wild"]["rows_files"]) for (const auto& r : loadJson(assets + "/" + c["file"].get<std::string>())) wildRows.push_back(r);
    for (const auto& c : a.v3["trainers"]["rows_files"]) for (const auto& r : loadJson(assets + "/" + c["file"].get<std::string>())) trainerRows.push_back(r);
    CHECK(wildRows.size() == 1822 && trainerRows.size() == 8005);
    Json reports = Json::array();
    int generated = 0;

    auto legacy = [&](const std::string& seed, const Options& o, bool rewards, int starter, Result& r) {
        CHECK(generate(a.tables, a.starters, read, seed, o, starter, r));
        r.report["options"]["research_rewards"] = rewards;
        std::string error;
        CHECK(za::native::protectProgression(a.progression, read, seed, r, error));
        if (rewards) CHECK(za::native::randomizeResearchRewards(a.rewards, read, seed, r, error));
    };
    auto run = [&](const std::string& seed, const Settings& s, const char* label, Result& r) {
        Json ui = settingsToUi(s);
        CHECK(generateRun(a, read, seed, s, ui, r));
        Result again;
        CHECK(generateRun(a, read, seed, s, ui, again));
        CHECK(again.tables == r.tables && again.save == r.save && again.report == r.report);  // determinism
        Settings back;
        std::string error;
        CHECK(settingsFromUi(ui, back, error));
        CHECK(settingsToUi(back) == ui);  // the resolved settings round-trip through the ui_options schema
        reports.push_back({{"label", label}, {"seed", seed}, {"report", r.report}});
        generated++;
    };

    // ---------------------------------------------------------------- 1. equivalence with today's pipeline
    std::cout << "[1] equivalence: " << seeds << " seeds, default settings\n";
    for (int i = 0; i < seeds; i++) {
        std::string seed = std::to_string(1000 + i * 7919);
        Result v, l;
        Settings s;
        run(seed, s, "default", v);
        legacy(seed, Options{}, true, 0, l);
        CHECK(v.tables.size() == 4 && v.tables == l.tables);
        CHECK(v.save == l.save);
        CHECK(v.report["rock_route"] == l.report["rock_route"] && v.report["table_sha256"] == l.report["table_sha256"]);
        if (v.report["starter"] != l.report["starter"] || v.report["counts"] != l.report["counts"])
            std::cerr << "v3 starter " << v.report["starter"] << " counts " << v.report["counts"].dump() << " | legacy starter " << l.report["starter"] << " counts " << l.report["counts"].dump() << "\n";
        CHECK(v.report["starter"] == l.report["starter"] && v.report["counts"] == l.report["counts"]);
        CHECK(v.report["progression"]["changes"] == l.report["progression"]["changes"]);
        CHECK(v.report["research_rewards"] == l.report["research_rewards"]);
        if (i < 2) { writeFile(out + "/" + seed + "-default-wild.bin", v.tables["wild"]); writeFile(out + "/" + seed + "-default-trainers.bin", v.tables["trainers"]); }
    }
    std::cout << "[1b] equivalence: every toggle combination, three starters\n";
    for (int mask = 0; mask < 32; mask++) {
        std::string seed = "toggle-" + std::to_string(mask);
        Options o; o.wild = mask & 1; o.trainers = mask & 2; o.mega_trainers = mask & 4; o.dlc_rematches = mask & 8;
        bool rewards = mask & 16;
        int starter = mask % 3 == 0 ? 0 : mask % 3 == 1 ? 152 : 1;
        Settings s = settingsFromLegacy(o, rewards, starter);
        Result v, l;
        run(seed, s, "toggle", v);
        legacy(seed, o, rewards, starter, l);
        CHECK(v.tables == l.tables && v.save == l.save && v.report["rock_route"] == l.report["rock_route"]);
        CHECK(v.report["starter"] == starter || starter == 0);
    }

    // ---------------------------------------------------------------- 2+3. every level, determinism and invariants
    std::cout << "[2] levels\n";
    const int levelSeeds = std::max(3, seeds / 10);
    for (int i = 0; i < levelSeeds; i++) {
        std::string seed = "level-" + std::to_string(i);
        Result base; { Settings s; run(seed, s, "default", base); }
        auto wildOf = [&](const Result& r, size_t row, const char* field) { return i32(r.tables.at("wild"), wildRows[row]["fields"][field]["offset"]); };
        // Wild: shuffle zones -- levels untouched, species of every ordinary slot come from the donor zone, fixed/Mega/rock untouched.
        {
            Settings s; s.wild = WildMode::Zones; Result r; run(seed, s, "wild-zones", r);
            std::map<std::string, std::set<std::pair<int, int>>> original, got;
            const Json& donors = r.report["v3"]["wild"]["zones"];
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                CHECK(wildOf(r, k, "minLevel") == w["min_level"] && wildOf(r, k, "maxLevel") == w["max_level"]);
                CHECK(f32(r.tables["wild"], w["fields"]["oyabunProbability"]["offset"]) == w["oyabun"].get<float>());
                if (w["rock_provider"]) { CHECK(wildOf(r, k, "devNo") == r.report["rock_route"]["species"]); continue; }
                if (w["fixed"] || w["mega"] || w["zone_class"].is_null()) { CHECK(wildOf(r, k, "devNo") == w["species"] && wildOf(r, k, "formNo") == w["form"]); continue; }
                std::string key = w["zone_class"].get<std::string>() + "/" + w["zone"].get<std::string>();
                original[key].insert({w["species"], w["form"]});
                got[key].insert({wildOf(r, k, "devNo"), wildOf(r, k, "formNo")});
            }
            for (const auto& [key, species] : got) {
                std::string cls = key.substr(0, key.find('/')), zone = key.substr(key.find('/') + 1);
                if (!donors.contains(cls) || !donors[cls].contains(zone)) { CHECK(species == original[key]); continue; }
                std::string donor = donors[cls][zone];
                CHECK(donor != zone);
                for (const auto& sp : species) CHECK(original[cls + "/" + donor].count(sp));
            }
            CHECK(donors["wild"].size() == 20 && donors["outzone"].size() == 10);
        }
        // Wild: shuffle within zone -- multiset of ordinary (species, form, sex) per zone preserved.
        {
            Settings s; s.wild = WildMode::InZone; Result r; run(seed, s, "wild-in-zone", r);
            std::map<std::string, std::multiset<std::tuple<int, int, int>>> original, got;
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                if (w["rock_provider"] || w["fixed"] || w["mega"] || w["zone_class"].is_null()) continue;
                std::string key = w["zone_class"].get<std::string>() + "/" + w["zone"].get<std::string>();
                original[key].insert({w["species"], w["form"], w["sex"]});
                got[key].insert({wildOf(r, k, "devNo"), wildOf(r, k, "formNo"), wildOf(r, k, "sex")});
            }
            CHECK(original == got);
            CHECK(r.report["v3"]["wild"]["species_changed"].get<int>() > 1000);
        }
        // Wild: chaos -- no rock protection, authored rows randomized, forms random, sex -1.
        {
            Settings s; s.wild = WildMode::Chaos; Result r; run(seed, s, "wild-chaos", r);
            int authoredChanged = 0;
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                if (w["mega"]) continue;
                if (w["authored"] && wildOf(r, k, "devNo") != w["species"]) authoredChanged++;
                CHECK(wildOf(r, k, "sex") == -1);
            }
            CHECK(authoredChanged > 100 && r.report["progression"]["rock_route_applied"] == false);
        }
        // Wild levels and Alpha, forms.
        for (WildLevels lv : {WildLevels::Plus10, WildLevels::Plus25, WildLevels::Range, WildLevels::Mixed}) {
            Settings s; s.wildLevels = lv; Result r; run(seed, s, "wild-levels", r);
            CHECK(r.tables["trainers"] == base.tables["trainers"]);
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                int lo = wildOf(r, k, "minLevel"), hi = wildOf(r, k, "maxLevel");
                CHECK(wildOf(r, k, "devNo") == wildOf(base, k, "devNo") && 1 <= lo && lo <= hi && hi <= 100);
                if (w["rock_provider"]) CHECK(lo == w["min_level"] && hi == w["max_level"]);
                else if (lv == WildLevels::Plus10) CHECK(lo == std::clamp((w["min_level"].get<int>() * 110 + 50) / 100, 1, 100));
                else if (lv == WildLevels::Range) CHECK(std::abs(lo - w["min_level"].get<int>()) <= 5 || lo == 1 || lo == 100);
            }
            CHECK(r.report["v3"]["wild"]["levels_changed"].get<int>() > 1000);
        }
        for (AlphaRate ar : {AlphaRate::X2, AlphaRate::X5, AlphaRate::Always}) {
            Settings s; s.alpha = ar; Result r; run(seed, s, "alpha", r);
            int at100 = 0;
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                float p = f32(r.tables["wild"], w["fields"]["oyabunProbability"]["offset"]), o = w["oyabun"].get<float>();
                if (o == 0 || o == 100) CHECK(p == o);
                else CHECK(p == (ar == AlphaRate::X2 ? std::min(100.0f, o * 2) : ar == AlphaRate::X5 ? std::min(100.0f, o * 5) : 100.0f));
                if (p == 100) at100++;
                CHECK(wildOf(r, k, "devNo") == wildOf(base, k, "devNo"));
            }
            CHECK(at100 >= 140 && (ar != AlphaRate::Always || at100 == 140 + 867));
        }
        {
            Settings s; s.forms = Forms::Random; Result r; run(seed, s, "forms", r);
            const Json& multi = loadJson(assets + "/v3.personal.json")["multi_forms"];
            int changed = 0;
            for (size_t k = 0; k < wildRows.size(); k++) {
                const Json& w = wildRows[k];
                int sp = wildOf(r, k, "devNo"), form = wildOf(r, k, "formNo");
                CHECK(sp == wildOf(base, k, "devNo"));
                if (w["mega"] || w["fixed"]) { CHECK(form == wildOf(base, k, "formNo")); continue; }
                if (form != wildOf(base, k, "formNo")) { changed++; CHECK(multi.contains(std::to_string(sp))); bool ok = false; for (const auto& f : multi[std::to_string(sp)]) ok |= f == form; CHECK(ok); }
            }
            CHECK(changed > 50 && changed == r.report["v3"]["wild"]["forms_changed"]);
        }
        // Wild off with Alpha always: template base, vanilla species.
        {
            Settings s; s.wild = WildMode::Off; s.alpha = AlphaRate::Always; Result r; run(seed, s, "off-alpha", r);
            for (size_t k = 0; k < wildRows.size(); k++) CHECK(wildOf(r, k, "devNo") == wildRows[k]["species"] && wildOf(r, k, "formNo") == wildRows[k]["form"]);
        }
        // Trainers.
        auto trainerOf = [&](const Result& r, size_t row, const char* field) { const Json& f = trainerRows[row]["fields"][field]; int64_t v = 0; const Bytes& d = r.tables.at("trainers"); size_t p = f["offset"], n = f["bytes"]; for (size_t b = 0; b < n; b++) v |= int64_t(d[p + b]) << (8 * b); if (f["signed"] && n < 8 && (v >> (n * 8 - 1)) & 1) v -= int64_t(1) << (n * 8); return int(v); };
        {
            Settings s; s.trainers = TrainersMode::Swap; Result r; run(seed, s, "trainers-swap", r);
            std::map<std::string, std::vector<int>> teamsBefore, teamsAfter;
            for (size_t k = 0; k < trainerRows.size(); k++) {
                const Json& t = trainerRows[k];
                CHECK(trainerOf(r, k, "level") == t["level"]);
                if (t["mega"]) continue;
                teamsBefore[t["identity"][0]].push_back(t["species"]);
                teamsAfter[t["identity"][0]].push_back(trainerOf(r, k, "devId"));
            }
            int moved = 0;
            for (const auto& [trid, team] : teamsAfter) if (team != teamsBefore[trid]) moved++;
            CHECK(moved > 2000 && r.report["v3"]["trainers"]["swap"]["groups"].get<int>() > 10);
            // every received team exists as some trainer's original team
            std::set<std::vector<int>> originals;
            for (const auto& [trid, team] : teamsBefore) originals.insert(team);
            for (const auto& [trid, team] : teamsAfter) CHECK(originals.count(team));
        }
        {
            Settings s; s.trainers = TrainersMode::Strength; Result r; run(seed, s, "trainers-strength", r);
            const Json& entries = loadJson(assets + "/v3.personal.json")["entries"];
            std::map<std::pair<int, int>, int> bst;
            for (const auto& e : entries) { int sum = 0; for (const auto& x : e["stats"]) sum += x.get<int>(); bst[{e["species"], e["form"]}] = sum; }
            int within = 0, total = 0;
            for (size_t k = 0; k < trainerRows.size(); k++) {
                const Json& t = trainerRows[k];
                if (t["mega"]) continue;
                int sp = trainerOf(r, k, "devId");
                CHECK(sp != t["species"] && trainerOf(r, k, "formId") == 0);
                auto it = bst.find({t["species"], t["form"]});
                int target = it != bst.end() ? it->second : bst.at({t["species"], 0});
                total++;
                if (std::abs(bst.at({sp, 0}) - target) <= std::max(20, target / 10)) within++;
            }
            CHECK(within * 100 / total > 85);
        }
        for (TrainerLevels tl : {TrainerLevels::Plus10, TrainerLevels::Plus30}) {
            Settings s; s.trainerLevels = tl; Result r; run(seed, s, "trainer-levels", r);
            int pct = tl == TrainerLevels::Plus10 ? 10 : 30;
            for (size_t k = 0; k < trainerRows.size(); k++) CHECK(trainerOf(r, k, "level") == std::clamp((trainerRows[k]["level"].get<int>() * (100 + pct) + 50) / 100, 1, 100));
            CHECK(r.tables["wild"] == base.tables["wild"]);
        }
        {
            Settings s; s.trainers = TrainersMode::Off; s.megaTrainers = false; s.trainerLevels = TrainerLevels::Plus20; Result r; run(seed, s, "trainer-levels-only", r);
            for (size_t k = 0; k < trainerRows.size(); k++) { CHECK(trainerOf(r, k, "devId") == trainerRows[k]["species"]); CHECK(trainerOf(r, k, "level") == std::clamp((trainerRows[k]["level"].get<int>() * 120 + 50) / 100, 1, 100)); }
        }
        std::set<int> usable;
        for (const auto& m : a.v3["moves"]["usable"]) usable.insert(m.get<int>());
        for (TrainerMoves tm : {TrainerMoves::Legal, TrainerMoves::Any}) {
            Settings s; s.trainerMoves = tm; Result r; run(seed, s, "trainer-moves", r);
            for (size_t k = 0; k < trainerRows.size(); k++) {
                std::set<int> seen;
                for (int m = 0; m < 4; m++) {
                    const Json& f = trainerRows[k]["move_fields"][m]["wazaId"];
                    int move = int(r.tables["trainers"][f["offset"]]) | (int(r.tables["trainers"][f["offset"].get<size_t>() + 1]) << 8);
                    if (move) { CHECK(usable.count(move) && !seen.count(move)); seen.insert(move); }
                }
                CHECK(!seen.empty());
            }
        }
        for (TrainerItems ti : {TrainerItems::Random, TrainerItems::None}) {
            Settings s; s.trainerItems = ti; Result r; run(seed, s, "trainer-items", r);
            std::set<int> pool;
            for (const auto& x : a.v3["trainers"]["held_item_pool"]) pool.insert(x.get<int>());
            for (size_t k = 0; k < trainerRows.size(); k++) {
                int item = trainerOf(r, k, "item");
                if (trainerRows[k]["mega"]) continue;
                CHECK(ti == TrainerItems::None ? item == 0 : pool.count(item) > 0);
            }
        }
        // Research requirements, base stats, catch rate.
        for (ResearchRequirements rr : {ResearchRequirements::Easier, ResearchRequirements::Harder}) {
            for (bool rewards : {true, false}) {
                Settings s; s.researchRequirements = rr; s.researchRewards = rewards; Result r; run(seed, s, "research-req", r);
                const Bytes& d = r.tables.at("research_rewards");
                uint32_t prev = 0;
                for (const auto& row : a.v3["research"]["rows"]) {
                    size_t p = row["points_offset"]; uint32_t pts = uint32_t(i32(d, p)), orig = row["points"];
                    CHECK(pts > prev && (rr == ResearchRequirements::Easier ? pts <= std::max(orig / 2, prev + 1) : pts >= orig * 3 / 2));
                    prev = pts;
                }
                if (!rewards) for (const auto& row : a.rewards["rows"]) CHECK(uint32_t(i32(d, row["item_offset"])) == row["item"].get<uint32_t>());
            }
        }
        {
            const Json& entries = loadJson(assets + "/v3.personal.json")["entries"];
            for (BaseStats bs : {BaseStats::Shuffle, BaseStats::Random}) {
                Settings s; s.baseStats = bs; s.catchRate = CatchRate::X2; Result r; run(seed, s, "personal", r);
                CHECK(r.tables.size() == 5 && r.tables.count("personal"));
                const Bytes& d = r.tables.at("personal");
                CHECK(d.size() == a.v3["personal"]["bytes"]);
                for (const auto& e : entries) {
                    size_t so = e["stats_offset"];
                    std::multiset<int> orig, got;
                    for (int k = 0; k < 6; k++) { orig.insert(e["stats"][k].get<int>()); got.insert(d[so + k]); }
                    if (!e["present"]) { CHECK(orig == got); if (e.contains("catch_offset")) CHECK(d[e["catch_offset"].get<size_t>()] == e["catch"].get<int>()); continue; }
                    if (bs == BaseStats::Shuffle) CHECK(orig == got);
                    else for (int k = 0; k < 6; k++) CHECK(d[so + k] >= 1 && std::abs(int(d[so + k]) - e["stats"][k].get<int>()) <= e["stats"][k].get<int>() * 31 / 100 + 1);
                    if (e.contains("catch_offset")) CHECK(d[e["catch_offset"].get<size_t>()] == std::min(255, e["catch"].get<int>() * 2));
                }
            }
        }
        // Combinations.
        {
            Settings s; s.wild = WildMode::Zones; s.wildLevels = WildLevels::Mixed; s.alpha = AlphaRate::X5; s.forms = Forms::Random;
            s.trainers = TrainersMode::Strength; s.trainerLevels = TrainerLevels::Plus20; s.trainerMoves = TrainerMoves::Legal; s.trainerItems = TrainerItems::Random;
            s.starter = 656; s.researchRequirements = ResearchRequirements::Harder; s.baseStats = BaseStats::Shuffle; s.catchRate = CatchRate::Max;
            Result r; run(seed, s, "combo-a", r);
            CHECK(r.report["starter"] == 656 && r.tables.size() == 5);
        }
        {
            Settings s; s.wild = WildMode::Chaos; s.wildLevels = WildLevels::Range; s.alpha = AlphaRate::Always; s.trainers = TrainersMode::Swap; s.megaTrainers = false;
            s.trainerMoves = TrainerMoves::Any; s.trainerItems = TrainerItems::None; s.dlcRematches = false; s.researchRewards = false; s.researchRequirements = ResearchRequirements::Easier;
            Result r; run(seed, s, "combo-b", r);
            CHECK(r.tables.size() == 4);
        }
    }

    // ---------------------------------------------------------------- 4. negative
    std::cout << "[4] negative\n";
    {
        Settings s; std::string error;
        CHECK(!settingsFromUi(Json{{"schema", 2}, {"values", {{"wild_mode", "sideways"}}}}, s, error) && error.find("wild_mode") != std::string::npos);
        CHECK(!settingsFromUi(Json{{"values", {{"wild_mega_rate", "x2"}}}}, s, error));
        CHECK(!settingsFromUi(Json{{"values", {{"held_items", "random"}}}}, s, error));
        CHECK(!settingsFromUi(Json{{"values", {{"starter_mode", "vanilla"}, {"starter_pick", 1}}}}, s, error));
        CHECK(settingsFromUi(Json{{"values", {{"starter_mode", "any"}, {"starter_pick", 656}, {"music", "chaos"}, {"player_name", "Tomer"}, {"future_option", "x"}}}}, s, error) && s.starter == 656);
        CHECK(settingsFromUi(Json{{"values", {{"starter_mode", "vanilla"}}}}, s, error) && s.starter == 152);
        CHECK(settingsFromUi(Json(), s, error) && s.starter == 0 && s.wild == WildMode::Random);
        CHECK(settingsFromUi(Json{{"schema", 2}, {"values", {{"mega_trainers", "off"}, {"research_rewards", false}}}}, s, error) && !s.megaTrainers && !s.researchRewards);
        Result r;
        auto corruptChunk = [&](const std::string& name, Bytes& b) { bool ok = read(name, b); if (ok && name.rfind("v3.wild.rows-003", 0) == 0) b[10] ^= 1; return ok; };
        Settings z; z.wild = WildMode::Zones;
        CHECK(!generateRun(a, corruptChunk, "x", z, Json(), r) && r.error == "Wild row integrity failed");
        auto corruptTemplate = [&](const std::string& name, Bytes& b) { bool ok = read(name, b); if (ok && name == "progression-wild.bin") b[100] ^= 1; return ok; };
        CHECK(!generateRun(a, corruptTemplate, "x", z, Json(), r) && r.error == "Wild template integrity failed");
        auto corruptPersonal = [&](const std::string& name, Bytes& b) { bool ok = read(name, b); if (ok && name == "personal.vanilla.bin") b[1000] ^= 1; return ok; };
        Settings ps; ps.catchRate = CatchRate::Max;
        CHECK(!generateRun(a, corruptPersonal, "x", ps, Json(), r) && r.error == "Personal table integrity failed");
        Assets bad = a; bad.v3["build_id"] = "0";
        CHECK(!generateRun(bad, read, "x", z, Json(), r) && r.error == "v3 asset mismatch");
        Settings badStarter; badStarter.starter = 999;
        CHECK(!generateRun(a, read, "x", badStarter, Json(), r));
    }
    std::ofstream f(out + "/reports.json");
    f << reports.dump();
    assert(f.good());
    std::cout << "PASS: " << generated << " generations (" << seeds << " equivalence seeds, " << levelSeeds << " seeds per level), reports in " << out << "/reports.json\n";
}
