#include "launcher_core.h"

#include <algorithm>
#include <atomic>
#include <cerrno>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <dirent.h>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>

#include "assets_hashes_v3.h"  // SHA-256 pins of the complete rando-v3 assets shipped with this build
#include "rando_v3.hpp"
#include "settings_codes.h"
#include "import_repair_v3.hpp"
#include "name_keyboard.hpp"
#include "progression.hpp"
#include "research_rewards.hpp"
#include "run_name.hpp"
#include "run_store.hpp"
#include "za_music.hpp"
#include "za_music_plan.hpp"
#include "za_player_name.hpp"

#ifdef ZA_RANDOMIZER_PS5
#include "platform/ps5_compat.h"  // opendir / readdir: the platform layer's (as run_store_v3.cpp)
#endif
#define ZA_SLOT_IMPLEMENTATION
#include "za_slot.h"
#include "saves_fs.h"
#include <mbedtls/sha256.h>

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
    const za::v3::Assets* assets = nullptr;
    za::native::MusicMode music = za::native::MusicMode::Off;
    std::string seed, id, error, playerName, uiOptionsJson, gameImage, root;
    za::Reader readAsset;
    void (*log)(const char*) = nullptr;
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
    Json ui = Json::parse(j.uiOptionsJson, nullptr, false);
    za::v3::Settings settings;
    if (!ui.is_discarded() && za::v3::settingsFromUi(ui, settings, j.error) &&
        za::v3::generateRun(*j.assets, j.readAsset, j.seed, settings, ui, result, progress)) {
        const std::string gameImage = j.gameImage;
        if (za::native::nameRun(j.playerName, result, j.error) &&
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
            model::Values values = model::defaults();
            if (!model::fromJson(j.uiOptionsJson, values)) {
                j.error = "Could not encode the settings comparison codes";
            } else {
                values.setText("player_name", j.playerName);
                const codes::SettingsCodes encoded = codes::compute(values);
                result.report["settings_codes"] = {{"schema", codes::Schema}, {"algorithm", codes::CurrentAlgorithm},
                    {"game_build", codes::CurrentGameBuild},
                    {"word_bank", {{"version", codes::WordBankVersion}, {"sha256", codes::WordBankSha256}}},
                    {"overall", encoded.overall}, {"categories", {{"wild", encoded.wild}, {"trainers", encoded.trainers},
                    {"starter", encoded.starter}, {"research", encoded.research}, {"music", encoded.music},
                    {"player", encoded.player}, {"cheats", encoded.cheats}}}};
                j.success = za::native::publishRun(j.root, j.id, j.assets->tables, result, j.error);
            }
        }
    } else {
        if (j.error.empty()) j.error = ui.is_discarded() ? "Invalid UI settings" : result.error;
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

// ------------------------------------------------------------------------------------------ saved runs
namespace saves {

Compat damagedRun() { return {false, "DAMAGED", "Files are incomplete or failed their integrity check."}; }

Compat compatibilityOfReport(const std::string& text) {
    const Json r = Json::parse(text, nullptr, false);
    if (r.is_discarded() || !r.is_object()) return damagedRun();
    auto str = [&](const char* key) { return r.contains(key) && r[key].is_string() ? r[key].get<std::string>() : std::string(); };
    const std::string v3 = str("v3_algorithm"), base = str("algorithm"), build = str("build_id");
    if (v3.empty())
        return {false, "OLD VERSION", "Made by the old v2 generator" + (base.empty() ? std::string() : " (" + base + ")") +
                                      ". This build only continues v3 runs."};
    if (v3 != za::v3::Algorithm)
        return {false, "OLD VERSION", "Made by generator " + v3 + "; this build continues " + std::string(za::v3::Algorithm) + " runs."};
    if (build != codes::CurrentGameBuild) return {false, "OTHER GAME BUILD", "Made for a different game build than this one."};
    if (!r.contains("v3") || !r["v3"].is_object()) return {false, "DAMAGED", "The report is missing the v3 generator record."};
    if (!r.contains("ui_options") || !r["ui_options"].is_object() || !r["ui_options"].contains("schema") || r["ui_options"]["schema"] != 2 ||
        !r["ui_options"].contains("values") || !r["ui_options"]["values"].is_object())
        return {false, "DAMAGED", "The report is missing the run's settings (ui_options schema 2)."};
    return {true, "", ""};
}

FsOps systemFs() { return {::rename, ::unlink, ::rmdir}; }

std::vector<std::string> runDirectories(const std::string& root) {
    std::vector<std::string> ids;
    DIR* d = opendir(root.c_str());
    if (!d) return ids;
    while (struct dirent* e = readdir(d)) {
        const std::string name = e->d_name;
        if (!za::native::validId(name)) continue;
        if (!fs_detail::isDirectoryNoFollow((root + "/" + name).c_str())) continue;
        ids.push_back(name);
    }
    closedir(d);
    std::sort(ids.begin(), ids.end(), [](const std::string& a, const std::string& b) { return a > b; });
    return ids;
}

std::string activeMarker(const std::string& root) {
    Bytes raw;
    if (!za::native::readFile(root + "/active.json", raw, 4096)) return {};
    const Json j = Json::parse(raw, nullptr, false);
    if (j.is_discarded() || !j.is_object() || !j.contains("id") || !j["id"].is_string()) return {};
    return j["id"].get<std::string>();
}

static bool removeTree(const std::string& dir, int depth, const FsOps& ops) {
    if (depth > 24) return false;
    DIR* d = opendir(dir.c_str());
    if (!d) return false;
    bool ok = true;
    std::vector<std::string> names;
    while (struct dirent* e = readdir(d)) {
        if (std::strcmp(e->d_name, ".") && std::strcmp(e->d_name, "..")) names.push_back(e->d_name);
    }
    closedir(d);
    for (const auto& name : names) {
        const std::string p = dir + "/" + name;
        struct stat st {};
        if (lstat(p.c_str(), &st)) { ok = false; continue; }
        if (S_ISDIR(st.st_mode)) ok = removeTree(p, depth + 1, ops) && ok;  // lstat: a symlink is unlinked, never followed
        else if (ops.unlinkFn(p.c_str())) ok = false;
    }
    return ok && !ops.rmdirFn(dir.c_str());
}

static void syncDirectory(const std::string& path) {
    int fd = open(path.c_str(), O_RDONLY);
    if (fd < 0) return;
    (void)ui_fsync(fd);  // some console filesystems do not implement directory fsync (run_store_v3.cpp)
    close(fd);
}

DeleteResult deleteRun(const std::string& root, const std::string& id, std::string& error, const FsOps& ops) {
    error.clear();
    if (!za::native::validId(id)) { error = "Not a run folder name."; return DeleteResult::Failed; }
    const std::string dir = root + "/" + id, trash = root + "/.deleting-" + id;
    struct stat st {};
    const int inspected = lstat(dir.c_str(), &st);
    if (inspected && (errno == EPERM || errno == ENOSYS || errno == ENOTSUP)) {
        error = "This system cannot safely inspect the run for deletion. Nothing was deleted.";
        return DeleteResult::Failed;
    }
    if (inspected || !S_ISDIR(st.st_mode)) {
        error = "The run folder rando/" + id + " is missing.";
        return DeleteResult::Failed;
    }
    if (!lstat(trash.c_str(), &st) && !removeTree(trash, 0, ops)) {
        error = "An earlier deletion of this run could not be finished (rando/.deleting-" + id + "). Nothing was deleted.";
        return DeleteResult::Failed;
    }
    const bool wasActive = activeMarker(root) == id;
    if (ops.renameFn(dir.c_str(), trash.c_str())) {
        error = "Could not move rando/" + id + " aside (errno " + std::to_string(errno) + "). Nothing was deleted.";
        return DeleteResult::Failed;
    }
    if (wasActive && ops.unlinkFn((root + "/active.json").c_str()) && errno != ENOENT) {
        const int saved = errno;
        if (ops.renameFn(trash.c_str(), dir.c_str())) {
            error = "Could not clear the active-run marker (errno " + std::to_string(saved) +
                    ") nor put the run back; its files are hidden and will be erased at the next start.";
            return DeleteResult::Failed;
        }
        error = "Could not clear the active-run marker (errno " + std::to_string(saved) + "). The run was put back; nothing was deleted.";
        return DeleteResult::Failed;
    }
    syncDirectory(root);
    if (!removeTree(trash, 0, ops)) {
        error = "Some files of the run could not be erased yet; they are hidden and will be erased at the next start.";
        return DeleteResult::DeletedWithLeftovers;
    }
    return DeleteResult::Deleted;
}

int sweepDeleting(const std::string& root, const FsOps& ops) {
    int removed = 0;
    DIR* d = opendir(root.c_str());
    if (!d) return 0;
    std::vector<std::string> names;
    while (struct dirent* e = readdir(d)) {
        const std::string name = e->d_name;
        if (name.rfind(".deleting-", 0) == 0 && za::native::validId(name.substr(10))) names.push_back(name);
    }
    closedir(d);
    for (const auto& name : names) {
        struct stat st {};
        const std::string p = root + "/" + name;
        if (!lstat(p.c_str(), &st) && S_ISDIR(st.st_mode) && removeTree(p, 0, ops)) removed++;
    }
    return removed;
}

static int sha256Fn(const uint8_t* data, size_t n, uint8_t out[32]) { return mbedtls_sha256(data, n, out, 0); }

// SwishCrypto's save hash: SHA-256(intro salt + payload + outro salt) (the salts of port/rando-v2/za_player_name.cpp)
static constexpr uint8_t IntroHash[64] = {
    0x9E, 0xC9, 0x9C, 0xD7, 0x0E, 0xD3, 0x3C, 0x44, 0xFB, 0x93, 0x03, 0xDC, 0xEB, 0x39, 0xB4, 0x2A,
    0x19, 0x47, 0xE9, 0x63, 0x4B, 0xA2, 0x33, 0x44, 0x16, 0xBF, 0x82, 0xA2, 0xBA, 0x63, 0x55, 0xB6,
    0x3D, 0x9D, 0xF2, 0x4B, 0x5F, 0x7B, 0x6A, 0xB2, 0x62, 0x1D, 0xC2, 0x1B, 0x68, 0xE5, 0xC8, 0xB5,
    0x3A, 0x05, 0x90, 0x00, 0xE8, 0xA8, 0x10, 0x3D, 0xE2, 0xEC, 0xF0, 0x0C, 0xB2, 0xED, 0x4F, 0x6D,
};
static constexpr uint8_t OutroHash[64] = {
    0xD6, 0xC0, 0x1C, 0x59, 0x8B, 0xC8, 0xB8, 0xCB, 0x46, 0xE1, 0x53, 0xFC, 0x82, 0x8C, 0x75, 0x75,
    0x13, 0xE0, 0x45, 0xDF, 0x32, 0x69, 0x3C, 0x75, 0xF0, 0x59, 0xF8, 0xD9, 0xA2, 0x5F, 0xB2, 0x17,
    0xE0, 0x80, 0x52, 0xDB, 0xEA, 0x89, 0x73, 0x99, 0x75, 0x79, 0xAF, 0xCB, 0x2E, 0x80, 0x07, 0xE6,
    0xF1, 0x26, 0xE0, 0x03, 0x0A, 0xE6, 0x6F, 0xF6, 0x41, 0xBF, 0x7E, 0x59, 0xC2, 0xAE, 0x55, 0xFD,
};
int swishHash(const uint8_t* payload, size_t n, uint8_t out[32]) {
    mbedtls_sha256_context ctx;
    mbedtls_sha256_init(&ctx);
    const int rc = mbedtls_sha256_starts(&ctx, 0) || mbedtls_sha256_update(&ctx, IntroHash, sizeof IntroHash) ||
                   mbedtls_sha256_update(&ctx, payload, n) || mbedtls_sha256_update(&ctx, OutroHash, sizeof OutroHash) ||
                   mbedtls_sha256_finish(&ctx, out);
    mbedtls_sha256_free(&ctx);
    return rc;
}

bool writeSlotContainer(const std::string& runDir, const std::string& reportJson, uint64_t saveTime, uint64_t createdTime,
                        std::string& error) {
    if (reportJson.size() > (1u << 20)) { error = "report.json exceeds the supported size"; return false; }
    const Json report = Json::parse(reportJson, nullptr, false);
    if (report.is_discarded() || !report.is_object()) { error = "report.json unreadable"; return false; }
    Bytes save;
    if (!za::native::readFile(runDir + "/save/save_0/main", save, 64u << 20)) { error = "save unreadable"; return false; }
    za_slot_summary s;
    std::memset(&s, 0, sizeof s);
    s.save_time = saveTime;
    s.created_time = createdTime;
    s.flags = za_slot_save_read(save.data(), save.size(), swishHash, &s);
    if (!sha256Fn(save.data(), save.size(), s.save_sha256)) s.flags |= ZA_SLOT_HAS_SAVE_HASH;
    auto put = [](char* dst, size_t cap, const std::string& v) { std::snprintf(dst, cap, "%s", v.c_str()); };
    auto str = [&](const char* key) { return report.contains(key) && report[key].is_string() ? report[key].get<std::string>() : std::string(); };
    put(s.run_id, sizeof s.run_id, str("native_run_id"));
    put(s.seed, sizeof s.seed, str("seed"));
    put(s.algorithm, sizeof s.algorithm, str("v3_algorithm").empty() ? str("algorithm") : str("v3_algorithm"));
    put(s.build_id, sizeof s.build_id, str("build_id"));
    const Compat compat = compatibilityOfReport(reportJson);
    Json rand = {{"schema", "za-slot-rand-1"}, {"run_id", str("native_run_id")}, {"v3_algorithm", str("v3_algorithm")},
                 {"base_algorithm", str("algorithm")}, {"build_id", str("build_id")}, {"supported_by_writer", compat.supported},
                 {"starter_name", str("starter_name")}, {"player_name", za::native::reportPlayerName(report)},
                 {"save_unix_time", saveTime}, {"created_unix_time", createdTime},
                 {"progress_source", (s.flags & ZA_SLOT_HAS_CAUGHT) ? "save" : "none"}};
    // Keep an additive, immutable snapshot of the original metadata. A newer
    // generator's fields must survive container refreshes without this UI
    // inventing support for them or rewriting the source report.json.
    rand["source_report"] = report;
    Json sett = {{"schema", "za-slot-settings-1"}, {"seed", str("seed")}};
    if (report.contains("ui_options")) sett["ui_options"] = report["ui_options"];
    if (report.contains("settings_codes") && report["settings_codes"].is_object() && report["settings_codes"].contains("overall"))
        sett["settings_phrase"] = report["settings_codes"]["overall"];
    const std::string randText = rand.dump(), settText = sett.dump();
    const size_t need = za_slot_build(nullptr, 0, &s, randText.data(), randText.size(), settText.data(), settText.size(), save.data(), save.size());
    Bytes out(need);
    za_slot_build(out.data(), out.size(), &s, randText.data(), randText.size(), settText.data(), settText.size(), save.data(), save.size());
    if (za_slot_write_atomic((runDir + "/" + SlotFile).c_str(), out.data(), out.size())) {
        error = "write failed errno=" + std::to_string(errno);
        return false;
    }
    return true;
}

bool Names::parse(const std::string& text) {
    *this = Names();
    const Json j = Json::parse(text, nullptr, false);
    if (j.is_discarded() || !j.is_object() || !j.contains("schema") || j["schema"] != "za-slot-names-1") return false;
    auto str = [](const Json& o, const char* k) { return o.contains(k) && o[k].is_string() ? o[k].get<std::string>() : std::string(); };
    auto num = [](const Json& o, const char* k) { return o.contains(k) && o[k].is_number() ? o[k].get<double>() : 0.0; };
    auto ranges = [&](const char* key, std::vector<Range>& out) {
        if (!j.contains(key) || !j[key].is_array()) return;
        for (const auto& r : j[key]) {
            if (!r.is_object() || !r.contains("phase_min") || !r["phase_min"].is_number_unsigned() || !r.contains("phase_max") ||
                !r["phase_max"].is_number_unsigned()) continue;
            Range x;
            x.min = uint32_t(r["phase_min"].get<uint64_t>());
            x.max = uint32_t(r["phase_max"].get<uint64_t>());
            x.label = str(r, "label");
            x.title = str(r, "title");
            if (x.min <= x.max && (!x.label.empty() || !x.title.empty())) out.push_back(std::move(x));
        }
    };
    ranges("missions", missions);
    ranges("dlc_missions", dlcMissions);
    if (j.contains("maps") && j["maps"].is_object())
        for (const auto& [k, v] : j["maps"].items())
            if (v.is_string() && !v.get<std::string>().empty()) maps.emplace_back(k, v.get<std::string>());
    if (j.contains("areas") && j["areas"].is_array())
        for (const auto& a : j["areas"]) {
            if (!a.is_object()) continue;
            Area x{str(a, "map"), str(a, "name"), float(num(a, "x0")), float(num(a, "z0")), float(num(a, "x1")), float(num(a, "z1"))};
            if (!x.map.empty() && !x.name.empty()) areas.push_back(std::move(x));
        }
    loaded = true;
    return true;
}

std::string Names::mission(uint32_t storyPhase, uint32_t dlcPhase) const {
    auto find = [](const std::vector<Range>& list, uint32_t phase) -> const Range* {
        for (const auto& r : list)
            if (phase >= r.min && phase <= r.max) return &r;
        return nullptr;
    };
    auto join = [](const Range& r) { return r.label.empty() ? r.title : r.title.empty() ? r.label : r.label + "  \xC2\xB7  " + r.title; };
    // the last story range is open-ended: once the story is finished (phase.bin's last value is 103000; the post-game
    // starts at 102000) a started DLC (SYS_WORK_DLC_PHASE != 0) is what the player is on
    if (dlcPhase && storyPhase >= 102000)
        if (const Range* r = find(dlcMissions, dlcPhase)) return join(*r);
    if (const Range* r = find(missions, storyPhase)) return join(*r);
    if (dlcPhase)
        if (const Range* r = find(dlcMissions, dlcPhase)) return join(*r);
    return storyPhase ? "Phase " + std::to_string(storyPhase) : std::string();
}

std::string Names::place(const std::string& mapId, float x, float z) const {
    std::string mapName;
    for (const auto& [id, name] : maps)
        if (id == mapId) { mapName = name; break; }
    for (const auto& a : areas)
        if (a.map == mapId && x >= std::min(a.x0, a.x1) && x <= std::max(a.x0, a.x1) && z >= std::min(a.z0, a.z1) && z <= std::max(a.z0, a.z1))
            return (mapName.empty() ? mapId : mapName) + " \xE2\x80\x94 " + a.name;
    return mapName.empty() ? mapId : mapName;
}

}  // namespace saves

struct Controller::Impl {
    Paths paths;
    Platform platform;
    za::v3::Assets generator;
    Json& assets = generator.tables;
    Json& starters = generator.starters;
    Json& rewards = generator.rewards;
    Json& progression = generator.progression;
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
    Screen deleteReturn = Screen::SavedRuns;
    saves::Names names;  // slot-names.json, read once at start

    uint64_t now() const { return platform.unixTime ? platform.unixTime() : uint64_t(time(nullptr)); }

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
    return dateOfUnix(std::strtoull(id.substr(1, 16).c_str(), nullptr, 16));
}

std::string Controller::dateOfUnix(uint64_t t) {
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

static std::string reportAlgorithm(const Json& report) {
    for (const char* key : {"v3_algorithm", "algorithm"})
        if (report.contains(key) && report[key].is_string()) return report[key].get<std::string>();
    return {};
}

std::string Controller::configurationCodeFromReport(const std::string& text) {
    const Json report = Json::parse(text, nullptr, false);
    if (report.is_discarded() || !report.is_object()) return {};
    if (!report.contains("ui_options") || !report["ui_options"].is_object() ||
        !report["ui_options"].contains("schema") || report["ui_options"]["schema"] != 2 ||
        !report["ui_options"].contains("values") || !report["ui_options"]["values"].is_object() ||
        !report.contains("build_id") || !report["build_id"].is_string()) return {};
    // Old booleans cannot reconstruct every category (for example random-vs-picked starters and cheat defaults).
    // Show unavailable rather than silently filling the missing information with this UI build's defaults.
    const Json& values = report["ui_options"]["values"];
    model::Values decoded;
    if (!model::fromJson(report["ui_options"].dump(), decoded)) return {};
    const Json canonical = Json::parse(model::toJson(decoded), nullptr, false);
    if (canonical.is_discarded()) return {};
    for (const auto& page : model::launcherPages())
        for (const auto& row : page.rows)
            if ((row.kind == model::Kind::Level || row.kind == model::Kind::Toggle || row.kind == model::Kind::Number ||
                 row.kind == model::Kind::Text || row.kind == model::Kind::Pick) &&
                (!values.contains(row.id) || values[row.id] != canonical["values"][row.id])) return {};
    return codes::configurationCode(decoded, reportAlgorithm(report), report["build_id"].get<std::string>());
}

std::vector<RunCard> Controller::loadCards(const std::string& root, const std::string& activeId, void (*log)(const char*)) {
    return loadCards(root, activeId, log, nullptr);
}

std::vector<RunCard> Controller::loadCards(const std::string& root, const std::string& activeId, void (*log)(const char*),
                                           const saves::Names* names) {
    std::vector<RunCard> cards;
    const std::vector<Run> complete = za::native::listRuns(root);
    size_t unsupported = 0;
    for (const std::string& id : saves::runDirectories(root)) {
        const auto it = std::find_if(complete.begin(), complete.end(), [&](const Run& r) { return r.id == id; });
        RunCard card;
        card.id = id;
        card.date = dateOfRunId(id);
        Bytes bytes;
        std::string text;
        if (za::native::readFile(root + "/" + id + "/report.json", bytes, 1u << 20)) text.assign(bytes.begin(), bytes.end());
        const Json report = Json::parse(text, nullptr, false);
        const bool parsed = !report.is_discarded() && report.is_object();
        saves::Compat compat = it == complete.end() ? saves::damagedRun() : saves::compatibilityOfReport(text);
        card.supported = compat.supported;
        card.badge = compat.badge;
        card.reason = compat.reason;
        if (it != complete.end()) {
            card.seed = it->seed;
            card.starter = it->starter;
        } else if (parsed) {
            card.seed = report.contains("seed") && report["seed"].is_string() ? report["seed"].get<std::string>() : "";
            card.starter = report.contains("starter_name") && report["starter_name"].is_string() ? report["starter_name"].get<std::string>() : "";
        }
        if (card.seed.empty()) card.seed = "?";
        if (card.starter.empty()) card.starter = "Unknown";
        card.active = card.supported && id == activeId;
        if (parsed) {
            model::Values v = valuesFromReport(text);
            card.summary = model::summary(v);
            card.trainer = v.text("player_name");
            card.configCode = configurationCodeFromReport(text);
            card.codeAlgorithm = reportAlgorithm(report);
        }
        if (card.trainer.empty()) card.trainer = "Trainer";
        // slot container: only its head is read (za_slot_read_summary_file); a missing/old/corrupt one shows "—"
        za_slot_summary slot;
        const int slotResult = za_slot_read_summary_file((root + "/" + id + "/" + saves::SlotFile).c_str(), &slot);
        uint64_t played = 0;
        if (slotResult == ZA_SLOT_OK && slot.run_id == id) {
            played = slot.save_time;
            if (slot.flags & ZA_SLOT_HAS_CAUGHT) card.caught = int(slot.caught > 9999 ? 9999 : slot.caught);
            if (slot.flags & ZA_SLOT_HAS_SEEN) card.seen = int(slot.seen > 9999 ? 9999 : slot.seen);
            if (slot.flags & ZA_SLOT_HAS_LOCATION)
                card.location = names ? names->place(slot.location, slot.x, slot.z) : std::string(slot.location);
            if (slot.flags & ZA_SLOT_HAS_PHASE)
                card.mission = names ? names->mission(slot.story_phase, slot.dlc_phase)
                                     : (slot.story_phase ? "Phase " + std::to_string(slot.story_phase) : std::string());
            if (slot.flags & ZA_SLOT_HAS_RESEARCH) card.researchLevel = int(slot.research_level > 999 ? 999 : slot.research_level);
        } else if (slotResult != ZA_SLOT_MISSING) {
            logf(log, "[ui-v2] slot container of %s ignored: %s\n", id.c_str(), za_slot_result_name(slotResult));
        }
        if (!played) {
            struct stat st {};
            if (!stat((root + "/" + id + "/save/save_0/main").c_str(), &st) && st.st_mtime > 0) played = uint64_t(st.st_mtime);
        }
        card.lastPlayed = dateOfUnix(played);
        unsupported += !card.supported;
        cards.push_back(std::move(card));
    }
    logf(log, "[ui-v2] %zu saved runs listed (%zu cannot be continued by this build)\n", cards.size(), unsupported);
    return cards;
}

void Controller::refreshRuns() {
    Impl& I = *impl_;
    const std::string marker = za::native::activeRun(I.paths.runRoot);
    state_.runs = loadCards(I.paths.runRoot, marker, I.platform.log, &I.names);
    I.active.clear();
    state_.activeRun = -1;
    for (size_t i = 0; i < state_.runs.size(); i++) {
        if (state_.runs[i].id != marker) continue;
        if (state_.runs[i].supported) {
            I.active = marker;
            state_.activeRun = int(i);
        } else {
            logf(I.platform.log, "[ui-v2] active run %s cannot be continued by this build (%s); not offered\n", marker.c_str(),
                 state_.runs[i].reason.c_str());
        }
    }
    const int n = int(state_.runs.size());
    if (state_.slotIndex > n) state_.slotIndex = n;
    if (state_.runIndex >= n) state_.runIndex = n ? n - 1 : 0;
}

bool Controller::init() {
    Impl& I = *impl_;
    bool assetsOK = I.jsonAsset("tables.json", ZA_TABLES_SHA256, I.assets) && I.jsonAsset("starter-deltas.json", ZA_STARTERS_SHA256, I.starters) &&
                    I.jsonAsset("research-rewards.json", ZA_REWARDS_SHA256, I.rewards) && I.jsonAsset("progression.json", ZA_PROGRESSION_SHA256, I.progression) &&
                    I.jsonAsset("v3.json", ZA_V3_SHA256, I.generator.v3);
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
    if (int swept = saves::sweepDeleting(I.paths.runRoot)) logf(I.platform.log, "[ui-v2] finished %d interrupted run deletion(s)\n", swept);
    {
        Bytes namesBytes;
        if (za::native::readFile(I.paths.assets + saves::NamesFile, namesBytes, 4u << 20) && I.names.parse(std::string(namesBytes.begin(), namesBytes.end())))
            logf(I.platform.log, "[ui-v2] slot names: %zu missions, %zu maps, %zu areas\n", I.names.missions.size(), I.names.maps.size(), I.names.areas.size());
        else
            I.log("[ui-v2] slot names not available; cards show raw phase / map ids\n");
    }
    I.runs = za::native::listRuns(I.paths.runRoot);
    refreshRuns();
    state_.recentSeeds.clear();
    for (const auto& c : state_.runs)
        if (state_.recentSeeds.size() < 3) state_.recentSeeds.push_back(c.seed);
    state_.seed = I.platform.freshSeed ? I.platform.freshSeed() : "1";
    state_.values = model::defaults();
    state_.values.setText("player_name", I.defaultPlayerName());
    state_.nav = model::Nav{0, I.active.empty() ? 1 : 0};
    // the save-slot menu first: the cursor on the active run, else on the empty slot
    state_.screen = Screen::SavedRuns;
    state_.slotIndex = state_.activeRun >= 0 ? state_.activeRun : int(state_.runs.size());
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
        const auto card = std::find_if(state_.runs.begin(), state_.runs.end(), [&](const RunCard& r) { return r.id == id; });
        if (card == state_.runs.end() || !card->supported) {
            toast(Toast::Warn, "Old version - can't continue", card == state_.runs.end() ? "" : card->reason);
            return;
        }
        if (za::native::selectRun(I.paths.runRoot, id, error)) {
            // a run made before slot containers existed gets one now (display data only; failure is logged)
            const std::string dir = I.paths.runRoot + "/" + id;
            za_slot_summary head;
            if (za_slot_read_summary_file((dir + "/" + saves::SlotFile).c_str(), &head) != ZA_SLOT_OK) {
                Bytes report;
                struct stat st {};
                const uint64_t played = !stat((dir + "/save/save_0/main").c_str(), &st) ? uint64_t(st.st_mtime) : 0;
                std::string slotError;
                if (!za::native::readFile(dir + "/report.json", report, 1u << 20) ||
                    !saves::writeSlotContainer(dir, std::string(report.begin(), report.end()), played, 0, slotError))
                    logf(I.platform.log, "[ui-v2] slot container not written for %s: %s\n", id.c_str(), slotError.c_str());
            }
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
            if (b == B::Cross || b == B::Circle) { state_.screen = I.before; state_.errorText.clear(); state_.errorTitle.clear(); state_.errorNote.clear(); }
            return;
        case Screen::Generating: return;
        case Screen::Confirm:
            if (b == B::Circle) { state_.screen = Screen::Settings; return; }
            if (b != B::Cross) return;
            {
                Job& j = I.job;
                const model::Values& v = state_.values;
                j.assets = &I.generator;
                j.music = I.musicReady ? za::native::MusicMode(v.get("music", 0) % za::native::MusicModeCount) : za::native::MusicMode::Off;
                j.seed = state_.seed;
                j.playerName = v.text("player_name");
                if (!za::native::validPlayerName(j.playerName)) j.playerName = "Trainer";
                j.uiOptionsJson = model::toJson(v);
                j.gameImage = I.paths.gameImage;
                j.root = I.paths.runRoot;
                j.readAsset = [this](const std::string& name, Bytes& bytes) { return impl_->readAsset(name, bytes); };
                j.log = I.platform.log;
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
        case Screen::DeleteConfirm: {
            using DM = State::DeleteMode;
            if (b == B::Circle) { state_.screen = I.deleteReturn; state_.deleteStage = 0; return; }
            if (b != B::Cross) return;
            if (state_.deleteMode == DM::Everything && state_.deleteStage == 0) { state_.deleteStage = 1; return; }  // the second confirm
            state_.deleteStage = 0;
            const bool many = state_.deleteMode != DM::One;
            std::vector<RunCard> targets;
            if (state_.deleteMode == DM::Unsupported) {
                for (const auto& r : state_.runs)
                    if (!r.supported) targets.push_back(r);
            } else if (state_.deleteMode == DM::Everything) {
                targets = state_.runs;
            } else if (state_.deleteIndex >= 0 && state_.deleteIndex < int(state_.runs.size())) {
                targets.push_back(state_.runs[size_t(state_.deleteIndex)]);
            }
            int deleted = 0;
            bool leftovers = false;
            std::string error, failedSeed;
            for (const auto& r : targets) {
                const saves::DeleteResult result = saves::deleteRun(I.paths.runRoot, r.id, error);
                logf(I.platform.log, "[ui-v2] delete run=%s seed=%s result=%d %s\n", r.id.c_str(), r.seed.c_str(), int(result), error.c_str());
                if (result == saves::DeleteResult::Failed) { failedSeed = r.seed; break; }
                deleted++;
                leftovers = leftovers || result == saves::DeleteResult::DeletedWithLeftovers;
            }
            refreshRuns();
            if (!failedSeed.empty()) {
                I.before = I.deleteReturn;
                state_.screen = Screen::Error;
                state_.errorTitle = !many ? "Could not delete this run"
                                    : state_.deleteMode == DM::Everything ? "Could not delete every run" : "Could not delete every unsupported run";
                state_.errorText = (many ? "Seed " + groupedSeed(failedSeed) + ": " : std::string()) + error;
                state_.errorNote = deleted ? std::to_string(deleted) + " run(s) were deleted before this one; the others were not touched."
                                           : "No run was deleted. Your other runs and saves were not touched.";
                return;
            }
            state_.screen = I.deleteReturn;
            if (many) toast(leftovers ? Toast::Warn : Toast::Ok, std::to_string(deleted) + (deleted == 1 ? " run deleted" : " runs deleted"),
                            leftovers ? "Some files are erased at the next start"
                                      : state_.deleteMode == DM::Everything ? "No run is active now" : "Supported runs were not touched");
            else toast(leftovers ? Toast::Warn : Toast::Ok, "Run deleted", targets.empty() ? "" :
                       "Seed " + groupedSeed(targets[0].seed) + (leftovers ? "  ·  some files are erased at the next start" : ""));
            return;
        }
        case Screen::SavedRuns: {
            // the save-slot menu: runs newest first, then the empty slot
            const int n = int(state_.runs.size());
            if (b == B::Up) { state_.slotIndex = (state_.slotIndex + n) % (n + 1); return; }
            if (b == B::Down) { state_.slotIndex = (state_.slotIndex + 1) % (n + 1); return; }
            if (b == B::Cross) {
                if (state_.slotIndex >= n) {
                    state_.screen = Screen::Settings;
                    state_.nav = model::Nav{0, 1};  // Play page, "Start a new run"
                } else {
                    select(state_.runs[size_t(state_.slotIndex)].id);
                }
                return;
            }
            if (b == B::Square && state_.slotIndex < n) {
                state_.deleteMode = State::DeleteMode::One;
                state_.deleteStage = 0;
                state_.deleteIndex = state_.slotIndex;
                state_.deleteFromCards = false;
                I.deleteReturn = Screen::SavedRuns;
                state_.screen = Screen::DeleteConfirm;
                return;
            }
            if (b == B::Triangle) {
                if (!unsupportedCount(state_)) { toast(Toast::Info, "Every run is supported", "Nothing to delete"); return; }
                state_.deleteMode = State::DeleteMode::Unsupported;
                state_.deleteStage = 0;
                state_.deleteIndex = -1;
                state_.deleteFromCards = false;
                I.deleteReturn = Screen::SavedRuns;
                state_.screen = Screen::DeleteConfirm;
                return;
            }
            if (b == B::R2) {
                if (!n) { toast(Toast::Info, "No runs to delete"); return; }
                state_.deleteMode = State::DeleteMode::Everything;
                state_.deleteStage = 0;
                state_.deleteIndex = -1;
                state_.deleteFromCards = false;
                I.deleteReturn = Screen::SavedRuns;
                state_.screen = Screen::DeleteConfirm;
                return;
            }
            return;
        }
        case Screen::Settings: break;
    }
    if (b == B::Circle && state_.nav.page == 0) { state_.screen = Screen::SavedRuns; return; }
    // the settings pages (and the Saved runs cards, which are a page)
    const model::PageDef& p = model::page(state_.nav.page);
    if (p.cards) {
        int n = int(state_.runs.size());
        if (b == B::Up && n) { state_.runIndex = (state_.runIndex + n - 1) % n; return; }
        if (b == B::Down && n) { state_.runIndex = (state_.runIndex + 1) % n; return; }
        if (b == B::Cross) { if (n) select(state_.runs[size_t(state_.runIndex)].id); return; }
        if (b == B::Square) {
            if (n) {
                state_.deleteMode = State::DeleteMode::One;
                state_.deleteStage = 0;
                state_.deleteIndex = state_.runIndex;
                state_.deleteFromCards = true;
                I.deleteReturn = Screen::Settings;
                state_.screen = Screen::DeleteConfirm;
            }
            return;
        }
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
        case model::Event::OpenSavedRuns:
            state_.screen = Screen::SavedRuns;
            state_.slotIndex = state_.activeRun >= 0 ? state_.activeRun : int(state_.runs.size());
            break;
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
                {
                    const std::string dir = I.paths.runRoot + "/" + j.id;
                    Bytes report;
                    std::string slotError;
                    const uint64_t t = I.now();
                    if (!za::native::readFile(dir + "/report.json", report, 1u << 20) ||
                        !saves::writeSlotContainer(dir, std::string(report.begin(), report.end()), t, t, slotError))
                        logf(I.platform.log, "[ui-v2] slot container not written: %s (the run is unaffected)\n", slotError.c_str());
                }
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
    // the observer's remote "continue": only the active run, only when it is supported (I.active is empty otherwise)
    if (((state_.screen == Screen::Settings && state_.nav.page == 0) || state_.screen == Screen::SavedRuns) && I.platform.observerContinue && !I.active.empty() &&
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
