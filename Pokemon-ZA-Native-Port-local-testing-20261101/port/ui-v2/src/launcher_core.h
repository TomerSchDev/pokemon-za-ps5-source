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
    static std::vector<RunCard> loadCards(const std::string& root, const std::string& activeId, void (*log)(const char*));
    // A run card's date from the run id ("r%016llx-%08x": the creation time in seconds).
    static std::string dateOfRunId(const std::string& id);
    // Values from a report.json (its "ui_options" when present, else today's booleans and music mode).
    static model::Values valuesFromReport(const std::string& reportJson);

private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
    State state_;
    bool dirty_ = true;
    std::string selected_, created_;
};

}  // namespace ui::launcher
