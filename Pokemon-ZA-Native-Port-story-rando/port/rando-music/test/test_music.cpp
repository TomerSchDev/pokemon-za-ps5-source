// Host tests (ASan/UBSan) for the r29-music core and run store.
//   test_music PLAN.json ROMFS_BIN OUT_DIR
// Uses the game's BGM.bnk read-only from the RomFS image; writes shuffled copies only into OUT_DIR (for the
// independent Python oracle) and run folders only into OUT_DIR/runs.
#include "run_store.hpp"
#include "za_music.hpp"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <map>
#include <set>
#include <sys/stat.h>

using namespace za;
using namespace za::native;

static int failures = 0;
#define CHECK(c)                                                       \
    do {                                                               \
        if (!(c)) {                                                    \
            fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); \
            failures++;                                                \
        }                                                              \
    } while (0)

static uint32_t rd32(const Bytes& d, size_t p) {
    return uint32_t(d[p]) | (uint32_t(d[p + 1]) << 8) | (uint32_t(d[p + 2]) << 16) | (uint32_t(d[p + 3]) << 24);
}
static void writeAll(const std::string& path, const Bytes& data) {
    std::ofstream f(path, std::ios::binary);
    f.write(reinterpret_cast<const char*>(data.data()), std::streamsize(data.size()));
    CHECK(f.good());
}

struct Plan {
    Json j;
    std::map<uint32_t, size_t> unitOf;  // song -> unit
    std::vector<std::string> category;  // unit -> category
};
static uint32_t hex(const std::string& s) { return uint32_t(std::stoul(s, nullptr, 16)); }

int main(int argc, char** argv) {
    if (argc != 4) return fprintf(stderr, "usage: test_music PLAN ROMFS OUT\n"), 2;
    const std::string planPath = argv[1], image = argv[2], out = argv[3];
    Bytes raw;
    CHECK(readFile(planPath, raw, 4u << 20));
    const std::string planText(raw.begin(), raw.end());
    Plan plan;
    plan.j = Json::parse(planText);
    for (const auto& u : plan.j["units"]) {
        plan.category.push_back(u["category"]);
        for (const auto& m : u["members"]) plan.unitOf[hex(m)] = plan.category.size() - 1;
    }
    Bytes bank;
    CHECK(readBankFromRomfs(image, plan.j, bank));
    CHECK(sha256(bank) == plan.j["bank"]["sha256"].get<std::string>());
    std::vector<std::pair<size_t, size_t>> slots;  // offset, unit
    for (const auto& s : plan.j["slots"]) slots.emplace_back(s["offset"].get<size_t>(), s["unit"].get<size_t>());

    // A. determinism, category safety, derangement, byte-exact scope, for 100 seeds x 2 modes (+ text seeds)
    std::set<std::string> distinct[2];
    std::vector<std::string> seeds;
    for (int i = 0; i < 100; i++) seeds.push_back(std::to_string(i));
    seeds.push_back("30081997");
    seeds.push_back("9999999999999999");
    for (int m = 0; m < 2; m++) {
        const MusicMode mode = m ? MusicMode::Chaos : MusicMode::Category;
        for (const auto& seed : seeds) {
            Bytes a, b;
            Json ra, rb;
            std::string error;
            CHECK(shuffleMusic(planText, bank, seed, mode, a, ra, error));
            CHECK(shuffleMusic(planText, bank, seed, mode, b, rb, error));
            CHECK(a == b && ra == rb);
            CHECK(a.size() == bank.size());
            distinct[m].insert(sha256(a));
            std::map<size_t, size_t> unitTarget;
            size_t s = 0;
            for (size_t i = 0; i < bank.size(); i++) {
                if (a[i] == bank[i]) continue;
                while (s < slots.size() && slots[s].first + 4 <= i) s++;
                CHECK(s < slots.size() && i >= slots[s].first);  // only slot words change
            }
            for (const auto& [off, unit] : slots) {
                const uint32_t now = rd32(a, off);
                const auto it = plan.unitOf.find(now);
                CHECK(it != plan.unitOf.end());  // always a planned (looping, non-silent, >= 30 s) song
                if (it == plan.unitOf.end()) continue;
                if (mode == MusicMode::Category) CHECK(plan.category[it->second] == plan.category[unit]);
                const auto known = unitTarget.find(unit);
                if (known == unitTarget.end()) unitTarget[unit] = it->second;
                else CHECK(known->second == it->second);  // a unit moves as a whole
            }
            for (const auto& [from, to] : unitTarget) CHECK(from != to);  // every category has >= 2 units: derangement
            CHECK(ra["mode"] == musicModeId(mode) && ra["sha256"] == sha256(a) && ra["original_sha256"] == sha256(bank));
            if (seed == "1" || seed == "2" || seed == "30081997") {
                writeAll(out + "/music-" + musicModeId(mode) + "-" + seed + ".bnk", a);
                std::ofstream r(out + "/music-" + musicModeId(mode) + "-" + seed + ".json");
                r << ra.dump(1);
            }
        }
        CHECK(distinct[m].size() == seeds.size());  // every seed gives a different bank
    }
    { std::ofstream list(out + "/seeds.json"); list << Json(seeds).dump(); }
    for (const auto& seed : seeds)
        for (int m = 0; m < 2; m++) {
            Bytes a;
            Json r;
            std::string error;
            shuffleMusic(planText, bank, seed, m ? MusicMode::Chaos : MusicMode::Category, a, r, error);
            std::ofstream f(out + "/sha-" + musicModeId(m ? MusicMode::Chaos : MusicMode::Category) + "-" + seed + ".txt");
            f << sha256(a);
        }

    // B. negative cases fail closed with the output untouched
    {
        Bytes o;
        Json r;
        std::string error;
        Bytes bad = bank;
        bad[bad.size() / 2] ^= 1;
        CHECK(!shuffleMusic(planText, bad, "1", MusicMode::Category, o, r, error));
        CHECK(!shuffleMusic(planText, bank, "1", MusicMode::Off, o, r, error));
        CHECK(!shuffleMusic(planText, bank, "", MusicMode::Category, o, r, error));
        CHECK(!shuffleMusic(planText.substr(0, planText.size() / 2), bank, "1", MusicMode::Category, o, r, error));
        auto mutate = [&](auto fn) {
            Json j = Json::parse(planText);
            fn(j);
            Bytes x;
            Json y;
            std::string e;
            return shuffleMusic(j.dump(), bank, "1", MusicMode::Category, x, y, e);
        };
        CHECK(mutate([](Json&) {}));
        CHECK(!mutate([](Json& j) { j["algorithm"] = "other"; }));
        CHECK(!mutate([](Json& j) { j["slots"][0]["offset"] = j["slots"][0]["offset"].get<size_t>() + 1; }));
        CHECK(!mutate([](Json& j) { j["slots"][0]["offset"] = 4; }));
        CHECK(!mutate([](Json& j) { j["slots"][1]["offset"] = j["slots"][0]["offset"]; }));
        CHECK(!mutate([](Json& j) { j["slots"][0]["song"] = "00000001"; }));
        CHECK(!mutate([](Json& j) { j["units"][0]["members"].push_back(j["units"][1]["members"][0]); }));
        CHECK(!mutate([](Json& j) { j["units"][0]["members"][0] = "12345678"; }));
        CHECK(!mutate([](Json& j) { j["units"][0]["category"] = "demo"; }));
        CHECK(!mutate([](Json& j) { j["units"][0]["unit"] = 5; }));
        CHECK(!mutate([](Json& j) { j["slots"][0]["unit"] = 99999; }));
        CHECK(!mutate([](Json& j) { j["bank"]["sha256"] = std::string(64, '0'); }));
        CHECK(!mutate([](Json& j) { j["slots"][0]["offset"] = "12"; }));  // wrong type: fails closed, no abort
        Result res;
        res.report = {{"options", Json::object()}};
        CHECK(randomizeMusic(planText, [&](const Json&, Bytes&) { return false; }, "1", MusicMode::Off, res, error));
        CHECK(res.report["music"]["mode"] == "off" && res.tables.empty() && res.report["options"]["music"] == "off");
        Result res2;
        res2.report = {{"options", Json::object()}};
        CHECK(!randomizeMusic(planText, [&](const Json&, Bytes&) { return false; }, "1", MusicMode::Category, res2, error));
        CHECK(res2.tables.empty() && !res2.report.contains("music"));
    }

    // C. run store: music runs publish, verify on Continue, reject a tampered bank; plain runs unchanged
    const std::string root = out + "/runs";
    mkdir(root.c_str(), 0755);
    Json assets = {{"tables", {{"trainers", {{"path", "a/trainers.bin"}}}, {"wild", {{"path", "a/wild.bin"}}},
                               {"dlc", {{"path", "a/dlc.bin"}}}, {MusicTableName, {{"path", MusicBankPath}}}}}};
    auto run = [&](const std::string& id, MusicMode mode, std::string& error) {
        Result r;
        r.tables = {{"trainers", Bytes{1, 2}}, {"wild", Bytes{3}}, {"dlc", Bytes{4, 5, 6}}};
        r.save = Bytes(64, 7);
        r.report = {{"seed", "1"}, {"starter_name", "Tester"}, {"options", Json::object()}};
        if (!randomizeMusic(planText, [&](const Json& p, Bytes& b) { return readBankFromRomfs(image, p, b); }, "1", mode, r, error)) return false;
        return publishRun(root, id, assets, r, error);
    };
    std::string error;
    CHECK(run("r1-music", MusicMode::Category, error));
    CHECK(run("r2-plain", MusicMode::Off, error));
    CHECK(run("r3-chaos", MusicMode::Chaos, error));
    CHECK(!run("r1-music", MusicMode::Category, error));  // never overwrites a run
    auto listed = [&](const std::string& id) {
        for (const auto& r : listRuns(root))
            if (r.id == id) return true;
        return false;
    };
    CHECK(listed("r1-music") && listed("r2-plain") && listed("r3-chaos"));
    Bytes rep;
    CHECK(readFile(root + "/r1-music/report.json", rep));
    Json report = Json::parse(rep);
    CHECK(report["native_tables"].size() == 3 && report["native_music"]["path"] == MusicBankPath);
    CHECK(report["music"]["mode"] == "category" && report["options"]["music"] == "category");
    Bytes onDisk;
    CHECK(readFile(root + "/r1-music/romfs/" + std::string(MusicBankPath), onDisk));
    CHECK(sha256(onDisk) == report["native_music"]["sha256"].get<std::string>() && onDisk.size() == bank.size());
    CHECK(readFile(root + "/r2-plain/report.json", rep));
    report = Json::parse(rep);
    CHECK(!report.contains("native_music") && report["music"]["mode"] == "off");
    struct stat st{};
    CHECK(stat((root + "/r2-plain/romfs/" + std::string(MusicBankPath)).c_str(), &st) != 0);
    CHECK(selectRun(root, "r1-music", error) && activeRun(root) == "r1-music");
    onDisk[onDisk.size() / 3] ^= 0x40;  // tamper: Continue must refuse, other runs stay valid
    writeAll(root + "/r1-music/romfs/" + std::string(MusicBankPath), onDisk);
    CHECK(!listed("r1-music") && listed("r2-plain") && listed("r3-chaos"));
    CHECK(activeRun(root).empty());
    CHECK(!selectRun(root, "r1-music", error));

    printf(failures ? "FAILED: %d checks\n" : "PASS: 102 seeds x 2 modes deterministic, category-safe, derangements, only planned slot words; "
                                               "16 negative cases fail closed; run store publish/verify/tamper/plain\n",
           failures);
    return failures ? 1 : 0;
}
