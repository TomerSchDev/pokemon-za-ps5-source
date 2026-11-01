#include "launcher_core.h"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

#include "assets_hashes.h"      // ZA_*_SHA256 of the packaged assets (the build's object folder)
#include "import_repair.hpp"
#include "name_keyboard.hpp"
#include "progression.hpp"
#include "research_rewards.hpp"
#include "run_name.hpp"
#include "run_store.hpp"
#include "za_music.hpp"
#include "za_music_plan.hpp"
#include "za_player_name.hpp"

#ifdef _WIN32
#include <io.h>
#define ui_fsync(fd) _commit(fd)
#else
#define ui_fsync(fd) fsync(fd)
#endif

namespace ui::launcher {
using za::Json;
using za::Bytes;
using za::native::Run;

namespace {

constexpr uint32_t KUp = 0x10, KRight = 0x20, KDown = 0x40, KLeft = 0x80, KTriangle = 0x1000, KCircle = 0x2000, KCross = 0x4000, KSquare = 0x8000;

struct Job {
    const Json* assets = nullptr;
    const Json* starters = nullptr;
    const Json* rewards = nullptr;
    const Json* progression = nullptr;
    za::Options options;
    bool researchRewards = true;
    za::native::MusicMode music = za::native::MusicMode::Off;
    std::string seed, id, error, playerName, uiOptionsJson, gameImage, root;
    za::Reader readAsset;
    void (*log)(const char*) = nullptr;
    int starter = 0;
    bool success = false;
    std::atomic<int> stage{0}, done{0}, total{1};
    std::atomic<bool> finished{false};
};

void logf(void (*log)(const char*), const char* fmt, ...) __attribute__((format(printf, 2, 3)));
void logf(void (*log)(const char*), const char* fmt, ...) {
    if (!log) return;
    char line[512];
    va_list args;
    va_start(args, fmt);
    std::vsnprintf(line, sizeof line, fmt, args);
    va_end(args);
    log(line);
}

void* generateJob(void* arg) {
    auto& j = *static_cast<Job*>(arg);
    za::Result result;
    auto progress = [&](za::BuildStage s, uint32_t d, uint32_t n) { j.total = int(n); j.done = int(d); j.stage = int(s); };
    if (za::generate(*j.assets, *j.starters, j.readAsset, j.seed, j.options, j.starter, result, progress)) {
        result.report["options"]["research_rewards"] = j.researchRewards;
        // ui-v2: the settings of the new run, by stable option id (ui_model.cpp; the generator reads them by id)
        Json ui = Json::parse(j.uiOptionsJson, nullptr, false);
        if (!ui.is_discarded()) result.report["ui_options"] = ui;
        const std::string gameImage = j.gameImage;
        if (za::native::protectProgression(*j.progression, j.readAsset, j.seed, result, j.error) &&
            (!j.researchRewards || za::native::randomizeResearchRewards(*j.rewards, j.readAsset, j.seed, result, j.error)) &&
            za::native::nameRun(j.playerName, result, j.error) &&
            za::native::randomizeMusic(za::native::zaMusicPlanJson(),
                                       [&](const Json& plan, Bytes& bank) { return za::native::readBankFromRomfs(gameImage, plan, bank); },
                                       j.seed, j.music, result, j.error)) {
            logf(j.log, "[za-randomizer] trainer name set (%zu chars), %d Pokemon renamed, %d kept\n", j.playerName.size(),
                 result.report["player_name_pokemon"].value("renamed", 0), result.report["player_name_pokemon"].value("kept", 0));
            if (j.music != za::native::MusicMode::Off) {
                const Json& m = result.report["music"];
                logf(j.log, "[za-randomizer] music mode=%s slots=%zu changed=%zu bank=%s\n", za::native::musicModeId(j.music),
                     m.value("slots", size_t(0)), m.value("changed_slots", size_t(0)), m.value("sha256", std::string()).c_str());
            } else {
                logf(j.log, "[za-randomizer] music mode=off (original music)\n");
            }
            j.success = za::native::publishRun(j.root, j.id, *j.assets, result, j.error);
        }
    } else {
        j.error = result.error;
    }
    logf(j.log, "[za-randomizer] generation %s seed=%s run=%s starter=%d\n", j.success ? "complete" : "FAILED", j.seed.c_str(), j.id.c_str(),
         j.success ? result.report.value("starter", 0) : 0);
    j.finished.store(true, std::memory_order_release);
    return nullptr;
}

// cheats.txt (v2, as port/perf-r28/src/cheats-r28.cpp reads it) for a new run: the launcher's "Cheat defaults" page.
bool writeCheatDefaults(const std::string& runDir, int shiny, int capture, int fpsCounter) {
    const std::string path = runDir + "/cheats.txt", temp = path + ".new";
    char text[64];
    std::snprintf(text, sizeof text, "za-cheats-v2\n%d %d %d 0\n", shiny, capture, fpsCounter);
    int fd = open(temp.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return false;
    size_t n = std::strlen(text), at = 0;
    bool ok = true;
    while (at < n) {
        ssize_t w = write(fd, text + at, n - at);
        if (w < 0 && errno == EINTR) continue;
        if (w <= 0) { ok = false; break; }
        at += size_t(w);
    }
    if (ok && ui_fsync(fd)) ok = false;
    if (close(fd)) ok = false;
    if (!ok) { unlink(temp.c_str()); return false; }
    if (rename(temp.c_str(), path.c_str())) { unlink(temp.c_str()); return false; }
    return true;
}

}  // namespace

struct Controller::Impl {
    Paths paths;
    Platform platform;
    Json assets, starters, rewards, progression;
    std::vector<Run> runs;
    std::string active;
    bool musicReady = false;
    za::native::NameKeyboard keyboard;
    bool replaceSeed = true;
    Job job;
    pthread_t thread{};
    bool threadStarted = false;
    int previousDone = -1, previousStage = -1;
    uint64_t toastUntilMs = 0;
    Screen before = Screen::Settings;  // where an error returns to

    void log(const char* line) { if (platform.log) platform.log(line); }
    bool readAsset(const std::string& name, Bytes& bytes) {
        if (name.empty() || name.find('/') != std::string::npos || name.find('\\') != std::string::npos || name.find("..") != std::string::npos) return false;
        return za::native::readFile(paths.assets + name, bytes);
    }
    bool jsonAsset(const char* name, const char* expected, Json& out) {
        Bytes bytes;
        if (!readAsset(name, bytes)) { logf(platform.log, "[za-randomizer] asset read failed %s errno=%d\n", name, errno); return false; }
        auto digest = za::sha256(bytes);
        if (digest != expected) {
            logf(platform.log, "[za-randomizer] asset hash mismatch %s actual=%s expected=%s\n", name, digest.c_str(), expected);
            return false;
        }
        out = Json::parse(bytes, nullptr, false);
        bool ok = !out.is_discarded() && out.is_object();
        logf(platform.log, "[za-randomizer] asset verified %s bytes=%zu parsed=%d\n", name, bytes.size(), int(ok));
        return ok;
    }
    std::string defaultPlayerName() {
        const auto remembered = za::native::rememberedPlayerName(paths.runRoot);
        if (!remembered.empty()) return remembered;
        Bytes bytes;
        std::string name, error;
        if (readAsset("city-save.bin", bytes) && za::native::readPlayerName(bytes, name, error) && za::native::validPlayerName(name)) return name;
        return "Trainer";
    }
};

Controller::Controller(const Paths& paths, const Platform& platform) : impl_(new Impl) {
    impl_->paths = paths;
    impl_->platform = platform;
    if (!paths.buildLabel.empty()) state_.buildLabel = paths.buildLabel;
    state_.statusLine = model::capabilitiesPresent() ? "Options follow this build's generator (capabilities.json)  ·  early Rock route guard on"
                                                     : "Early Rock route guard on  ·  all other ordinary spawns follow the settings";
}

Controller::~Controller() {
    if (impl_->threadStarted) pthread_join(impl_->thread, nullptr);
}

std::string Controller::dateOfRunId(const std::string& id) {
    // r%016llx-%08x
    if (id.size() < 18 || id[0] != 'r' || id[17] != '-') return "";
    unsigned long long t = std::strtoull(id.substr(1, 16).c_str(), nullptr, 16);
    if (!t) return "";
    time_t tt = time_t(t);
    struct tm tmv {};
#ifdef _WIN32
    gmtime_s(&tmv, &tt);
#else
    gmtime_r(&tt, &tmv);
#endif
    static const char* months[] = {"Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"};
    char buf[32];
    std::snprintf(buf, sizeof buf, "%d %s %d", tmv.tm_mday, months[tmv.tm_mon % 12], tmv.tm_year + 1900);
    return buf;
}

model::Values Controller::valuesFromReport(const std::string& reportJson) {
    model::Values v = model::defaults();
    Json j = Json::parse(reportJson, nullptr, false);
    if (j.is_discarded() || !j.is_object()) return v;
    if (j.contains("ui_options") && j["ui_options"].is_object()) {
        model::Values parsed = model::defaults();
        if (model::fromJson(j["ui_options"].dump(), parsed)) return parsed;
    }
    // r6..r29 reports: today's booleans, the music mode, the player name
    if (j.contains("options") && j["options"].is_object()) {
        const Json& o = j["options"];
        auto flag = [&](const char* key, bool def) { return o.contains(key) && o[key].is_boolean() ? o[key].get<bool>() : def; };
        const model::RowDef* wild = model::findRow("wild_mode");
        const model::RowDef* trainers = model::findRow("trainers_mode");
        auto indexOf = [](const model::RowDef* r, const char* optionId) {
            if (!r) return 0;
            for (size_t i = 0; i < r->options.size(); i++)
                if (!std::strcmp(r->options[i].id, optionId)) return int(i);
            return 0;
        };
        v.set("wild_mode", indexOf(wild, flag("wild", true) ? "random" : "off"));
        v.set("trainers_mode", indexOf(trainers, flag("trainers", true) ? "random" : "off"));
        v.set("mega_trainers", flag("mega_trainers", true) ? 1 : 0);
        v.set("dlc_rematches", flag("dlc_rematches", true) ? 1 : 0);
        v.set("research_rewards", flag("research_rewards", true) ? 1 : 0);
        std::string music = o.contains("music") && o["music"].is_string() ? o["music"].get<std::string>() : "";
        if (music.empty() && j.contains("music") && j["music"].is_object() && j["music"].contains("mode") && j["music"]["mode"].is_string())
            music = j["music"]["mode"].get<std::string>();
        if (!music.empty()) v.set("music", indexOf(model::findRow("music"), music.c_str()));
    }
    if (j.contains("starter") && j["starter"].is_number_integer()) {
        // an old report does not say whether the player chose the starter or the seed did: a species of the vanilla
        // trio is shown as "Vanilla choice", one of the nine as "Any starter", anything else as "Random by seed"
        int species = j["starter"].get<int>();
        for (int mode = 0; mode < 2; mode++) {
            const auto& list = model::starterList(mode);
            bool found = false;
            for (size_t i = 0; i < list.size() && !found; i++)
                if (list[i].species == species) { v.set("starter_mode", mode); v.set("starter_pick", int(i)); found = true; }
            if (found) break;
        }
    }
    std::string name = za::native::reportPlayerName(j);
    if (!name.empty()) v.setText("player_name", name);
    return v;
}

std::vector<RunCard> Controller::loadCards(const std::string& root, const std::string& activeId, void (*log)(const char*)) {
    std::vector<RunCard> cards;
    for (const Run& run : za::native::listRuns(root)) {
        RunCard card;
        card.id = run.id;
        card.seed = run.seed;
        card.starter = run.starter;
        card.date = dateOfRunId(run.id);
        card.active = run.id == activeId;
        Bytes bytes;
        if (za::native::readFile(root + "/" + run.id + "/report.json", bytes, 1u << 20)) {
            std::string text(bytes.begin(), bytes.end());
            model::Values v = valuesFromReport(text);
            card.summary = model::summary(v);
            card.trainer = v.text("player_name");
        }
        if (card.trainer.empty()) card.trainer = "Trainer";
        cards.push_back(std::move(card));
    }
    logf(log, "[ui-v2] %zu saved runs listed\n", cards.size());
    return cards;
}

bool Controller::init() {
    Impl& I = *impl_;
    bool assetsOK = I.jsonAsset("tables.json", ZA_TABLES_SHA256, I.assets) && I.jsonAsset("starter-deltas.json", ZA_STARTERS_SHA256, I.starters) &&
                    I.jsonAsset("research-rewards.json", ZA_REWARDS_SHA256, I.rewards) && I.jsonAsset("progression.json", ZA_PROGRESSION_SHA256, I.progression);
    bool storageOK = assetsOK && za::native::makeDirs(I.paths.runRoot);
    if (!assetsOK || !storageOK) {
        logf(I.platform.log, "[za-randomizer] startup assets=%d storage=%d errno=%d\n", int(assetsOK), int(storageOK), errno);
        I.log("[za-randomizer] asset integrity or run storage failure\n");
        state_.screen = Screen::Error;
        state_.fatal = true;
        state_.errorText = assetsOK ? "The run storage could not be created." : "The randomizer data could not be loaded or failed its integrity check.";
        dirty_ = true;
        return false;
    }
    I.assets["tables"]["research_rewards"] = {{"path", "ik_event/bin/research_lv/research_lv.bin"}};
    I.assets["tables"][za::native::MusicTableName] = {{"path", za::native::MusicBankPath}};
    const std::string planText = za::native::zaMusicPlanJson();
    I.musicReady = za::sha256(Bytes(planText.begin(), planText.end())) == za::native::zaMusicPlanSha256();
    I.log(I.musicReady ? "[za-randomizer] music plan verified\n" : "[za-randomizer] music plan integrity FAILED; MUSIC stays OFF\n");
    std::string repairError;
    if (!I.paths.repairStage.empty() && !za::native::importStagedRepair(I.paths.runRoot, I.paths.repairStage, I.assets, repairError)) {
        I.log(("[za-randomizer] repair REFUSED: " + repairError + "\n").c_str());
        state_.screen = Screen::Error;
        state_.fatal = true;
        state_.errorText = "A staged run repair could not be verified: " + repairError + " The original run and save have been retained.";
        dirty_ = true;
        return false;
    }
    I.log("[za-randomizer] optional staged repair checked; run storage ready\n");
    I.runs = za::native::listRuns(I.paths.runRoot);
    I.active = za::native::activeRun(I.paths.runRoot);
    state_.runs = loadCards(I.paths.runRoot, I.active, I.platform.log);
    state_.activeRun = -1;
    for (size_t i = 0; i < state_.runs.size(); i++)
        if (state_.runs[i].active) state_.activeRun = int(i);
    state_.recentSeeds.clear();
    for (const auto& c : state_.runs)
        if (state_.recentSeeds.size() < 3) state_.recentSeeds.push_back(c.seed);
    state_.seed = I.platform.freshSeed ? I.platform.freshSeed() : "1";
    state_.values = model::defaults();
    state_.values.setText("player_name", I.defaultPlayerName());
    state_.nav = model::Nav{0, I.active.empty() ? 1 : 0};
    state_.screen = Screen::Settings;
    dirty_ = true;
    return true;
}

static void copyKeyboard(const za::native::NameKeyboard& k, NameScreen& out) {
    out.text = k.text();
    out.message = k.message();
    out.row = k.row();
    out.lower = k.lower();
    out.labels.assign(size_t(za::native::NameKeyboard::Rows), {});
    out.widths.assign(size_t(za::native::NameKeyboard::Rows), {});
    out.column = 0;
    for (int row = 0; row < za::native::NameKeyboard::Rows; row++) {
        for (int col = 0; col < za::native::NameKeyboard::Columns;) {
            int width = za::native::NameKeyboard::keyWidth(row, col);
            if (row == k.row() && col == za::native::NameKeyboard::keyStart(k.row(), k.column())) out.column = int(out.labels[size_t(row)].size());
            out.labels[size_t(row)].push_back(k.label(row, col));
            out.widths[size_t(row)].push_back(width);
            col += width;
        }
    }
}

void Controller::press(model::Button b) {
    Impl& I = *impl_;
    using B = model::Button;
    if (done()) return;
    dirty_ = true;
    auto toast = [&](Toast::Kind kind, const std::string& text, const std::string& detail = "") {
        state_.toastVisible = true;
        state_.toast = {kind, text, detail};
        I.toastUntilMs = 0;  // armed by the next tick
    };
    auto select = [&](const std::string& id) {
        std::string error;
        if (za::native::selectRun(I.paths.runRoot, id, error)) {
            selected_ = id;
            logf(I.platform.log, "[za-randomizer] boot selected run=%s\n", id.c_str());
        } else {
            I.before = Screen::Settings;
            state_.screen = Screen::Error;
            state_.errorText = error;
        }
    };
    switch (state_.screen) {
        case Screen::Error:
            if (state_.fatal) return;
            if (b == B::Cross || b == B::Circle) { state_.screen = I.before; state_.errorText.clear(); }
            return;
        case Screen::Generating: return;
        case Screen::Confirm:
            if (b == B::Circle) { state_.screen = Screen::Settings; return; }
            if (b != B::Cross) return;
            {
                Job& j = I.job;
                const model::Values& v = state_.values;
                j.assets = &I.assets; j.starters = &I.starters; j.rewards = &I.rewards; j.progression = &I.progression;
                j.options = za::Options{};
                j.options.wild = v.get("wild_mode", 3) != 0;
                j.options.trainers = v.get("trainers_mode", 3) != 0;
                j.options.mega_trainers = v.get("mega_trainers", 1) != 0;
                j.options.dlc_rematches = v.get("dlc_rematches", 1) != 0;
                j.researchRewards = v.get("research_rewards", 1) != 0;
                j.music = I.musicReady ? za::native::MusicMode(v.get("music", 0) % za::native::MusicModeCount) : za::native::MusicMode::Off;
                j.seed = state_.seed;
                j.playerName = v.text("player_name");
                if (!za::native::validPlayerName(j.playerName)) j.playerName = "Trainer";
                j.uiOptionsJson = model::toJson(v);
                j.gameImage = I.paths.gameImage;
                j.root = I.paths.runRoot;
                j.readAsset = [this](const std::string& name, Bytes& bytes) { return impl_->readAsset(name, bytes); };
                j.log = I.platform.log;
                int mode = v.get("starter_mode", 2);
                const auto& list = model::starterList(mode);
                j.starter = list.empty() ? 0 : list[size_t(std::max(0, std::min(v.get("starter_pick", 0), int(list.size()) - 1)))].species;
                char id[64];
                unsigned long long t = I.platform.unixTime ? I.platform.unixTime() : (unsigned long long)time(nullptr);
                unsigned r = I.platform.random32 ? I.platform.random32() : unsigned(std::rand());
                std::snprintf(id, sizeof id, "r%016llx-%08x", t, r);
                j.id = id;
                j.error.clear(); j.success = false; j.finished = false; j.done = 0; j.total = 1; j.stage = 0;
                I.previousDone = I.previousStage = -1;
                state_.genStage = 0; state_.genDone = 0; state_.genTotal = 1;
                if (pthread_create(&I.thread, nullptr, generateJob, &j)) {
                    I.before = Screen::Settings;
                    state_.screen = Screen::Error;
                    state_.errorText = "Could not start generation";
                } else {
                    I.threadStarted = true;
                    state_.screen = Screen::Generating;
                }
            }
            return;
        case Screen::Seed: {
            if (b == B::Circle) { state_.screen = Screen::Settings; return; }
            int& k = state_.keypad;
            if (b == B::Left) k = k / 3 * 3 + (k % 3 + 2) % 3;
            if (b == B::Right) k = k / 3 * 3 + (k % 3 + 1) % 3;
            if (b == B::Up) k = (k + 9) % 12;
            if (b == B::Down) k = (k + 3) % 12;
            if (b == B::Square) { if (!state_.seedInput.empty()) state_.seedInput.pop_back(); I.replaceSeed = false; }
            if (b == B::Triangle) { state_.seedInput = I.platform.freshSeed ? I.platform.freshSeed() : "1"; I.replaceSeed = true; }
            if (b == B::Cross) {
                if (k == 9) { state_.seedInput.clear(); I.replaceSeed = false; }
                else if (k == 11) {
                    if (!state_.seedInput.empty()) {
                        auto first = state_.seedInput.find_first_not_of('0');
                        state_.seed = first == std::string::npos ? "0" : state_.seedInput.substr(first);
                        state_.screen = Screen::Settings;
                    }
                } else {
                    if (I.replaceSeed) { state_.seedInput.clear(); I.replaceSeed = false; }
                    if (state_.seedInput.size() < 16) state_.seedInput += k == 10 ? '0' : char('1' + k);
                }
            }
            return;
        }
        case Screen::Name: {
            uint32_t bits = b == B::Up ? KUp : b == B::Down ? KDown : b == B::Left ? KLeft : b == B::Right ? KRight : b == B::Cross ? KCross
                          : b == B::Circle ? KCircle : b == B::Triangle ? KTriangle : b == B::Square ? KSquare : 0;
            if (!bits) return;
            auto action = I.keyboard.press(bits);
            if (action == za::native::NameKeyboard::Action::Done) { state_.values.setText("player_name", I.keyboard.result()); state_.screen = Screen::Settings; }
            else if (action == za::native::NameKeyboard::Action::Cancel) state_.screen = Screen::Settings;
            copyKeyboard(I.keyboard, state_.name);
            return;
        }
        case Screen::SavedRuns:
        case Screen::Settings: break;
    }
    // the settings pages (and the Saved runs cards, which are a page)
    const model::PageDef& p = model::page(state_.nav.page);
    if (p.cards) {
        int n = int(state_.runs.size());
        if (b == B::Up && n) { state_.runIndex = (state_.runIndex + n - 1) % n; return; }
        if (b == B::Down && n) { state_.runIndex = (state_.runIndex + 1) % n; return; }
        if (b == B::Cross) { if (n) select(state_.runs[size_t(state_.runIndex)].id); return; }
        if (b == B::Triangle) return;  // nothing to reset on the cards
    }
    model::Event e = model::handle(state_.nav, state_.values, b, false);
    switch (e.type) {
        case model::Event::Continue:
            if (I.active.empty()) toast(Toast::Info, "No run yet", "Start a new run below");
            else select(I.active);
            break;
        case model::Event::StartNewRun: state_.screen = Screen::Confirm; break;
        case model::Event::OpenSeed: state_.seedInput = state_.seed; state_.keypad = 0; I.replaceSeed = true; state_.screen = Screen::Seed; break;
        case model::Event::OpenSavedRuns: state_.nav.page = savedRunsPage(); state_.nav.row = 0; break;
        case model::Event::OpenName:
            I.keyboard = za::native::NameKeyboard(state_.values.text("player_name"));
            copyKeyboard(I.keyboard, state_.name);
            state_.screen = Screen::Name;
            break;
        case model::Event::RandomSeed:
            state_.seed = I.platform.freshSeed ? I.platform.freshSeed() : "1";
            toast(Toast::Info, "New random seed", groupedSeed(state_.seed));
            break;
        case model::Event::Changed:
            if (e.text == "music" && !I.musicReady) { state_.values.set("music", 0); toast(Toast::Warn, "Music plan unavailable in this build"); }
            break;
        case model::Event::Toast: toast(e.text.find("reset") != std::string::npos ? Toast::Info : Toast::Warn, e.text); break;
        case model::Event::BackToPlay:
        case model::Event::None: break;
    }
}

void Controller::tick(uint64_t nowMs) {
    Impl& I = *impl_;
    if (done()) return;
    if (state_.toastVisible) {
        if (!I.toastUntilMs) I.toastUntilMs = nowMs + 2500;
        else if (nowMs >= I.toastUntilMs) { state_.toastVisible = false; I.toastUntilMs = 0; dirty_ = true; }
    }
    if (state_.screen == Screen::Generating) {
        Job& j = I.job;
        if (j.finished.load(std::memory_order_acquire)) {
            pthread_join(I.thread, nullptr);
            I.threadStarted = false;
            dirty_ = true;
            if (j.success) {
                if (!za::native::rememberPlayerName(I.paths.runRoot, j.playerName))
                    I.log("[za-randomizer] run created; trainer-name preference could not be saved\n");
                const model::Values& v = state_.values;
                if (!writeCheatDefaults(I.paths.runRoot + "/" + j.id, v.get("shiny_default", 0), v.get("capture_default", 0), v.get("fps_counter_default", 1)))
                    I.log("[ui-v2] cheat defaults could not be written; the run starts with the overlay's defaults\n");
                else
                    logf(I.platform.log, "[ui-v2] cheat defaults written: shiny=%d capture=%d fps=%d\n", v.get("shiny_default", 0), v.get("capture_default", 0),
                         v.get("fps_counter_default", 1));
                created_ = j.id;
                selected_ = j.id;  // publishRun already made it the active run
                logf(I.platform.log, "[za-randomizer] boot selected run=%s\n", j.id.c_str());
            } else {
                I.before = Screen::Settings;
                state_.screen = Screen::Error;
                state_.errorText = j.error.empty() ? "Generation failed" : j.error;
            }
        } else {
            int d = j.done.load(), s = j.stage.load(), t = j.total.load();
            if (d != I.previousDone || s != I.previousStage) {
                I.previousDone = d; I.previousStage = s;
                state_.genStage = s < 0 ? 0 : s > 5 ? 5 : s;
                state_.genDone = d > t ? t : d;
                state_.genTotal = t;
                dirty_ = true;
            }
        }
        return;
    }
    if (state_.screen == Screen::Settings && state_.nav.page == 0 && I.platform.observerContinue && !I.active.empty() &&
        I.platform.observerContinue(I.active.c_str())) {
        std::string error;
        if (za::native::selectRun(I.paths.runRoot, I.active, error)) {
            selected_ = I.active;
            logf(I.platform.log, "[za-randomizer] boot selected run=%s (observer)\n", I.active.c_str());
        } else {
            I.before = Screen::Settings;
            state_.screen = Screen::Error;
            state_.errorText = error;
        }
        dirty_ = true;
    }
}

std::string Controller::selectedSummary() const { return model::summary(state_.values); }

}  // namespace ui::launcher
