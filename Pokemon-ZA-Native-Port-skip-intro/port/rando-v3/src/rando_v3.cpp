#include "rando_v3.hpp"
#include "progression.hpp"
#include "research_rewards.hpp"
#include <mbedtls/sha256.h>
#include <algorithm>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <set>

namespace za::v3 {
namespace {
// ------------------------------------------------------------------------------------------------ the r15 sampler
// Byte-for-byte the same construction as core/randomizer.cpp (same algorithm/build strings, so the same seed gives
// the same key): HMAC-SHA256(key, json([domain, identity, retry])) with rejection sampling. Stateless per
// (domain, identity), so the order rows are visited in never matters.
constexpr const char* BaseAlgorithm = "za202-randomizer-alpha1";
constexpr const char* Build = "b1f12fd919eae86ab8a978317677e64bce443d1f";
std::array<uint8_t, 32> digest(const uint8_t* p, size_t n) {
    std::array<uint8_t, 32> out{};
    if (mbedtls_sha256(p, n, out.data(), 0) != 0) std::abort();
    return out;
}
std::array<uint8_t, 32> digest(const std::string& s) { return digest(reinterpret_cast<const uint8_t*>(s.data()), s.size()); }
struct Seed {
    std::array<uint8_t, 32> key;
    explicit Seed(const std::string& s) : key(digest(Json::array({BaseAlgorithm, Build, s}).dump())) {}
    uint64_t number(const std::string& domain, const Json& identity, uint64_t bound) const {
        if (!bound) std::abort();
        uint64_t rem = (UINT64_MAX % bound + 1) % bound;
        for (int retry = 0; retry < 1000; retry++) {
            auto msg = Json::array({domain, identity, retry}).dump();
            Bytes inner(64), outer(96);
            for (size_t i = 0; i < 64; i++) { inner[i] = (i < 32 ? key[i] : 0) ^ 0x36; outer[i] = (i < 32 ? key[i] : 0) ^ 0x5c; }
            inner.insert(inner.end(), msg.begin(), msg.end());
            auto h = digest(inner.data(), inner.size());
            std::copy(h.begin(), h.end(), outer.begin() + 64);
            h = digest(outer.data(), outer.size());
            uint64_t w = 0;
            for (int i = 0; i < 8; i++) w = (w << 8) | h[i];
            if (rem == 0 || w <= UINT64_MAX - rem) return w % bound;
        }
        std::abort();
    }
};
struct Pool {
    std::vector<Json> values;
    explicit Pool(const Json& input) {
        std::vector<std::pair<std::string, Json>> ordered;
        for (const auto& v : input) ordered.emplace_back(v.dump(), v);
        std::stable_sort(ordered.begin(), ordered.end(), [](const auto& a, const auto& b) { return a.first < b.first; });
        for (auto& p : ordered) values.push_back(std::move(p.second));
    }
    template <class Reject>
    const Json* choose(const Seed& rng, const std::string& domain, const Json& id, Reject reject) const {
        size_t n = 0;
        for (const auto& v : values) if (!reject(v)) ++n;
        if (!n) return nullptr;
        auto selected = rng.number(domain, id, n);
        for (const auto& v : values) if (!reject(v)) { if (selected == 0) return &v; --selected; }
        return nullptr;
    }
    const Json* choose(const Seed& rng, const std::string& domain, const Json& id, const Json& excluded) const {
        return choose(rng, domain, id, [&](const Json& v) { return v == excluded; });
    }
};
// A seeded permutation of [0, n): Fisher-Yates (any permutation) or Sattolo (one cycle: no element stays put).
std::vector<size_t> permutation(const Seed& rng, const std::string& domain, const Json& identity, size_t n, bool cycle) {
    std::vector<size_t> perm(n);
    for (size_t i = 0; i < n; i++) perm[i] = i;
    for (size_t i = n; i-- > 1;) {
        Json id = identity; id.push_back(i);
        size_t j = size_t(rng.number(domain, id, cycle ? i : i + 1));
        std::swap(perm[i], perm[j]);
    }
    return perm;
}
// ------------------------------------------------------------------------------------------------ field writes
// core/randomizer.cpp's patch() plus one case: {"float": true} writes the IEEE-754 bits of a double (oyabunProbability).
bool patch(Bytes& data, const Json& field, const Json& value) {
    if (field.contains("capacity")) {
        if (!value.is_string()) return false;
        auto str = value.get<std::string>();
        size_t p = field.at("data"), l = field.at("length"), cap = field.at("capacity");
        if (cap > 1024 || str.size() > cap || p > data.size() || cap + 1 > data.size() - p || l > data.size() || 4 > data.size() - l) return false;
        std::fill(data.begin() + p, data.begin() + p + cap + 1, 0);
        std::copy(str.begin(), str.end(), data.begin() + p);
        for (int i = 0; i < 4; i++) data[l + i] = uint8_t(str.size() >> (8 * i));
        return true;
    }
    size_t p = field.at("offset"), n = field.at("bytes");
    if (!(n == 1 || n == 2 || n == 4 || n == 8) || p > data.size() || n > data.size() - p) return false;
    if (field.value("float", false)) {
        if (n != 4 || !value.is_number()) return false;
        float f = value.get<float>();
        if (!(f >= 0.0f && f <= 100.0f)) return false;
        uint32_t bits;
        std::memcpy(&bits, &f, 4);
        for (size_t i = 0; i < 4; i++) data[p + i] = uint8_t(bits >> (8 * i));
        return true;
    }
    bool sign = field.at("signed");
    if (!value.is_number_integer() && !value.is_boolean()) return false;
    int64_t v = value.is_boolean() ? (value.get<bool>() ? 1 : 0) : value.get<int64_t>();
    if (!sign && v < 0) return false;
    if (n < 8 && (v < (sign ? -(int64_t(1) << (n * 8 - 1)) : 0) || uint64_t(v >= 0 ? v : 0) > (sign ? (uint64_t(1) << (n * 8 - 1)) - 1 : (uint64_t(1) << (n * 8)) - 1))) return false;
    for (size_t i = 0; i < n; i++) data[p + i] = uint8_t(uint64_t(v) >> (8 * i));
    return true;
}
// ------------------------------------------------------------------------------------------------ learnsets
using PersonalIndex = std::map<std::pair<int, int>, const Json*>;
const Json* personalEntry(const PersonalIndex& personal, int sp, int form) {
    auto found = personal.find({sp, form});
    if (found != personal.end()) return found->second;
    if (form) return personalEntry(personal, sp, 0);
    return nullptr;
}
// core/randomizer.cpp moves(): the last four level-up moves learned by `level` (at least the earliest one).
std::vector<Json> learnsetMoves(const PersonalIndex& personal, int sp, int form, int level) {
    const Json* entry = personalEntry(personal, sp, form);
    if (!entry) return {};
    std::vector<Json> learned, available;
    for (const auto& m : entry->at("learnset")) {
        int lvl = m.at("level"), move = m.at("move");
        if (!move || lvl < 0) continue;
        available.push_back(m);
        if (lvl > std::max(1, level)) continue;
        std::erase_if(learned, [&](const Json& x) { return x.at("move") == move; });
        learned.push_back(m);
    }
    if (learned.empty() && !available.empty()) {
        std::stable_sort(available.begin(), available.end(), [](const Json& a, const Json& b) { return a.at("level") < b.at("level"); });
        learned.push_back(available.front());
    }
    if (learned.size() > 4) learned.erase(learned.begin(), learned.end() - 4);
    return learned;
}
int masteryOf(const PersonalIndex& personal, int sp, int form, int move) {
    const Json* entry = personalEntry(personal, sp, form);
    if (!entry) return 0;
    int best = 0;
    for (const auto& m : entry->at("learnset")) if (m.at("move") == move) best = std::max(best, m.at("mastery").get<int>());
    return best;
}
int scaleLevel(int level, int percent) {  // +percent, rounded half up, within the game's 1..100
    return std::clamp((level * (100 + percent) + 50) / 100, 1, 100);
}
// ------------------------------------------------------------------------------------------------ streamed rows
// Verified chunk reader (the same shape as core/randomizer.cpp visit(): every chunk is hash-checked before parsing).
template <class Fn>
bool visitRows(const Json& table, const Reader& read, Fn apply) {
    uint32_t total = table.at("row_count"), completed = 0;
    for (const auto& chunk : table.at("rows_files")) {
        std::string file = chunk.at("file");
        Bytes bytes;
        if (file.find('/') != std::string::npos || file.find('\\') != std::string::npos || !read(file, bytes) || bytes.size() > 512 * 1024 ||
            sha256(bytes) != chunk.at("sha256").get<std::string>()) return false;
        auto rows = Json::parse(bytes, nullptr, false);
        if (rows.is_discarded() || !rows.is_array() || rows.size() != chunk.at("count").get<size_t>()) return false;
        for (const auto& row : rows) { if (!apply(row)) return false; ++completed; }
    }
    return completed == total;
}
bool readVerified(const Reader& read, const std::string& file, const std::string& sha, size_t bytes, Bytes& out) {
    if (file.empty() || file.find('/') != std::string::npos || file.find('\\') != std::string::npos || !read(file, out)) return false;
    return out.size() == bytes && out.size() <= 16 * 1024 * 1024 && sha256(out) == sha;
}

struct Choice { int species = 0, form = 0, sex = 0; };

// ------------------------------------------------------------------------------------------------ option ids
template <class E> struct Ids { const char* key; std::vector<std::pair<const char*, E>> ids; };
const Ids<WildMode> wildIds{"wild_mode", {{"off", WildMode::Off}, {"zones", WildMode::Zones}, {"in_zone", WildMode::InZone}, {"random", WildMode::Random}, {"chaos", WildMode::Chaos}}};
const Ids<WildLevels> wildLevelIds{"wild_levels", {{"vanilla", WildLevels::Vanilla}, {"plus10", WildLevels::Plus10}, {"plus25", WildLevels::Plus25}, {"range", WildLevels::Range}, {"mixed", WildLevels::Mixed}}};
const Ids<AlphaRate> alphaIds{"alpha_rate", {{"vanilla", AlphaRate::Vanilla}, {"x2", AlphaRate::X2}, {"x5", AlphaRate::X5}, {"always", AlphaRate::Always}}};
const Ids<Forms> formIds{"forms", {{"vanilla", Forms::Vanilla}, {"random", Forms::Random}}};
const Ids<TrainersMode> trainerIds{"trainers_mode", {{"off", TrainersMode::Off}, {"swap", TrainersMode::Swap}, {"strength", TrainersMode::Strength}, {"random", TrainersMode::Random}}};
const Ids<TrainerLevels> trainerLevelIds{"trainer_levels", {{"vanilla", TrainerLevels::Vanilla}, {"plus10", TrainerLevels::Plus10}, {"plus20", TrainerLevels::Plus20}, {"plus30", TrainerLevels::Plus30}}};
const Ids<TrainerMoves> trainerMoveIds{"trainer_moves", {{"learnset", TrainerMoves::Learnset}, {"legal", TrainerMoves::Legal}, {"any", TrainerMoves::Any}}};
const Ids<TrainerItems> trainerItemIds{"trainer_items", {{"vanilla", TrainerItems::Vanilla}, {"random", TrainerItems::Random}, {"none", TrainerItems::None}}};
const Ids<ResearchRequirements> researchIds{"research_requirements", {{"vanilla", ResearchRequirements::Vanilla}, {"easier", ResearchRequirements::Easier}, {"harder", ResearchRequirements::Harder}}};
const Ids<BaseStats> baseStatIds{"base_stats", {{"vanilla", BaseStats::Vanilla}, {"shuffle", BaseStats::Shuffle}, {"random", BaseStats::Random}}};
const Ids<CatchRate> catchIds{"catch_rate", {{"vanilla", CatchRate::Vanilla}, {"x2", CatchRate::X2}, {"max", CatchRate::Max}}};
const Ids<StartPoint> startIds{"start_point", {{"beginning", StartPoint::Beginning}, {"chapter4", StartPoint::Chapter4}}};

template <class E>
bool readLevel(const Json& values, const Ids<E>& ids, E& out, std::string& error) {
    if (!values.contains(ids.key)) return true;
    const Json& v = values.at(ids.key);
    if (!v.is_string()) { error = std::string(ids.key) + ": expected an option id"; return false; }
    for (const auto& [id, e] : ids.ids) if (v == id) { out = e; return true; }
    error = std::string(ids.key) + ": unknown option '" + v.get<std::string>() + "'";
    return false;
}
template <class E>
const char* idOf(const Ids<E>& ids, E e) {
    for (const auto& [id, x] : ids.ids) if (x == e) return id;
    return "?";
}
bool readToggle(const Json& values, const char* key, bool& out, std::string& error) {
    if (!values.contains(key)) return true;
    const Json& v = values.at(key);
    if (v.is_boolean()) { out = v.get<bool>(); return true; }
    if (v == "on") { out = true; return true; }
    if (v == "off") { out = false; return true; }
    error = std::string(key) + ": expected on/off";
    return false;
}
bool requireVanilla(const Json& values, const char* key, const char* vanilla, std::string& error) {
    if (!values.contains(key) || values.at(key) == vanilla) return true;
    error = std::string(key) + ": not supported by this build (only '" + vanilla + "')";
    return false;
}
}  // namespace

// ================================================================================================ settings
bool settingsFromUi(const Json& uiOptions, Settings& out, std::string& error) {
    out = Settings{};
    if (uiOptions.is_null()) return true;
    if (!uiOptions.is_object()) { error = "ui_options must be an object"; return false; }
    const Json& values = uiOptions.contains("values") ? uiOptions.at("values") : uiOptions;
    if (!values.is_object()) { error = "ui_options.values must be an object"; return false; }
    if (uiOptions.contains("schema") && uiOptions.at("schema") != 2) { error = "ui_options schema must be 2"; return false; }
    if (!readLevel(values, wildIds, out.wild, error) || !readLevel(values, wildLevelIds, out.wildLevels, error) ||
        !readLevel(values, alphaIds, out.alpha, error) || !readLevel(values, formIds, out.forms, error) ||
        !readLevel(values, trainerIds, out.trainers, error) || !readToggle(values, "mega_trainers", out.megaTrainers, error) ||
        !readToggle(values, "dlc_rematches", out.dlcRematches, error) || !readLevel(values, trainerLevelIds, out.trainerLevels, error) ||
        !readLevel(values, trainerMoveIds, out.trainerMoves, error) || !readLevel(values, trainerItemIds, out.trainerItems, error) ||
        !readToggle(values, "research_rewards", out.researchRewards, error) || !readLevel(values, researchIds, out.researchRequirements, error) ||
        !readLevel(values, baseStatIds, out.baseStats, error) || !readLevel(values, catchIds, out.catchRate, error) ||
        !readLevel(values, startIds, out.start, error)) return false;
    // Only release options validated in capabilities.json are accepted from UI reports. Direct Settings callers
    // can exercise experimental algorithms in host tests, but those tiers must not become selectable by accident.
    if (out.wild != WildMode::Off && out.wild != WildMode::Random) { error = "wild_mode: not supported by this build"; return false; }
    if (out.trainers != TrainersMode::Off && out.trainers != TrainersMode::Random) { error = "trainers_mode: not supported by this build"; return false; }
    for (const auto& [key, vanilla] : std::vector<std::pair<const char*, const char*>>{
             {"forms", "vanilla"}, {"trainer_levels", "vanilla"}, {"trainer_moves", "learnset"}, {"trainer_items", "vanilla"},
             {"research_requirements", "vanilla"}, {"base_stats", "vanilla"}, {"catch_rate", "vanilla"},
             {"wild_mega_rate", "vanilla"}, {"held_items", "vanilla"}, {"starting_money", "vanilla"}})
        if (!requireVanilla(values, key, vanilla, error)) return false;
    if (values.contains("starter_level") && values.at("starter_level") != 7) { error = "starter_level: only 7 is supported"; return false; }
    // Starter: vanilla / any = a species from the row's list; random = 0 (the seed decides from the 343 templates).
    std::string mode = values.value("starter_mode", "random");
    static const std::vector<int> vanilla = {152, 498, 158}, any = {1, 4, 7, 152, 158, 498, 650, 653, 656};
    if (mode == "random") out.starter = 0;
    else if (mode == "vanilla" || mode == "any") {
        const auto& list = mode == "vanilla" ? vanilla : any;
        int pick = list.front();
        if (values.contains("starter_pick") && !values.at("starter_pick").is_null()) {
            if (!values.at("starter_pick").is_number_integer()) { error = "starter_pick: expected a species number"; return false; }
            pick = values.at("starter_pick").get<int>();
        }
        if (std::find(list.begin(), list.end(), pick) == list.end()) { error = "starter_pick: species " + std::to_string(pick) + " is not in the " + mode + " list"; return false; }
        out.starter = pick;
    } else { error = "starter_mode: unknown option '" + mode + "'"; return false; }
    return true;
}
Json settingsToUi(const Settings& s) {
    Json v = Json::object();
    v["wild_mode"] = idOf(wildIds, s.wild); v["wild_levels"] = idOf(wildLevelIds, s.wildLevels); v["wild_mega_rate"] = "vanilla";
    v["alpha_rate"] = idOf(alphaIds, s.alpha); v["held_items"] = "vanilla"; v["forms"] = idOf(formIds, s.forms);
    v["trainers_mode"] = idOf(trainerIds, s.trainers); v["mega_trainers"] = s.megaTrainers ? "on" : "off"; v["dlc_rematches"] = s.dlcRematches ? "on" : "off";
    v["trainer_levels"] = idOf(trainerLevelIds, s.trainerLevels); v["trainer_moves"] = idOf(trainerMoveIds, s.trainerMoves); v["trainer_items"] = idOf(trainerItemIds, s.trainerItems);
    static const std::vector<int> vanilla = {152, 498, 158};
    v["starter_mode"] = s.starter == 0 ? "random" : std::find(vanilla.begin(), vanilla.end(), s.starter) != vanilla.end() ? "vanilla" : "any";
    if (s.starter) v["starter_pick"] = s.starter; else v["starter_pick"] = nullptr;
    v["starter_level"] = 7;
    v["research_rewards"] = s.researchRewards ? "on" : "off"; v["research_requirements"] = idOf(researchIds, s.researchRequirements);
    v["base_stats"] = idOf(baseStatIds, s.baseStats); v["catch_rate"] = idOf(catchIds, s.catchRate);
    if (s.start != StartPoint::Beginning) v["start_point"] = idOf(startIds, s.start);  // absent = beginning (older reports)
    return Json{{"schema", 2}, {"values", v}};
}
Settings settingsFromLegacy(const Options& o, bool researchRewards, int starter) {
    Settings s;
    s.wild = o.wild ? WildMode::Random : WildMode::Off;
    s.trainers = o.trainers ? TrainersMode::Random : TrainersMode::Off;
    s.megaTrainers = o.mega_trainers; s.dlcRematches = o.dlc_rematches; s.researchRewards = researchRewards; s.starter = starter;
    return s;
}
Options legacyOptions(const Settings& s) {
    Options o;
    o.wild = s.wild != WildMode::Off; o.trainers = s.trainers != TrainersMode::Off; o.mega_trainers = s.megaTrainers; o.dlc_rematches = s.dlcRematches;
    return o;
}

// ================================================================================================ generation
namespace {
struct WildRow {
    std::string identity, zoneClass, zone;
    int species = 0, form = 0, sex = 0, minLevel = 0, maxLevel = 0, oyabunAdd = 0;
    double oyabun = 0;
    bool authored = false, fixed = false, rockProvider = false, mega = false;
    Json fields;
};
struct TrainerRow {
    std::string trid; int slot = 0; bool mega = false, megaTrainer = false; int teamSize = 0;
    int species = 0, form = 0, item = 0, level = 0, sex = 0;
    std::vector<std::pair<int, bool>> moves;  // original wazaId / isPlusWaza
    Json fields, moveFields;
};
struct Ctx {
    const Assets& a; const Reader& read; const Seed rng; const Settings& s; Result& out; const Progress& progress;
    Pool normalPool, wildMegas, trainerMegas; PersonalIndex personal; std::set<int> stones;
    Json pextra;  // v3.personal.json: entries (stats/catch offsets), multi_forms, tm_moves
    Json counts = Json::object(), v3 = Json::object();
    std::string error;
    bool fail(const std::string& e) { error = e; return false; }
    void report(BuildStage stage, uint32_t done, uint32_t total) { if (progress) progress(stage, done, total); }
};
std::vector<size_t> sortedByLevel(const std::vector<WildRow>& rows, const std::vector<size_t>& idx) {
    std::vector<size_t> v = idx;
    std::stable_sort(v.begin(), v.end(), [&](size_t x, size_t y) {
        const WildRow& p = rows[x]; const WildRow& q = rows[y];
        if (p.minLevel != q.minLevel) return p.minLevel < q.minLevel;
        if (p.maxLevel != q.maxLevel) return p.maxLevel < q.maxLevel;
        return p.identity < q.identity;
    });
    return v;
}
// Groups (zone class -> zone id -> row indices) and the seeded donor zone of every zone of a class: a single cycle
// over the class's zones sorted by id, so no zone keeps its own species. Classes: wild (the 20 wild zones), outzone
// (the 10 street districts), dungeon (4), hyperspace (7). Rows outside any group (story/quest spawns) never move.
using Groups = std::map<std::string, std::map<std::string, std::vector<size_t>>>;
Groups groupRows(const std::vector<WildRow>& rows) {
    Groups g;
    for (size_t i = 0; i < rows.size(); i++) if (!rows[i].zoneClass.empty()) g[rows[i].zoneClass][rows[i].zone].push_back(i);
    return g;
}
std::map<std::string, std::string> zoneDonors(const Seed& rng, const std::string& domain, const Groups& groups, Json& reportInto) {
    std::map<std::string, std::string> donor;
    for (const auto& [cls, zones] : groups) {
        std::vector<std::string> order;
        for (const auto& [zone, rows] : zones) order.push_back(zone);
        if (order.size() < 2) { for (const auto& z : order) donor[z] = z; continue; }
        auto perm = permutation(rng, domain, Json::array({cls}), order.size(), true);
        for (size_t k = 0; k < order.size(); k++) { donor[order[k]] = order[perm[k]]; reportInto[cls][order[k]] = order[perm[k]]; }
    }
    return donor;
}
std::vector<size_t> ordinarySlots(const std::vector<WildRow>& rows, const std::vector<size_t>& zone) {
    std::vector<size_t> v;
    for (size_t i : zone) if (!rows[i].fixed && !rows[i].mega) v.push_back(i);
    return sortedByLevel(rows, v);
}

bool wildTable(Ctx& c, const Json& rockRoute) {
    const Json& index = c.a.v3.at("wild");
    const bool vanillaFields = c.s.wildLevels == WildLevels::Vanilla && c.s.alpha == AlphaRate::Vanilla && c.s.forms == Forms::Vanilla;
    Json& prog = c.out.report["progression"];
    if (c.s.wild == WildMode::Off && vanillaFields) {
        // Today's "wild off": the original file; protectProgression's own wording for the report.
        prog = {{"algorithm", "za202-story-guard-v2"}, {"wild", "original table unchanged"}, {"tm_catalog_count", c.a.progression.at("tm_count")}, {"limitations", c.a.progression.at("limitations")}};
        c.v3["wild"] = {{"mode", idOf(wildIds, c.s.wild)}, {"table", "vanilla"}};
        return true;
    }
    std::vector<WildRow> rows;
    if (!visitRows(index, c.read, [&](const Json& r) {
            WildRow w;
            w.identity = r.at("identity"); w.species = r.at("species"); w.form = r.at("form"); w.sex = r.at("sex");
            w.minLevel = r.at("min_level"); w.maxLevel = r.at("max_level"); w.oyabun = r.at("oyabun"); w.oyabunAdd = r.at("oyabun_add");
            w.authored = r.at("authored"); w.fixed = r.at("fixed"); w.rockProvider = r.at("rock_provider"); w.mega = r.at("mega");
            if (!r.at("zone_class").is_null()) { w.zoneClass = r.at("zone_class"); w.zone = r.at("zone"); }
            w.fields = r.at("fields");
            rows.push_back(std::move(w));
            return true;
        })) return c.fail("Wild row integrity failed");
    Bytes data;
    if (!readVerified(c.read, index.at("template"), index.at("template_sha256"), index.at("bytes"), data)) return c.fail("Wild template integrity failed");
    const uint32_t total = uint32_t(rows.size());
    c.report(BuildStage::Wild, 0, total);
    const bool chaos = c.s.wild == WildMode::Chaos;
    std::vector<Choice> choice(rows.size());
    for (size_t i = 0; i < rows.size(); i++) choice[i] = {rows[i].species, rows[i].form, rows[i].sex};
    Json zoneReport = Json::object();
    int randomized = 0, randomizedMega = 0;
    auto megaEntry = [&](const WildRow& w) -> Json {
        for (const auto& m : c.a.tables.at("mega")) if (m.at("species") == w.species && m.at("mega_form") == w.form) return m;
        return nullptr;
    };
    auto randomMega = [&](size_t i) {
        Json original = megaEntry(rows[i]);
        if (original.is_null()) return c.fail("Mega slot without a Mega entry");
        const Json* m = c.wildMegas.choose(c.rng, "wild-mega", rows[i].identity, original);
        if (!m) return c.fail("Empty wild Mega pool");
        choice[i] = {m->at("species"), m->at("mega_form"), 0};
        return true;
    };
    auto randomSpecies = [&](size_t i, int sex) {
        const Json* n = c.normalPool.choose(c.rng, "wild", rows[i].identity, Json(rows[i].species));
        if (!n) return c.fail("Empty species pool");
        choice[i] = {n->get<int>(), 0, sex};
        return true;
    };
    if (c.s.wild == WildMode::Random || chaos) {
        for (size_t i = 0; i < rows.size(); i++) {
            const WildRow& w = rows[i];
            // Today's core samples every non-boss row and counts it ("wild" / "wild-mega"); protectProgression then
            // restores the authored rows (the 23 wild Mega slots are among them). Same tables, same counts here.
            (w.mega ? randomizedMega : randomized)++;
            if (!chaos && w.rockProvider) { choice[i] = {rockRoute.at("species"), 0, 0}; continue; }
            if (!chaos && w.fixed) continue;
            if (w.mega) { if (!randomMega(i)) return false; continue; }
            if (!randomSpecies(i, chaos ? -1 : 0)) return false;  // today writes sex 0; chaos lets the game roll it
        }
    } else if (c.s.wild == WildMode::Zones || c.s.wild == WildMode::InZone) {
        Groups groups = groupRows(rows);
        if (c.s.wild == WildMode::Zones) {
            auto donor = zoneDonors(c.rng, "wild-zone-shuffle", groups, zoneReport);
            for (const auto& [cls, zones] : groups)
                for (const auto& [zone, members] : zones) {
                    auto slots = ordinarySlots(rows, members), from = ordinarySlots(rows, groups.at(cls).at(donor.at(zone)));
                    if (from.empty() || donor.at(zone) == zone) continue;
                    for (size_t k = 0; k < slots.size(); k++) {
                        const WildRow& d = rows[from[k * from.size() / slots.size()]];
                        choice[slots[k]] = {d.species, d.form, d.sex};
                        randomized++;
                    }
                }
        } else {
            for (const auto& [cls, zones] : groups)
                for (const auto& [zone, members] : zones) {
                    auto slots = ordinarySlots(rows, members);
                    if (slots.size() < 2) continue;
                    auto perm = permutation(c.rng, "wild-in-zone", Json::array({zone}), slots.size(), false);
                    for (size_t k = 0; k < slots.size(); k++) {
                        const WildRow& d = rows[slots[perm[k]]];
                        choice[slots[k]] = {d.species, d.form, d.sex};
                        if (perm[k] != k) randomized++;
                    }
                }
        }
        for (size_t i = 0; i < rows.size(); i++) if (rows[i].rockProvider) choice[i] = {rockRoute.at("species"), 0, 0};
    }
    // Forms: a random present, non-Mega form of the chosen species (implied by Chaos; never on fixed or Mega slots).
    int formsChanged = 0;
    if (c.s.forms == Forms::Random || chaos) {
        const Json& multi = c.pextra.at("multi_forms");
        for (size_t i = 0; i < rows.size(); i++) {
            const WildRow& w = rows[i];
            if (w.mega || (!chaos && (w.fixed || w.rockProvider))) continue;
            auto it = multi.find(std::to_string(choice[i].species));
            if (it == multi.end()) continue;
            const Json& forms = *it;
            int form = forms[size_t(c.rng.number("wild-form", w.identity, forms.size()))];
            if (form != choice[i].form) { choice[i].form = form; formsChanged++; }
        }
    }
    // Levels: keep the tutorial/rock-route spawns (except in Chaos); +X% rounds half up and clamps to 1..100.
    std::vector<std::pair<int, int>> levels(rows.size());
    for (size_t i = 0; i < rows.size(); i++) levels[i] = {rows[i].minLevel, rows[i].maxLevel};
    int levelsChanged = 0;
    if (c.s.wildLevels != WildLevels::Vanilla) {
        auto protectedRow = [&](size_t i) { return !chaos && rows[i].rockProvider; };
        if (c.s.wildLevels == WildLevels::Plus10 || c.s.wildLevels == WildLevels::Plus25) {
            int pct = c.s.wildLevels == WildLevels::Plus10 ? 10 : 25;
            for (size_t i = 0; i < rows.size(); i++) if (!protectedRow(i)) levels[i] = {scaleLevel(rows[i].minLevel, pct), scaleLevel(rows[i].maxLevel, pct)};
        } else if (c.s.wildLevels == WildLevels::Range) {
            for (size_t i = 0; i < rows.size(); i++) {
                if (protectedRow(i)) continue;
                int lo = std::clamp(rows[i].minLevel + int(c.rng.number("wild-level-range-min", rows[i].identity, 11)) - 5, 1, 100);
                int hi = std::clamp(rows[i].maxLevel + int(c.rng.number("wild-level-range-max", rows[i].identity, 11)) - 5, 1, 100);
                if (lo > hi) std::swap(lo, hi);
                levels[i] = {lo, hi};
            }
        } else {  // Mixed: every zone takes another zone's level ranges, slot by slot in level order
            Groups groups = groupRows(rows);
            auto donor = zoneDonors(c.rng, "wild-level-zones", groups, c.v3["wild_level_zones"]);
            for (const auto& [cls, zones] : groups)
                for (const auto& [zone, members] : zones) {
                    auto slots = sortedByLevel(rows, members), from = sortedByLevel(rows, groups.at(cls).at(donor.at(zone)));
                    if (from.empty() || donor.at(zone) == zone) continue;
                    for (size_t k = 0; k < slots.size(); k++) {
                        if (protectedRow(slots[k])) continue;
                        const WildRow& d = rows[from[k * from.size() / slots.size()]];
                        levels[slots[k]] = {d.minLevel, d.maxLevel};
                    }
                }
        }
        for (size_t i = 0; i < rows.size(); i++) if (levels[i] != std::make_pair(rows[i].minLevel, rows[i].maxLevel)) levelsChanged++;
    }
    // Alpha: scale existing nonzero chances, capped at 100. Zero-chance and fixed quest Alpha rows stay as
    // authored. Keep the early Rock providers too: their Alpha level bonus must not become guaranteed.
    std::vector<double> alpha(rows.size());
    int alphaChanged = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        double p = rows[i].oyabun;
        if (p > 0 && p < 100 && (chaos || !rows[i].rockProvider)) {
            if (c.s.alpha == AlphaRate::X2) p = std::min(100.0, p * 2);
            else if (c.s.alpha == AlphaRate::X5) p = std::min(100.0, p * 5);
            else if (c.s.alpha == AlphaRate::Always) p = 100;
        }
        alpha[i] = p;
        if (p != rows[i].oyabun) alphaChanged++;
    }
    // Writes.
    Json changes = Json::array();
    int retained = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        const WildRow& w = rows[i]; const Json& f = w.fields;
        if (!patch(data, f.at("devNo"), choice[i].species) || !patch(data, f.at("formNo"), choice[i].form) || !patch(data, f.at("sex"), choice[i].sex)) return c.fail("Invalid wild patch");
        if (!patch(data, f.at("minLevel"), levels[i].first) || !patch(data, f.at("maxLevel"), levels[i].second)) return c.fail("Invalid wild level patch");
        if (alpha[i] != w.oyabun && !patch(data, f.at("oyabunProbability"), alpha[i])) return c.fail("Invalid Alpha patch");
        if (w.fixed && !w.rockProvider && choice[i].species == w.species) retained++;
        if (choice[i].species != w.species) changes.push_back({{"id", w.identity}, {"from", w.species}, {"species", choice[i].species}});
        if ((i + 1) % 32 == 0 || i + 1 == rows.size()) c.report(BuildStage::Wild, uint32_t(i + 1), total);
    }
    if (randomized) c.counts["wild"] = randomized;
    if (randomizedMega) c.counts["wild-mega"] = randomizedMega;
    c.out.tables["wild"] = std::move(data);
    prog = {{"algorithm", "za202-story-guard-v2"}, {"tm_catalog_count", c.a.progression.at("tm_count")}, {"guarded_encounters", rows.size()},
            {"retained_original_encounters", retained}, {"changes", changes},
            {"scope", chaos ? "Chaos: no early-rock provider, authored move sets randomized too" : "Seeded early rock provider plus authored move sets; all other encounters use the original seeded randomizer output"},
            {"limitations", c.a.progression.at("limitations")}};
    if (chaos) prog["rock_route_applied"] = false;
    c.v3["wild"] = {{"mode", idOf(wildIds, c.s.wild)}, {"table", "progression template"}, {"species_changed", changes.size()}, {"zones", zoneReport},
                    {"levels", idOf(wildLevelIds, c.s.wildLevels)}, {"levels_changed", levelsChanged}, {"alpha", idOf(alphaIds, c.s.alpha)}, {"alpha_changed", alphaChanged},
                    {"forms", chaos ? "random" : idOf(formIds, c.s.forms)}, {"forms_changed", formsChanged}, {"sex_written", chaos ? -1 : 0}};
    return true;
}

// Trainers whose whole teams can trade places: same team size and the same Mega slot positions, sorted by their
// strongest level; groups of at least four trainers spanning about ten levels; one seeded cycle per group.
struct Team { std::string trid; int maxLevel = 0; std::vector<size_t> slots; int key = 0; };
std::map<std::string, std::string> swapDonors(const Seed& rng, const std::vector<TrainerRow>& rows, Json& reportInto) {
    std::map<std::string, Team> teams;
    for (size_t i = 0; i < rows.size(); i++) {
        Team& t = teams[rows[i].trid];
        t.trid = rows[i].trid; t.maxLevel = std::max(t.maxLevel, rows[i].level); t.slots.push_back(i);
    }
    std::map<int, std::vector<Team*>> byKey;
    for (auto& [trid, t] : teams) {
        int mask = 0;
        for (size_t k = 0; k < t.slots.size(); k++) if (rows[t.slots[k]].mega) mask |= 1 << k;
        t.key = int(t.slots.size()) * 64 + mask;
        byKey[t.key].push_back(&t);
    }
    std::map<std::string, std::string> donor;
    int groupsFormed = 0, trainersMoved = 0;
    for (auto& [key, list] : byKey) {
        std::sort(list.begin(), list.end(), [](const Team* a, const Team* b) { return a->maxLevel != b->maxLevel ? a->maxLevel < b->maxLevel : a->trid < b->trid; });
        std::vector<std::vector<Team*>> groups;
        std::vector<Team*> cur;
        for (Team* t : list) {
            if (!cur.empty() && cur.size() >= 4 && t->maxLevel - cur.front()->maxLevel > 10) { groups.push_back(cur); cur.clear(); }
            cur.push_back(t);
        }
        if (!cur.empty()) { if (cur.size() < 4 && !groups.empty()) groups.back().insert(groups.back().end(), cur.begin(), cur.end()); else groups.push_back(cur); }
        for (size_t g = 0; g < groups.size(); g++) {
            auto& members = groups[g];
            if (members.size() < 2) { for (Team* t : members) donor[t->trid] = t->trid; continue; }
            auto perm = permutation(rng, "trainer-swap", Json::array({key, g}), members.size(), true);
            for (size_t k = 0; k < members.size(); k++) donor[members[k]->trid] = members[perm[k]]->trid;
            groupsFormed++; trainersMoved += int(members.size());
        }
    }
    reportInto = {{"groups", groupsFormed}, {"trainers_moved", trainersMoved}};
    return donor;
}

bool trainersTable(Ctx& c) {
    const Json& index = c.a.v3.at("trainers");
    const bool fieldsVanilla = c.s.trainerLevels == TrainerLevels::Vanilla && c.s.trainerMoves == TrainerMoves::Learnset && c.s.trainerItems == TrainerItems::Vanilla;
    if (c.s.trainers == TrainersMode::Off && !c.s.megaTrainers && fieldsVanilla) { c.v3["trainers"] = {{"mode", "off"}, {"table", "vanilla"}}; return true; }
    std::vector<TrainerRow> rows;
    if (!visitRows(index, c.read, [&](const Json& r) {
            TrainerRow t;
            t.trid = r.at("identity")[0]; t.slot = r.at("identity")[1]; t.mega = r.at("mega"); t.megaTrainer = r.at("mega_trainer"); t.teamSize = r.at("team_size");
            t.species = r.at("species"); t.form = r.at("form"); t.item = r.at("item"); t.level = r.at("level"); t.sex = r.at("sex");
            for (const auto& m : r.at("moves")) t.moves.emplace_back(m.at("move").get<int>(), m.at("plus").get<bool>());
            if (t.moves.size() != 4 || r.at("move_fields").size() != 4) return false;
            t.fields = r.at("fields"); t.moveFields = r.at("move_fields");
            rows.push_back(std::move(t));
            return true;
        })) return c.fail("Trainer row integrity failed");
    Bytes data;
    if (!readVerified(c.read, index.at("template"), index.at("template_sha256"), index.at("bytes"), data)) return c.fail("Trainer template integrity failed");
    const uint32_t total = uint32_t(rows.size());
    c.report(BuildStage::Trainers, 0, total);
    std::map<std::string, std::vector<size_t>> teamSlots;
    for (size_t i = 0; i < rows.size(); i++) teamSlots[rows[i].trid].push_back(i);
    std::map<std::string, std::string> donor;
    Json swapReport = Json::object();
    if (c.s.trainers == TrainersMode::Swap) donor = swapDonors(c.rng, rows, swapReport);
    std::map<std::pair<int, int>, int> bst;
    for (const auto& e : c.pextra.at("entries")) { int sum = 0; for (const auto& x : e.at("stats")) sum += x.get<int>(); bst[{e.at("species"), e.at("form")}] = sum; }
    const Json& tmMoves = c.pextra.at("tm_moves");
    std::vector<int> usable = c.a.v3.at("moves").at("usable").get<std::vector<int>>();
    std::vector<int> heldPool = index.at("held_item_pool").get<std::vector<int>>();
    if (usable.empty() || heldPool.empty()) return c.fail("Trainer move or item pool missing");
    const int levelPct = c.s.trainerLevels == TrainerLevels::Plus10 ? 10 : c.s.trainerLevels == TrainerLevels::Plus20 ? 20 : c.s.trainerLevels == TrainerLevels::Plus30 ? 30 : 0;
    int randomized = 0, randomizedMega = 0, levelsChanged = 0, itemsChanged = 0, movesRewritten = 0;
    for (size_t i = 0; i < rows.size(); i++) {
        const TrainerRow& r = rows[i];
        const Json identity = Json::array({r.trid, r.slot});
        int species = r.species, form = r.form, item = r.item, sex = r.sex, level = levelPct ? scaleLevel(r.level, levelPct) : r.level;
        if (level != r.level) levelsChanged++;
        std::vector<std::pair<int, bool>> moves = r.moves;
        bool speciesWritten = false, movesFromLearnset = false;
        if (r.mega) {
            if (c.s.megaTrainers) {
                const Json* m = c.trainerMegas.choose(c.rng, "trainer-mega", identity, [&](const Json& x) { return x.at("species") == r.species && x.at("form") == r.form; });
                if (!m) return c.fail("Empty trainer Mega pool");
                species = m->at("species"); form = m->at("form"); item = m->at("item"); sex = 0;
                speciesWritten = movesFromLearnset = true; randomizedMega++;
            }
        } else if (c.s.trainers == TrainersMode::Random) {
            const Json* n = c.normalPool.choose(c.rng, "trainer", identity, Json(r.species));
            if (!n) return c.fail("Empty species pool");
            species = n->get<int>(); form = 0; if (c.stones.contains(item)) item = 0; sex = 0;
            speciesWritten = movesFromLearnset = true; randomized++;
        } else if (c.s.trainers == TrainersMode::Strength) {
            auto found = bst.find({r.species, r.form});
            int target = found != bst.end() ? found->second : bst.at({r.species, 0});
            int band = std::max(20, target / 10);
            const Json* n = nullptr;
            for (int widen = 0; widen < 12 && !n; widen++, band = band * 3 / 2) {
                size_t count = 0;
                auto reject = [&](const Json& v) { int sp = v.get<int>(); return sp == r.species || std::abs(bst.at({sp, 0}) - target) > band; };
                for (const auto& v : c.normalPool.values) if (!reject(v)) count++;
                if (count >= 8) n = c.normalPool.choose(c.rng, "trainer-strength", identity, reject);
            }
            if (!n) return c.fail("No species of similar strength");
            species = n->get<int>(); form = 0; if (c.stones.contains(item)) item = 0; sex = 0;
            speciesWritten = movesFromLearnset = true; randomized++;
        } else if (c.s.trainers == TrainersMode::Swap) {
            const std::string& from = donor.at(r.trid);
            if (from != r.trid) {
                const auto& mine = teamSlots.at(r.trid); const auto& theirs = teamSlots.at(from);
                size_t pos = size_t(std::find(mine.begin(), mine.end(), i) - mine.begin());
                if (pos >= theirs.size()) return c.fail("Swap teams of different size");
                const TrainerRow& d = rows[theirs[pos]];
                if (d.mega) return c.fail("Swap onto a Mega slot");
                species = d.species; form = d.form; item = c.stones.contains(d.item) ? 0 : d.item; sex = d.sex; moves = d.moves;
                speciesWritten = true; randomized++;
            }
        }
        if (!r.mega && c.s.trainerItems == TrainerItems::Random) { item = heldPool[size_t(c.rng.number("trainer-item", identity, heldPool.size()))]; }
        else if (!r.mega && c.s.trainerItems == TrainerItems::None) item = 0;
        if (item != r.item) itemsChanged++;
        // Moves: today's learnset-by-level for a randomized species; "legal" = random moves the species can learn
        // (level-up or TM, implemented only); "any" = any implemented move. Four distinct moves when possible.
        bool writeMoves = speciesWritten;
        if (c.s.trainerMoves == TrainerMoves::Learnset) {
            if (movesFromLearnset) {
                auto learned = learnsetMoves(c.personal, species, form, level);
                if (learned.empty()) return c.fail("Missing moves");
                moves.clear();
                for (size_t k = 0; k < 4; k++) {
                    int move = k < learned.size() ? int(learned[k].at("move")) : 0;
                    int mastery = k < learned.size() ? int(learned[k].at("mastery")) : 0;
                    moves.emplace_back(move, move && mastery > 0 && mastery <= level);
                }
            }
        } else {
            std::vector<int> candidates;
            if (c.s.trainerMoves == TrainerMoves::Any) candidates = usable;
            else {
                std::set<int> set;
                if (const Json* e = personalEntry(c.personal, species, form)) for (const auto& m : e->at("learnset")) if (m.at("move") != 0) set.insert(m.at("move").get<int>());
                auto key = std::to_string(species) + ":" + std::to_string(form);
                auto it = tmMoves.find(key);
                if (it == tmMoves.end()) it = tmMoves.find(std::to_string(species) + ":0");
                if (it != tmMoves.end()) for (const auto& m : *it) set.insert(m.get<int>());
                candidates.assign(set.begin(), set.end());
            }
            moves.clear();
            for (int k = 0; k < 4; k++) {
                if (candidates.empty()) { moves.emplace_back(0, false); continue; }
                size_t at = size_t(c.rng.number("trainer-move", Json::array({r.trid, r.slot, k}), candidates.size()));
                int move = candidates[at];
                candidates.erase(candidates.begin() + long(at));
                int mastery = c.s.trainerMoves == TrainerMoves::Legal ? masteryOf(c.personal, species, form, move) : 0;
                moves.emplace_back(move, mastery > 0 && mastery <= level);
            }
            movesRewritten++;
            writeMoves = true;
        }
        const Json& f = r.fields;
        if (speciesWritten && (!patch(data, f.at("devId"), species) || !patch(data, f.at("formId"), form) || !patch(data, f.at("sex"), sex))) return c.fail("Invalid trainer patch");
        if ((speciesWritten || item != r.item) && !patch(data, f.at("item"), item)) return c.fail("Invalid trainer item patch");
        if (level != r.level && !patch(data, f.at("level"), level)) return c.fail("Invalid trainer level patch");
        if (writeMoves)
            for (size_t k = 0; k < 4; k++)
                if (!patch(data, r.moveFields[k].at("wazaId"), moves[k].first) || !patch(data, r.moveFields[k].at("isPlusWaza"), moves[k].second)) return c.fail("Invalid move patch");
        if ((i + 1) % 32 == 0 || i + 1 == rows.size()) c.report(BuildStage::Trainers, uint32_t(i + 1), total);
    }
    if (randomized) c.counts["trainer"] = randomized;
    if (randomizedMega) c.counts["trainer-mega"] = randomizedMega;
    c.out.tables["trainers"] = std::move(data);
    c.v3["trainers"] = {{"mode", idOf(trainerIds, c.s.trainers)}, {"table", "template"}, {"slots_changed", randomized}, {"mega_slots_changed", randomizedMega},
                        {"levels", idOf(trainerLevelIds, c.s.trainerLevels)}, {"levels_changed", levelsChanged}, {"moves", idOf(trainerMoveIds, c.s.trainerMoves)},
                        {"moves_rewritten", movesRewritten}, {"items", idOf(trainerItemIds, c.s.trainerItems)}, {"items_changed", itemsChanged}, {"swap", swapReport}};
    return true;
}

// core/randomizer.cpp's DLC rematch shuffle, unchanged: one seeded cycle over the 21 Mega rematch bosses.
bool dlcTable(Ctx& c) {
    if (!c.s.dlcRematches) { c.v3["dlc_boss"] = {{"table", "vanilla"}}; return true; }
    const Json& table = c.a.tables.at("tables").at("dlc_boss");
    Bytes data;
    if (!readVerified(c.read, table.at("file"), table.at("sha256"), table.at("bytes"), data)) return c.fail("Table integrity failed");
    Json rows = Json::array();
    if (!visitRows(table, c.read, [&](const Json& r) { rows.push_back(r); return true; })) return c.fail("DLC row integrity failed");
    c.report(BuildStage::Dlc, 0, uint32_t(rows.size()));
    if (rows.size() > 1) {
        std::vector<std::string> ids;
        std::map<std::string, Json> sources;
        for (const auto& r : rows) { std::string id = r.at("identity"); ids.push_back(id); sources[id] = r.at("source"); }
        std::sort(ids.begin(), ids.end());
        for (size_t i = ids.size() - 1; i > 0; i--) std::swap(ids[i], ids[c.rng.number("dlc-mega-rematch", i, i + 1)]);
        std::map<std::string, std::string> mapping;
        for (size_t i = 0; i < ids.size(); i++) mapping[ids[i]] = ids[(i + 1) % ids.size()];
        for (const auto& r : rows)
            for (const auto& [f, value] : sources.at(mapping.at(r.at("identity").get<std::string>())).items())
                if (!patch(data, r.at("fields").at(f), value)) return c.fail("Invalid DLC patch");
        c.counts["dlc-mega-rematch"] = rows.size();
    }
    c.report(BuildStage::Dlc, uint32_t(rows.size()), uint32_t(rows.size()));
    c.out.tables["dlc_boss"] = std::move(data);
    c.v3["dlc_boss"] = {{"table", "template"}, {"shuffled", rows.size()}};
    return true;
}

bool researchTable(Ctx& c) {
    if (c.s.researchRewards) {
        std::string error;
        if (!za::native::randomizeResearchRewards(c.a.rewards, c.read, c.out.report.at("seed"), c.out, error)) return c.fail(error);
    }
    if (c.s.researchRequirements == ResearchRequirements::Vanilla) { c.v3["research_requirements"] = {{"mode", "vanilla"}}; return true; }
    const Json& index = c.a.v3.at("research");
    if (!c.out.tables.contains("research_rewards")) {
        Bytes data;
        if (!readVerified(c.read, index.at("file"), index.at("sha256"), c.a.rewards.at("bytes"), data)) return c.fail("Reward table integrity failed");
        c.out.tables["research_rewards"] = std::move(data);
    }
    Bytes& data = c.out.tables.at("research_rewards");
    uint32_t previous = 0;
    Json changes = Json::array();
    for (const auto& row : index.at("rows")) {
        size_t p = row.at("points_offset"); uint32_t points = row.at("points");
        if (p > data.size() || data.size() - p < 4) return c.fail("Invalid research points offset");
        uint32_t have = uint32_t(data[p]) | (uint32_t(data[p + 1]) << 8) | (uint32_t(data[p + 2]) << 16) | (uint32_t(data[p + 3]) << 24);
        if (have != points) return c.fail("Research points mismatch");
        uint64_t scaled = c.s.researchRequirements == ResearchRequirements::Easier ? uint64_t(points) / 2 : uint64_t(points) * 3 / 2;
        uint32_t next = uint32_t(std::min<uint64_t>(std::max<uint64_t>(scaled, uint64_t(previous) + 1), std::numeric_limits<uint32_t>::max()));
        for (int i = 0; i < 4; i++) data[p + i] = uint8_t(next >> (8 * i));
        changes.push_back({{"level", row.at("level")}, {"from", points}, {"points", next}});
        previous = next;
    }
    c.out.report["table_sha256"]["research_rewards"] = sha256(data);
    c.v3["research_requirements"] = {{"mode", idOf(researchIds, c.s.researchRequirements)}, {"changes", changes}};
    return true;
}

bool personalTable(Ctx& c) {
    if (c.s.baseStats == BaseStats::Vanilla && c.s.catchRate == CatchRate::Vanilla) return true;
    const Json& index = c.a.v3.at("personal");
    Bytes data;
    if (!readVerified(c.read, index.at("file"), index.at("sha256"), index.at("bytes"), data)) return c.fail("Personal table integrity failed");
    int statsChanged = 0, catchChanged = 0;
    for (const auto& e : c.pextra.at("entries")) {
        if (!e.at("present").get<bool>()) continue;
        const Json identity = Json::array({e.at("species"), e.at("form")});
        size_t so = e.at("stats_offset");
        if (so > data.size() || data.size() - so < 6) return c.fail("Invalid base stat offset");
        std::vector<int> stats = e.at("stats").get<std::vector<int>>();
        if (stats.size() != 6) return c.fail("Invalid base stats");
        for (int k = 0; k < 6; k++) if (data[so + k] != uint8_t(stats[k])) return c.fail("Base stat mismatch");
        if (c.s.baseStats == BaseStats::Shuffle) {
            auto perm = permutation(c.rng, "base-stats", identity, 6, false);
            std::vector<int> next(6);
            for (int k = 0; k < 6; k++) next[k] = stats[perm[k]];
            if (next != stats) statsChanged++;
            stats = next;
        } else if (c.s.baseStats == BaseStats::Random) {
            std::vector<int> next(6);
            for (int k = 0; k < 6; k++) {
                Json id = identity; id.push_back(k);
                int pct = 70 + int(c.rng.number("base-stat-random", id, 61));
                next[k] = std::clamp((stats[k] * pct + 50) / 100, 1, 255);
            }
            if (next != stats) statsChanged++;
            stats = next;
        }
        for (int k = 0; k < 6; k++) data[so + k] = uint8_t(stats[k]);
        if (c.s.catchRate != CatchRate::Vanilla && e.contains("catch_offset")) {
            size_t co = e.at("catch_offset"); int rate = e.at("catch");
            if (co >= data.size() || data[co] != uint8_t(rate)) return c.fail("Catch rate mismatch");
            int next = c.s.catchRate == CatchRate::Max ? 255 : std::min(255, rate * 2);
            if (next != rate) catchChanged++;
            data[co] = uint8_t(next);
        }
    }
    c.out.tables[PersonalTable] = std::move(data);
    c.v3["personal"] = {{"path", index.at("path")}, {"base_stats", idOf(baseStatIds, c.s.baseStats)}, {"stats_changed", statsChanged}, {"catch_rate", idOf(catchIds, c.s.catchRate)}, {"catch_changed", catchChanged}};
    return true;
}
}  // namespace

// ================================================================================================ chapter-4 start
namespace {
bool hexPatches(const Json& list, Bytes& save, std::string& error) {
    if (!list.is_array()) { error = "Chapter-4 patch list malformed"; return false; }
    size_t previous = 0;
    for (const auto& p : list) {
        if (!p.is_object() || !p.contains("offset") || !p.contains("hex") || !p.at("offset").is_number_unsigned() || !p.at("hex").is_string()) {
            error = "Chapter-4 patch malformed"; return false;
        }
        const size_t pos = p.at("offset").get<size_t>();
        const std::string& h = p.at("hex").get_ref<const std::string&>();
        if (h.empty() || h.size() % 2 || pos < previous || pos > save.size() || h.size() / 2 > save.size() - pos) { error = "Chapter-4 patch out of range"; return false; }
        for (size_t i = 0; i < h.size(); i += 2) {
            auto nib = [](char c) { return c >= '0' && c <= '9' ? c - '0' : c >= 'a' && c <= 'f' ? c - 'a' + 10 : c >= 'A' && c <= 'F' ? c - 'A' + 10 : -1; };
            const int hi = nib(h[i]), lo = nib(h[i + 1]);
            if (hi < 0 || lo < 0) { error = "Chapter-4 patch data malformed"; return false; }
            save[pos + i / 2] = uint8_t(hi * 16 + lo);
        }
        previous = pos + h.size() / 2;
    }
    return true;
}
}  // namespace

bool applyChapter4Start(const Json& chapter4, int starter, Bytes& save, Json& report, std::string& error) {
    if (!chapter4.is_object() || chapter4.value("format", "") != "za-chapter4-start-v1" || chapter4.value("schema", 0) != 1 ||
        !chapter4.contains("common_patches") || !chapter4.contains("entries") || !chapter4.at("entries").is_array()) {
        error = "This build has no chapter-4 start data (chapter4-start.json)";
        return false;
    }
    const Json* entry = nullptr;
    for (const auto& e : chapter4.at("entries"))
        if (e.is_object() && e.value("species", -1) == starter) { entry = &e; break; }
    if (!entry || !entry->contains("start_sha256") || !entry->contains("output_sha256") || !entry->contains("patches")) {
        error = "No chapter-4 start for starter " + std::to_string(starter);
        return false;
    }
    if (sha256(save) != entry->at("start_sha256").get<std::string>()) { error = "Chapter-4 start: the starting save is not the expected one"; return false; }
    Bytes edited = save;
    if (!hexPatches(chapter4.at("common_patches"), edited, error) || !hexPatches(entry->at("patches"), edited, error)) return false;
    if (sha256(edited) != entry->at("output_sha256").get<std::string>()) { error = "Chapter-4 save integrity failed"; return false; }
    save = std::move(edited);
    report["start_point"] = "chapter4";
    report["chapter4"] = {{"target_phase", chapter4.value("target_phase", 0)}, {"starter_level", chapter4.value("starter_level", 0)},
                          {"spec_sha256", chapter4.value("spec_sha256", "")}, {"save_sha256", sha256(save)}};
    report["starter_level"] = chapter4.value("starter_level", report.value("starter_level", 7));
    report["save_sha256"] = sha256(save);
    report["in_game_verified"] = false;
    return true;
}

bool generateRun(const Assets& a, const Reader& read, const std::string& seed, const Settings& s, const Json& uiOptionsEcho, Result& out, const Progress& progress) {
    out = {};
    auto fail = [&](const std::string& e) { out.tables.clear(); out.save.clear(); out.report = Json(); out.error = e; return false; };
    if (!a.v3.is_object() || a.v3.value("schema", "") != "za-rando-v3-1" || a.v3.value("build_id", "") != Build || a.v3.value("algorithm", "") != Algorithm ||
        a.v3.value("base_algorithm", "") != BaseAlgorithm) return fail("v3 asset mismatch");
    // 1. Vanilla tables + the starting save through the unchanged core (its own integrity checks and starter logic).
    Result base;
    Options none;
    none.wild = none.trainers = none.mega_trainers = none.dlc_rematches = false;
    Progress starterOnly = progress ? Progress([&](BuildStage st, uint32_t d, uint32_t n) { if (st == BuildStage::Index || st == BuildStage::Starter) progress(st, d, n); }) : Progress();
    if (!generate(a.tables, a.starters, read, seed, none, s.starter, base, starterOnly)) return fail(base.error);
    out.save = std::move(base.save);
    out.tables = std::move(base.tables);  // trainers/wild/dlc_boss vanilla; replaced below when randomized
    out.report = base.report;
    Ctx c{a, read, Seed(seed), s, out, progress, Pool(a.tables.at("pool")), Pool(a.tables.at("mega")), Pool(a.tables.at("trainer_megas")), {}, {}, {}, Json::object(), Json::object(), {}};
    for (const auto& p : a.tables.at("personal")) c.personal.emplace(std::make_pair(int(p.at("species")), int(p.at("form"))), &p);
    {
        const Json& pi = a.v3.at("personal");
        Bytes bytes;
        if (!readVerified(read, pi.at("entries_file"), pi.at("entries_sha256"), pi.at("entries_bytes"), bytes)) return fail("Personal index integrity failed");
        c.pextra = Json::parse(bytes, nullptr, false);
        if (c.pextra.is_discarded() || !c.pextra.is_object() || !c.pextra.contains("entries") || !c.pextra.contains("multi_forms") || !c.pextra.contains("tm_moves")) return fail("Personal index malformed");
    }
    for (const auto& m : a.tables.at("mega")) if (int(m.at("item")) > 0) c.stones.insert(m.at("item").get<int>());
    // The early-rock route is planned exactly as protectProgression does (reported even when it is not applied).
    std::string error;
    Json route;
    if (!za::native::planRockRoute(a.progression, seed, s.wild != WildMode::Off, s.researchRewards, route, error)) return fail(error);
    out.report["rock_route"] = route;
    out.report["options"] = {{"wild", s.wild != WildMode::Off}, {"trainers", s.trainers != TrainersMode::Off}, {"mega_trainers", s.megaTrainers}, {"dlc_rematches", s.dlcRematches}, {"research_rewards", s.researchRewards}};
    if (!trainersTable(c)) return fail(c.error);
    if (!wildTable(c, route)) return fail(c.error);
    if (!dlcTable(c)) return fail(c.error);
    if (!researchTable(c)) return fail(c.error);
    if (!personalTable(c)) return fail(c.error);
    if (s.start == StartPoint::Chapter4) {
        if (!applyChapter4Start(a.chapter4, out.report.value("starter", 0), out.save, out.report, error)) return fail(error);
    }
    out.report["counts"] = c.counts;
    out.report["table_sha256"] = Json::object();
    for (const auto& [name, data] : out.tables) out.report["table_sha256"][name] = sha256(data);
    out.report["v3_algorithm"] = Algorithm;
    out.report["ui_options"] = uiOptionsEcho;
    out.report["ui_options_resolved"] = settingsToUi(s);
    out.report["v3"] = c.v3;
    if (progress) progress(BuildStage::Complete, 1, 1);
    return true;
}
}  // namespace za::v3
