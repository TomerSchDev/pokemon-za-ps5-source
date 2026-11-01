// ui-v2: the launcher's controller - everything bootMenu() of port/rando-music/native_menu_music.cpp did except
// drawing and the display: assets (hash-checked), the optional staged repair, the run list, the settings pages
// (ui_model), seed keypad, trainer-name keyboard (rando-v2 NameKeyboard), confirm, the generation job on its own
// thread (core generate -> protectProgression -> research rewards -> nameRun -> randomizeMusic -> publishRun), the
// new run's report.json "ui_options" (model::toJson) and cheats.txt defaults, and the active-run selection.
//
// No Vulkan, no SDL, no console API: the title's launcher_run (launcher_ps5.cpp) feeds it buttons and draws its
// State; the host tests drive it with a scripted button list over a temporary run root.
#pragma once
#include <cstdint>
#include <memory>
#include <string>
#include <vector>

#include "ui_launcher.h"

namespace ui::launcher {

struct Paths {
    std::string runRoot;      // the runs' folder (PS5: /download0/zarecomp/rando; PC: <data root>/rando)
    std::string assets;       // the immutable randomizer assets, with a trailing slash (PS5: /app0/randomizer-assets/)
    std::string gameImage;    // the game's RomFS image (PS5: /app0/game/romfs.bin), for the music bank
    std::string repairStage;  // optional staged repair (PS5: /app0/run-repair); empty = none
    std::string buildLabel;   // shown under the title ("r29-ui")
};

struct Platform {
    void (*log)(const char* line) = nullptr;                   // a klog / stderr line (with its newline)
    std::string (*freshSeed)() = nullptr;                      // random decimal seed (PS5: arc4random)
    bool (*observerContinue)(const char* activeRun) = nullptr; // za_observer_menu: continue exactly the active run
    uint64_t (*unixTime)() = nullptr;                          // for the run id
    uint32_t (*random32)() = nullptr;                          // for the run id
};

// ---- saved runs: compatibility, the slot container (za_slot.h), deletion
namespace saves {

// Whether THIS build can continue a saved run. The rule (documented in port/ui-v2/README-HE.md, tested in
// test/test_saves.cpp) is read from the run's report.json only; the slot container is display data:
//   1. the run passes the run store's integrity check (za::native::listRuns: complete report, save present, every
//      randomized table matches its recorded SHA-256), else "damaged";
//   2. report "v3_algorithm" == this build's generator ("za202-randomizer-v3"); absent = made by the v2 generator;
//   3. report "build_id" == this build's game build (codes::CurrentGameBuild);
//   4. report "v3" is an object (the v3 generator's own record);
//   5. report "ui_options" has "schema": 2 and a "values" object.
struct Compat {
    bool supported = false;
    std::string badge;   // "OLD VERSION" / "OTHER GAME BUILD" / "DAMAGED" (empty when supported)
    std::string reason;  // one line for the card
};
Compat compatibilityOfReport(const std::string& reportJson);
Compat damagedRun();

// Every directory under root whose name is a valid run id (complete or not), newest first.
std::vector<std::string> runDirectories(const std::string& root);

// File operations the deletion uses; the tests inject failures.
struct FsOps {
    int (*renameFn)(const char*, const char*);
    int (*unlinkFn)(const char*);
    int (*rmdirFn)(const char*);
};
FsOps systemFs();

enum class DeleteResult { Deleted, DeletedWithLeftovers, Failed };
// Deletes rando/<id>: (1) rename it to rando/.deleting-<id> - one atomic step that removes it from every listing;
// (2) if active.json named it, remove active.json (no active run); on failure the folder is renamed back and nothing
// changed; (3) remove .deleting-<id> recursively. A failure in (3) leaves only the hidden .deleting-<id> folder, which
// sweepDeleting() finishes at the next start. Never touches any other run, .pending-* staging or the active marker of
// another run.
DeleteResult deleteRun(const std::string& root, const std::string& id, std::string& error, const FsOps& ops = systemFs());
// Finishes interrupted deletions (rando/.deleting-<valid id> only). Returns how many were removed.
int sweepDeleting(const std::string& root, const FsOps& ops = systemFs());
// The id active.json names, without validating the run (empty when absent or unreadable).
std::string activeMarker(const std::string& root);

// The slot container rando/<id>/slot.zrs: built from report.json + the run's save (caught/seen/location read from
// the save bytes), written atomically. Returns false (and logs nothing) on failure; the game save is never touched.
inline constexpr const char* SlotFile = "slot.zrs";
// Display names for the slot cards: <assets>/slot-names.json (schema "za-slot-names-1"), extracted from the game's
// own message and story data at package time (port/ui-v2/tools/extract-slot-names.py; never in git). Optional: when
// it is absent or unreadable the cards show the raw ids ("Phase 21110", "t1").
struct Names {
    struct Range { uint32_t min = 0, max = 0; std::string label, title; };
    struct Area { std::string map, name; float x0 = 0, z0 = 0, x1 = 0, z1 = 0; };
    std::vector<Range> missions, dlcMissions;
    std::vector<std::pair<std::string, std::string>> maps;
    std::vector<Area> areas;
    bool loaded = false;
    bool parse(const std::string& json);
    // "Main Mission 2 · A New Life in Lumiose City"; "Phase 21110" when unknown; "" for phase 0
    std::string mission(uint32_t storyPhase, uint32_t dlcPhase) const;
    // "Lumiose City — Vert Sector 3", "Lumiose City", else the id
    std::string place(const std::string& mapId, float x, float z) const;
};
inline constexpr const char* NamesFile = "slot-names.json";

// SwishCrypto's save hash over a payload (for za_slot_save_progress's check): SHA-256(intro + payload + outro).
int swishHash(const uint8_t* payload, size_t n, uint8_t out[32]);
bool writeSlotContainer(const std::string& runDir, const std::string& reportJson, uint64_t saveTime, uint64_t createdTime,
                        std::string& error);

}  // namespace saves

class Controller {
public:
    Controller(const Paths& paths, const Platform& platform);
    ~Controller();
    Controller(const Controller&) = delete;
    Controller& operator=(const Controller&) = delete;

    // Loads and verifies the assets, imports a staged repair, lists the runs. A failure leaves the state on the fatal
    // error screen (the title keeps drawing it; the player closes the app) and returns false.
    bool init();
    // One button press (edge or repeat).
    void press(model::Button b);
    // Called every frame: generation progress, toast expiry, the observer's continue request.
    void tick(uint64_t nowMs);
    // The drawable state. dirty() says it changed since clearDirty().
    const State& state() const { return state_; }
    bool dirty() const { return dirty_; }
    void clearDirty() { dirty_ = false; }
    // A run was selected (continued or created): the title hands over to the game.
    bool done() const { return !selected_.empty(); }
    const std::string& selectedRun() const { return selected_; }
    // The settings of the selected run (for the title's log line).
    std::string selectedSummary() const;
    // What the launcher wrote for the run it created (empty when it continued an existing one).
    const std::string& createdRun() const { return created_; }

    // Builds the cards of the saved runs (reads every report.json under the root); public for the tests.
    static std::vector<RunCard> loadCards(const std::string& root, const std::string& activeId, void (*log)(const char*),
                                          const saves::Names* names = nullptr);
    // A run card's date from the run id ("r%016llx-%08x": the creation time in seconds).
    static std::string dateOfRunId(const std::string& id);
    // "31 Oct 2026" for a unix time (UTC); empty for 0.
    static std::string dateOfUnix(uint64_t t);
    // Values from a report.json (its "ui_options" when present, else today's booleans and music mode).
    static model::Values valuesFromReport(const std::string& reportJson);
    // Codes for older reports are recomputed only when their generator algorithm is known; missing metadata stays blank.
    static std::string configurationCodeFromReport(const std::string& reportJson);

private:
    void refreshRuns();  // re-lists the cards and the active run (never an unsupported one)
    struct Impl;
    std::unique_ptr<Impl> impl_;
    State state_;
    bool dirty_ = true;
    std::string selected_, created_;
};

}  // namespace ui::launcher
