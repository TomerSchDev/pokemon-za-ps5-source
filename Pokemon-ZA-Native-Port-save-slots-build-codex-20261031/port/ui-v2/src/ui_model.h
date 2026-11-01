// ui-v2: the data-driven menu model.
//
// A page is a list of rows; a row is a kind (level / toggle / number / text / action / link / pick) with its label,
// a one-sentence description and, for levels, the options with THEIR one-sentence descriptions. Adding a page or a
// row to the launcher is one entry in launcherPages() (ui_model.cpp) plus the generator reading the value by id:
// the layout code never changes. Values are kept by row id and serialized into the run's report.json as
// "ui_options": {"schema": 2, "values": {"wild_mode": "random", "trainer_levels": 20, "player_name": "Tomer"}}.
//
// Availability is part of the data: Avail::Now means port/randomizer/core writes that field today; Avail::Phase2 is
// generator work still to be done. The launcher only offers options whose availability is enabled for the build,
// so the UI stays honest about what a run will actually do.
#pragma once
#include <map>
#include <string>
#include <vector>

namespace ui::model {

enum class Kind {
    Action,  // Cross runs it (Continue, Start a new run, Reset)
    Level,   // one of N options, each with a description (Off / Shuffle zones / ...)
    Toggle,  // a two-option level (Off / On) drawn as a switch
    Number,  // an integer in [min, max] with a step and unit (+10 %, 50,000)
    Text,    // free text edited on the keyboard screen (trainer name)
    Pick,    // one of a list that depends on another row (the starter)
    Link,    // opens another screen (seed keypad, saved runs)
    Info     // read-only value
};

enum class Avail { Now, Phase2 };

struct Option {
    const char* id;     // stable id stored in report.json
    const char* label;  // "Shuffle zones"
    const char* desc;   // one sentence shown under the row while this option is selected
    Avail avail = Avail::Now;
};

struct RowDef {
    const char* id;
    const char* label;
    const char* desc;  // one sentence shown under the label (levels show the selected option's own sentence)
    Kind kind;
    std::vector<Option> options;  // Level / Toggle / Pick
    int min = 0, max = 0, step = 1, def = 0;  // Number (def is also the default option index for levels)
    const char* unit = "";
    Avail avail = Avail::Now;
    const char* shortLabel = "";  // for the saved-run summary ("Wild"); empty = not summarized
    const char* dependsOn = "";   // Pick: the Level row that selects which option list applies
};

struct PageDef {
    const char* id;
    const char* title;
    const char* blurb;  // one sentence under the page title
    std::vector<RowDef> rows;
    bool cards = false;  // Saved runs: the content area shows run cards instead of rows
};

// The launcher's pages, in navigation order. Pure data.
const std::vector<PageDef>& launcherPages();
// The in-game overlay's CHEATS tab rows (same row vocabulary; values are the live cheat state).
const std::vector<RowDef>& cheatRows();

// The starter lists for the Pick row: index = starter_mode option (vanilla / any / random).
struct Starter {
    int species;
    const char* name;
};
const std::vector<Starter>& starterList(int starterMode);

struct Values {
    std::map<std::string, int> ints;
    std::map<std::string, std::string> texts;
    int get(const std::string& id, int def = 0) const;
    void set(const std::string& id, int v) { ints[id] = v; }
    const std::string& text(const std::string& id) const;
    void setText(const std::string& id, const std::string& v) { texts[id] = v; }
};
// Defaults of every row of every page (today's behaviour: wild/trainers/megas/DLC/research on, music off, random starter).
Values defaults();

// What THIS build's generator writes (port/rando-v3/capabilities.json, read at build time by
// tools/gen-capabilities.py into capabilities_generated.inc). When that file is absent the static Avail of the data
// decides. Text rows and the Play page's actions are never gated.
struct CapEntry {
    const char* row;
    const char* option;  // an option id, or "*" for every value of a Number/Text row
};
bool capabilitiesPresent();
// The option `index` of a Level/Toggle row can be chosen in this build (Number: any value; Text/Pick: see rowShipped).
bool optionShipped(const RowDef& row, int index);
// The row has something to choose in this build (two or more shipped options; a Number with a range; Text; a Pick
// whose list is non-empty). A row that is not shipped shows the "NOT IN THIS BUILD" badge and cannot be changed.
bool rowShipped(const RowDef& row);
// Looks up a row by id (nullptr when unknown).
const RowDef* findRow(const std::string& id);
// Page index by id (-1 when unknown).
int pageIndexOf(const char* id);

// Display text of a row's current value ("Shuffle zones", "+20 %", "On", "Tomer", "7").
std::string valueText(const RowDef& row, const Values& v);
// The selected option of a Level/Toggle/Pick row, or nullptr.
const Option* selectedOption(const RowDef& row, const Values& v);
// Short summary for run cards: "Wild: Fully random · Trainers: Fully random · Megas · DLC rematches · Music: Off".
std::string summary(const Values& v);
// report.json "ui_options" object (deterministic key order).
std::string toJson(const Values& v);
// Reads what toJson wrote (unknown ids are kept so an older binary never drops a newer run's settings).
bool fromJson(const std::string& json, Values& out);

enum class Button { Up, Down, Left, Right, Cross, Circle, Triangle, Square, L1, R1, L2, R2 };

struct Nav {
    int page = 0;
    int row = 0;
};

struct Event {
    enum Type { None, Continue, StartNewRun, OpenSeed, OpenSavedRuns, OpenName, RandomSeed, Changed, Toast, BackToPlay };
    Type type = None;
    std::string text;  // Toast text / changed row id
};

// The settings screen's state machine. `allowPhase2` lets the host mockups select options the generator does not
// write yet; the title passes false, so a run can only be created with options that exist.
Event handle(Nav& nav, Values& v, Button b, bool allowPhase2 = false);
// Resets every setting row of a page to its default (what Triangle does); returns the page title.
const char* resetPage(int pageIndex, Values& v);

// Row count of a page (0 for card pages) and bounds-safe access.
const PageDef& page(int index);
int pageCount();

}  // namespace ui::model
