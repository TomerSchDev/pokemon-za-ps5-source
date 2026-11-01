// ui-v2: the item picker's state machine, over the existing r28 catalogue (port/cheats-r28/items.inc, 199 items
// with pocket and amount cap; the add API za_items_request(index, amount) and its READY / QUEUED / ADDED /
// POCKET FULL states are kept unchanged - the picker only chooses `index` and `amount`).
//
// Tabs (L1/R1): All · Medicine · Poké Balls · Other items · TMs · Favourites & recent. The list shows 10 rows with a
// scrollbar; D-pad moves (hold accelerates), L2/R2 jump a page, Triangle jumps to the next initial letter (TMs: next
// ten), Square toggles a favourite, Left/Right pick the amount preset of the row (1 / 10 / 99 / 999, capped by the
// item's cap: TMs are always ×1), Cross adds immediately. Pure logic, host-testable; no drawing here.
#pragma once
#include <cstdint>
#include <set>
#include <string>
#include <vector>

#include "ui_model.h"

namespace ui::items {

struct Item {
    uint16_t id, cap;
    uint8_t pocket;
    const char* name;
};
// The r28 catalogue, in its own order (index = za_items index).
const std::vector<Item>& catalog();

enum Tab { TabAll = 0, TabMedicine, TabBalls, TabOther, TabTMs, TabFavourites, TabCount };
const char* tabName(int tab);
// Pocket id of the catalogue -> tab (0 Medicine, 1 Poké Balls, 2 Other items, 6 TMs).
int tabOfPocket(int pocket);
const char* pocketName(int pocket);

extern const unsigned kAmounts[4];  // 1, 10, 99, 999 (the only amounts za_items_request accepts)

using Button = model::Button;  // one button vocabulary for the launcher, the picker and the overlay

struct Request {
    bool issued = false;
    unsigned index = 0, amount = 0;  // za_items_request arguments
};

class Picker {
public:
    Picker();
    int tab() const { return tab_; }
    // Indices into catalog() shown by the current tab, in display order (catalogue order; favourites tab:
    // favourites first, then the most recent additions).
    const std::vector<unsigned>& visible() const { return visible_; }
    int cursor() const { return cursor_; }        // position within visible()
    int first() const { return first_; }          // first displayed row
    int visibleRows() const { return rows_; }
    const Item* current() const;                  // the item under the cursor, or nullptr (empty tab)
    unsigned amountIndex(unsigned itemIndex) const;  // 0..3 preset chosen for that item
    unsigned amount(unsigned itemIndex) const;       // the preset's amount, capped
    bool isFavourite(unsigned itemIndex) const { return favourites_.count(itemIndex) != 0; }
    const std::vector<unsigned>& recent() const { return recent_; }
    // The initial letters present in the current tab (the alphabet strip highlights these).
    std::string letters() const;
    char currentLetter() const;

    // Returns a Request when Cross was pressed on an item (the caller forwards it to za_items_request and shows the
    // toast from the status it gets back). Circle is handled by the overlay (closes it).
    Request press(Button b);
    void setTab(int tab);
    void noteAdded(unsigned itemIndex);  // moves the item to the front of the recent list (max 12)

    // Persistence of favourites/recent (one line each; stored next to the run's cheats.txt as favourites.txt).
    std::string serialize() const;
    bool deserialize(const std::string& text);

private:
    void rebuild();
    void clampCursor();
    void move(int delta);
    int tab_ = TabAll, cursor_ = 0, first_ = 0, rows_ = 10;
    std::vector<unsigned> visible_;
    std::set<unsigned> favourites_;
    std::vector<unsigned> recent_;
    std::vector<unsigned char> amountIndex_;  // per catalogue index
};

// Hold-to-accelerate repeat timing shared by the picker and the launcher lists: the delay before the next repeat
// after `heldMs` milliseconds of holding (400 ms initial, 110 ms, then 45 ms after 1.2 s).
unsigned repeatDelayMs(unsigned heldMs);

}  // namespace ui::items
