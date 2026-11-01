// ui-v2 host test of the launcher controller over the REAL randomizer core: a scripted button sequence types a seed,
// changes a setting, creates a run (generate -> progression -> research rewards -> name -> publishRun), then a second
// controller lists it, shows its card and continues it. Also the report.json compatibility readers (r27b / r28 /
// r28b-dlc-dex / r29-music shapes) and the trainer-name keyboard screen.
// Usage: test_launcher_flow <assets dir with trailing slash> <new temp root>
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <sys/stat.h>
#include <vector>
#include <unistd.h>
#include "randomizer.hpp"

#include "launcher_core.h"
#include "ui_launcher.h"
#include "ui_model.h"
#include "settings_codes.h"
#include "run_store.hpp"
#include "za_slot.h"

using namespace ui;
using B = model::Button;

static int failures = 0;
#define CHECK(cond)                                                               \
    do {                                                                          \
        if (!(cond)) {                                                            \
            std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); \
            failures++;                                                           \
        }                                                                         \
    } while (0)

static std::string readText(const std::string& path) {
    std::ifstream in(path, std::ios::binary);
    std::stringstream ss;
    ss << in.rdbuf();
    return ss.str();
}

static void log(const char* line) { std::fputs(line, stderr); }
static std::string fixedSeed() { return "4031"; }
static uint64_t fixedTime() { return 0x6ae50000ull; }
static uint32_t fixedRandom() { return 0x1234abcdu; }

static void press(launcher::Controller& c, std::initializer_list<B> buttons) {
    for (B b : buttons) { c.press(b); c.tick(1000); }
}

static void waitDone(launcher::Controller& c, uint64_t& clock) {
    for (int i = 0; i < 30000 && !c.done() && c.state().screen == launcher::Screen::Generating; i++) {
        clock += 10;
        c.tick(clock);
        usleep(1000);
    }
}

// Independently read the emitted field bytes using the asset index. This detects an old generator that only
// echoes the selected UI settings to report.json without applying the level/Alpha changes.
static void checkWildBytes(const std::string& assets, const std::string& run) {
    using za::Json;
    Json index = Json::parse(readText(assets + "v3.json"), nullptr, false);
    CHECK(!index.is_discarded());
    if (index.is_discarded()) return;
    const std::string bytes = readText(run + "/romfs/" + index["wild"]["path"].get<std::string>());
    size_t levelsChanged = 0, alphaChanged = 0, rows = 0, guards = 0;
    for (const auto& chunk : index["wild"]["rows_files"]) {
        Json entries = Json::parse(readText(assets + chunk["file"].get<std::string>()), nullptr, false);
        CHECK(entries.is_array());
        for (const auto& row : entries) {
            const bool guard = row.value("rock_provider", false);
            guards += guard;
            for (const char* field : {"minLevel", "maxLevel"}) {
                const int before = row[field[1] == 'i' ? "min_level" : "max_level"];
                const int expected = guard ? before : std::max(1, std::min(100, (before * 125 + 50) / 100));
                const size_t offset = row["fields"][field]["offset"];
                CHECK(offset + 4 <= bytes.size());
                if (offset + 4 > bytes.size()) continue;
                uint32_t actual = 0;
                for (int k = 0; k < 4; k++) actual |= uint32_t(uint8_t(bytes[offset + size_t(k)])) << (8 * k);
                CHECK(actual == uint32_t(expected));
                levelsChanged += expected != before;
            }
            const float before = row["oyabun"];
            const float expected = guard ? before : std::min(100.0f, before * 2.0f);
            const size_t offset = row["fields"]["oyabunProbability"]["offset"];
            CHECK(offset + sizeof(float) <= bytes.size());
            if (offset + sizeof(float) <= bytes.size()) {
                float actual = 0;
                std::memcpy(&actual, bytes.data() + offset, sizeof actual);
                CHECK(actual == expected);
                alphaChanged += actual != before;
            }
            rows++;
        }
    }
    CHECK(rows == 1822 && guards == 2 && levelsChanged > 1000 && alphaChanged > 500);
}

int main(int argc, char** argv) {
    if (argc != 3) { std::fprintf(stderr, "usage: test_launcher_flow <assets dir/> <new root>\n"); return 2; }
    launcher::Paths paths;
    paths.assets = argv[1];
    paths.runRoot = argv[2];
    paths.gameImage = "/nonexistent/romfs.bin";  // music stays Off in this test
    paths.buildLabel = "test";
    launcher::Platform plat;
    plat.log = log;
    plat.freshSeed = fixedSeed;
    plat.unixTime = fixedTime;
    plat.random32 = fixedRandom;
    uint64_t clock = 1000;

    // ---- a report.json of the shapes shipped so far (no ui_options): the compatibility readers
    {
        std::string r27b = R"({"schema":1,"seed":"9376797808","starter":25,"starter_name":"Pikachu","options":{"wild":true,"trainers":true,"mega_trainers":true,"dlc_rematches":true,"research_rewards":true},"player_name":"Tomer","player_name_template":"Test","native_run_id":"r000000006ae35da8-c4c60589","native_complete":true})";
        model::Values v = launcher::Controller::valuesFromReport(r27b);
        CHECK(model::summary(v) == "Wild: Fully random · Trainers: Fully random · Megas: Random Mega · DLC rematches: Shuffle · Starter: Random by seed · Research: Randomized · Music: Off");
        CHECK(v.text("player_name") == "Tomer");
        CHECK(launcher::Controller::configurationCodeFromReport(r27b).empty());  // old booleans omit category details
        std::string r28music = R"({"schema":1,"seed":"1","starter":152,"starter_name":"Chikorita","options":{"wild":false,"trainers":true,"mega_trainers":false,"dlc_rematches":true,"research_rewards":false,"music":"category"},"music":{"mode":"category","slots":64},"native_run_id":"r000000006ae46953-8efd14d1","native_complete":true})";
        v = launcher::Controller::valuesFromReport(r28music);
        CHECK(v.get("wild_mode") == 0 && v.get("trainers_mode") == 3 && v.get("mega_trainers") == 0 && v.get("research_rewards") == 0);
        CHECK(v.get("music") == 1 && v.get("starter_mode") == 0 && v.get("starter_pick") == 0);
        CHECK(model::summary(v) == "Wild: Off · Trainers: Fully random · DLC rematches: Shuffle · Starter: Vanilla choice · Music: Shuffle by category");
        // r6..r15 reports had no player_name and no music: the name shows as the template's default
        std::string r15 = R"({"schema":1,"seed":"12345","starter":656,"starter_name":"Froakie","options":{"wild":true,"trainers":false,"mega_trainers":true,"dlc_rematches":false},"native_run_id":"r000000006ae0f7c2-77d2a0b1","native_complete":true})";
        v = launcher::Controller::valuesFromReport(r15);
        CHECK(v.get("trainers_mode") == 0 && v.get("dlc_rematches") == 0 && v.get("starter_mode") == 1 && v.get("starter_pick") == 8);
        CHECK(v.text("player_name") == "Trainer");
        // a newer report with ui_options wins over the booleans, unknown ids survive
        std::string v3 = R"({"schema":1,"seed":"7","options":{"wild":true},"ui_options":{"schema":2,"values":{"wild_mode":"off","future_row":"x","player_name":"Zed","starter_mode":"any","starter_pick":4}}})";
        v = launcher::Controller::valuesFromReport(v3);
        CHECK(v.get("wild_mode") == 0 && v.text("player_name") == "Zed" && v.text("future_row") == "x" && v.get("starter_pick") == 1);
        CHECK(launcher::Controller::dateOfRunId("r000000006ae46953-8efd14d1") == "30 Oct 2026");
        CHECK(launcher::Controller::dateOfRunId("bogus").empty());
        za::Json recorded = {{"algorithm", "za202-randomizer-alpha1"}, {"build_id", codes::CurrentGameBuild},
                             {"ui_options", za::Json::parse(model::toJson(v))}};
        CHECK(launcher::Controller::configurationCodeFromReport(recorded.dump()) == codes::configurationCode(v, "za202-randomizer-alpha1"));
        CHECK(launcher::Controller::configurationCodeFromReport(recorded.dump()) != codes::configurationCode(v));
        recorded["ui_options"]["schema"] = "2";
        CHECK(launcher::Controller::configurationCodeFromReport(recorded.dump()).empty());
        recorded["ui_options"] = za::Json::parse(model::toJson(v));
        recorded["ui_options"]["values"]["wild_mode"] = "unknown";
        CHECK(launcher::Controller::configurationCodeFromReport(recorded.dump()).empty());
        recorded["ui_options"] = za::Json::parse(model::toJson(v));
        recorded["ui_options"]["values"].erase("wild_levels");
        CHECK(launcher::Controller::configurationCodeFromReport(recorded.dump()).empty());
    }

    // ---- first launch: no runs yet
    {
        launcher::Controller c(paths, plat);
        CHECK(c.init());
        const launcher::State& s = c.state();
        // the save-slot menu first; with no run only the empty slot exists and the cursor is on it
        CHECK(s.screen == launcher::Screen::SavedRuns && s.slotIndex == 0 && s.runs.empty());
        press(c, {B::Square, B::Triangle});  // nothing to delete
        CHECK(s.screen == launcher::Screen::SavedRuns && s.toastVisible && s.toast.text == "Every run is supported");
        press(c, {B::Cross});  // the empty slot -> the Play page on "Start a new run"
        CHECK(s.screen == launcher::Screen::Settings && s.nav.page == 0 && s.nav.row == 1);  // "Start a new run" when there is no run
        CHECK(s.runs.empty() && s.activeRun == -1 && s.seed == "4031");
        CHECK(s.values.text("player_name") == "Test" || s.values.text("player_name") == "Trainer");  // the template's own name, or the fallback
        // Continue with no run: a toast, nothing selected
        press(c, {B::Up, B::Cross});
        CHECK(!c.done() && s.toastVisible && s.toast.text == "No run yet");
        // the seed keypad: 1, then Done ("1")
        press(c, {B::Down, B::Down, B::Cross});
        CHECK(s.screen == launcher::Screen::Seed && s.seedInput == "4031" && s.keypad == 0);
        press(c, {B::Cross});  // the first digit replaces the prefilled seed
        CHECK(s.seedInput == "1");
        press(c, {B::Down, B::Down, B::Down, B::Right, B::Right, B::Cross});  // keypad 9 (Clear) -> 11 (Done)
        CHECK(s.screen == launcher::Screen::Settings && s.seed == "1");
        // the trainer name: Player page, row 0 -> keyboard; type "Zed"
        int player = model::pageIndexOf("player");
        CHECK(player > 0);
        for (int i = 0; i < model::pageCount() && s.nav.page != player; i++) press(c, {B::R1});
        CHECK(s.nav.page == player);
        press(c, {B::Cross});
        CHECK(s.screen == launcher::Screen::Name && s.name.labels.size() == 5);
        // clear the prefilled name: DEL is row 4 columns 6-7; go there and press it enough times
        press(c, {B::Down, B::Down, B::Down, B::Down});
        press(c, {B::Right, B::Right, B::Right, B::Right});  // row 4: ' & CASE SPACE DEL -> column index 4 of the compressed row
        for (int i = 0; i < 13; i++) press(c, {B::Cross});
        CHECK(s.name.text.empty());
        press(c, {B::Up, B::Up, B::Up, B::Up});  // row 0, physical column 6 ("G")
        for (int i = 0; i < 6; i++) press(c, {B::Left});  // back to "A"
        // Z is row 2 column 5
        press(c, {B::Down, B::Down, B::Right, B::Right, B::Right, B::Right, B::Right, B::Cross});
        press(c, {B::Triangle});  // lower case
        press(c, {B::Up, B::Up, B::Left, B::Cross});  // row 0 column 4 "e"
        press(c, {B::Left, B::Cross});  // row 0 column 3: "d"
        CHECK(s.name.text == "Zed");
        // Done is the last wide key of row 4
        press(c, {B::Down, B::Down, B::Down, B::Down});
        press(c, {B::Right, B::Right, B::Right});  // CASE -> SPACE -> DEL -> DONE
        press(c, {B::Cross});
        CHECK(s.screen == launcher::Screen::Settings);
        std::string typed = s.values.text("player_name");
        CHECK(typed == "Zed");
        // Wild page: Fully random -> Off (the only other shipped level)
        int wild = model::pageIndexOf("wild");
        for (int i = 0; i < model::pageCount() && s.nav.page != wild; i++) press(c, {B::L1});
        CHECK(s.nav.page == wild);
        press(c, {B::Right});
        CHECK(s.values.get("wild_mode") == 0);
        press(c, {B::Down, B::Right, B::Right});  // Wild levels: +25%, with original wild species
        CHECK(s.values.get("wild_levels") == 2);
        press(c, {B::Down, B::Down, B::Right});  // Alpha x2
        CHECK(s.values.get("alpha_rate") == 1);
        // Cheat defaults: Shiny -> 4x rolls
        int cheats = model::pageIndexOf("cheats");
        for (int i = 0; i < model::pageCount() && s.nav.page != cheats; i++) press(c, {B::R1});
        CHECK(s.nav.page == cheats);
        press(c, {B::Right});
        CHECK(s.values.get("shiny_default") == 1);
        // back to Play, Start a new run -> Confirm -> create
        press(c, {B::Circle});
        CHECK(s.nav.page == 0);
        press(c, {B::Down, B::Cross});
        CHECK(s.screen == launcher::Screen::Confirm);
        press(c, {B::Cross});
        CHECK(s.screen == launcher::Screen::Generating);
        waitDone(c, clock);
        CHECK(c.done());
        CHECK(!c.createdRun().empty() && c.selectedRun() == c.createdRun());
        std::string id = c.createdRun();
        CHECK(id == "r000000006ae50000-1234abcd");
        std::string report = readText(paths.runRoot + "/" + id + "/report.json");
        CHECK(report.find("\"ui_options\"") != std::string::npos);
        CHECK(report.find("\"wild_mode\": \"off\"") != std::string::npos);
        CHECK(report.find("\"shiny_default\": \"x4\"") != std::string::npos);
        CHECK(report.find("\"starter_mode\": \"random\"") != std::string::npos);
        CHECK(report.find("\"schema\": 2") != std::string::npos);
        CHECK(report.find("\"seed\": \"1\"") != std::string::npos);
        CHECK(report.find("\"player_name\": \"" + typed + "\"") != std::string::npos);
        // the legacy booleans are still there for the older readers
        CHECK(report.find("\"wild\": false") != std::string::npos);
        CHECK(report.find("\"v3_algorithm\": \"za202-randomizer-v3\"") != std::string::npos);
        CHECK(report.find("\"wild_levels\": \"plus25\"") != std::string::npos);
        CHECK(report.find("\"alpha_rate\": \"x2\"") != std::string::npos);
        const za::Json persisted = za::Json::parse(report);
        const auto encoded = codes::compute(s.values);
        CHECK(persisted["settings_codes"]["schema"] == codes::Schema);
        CHECK(persisted["settings_codes"]["algorithm"] == codes::CurrentAlgorithm);
        CHECK(persisted["settings_codes"]["game_build"] == codes::CurrentGameBuild);
        CHECK(persisted["settings_codes"]["word_bank"]["sha256"] == codes::WordBankSha256);
        CHECK(persisted["settings_codes"]["overall"] == encoded.overall);
        CHECK(persisted["settings_codes"]["categories"].size() == 7);
        CHECK(persisted["settings_codes"]["categories"]["wild"] == encoded.wild);
        CHECK(launcher::Controller::configurationCodeFromReport(report) == encoded.overall);
        checkWildBytes(paths.assets, paths.runRoot + "/" + id);
        CHECK(readText(paths.runRoot + "/" + id + "/cheats.txt") == "za-cheats-v2\n1 0 1 0\n");
        CHECK(readText(paths.runRoot + "/active.json").find(id) != std::string::npos);
        struct stat st {};
        CHECK(!stat((paths.runRoot + "/" + id + "/save/save_0/main").c_str(), &st) && st.st_size == 3186611);
        CHECK(readText(paths.runRoot + "/player-name.txt") == typed + "\n");
        // the slot container written at creation: summary readable from its head, the save copy identical
        za_slot_summary slot;
        CHECK(za_slot_read_summary_file((paths.runRoot + "/" + id + "/slot.zrs").c_str(), &slot) == ZA_SLOT_OK);
        CHECK(std::string(slot.run_id) == id && std::string(slot.seed) == "1" && slot.save_size == 3186611 && slot.save_time == fixedTime());
        CHECK(std::string(slot.algorithm) == "za202-randomizer-v3" && std::string(slot.build_id) == codes::CurrentGameBuild);
        // the template save + the starter: 2 caught / 3 seen, as an independent Python decoder of the same save reads it
        CHECK((slot.flags & ZA_SLOT_HAS_CAUGHT) && slot.caught == 2 && slot.seen == 3);
        CHECK((slot.flags & ZA_SLOT_HAS_LOCATION) && std::string(slot.location) == "t1");
        // story phase and research level, as the independent decoder reads them: SYS_WORK_PHASE 21110, research level 1
        CHECK((slot.flags & ZA_SLOT_HAS_PHASE) && slot.story_phase == 21110 && slot.dlc_phase == 0);
        CHECK((slot.flags & ZA_SLOT_HAS_RESEARCH) && slot.research_level == 1 && (slot.flags & ZA_SLOT_HAS_POSITION));
        std::printf("slot container: caught=%u seen=%u location=\"%s\" flags=%u\n", slot.caught, slot.seen, slot.location, slot.flags);
        const std::string container = readText(paths.runRoot + "/" + id + "/slot.zrs");
        const std::string gameSave = readText(paths.runRoot + "/" + id + "/save/save_0/main");
        const uint8_t* copy = nullptr;
        size_t copyLen = 0;
        CHECK(za_slot_verify((const uint8_t*)container.data(), container.size()) == ZA_SLOT_OK);
        CHECK(za_slot_section((const uint8_t*)container.data(), container.size(), ZA_SLOT_SAVE, &copy, &copyLen) == ZA_SLOT_OK &&
              copyLen == gameSave.size() && !std::memcmp(copy, gameSave.data(), copyLen));
    }
    // ---- second launch: the run is listed, is the active one, and Continue selects it
    {
        launcher::Controller c(paths, plat);
        CHECK(c.init());
        const launcher::State& s = c.state();
        CHECK(s.screen == launcher::Screen::SavedRuns && s.slotIndex == 0);  // the cursor on the active run
        CHECK(s.runs.size() == 1 && s.runs[0].supported && s.runs[0].caught >= 1 && !s.runs[0].lastPlayed.empty());
        // no slot-names.json in the test assets: the raw ids
        CHECK(s.runs[0].mission == "Phase 21110" && s.runs[0].researchLevel == 1 && s.runs[0].location == "t1");
        press(c, {B::Circle});  // nothing behind the slot menu
        CHECK(s.screen == launcher::Screen::SavedRuns);
        press(c, {B::Down, B::Cross});  // the empty slot -> Play
        CHECK(s.screen == launcher::Screen::Settings && s.nav.page == 0);
        press(c, {B::Circle});  // Play -> back to the slots
        CHECK(s.screen == launcher::Screen::SavedRuns);
        CHECK(s.slotIndex == 1);
        press(c, {B::Cross});  // still on the empty slot: Play, "Start a new run"
        CHECK(s.screen == launcher::Screen::Settings && s.nav.row == 1 && s.runs.size() == 1 && s.activeRun == 0);
        CHECK(s.runs[0].seed == "1" && s.runs[0].active && s.runs[0].summary.find("Wild: Off") != std::string::npos);
        CHECK(s.runs[0].trainer[0] == 'Z' && s.runs[0].summary.find("Shiny: 4") != std::string::npos);
        CHECK(!s.runs[0].configCode.empty() && s.runs[0].codeAlgorithm == codes::CurrentAlgorithm);
        CHECK(!s.runs[0].date.empty() && s.recentSeeds.size() == 1 && s.recentSeeds[0] == "1");
        // the Saved runs page (nav): Cross continues the highlighted run
        for (int i = 0; i < model::pageCount() && s.nav.page != launcher::savedRunsPage(); i++) press(c, {B::L1});
        CHECK(s.nav.page == launcher::savedRunsPage());
        press(c, {B::Cross});
        CHECK(c.done() && c.selectedRun() == "r000000006ae50000-1234abcd" && c.createdRun().empty());
    }
    // ---- third launch: Continue from the slot menu
    {
        launcher::Controller c(paths, plat);
        CHECK(c.init());
        press(c, {B::Cross});
        CHECK(c.done() && c.selectedRun() == "r000000006ae50000-1234abcd");
    }
    // ---- an old v2 run made active: listed as OLD VERSION, never continued (not by Cross, not by the observer),
    // the cursor starts on the empty slot; "delete all that can't continue" removes only it
    const std::string good = "r000000006ae50000-1234abcd", old = "r000000006ae00000-0ddc0ffe";
    {
        const std::string src = paths.runRoot + "/" + good, dst = paths.runRoot + "/" + old;
        CHECK(std::system(("cp -r '" + src + "' '" + dst + "'").c_str()) == 0);
        za::Json r = za::Json::parse(readText(dst + "/report.json"));
        r.erase("v3_algorithm");
        r.erase("v3");
        r.erase("ui_options");
        r["native_run_id"] = old;
        std::ofstream(dst + "/report.json", std::ios::binary) << r.dump(2);
        std::remove((dst + "/slot.zrs").c_str());
        std::ofstream(paths.runRoot + "/active.json", std::ios::binary) << "{\"id\":\"" + old + "\",\"schema\":1}";
        CHECK(za::native::activeRun(paths.runRoot) == old);  // the run store itself still accepts it
    }
    {
        launcher::Controller c(paths, plat);
        plat.observerContinue = [](const char*) { return true; };
        launcher::Controller observed(paths, plat);
        plat.observerContinue = nullptr;
        CHECK(observed.init());
        observed.tick(5000);
        CHECK(!observed.done());  // the observer never continues an unsupported active run
        CHECK(c.init());
        const launcher::State& s = c.state();
        CHECK(s.runs.size() == 2 && s.runs[0].id == good && s.runs[1].id == old);
        CHECK(s.runs[0].supported && !s.runs[1].supported && s.runs[1].badge == "OLD VERSION" && !s.runs[1].active);
        CHECK(s.activeRun == -1 && s.slotIndex == 2);
        CHECK(s.runs[1].caught == -1 && s.runs[1].location.empty());  // no slot container: "—"
        press(c, {B::Up, B::Cross});  // Cross on the old run: a toast, nothing selected
        CHECK(!c.done() && s.slotIndex == 1 && s.toastVisible && s.toast.kind == Toast::Warn);
        press(c, {B::Square});  // delete one: the dialog, then cancel
        CHECK(s.screen == launcher::Screen::DeleteConfirm && s.deleteMode == launcher::State::DeleteMode::One && s.deleteIndex == 1);
        press(c, {B::Circle});
        CHECK(s.screen == launcher::Screen::SavedRuns && s.runs.size() == 2);
        press(c, {B::Triangle});
        CHECK(s.screen == launcher::Screen::DeleteConfirm && s.deleteMode == launcher::State::DeleteMode::Unsupported);
        press(c, {B::Cross});
        CHECK(s.screen == launcher::Screen::SavedRuns && s.runs.size() == 1 && s.runs[0].id == good && s.toast.text == "1 run deleted");
        struct stat st {};
        CHECK(stat((paths.runRoot + "/" + old).c_str(), &st) != 0 && stat((paths.runRoot + "/active.json").c_str(), &st) != 0);
        CHECK(stat((paths.runRoot + "/" + good + "/save/save_0/main").c_str(), &st) == 0);
        // the good run is not active any more (its marker was the old run's); Cross still continues it
        press(c, {B::Up});
        CHECK(s.slotIndex == 0);
        press(c, {B::Cross});
        CHECK(c.done() && c.selectedRun() == good);
    }
    // ---- deleting the active run from the slot menu: no active run afterwards (a copy of the run is kept first for
    // test_saves: <root>-keep/<id>)
    CHECK(std::system(("rm -rf '" + paths.runRoot + "-keep' && mkdir -p '" + paths.runRoot + "-keep' && cp -r '" + paths.runRoot + "/" + good + "' '" +
                       paths.runRoot + "-keep/'").c_str()) == 0);
    {
        launcher::Controller c(paths, plat);
        CHECK(c.init());
        const launcher::State& s = c.state();
        CHECK(s.activeRun == 0 && s.slotIndex == 0);
        press(c, {B::Square, B::Cross});
        CHECK(s.screen == launcher::Screen::SavedRuns && s.runs.empty() && s.activeRun == -1 && s.slotIndex == 0 && s.toast.text == "Run deleted");
        CHECK(za::native::activeRun(paths.runRoot).empty());
    }
    // ---- "Delete all": two confirmations, every run (supported ones too), no active run afterwards
    CHECK(std::system(("cp -r '" + paths.runRoot + "-keep/" + good + "' '" + paths.runRoot + "/'").c_str()) == 0);
    CHECK(std::system(("cp -r '" + paths.runRoot + "-keep/" + good + "' '" + paths.runRoot + "/" + old + "'").c_str()) == 0);
    {
        za::Json r = za::Json::parse(readText(paths.runRoot + "/" + old + "/report.json"));
        r.erase("v3_algorithm");
        r["native_run_id"] = old;
        std::ofstream(paths.runRoot + "/" + old + "/report.json", std::ios::binary) << r.dump(2);
        std::ofstream(paths.runRoot + "/active.json", std::ios::binary) << "{\"id\":\"" + good + "\",\"schema\":1}";
    }
    {
        launcher::Controller c(paths, plat);
        CHECK(c.init());
        const launcher::State& s = c.state();
        CHECK(s.runs.size() == 2 && s.activeRun == 0);
        press(c, {B::R2});
        CHECK(s.screen == launcher::Screen::DeleteConfirm && s.deleteMode == launcher::State::DeleteMode::Everything && s.deleteStage == 0);
        press(c, {B::Cross});  // the first confirmation only advances
        CHECK(s.screen == launcher::Screen::DeleteConfirm && s.deleteStage == 1 && s.runs.size() == 2);
        press(c, {B::Circle});  // cancel at the second: nothing deleted, back to the slots
        CHECK(s.screen == launcher::Screen::SavedRuns && s.runs.size() == 2 && s.deleteStage == 0);
        press(c, {B::R2, B::Cross, B::Cross});
        CHECK(s.screen == launcher::Screen::SavedRuns && s.runs.empty() && s.activeRun == -1 && s.toast.text == "2 runs deleted");
        struct stat st {};
        CHECK(stat((paths.runRoot + "/active.json").c_str(), &st) != 0 && stat((paths.runRoot + "/player-name.txt").c_str(), &st) == 0);
        press(c, {B::R2});
        CHECK(s.screen == launcher::Screen::SavedRuns && s.toast.text == "No runs to delete");
    }
    if (failures) { std::fprintf(stderr, "%d check(s) failed\n", failures); return 1; }
    std::puts("PASS: launcher flow (slot menu, seed keypad, name keyboard, settings, confirm, generation with ui_options + cheats.txt + slot.zrs, cards, continue, unsupported run, delete one / all unsupported / active / everything) and report compatibility readers");
    return 0;
}
