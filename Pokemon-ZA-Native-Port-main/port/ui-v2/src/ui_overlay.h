// ui-v2: the in-game L3+R3 overlay (CHEATS tab + item pockets), drawn into a transparent 1920x1080 canvas that the
// runtime composites over the game. Only the panel, the FPS readout and the toast have pixels; the rest is 0 alpha.
#pragma once
#include <string>

#include "items_picker.h"
#include "ui_canvas.h"
#include "ui_model.h"
#include "ui_widgets.h"

namespace ui::overlay {

enum Tab { TabCheats = 0, TabItemsFirst = 1 };  // tabs 1..6 map to items::Tab 0..5

struct CheatState {
    int shiny = 0, capture = 0, moneyChoice = 0;
    bool fpsCounter = true;
    int fpsMode = 0;         // 0 = 30, 1 = 60 trial, 2 = fallback, -1 = controlled by config
    int hebrewMode = 0;      // 0 off, 1 on, -1 pack not available
    std::string moneyStatus; // "", "QUEUED - SAVE IN GAME", "ADDED 1×", "LOAD SAVE FIRST", "RETRY"
    bool settingsSaved = true;
    bool moneyAvailable = true;  // the MONEY hook is in this build
};

struct Readout {
    unsigned fpsX10 = 600, msX10 = 167;
    std::string mode = "60 MODE";
};

struct State {
    bool open = true;
    int tab = TabCheats;
    int row = 0;             // CHEATS tab cursor
    CheatState cheats;
    items::Picker picker;
    std::string itemStatus = "READY";  // za_items_status()
    unsigned itemsAdded = 0;           // za_items_applied()
    bool fpsCounter = true;
    Readout readout;
    bool toastVisible = false;
    Toast toast;
    // The title draws the readout and the toast on layers of their own (they change while the panel does not); the
    // mockups and tests draw everything into one canvas.
    bool drawReadout = true, drawToast = true, drawPanel = true;
};

// Draws the overlay into `c` (which must be cleared to transparent first).
void draw(Canvas& c, const Fonts& f, const State& s);
// The panel's rectangle in canvas pixels (what the title uploads and blends when the menu is open).
Rect panelRect();
// The readout pill (top right) and the toast band (bottom centre) as drawn by drawReadoutOnly / drawToastOnly.
Rect readoutRect(const Fonts& f, const State& s);
Rect toastRect(const Fonts& f, const Toast& t, int canvasW, int canvasH);
void drawReadoutOnly(Canvas& c, const Fonts& f, const State& s);
void drawToastOnly(Canvas& c, const Fonts& f, const Toast& t);

// What a button press asks the title to do. The state machine (tabs, cursors, the picker, the money choice) is
// updated here; the side effects on the game (za_* calls) and the resulting toasts are the title's.
struct Action {
    enum Kind {
        None,
        Close,            // Circle
        SettingsChanged,  // shiny / capture / fps counter changed: persist cheats.txt
        MoneyQueue,       // Cross on a money amount: za_money_request(amount)
        MoneyCancel,      // Normal chosen, or the amount changed: za_money_set_enabled(0)
        FpsTrial,         // Cross on FPS trial
        Hebrew,           // Cross on Hebrew trial
        Reset,            // Cross on Reset: shiny = capture = Normal (and persist)
        ItemRequest,      // Cross on an item: za_items_request(index, amount)
        FavouritesChanged // Square on an item: persist items-ui.txt
    } kind = None;
    unsigned index = 0, amount = 0;  // ItemRequest / MoneyQueue
};
Action press(State& s, items::Button b);

// The host simulation of the title's side effects (mockups and tests): applies an Action to the state as the real
// build would see it and returns the toast text ("Rare Candy ×99 queued", "Pocket full"...).
std::string simulate(State& s, const Action& a);

}  // namespace ui::overlay
