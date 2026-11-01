// ui-v2: the launcher screens, drawn from the model into a 1920x1080 canvas.
#pragma once
#include <string>
#include <vector>

#include "ui_canvas.h"
#include "ui_model.h"
#include "ui_widgets.h"

namespace ui::launcher {

// SavedRuns = the save-slot menu, the launcher's first screen (SMO-randomizer style); DeleteConfirm = its dialogs.
enum class Screen { Settings, Seed, SavedRuns, Confirm, Generating, Name, Error, DeleteConfirm };

struct RunCard {
    std::string id, seed, starter, trainer, date, summary;
    bool active = false;
    std::string configCode, codeAlgorithm;
    // save slots
    bool supported = true;           // saves::compatibilityOfReport
    std::string badge, reason;       // why it cannot be continued (empty when supported)
    std::string lastPlayed;          // date of the last game save (slot container, else the save file's time); "" = unknown
    std::string location;            // friendly place (slot-names.json), else the game's map id; "" = unknown ("—")
    int caught = -1, seen = -1;      // Pokedex counts from the slot container; -1 = unknown (drawn as "—")
    std::string mission;             // current main mission ("Main Mission 2 · A New Life in Lumiose City"; else "Phase 21110")
    int researchLevel = -1;          // Mable's research level from the slot container; -1 = unknown
};

// The trainer-name keyboard as drawn (the state machine is rando-v2's NameKeyboard; the controller copies its
// getters here so the drawing code depends on nothing but this header).
struct NameScreen {
    std::string text, message;
    int row = 0, column = 0;
    bool lower = false;
    std::vector<std::vector<std::string>> labels;  // 5 rows; a wide key (CASE/SPACE/DEL/DONE) appears once with width 2
    std::vector<std::vector<int>> widths;
};

struct State {
    Screen screen = Screen::Settings;
    model::Nav nav;
    model::Values values = model::defaults();
    std::string seed = "0";          // the seed that a new run would use
    std::string seedInput;           // the keypad's text
    int keypad = 0;                  // 0..11 (1-9, CLEAR, 0, DONE)
    std::vector<std::string> recentSeeds;
    std::vector<RunCard> runs;
    int runIndex = 0;
    int activeRun = -1;              // index into runs, or -1 (never an unsupported run)
    int slotIndex = 0;               // save-slot menu cursor: 0..runs.size()-1 = a run, runs.size() = the empty slot
    // DeleteConfirm
    enum class DeleteMode { One, Unsupported, Everything };
    DeleteMode deleteMode = DeleteMode::One;
    int deleteStage = 0;             // Everything asks twice: 0 = first confirm, 1 = the second
    int deleteIndex = -1;            // the run to delete (index into runs)
    bool deleteFromCards = false;    // drawn over the Saved runs page instead of the slot menu
    NameScreen name;
    // Generating
    int genStage = 0, genDone = 0, genTotal = 1;
    // Error
    std::string errorText;
    std::string errorTitle;          // empty = the default title
    std::string errorNote;           // empty = "Your runs and saves were not changed."
    bool fatal = false;              // the app cannot continue (assets / storage): no way back
    // Transient
    bool toastVisible = false;
    Toast toast;
    std::string buildLabel = "r28";
    std::string statusLine;          // bottom-right note of the settings screen (e.g. the capabilities source)
};

void draw(Canvas& c, const Fonts& f, const State& s);
// The page of the Saved runs cards (navigation target of the Play page's link).
int savedRunsPage();

// Unsupported runs in the list (for the "delete all" action).
int unsupportedCount(const State& s);

// The seed shown with thin spaces every three digits from the right ("2 315 984 632").
std::string groupedSeed(const std::string& seed);

}  // namespace ui::launcher
