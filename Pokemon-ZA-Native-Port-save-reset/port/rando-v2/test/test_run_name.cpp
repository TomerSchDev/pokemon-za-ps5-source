// Lifecycle tests use real fixture copies and a unique /tmp directory only.
#include "../run_name.hpp"
#include "../za_player_name.hpp"
#include "run_store.hpp"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <unistd.h>

using namespace za;
using namespace za::native;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)
static void write(const std::string& path, const Bytes& bytes) {
    std::ofstream f(path, std::ios::binary | std::ios::trunc);
    f.write(reinterpret_cast<const char*>(bytes.data()), std::streamsize(bytes.size()));
    CHECK(f.good());
}
static void write(const std::string& path, const std::string& text) { write(path, Bytes(text.begin(), text.end())); }

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    Bytes fixture;
    if (!readFile(std::string(argv[1]) + "/plain.bin", fixture) || fixture.size() < 0x10000) return 2;
    char tmp[] = "/tmp/za-r27-name-lifecycle-XXXXXX";
    if (!mkdtemp(tmp)) return 2;
    const std::string root = tmp;
    std::string error;
    Json assets = {{"tables", {{"trainers", {{"path", "trainers.bin"}}}, {"wild", {{"path", "wild.bin"}}},
                              {"dlc_boss", {{"path", "dlc.bin"}}}}}};
    Result original;
    original.save = fixture;
    original.tables = {{"trainers", {1}}, {"wild", {2}}, {"dlc_boss", {3}}};
    original.report = {{"seed", "123456"}, {"starter_name", "Tepig"}, {"save_sha256", sha256(fixture)}};

    // Pre-name reports replay identically. New reports reproduce the exact named
    // starting save, including the checksum that the repair script compares.
    Result oldReplay = original;
    CHECK(replayRunName(original.report, oldReplay, error));
    CHECK(oldReplay.save == original.save && oldReplay.report == original.report);
    Result named = original;
    CHECK(nameRun("Ash Ketchum", named, error));
    CHECK(named.report["save_sha256"] == sha256(named.save));
    CHECK(named.report["player_name_algorithm"] == PlayerNameAlgorithm);
    CHECK(named.report["player_name_template"] == "Test");
    CHECK(named.report["player_name_pokemon"]["renamed"] == 1);
    CHECK(named.tables == original.tables && fixture == original.save);
    Result replay = original;
    CHECK(replayRunName(named.report, replay, error));
    CHECK(replay.save == named.save && replay.report == named.report);
    auto prototype = named.report;
    prototype.erase("player_name_algorithm");
    replay = original;
    CHECK(replayRunName(prototype, replay, error) && replay.save == named.save);

    for (const auto& invalid : std::vector<Json>{Json::array(), {{"player_name", 123}}, {{"player_name", "Bad*"}},
            {{"player_name", ""}}, {{"player_name", "ABCDEFGHIJKLM"}},
            {{"player_name", "Ash"}, {"player_name_algorithm", "future-version"}},
            {{"player_name", "Ash"}, {"player_name_algorithm", 1}}, {{"player_name_algorithm", PlayerNameAlgorithm}}}) {
        replay = original;
        CHECK(!replayRunName(invalid, replay, error));
        CHECK(replay.save == original.save && replay.report == original.report);
    }
    replay = original;
    replay.save[1000] ^= 1;
    const Result damaged = replay;
    CHECK(!nameRun("Ash", replay, error));
    CHECK(replay.save == damaged.save && replay.report == damaged.report);
    CHECK(reportPlayerName(original.report).empty());
    CHECK(reportPlayerName(named.report) == "Ash Ketchum");
    CHECK(reportPlayerName(Json{{"player_name", 1}}).empty());

    // Publish an old run and a new named run. Continuing either run, even after
    // gameplay changes the save hash, must retain that current save verbatim.
    CHECK(publishRun(root, "r-old", assets, original, error));
    CHECK(publishRun(root, "r-named", assets, named, error));
    CHECK(activeRun(root) == "r-named" && listRuns(root).size() == 2);
    Result progressed = named;
    CHECK(nameRun("Progress", progressed, error)); // synthetic, valid changed save
    write(root + "/r-named/save/save_0/main", progressed.save);
    CHECK(selectRun(root, "r-old", error));
    CHECK(selectRun(root, "r-named", error));
    Bytes check;
    CHECK(readFile(root + "/r-named/save/save_0/main", check) && check == progressed.save);
    CHECK(!publishRun(root, "r-named", assets, original, error));
    CHECK(readFile(root + "/r-named/save/save_0/main", check) && check == progressed.save);
    CHECK(readFile(root + "/r-old/save/save_0/main", check) && check == fixture);
    CHECK(listRuns(root).size() == 2);
    // Repair replay is separate data, never a replacement for the progressed save.
    replay = original;
    CHECK(replayRunName(named.report, replay, error));
    CHECK(replay.save == named.save && replay.save != progressed.save);
    CHECK(readFile(root + "/r-named/save/save_0/main", check) && check == progressed.save);

    // Preference write/read, invalid input, stale stage recovery and failures.
    CHECK(rememberedPlayerName(root).empty());
    CHECK(rememberPlayerName(root, "Ash Ketchum"));
    CHECK(rememberedPlayerName(root) == "Ash Ketchum");
    CHECK(!rememberPlayerName(root, "Bad*"));
    CHECK(rememberedPlayerName(root) == "Ash Ketchum");
    write(root + "/victim", "must survive");
    CHECK(symlink((root + "/victim").c_str(), (root + "/player-name.txt.new").c_str()) == 0);
    CHECK(rememberPlayerName(root, "Serena"));
    CHECK(readFile(root + "/victim", check) && std::string(check.begin(), check.end()) == "must survive");
    CHECK(rememberedPlayerName(root) == "Serena");
    write(root + "/player-name.txt", "Tomer\r\n");
    CHECK(rememberedPlayerName(root) == "Tomer");
    write(root + "/player-name.txt", "Tomer\ninvalid");
    CHECK(rememberedPlayerName(root).empty());
    write(root + "/player-name.txt", std::string(65, 'A'));
    CHECK(rememberedPlayerName(root).empty());
    CHECK(rememberPlayerName(root, "Serena"));
    CHECK(std::filesystem::create_directory(root + "/player-name.txt.new"));
    CHECK(!rememberPlayerName(root, "Dawn"));
    CHECK(rememberedPlayerName(root) == "Serena");
    CHECK(!rememberPlayerName(root + "/does-not-exist", "Dawn"));
    CHECK(readFile(root + "/r-named/save/save_0/main", check) && check == progressed.save);
    std::printf("%s: run-name lifecycle, deterministic replay, old runs, progress retained, preferences (%d failures)\n",
                failures ? "FAIL" : "PASS", failures);
    // This path is generated here, never supplied by a caller or a live mount.
    if (root.rfind("/tmp/za-r27-name-lifecycle-", 0) != 0) return 2;
    std::filesystem::remove_all(root);
    return failures ? 1 : 0;
}
