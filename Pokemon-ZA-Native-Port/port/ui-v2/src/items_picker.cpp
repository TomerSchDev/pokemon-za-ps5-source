#include "items_picker.h"

#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <sstream>

namespace ui::items {

const std::vector<Item>& catalog() {
    static const std::vector<Item> items = {
#include "items.inc"  // port/cheats-r28/items.inc, included by path (-I), never copied
    };
    return items;
}

const unsigned kAmounts[4] = {1, 10, 99, 999};

const char* tabName(int tab) {
    switch (tab) {
        case TabAll: return "All";
        case TabMedicine: return "Medicine";
        case TabBalls: return "Poké Balls";
        case TabOther: return "Other items";
        case TabTMs: return "TMs";
        case TabFavourites: return "Favourites";
        default: return "?";
    }
}

int tabOfPocket(int pocket) {
    switch (pocket) {
        case 0: return TabMedicine;
        case 1: return TabBalls;
        case 2: return TabOther;
        case 6: return TabTMs;
        default: return TabOther;
    }
}

const char* pocketName(int pocket) { return tabName(tabOfPocket(pocket)); }

unsigned repeatDelayMs(unsigned heldMs) { return heldMs < 400 ? 400 - heldMs : heldMs < 1200 ? 110 : 45; }

Picker::Picker() : amountIndex_(catalog().size(), 0) {
    // TMs can only be ×1; everything else starts at ×1 as well (the player raises it per row).
    rebuild();
}

void Picker::rebuild() {
    visible_.clear();
    const auto& items = catalog();
    if (tab_ == TabFavourites) {
        for (unsigned i : favourites_) visible_.push_back(i);
        for (unsigned i : recent_)
            if (!favourites_.count(i)) visible_.push_back(i);
    } else {
        for (unsigned i = 0; i < items.size(); i++)
            if (tab_ == TabAll || tabOfPocket(items[i].pocket) == tab_) visible_.push_back(i);
    }
    clampCursor();
}

void Picker::clampCursor() {
    int n = int(visible_.size());
    if (n == 0) { cursor_ = first_ = 0; return; }
    cursor_ = std::clamp(cursor_, 0, n - 1);
    if (cursor_ < first_) first_ = cursor_;
    if (cursor_ >= first_ + rows_) first_ = cursor_ - rows_ + 1;
    first_ = std::clamp(first_, 0, std::max(0, n - rows_));
}

const Item* Picker::current() const {
    if (visible_.empty()) return nullptr;
    return &catalog()[visible_[size_t(cursor_)]];
}

unsigned Picker::amountIndex(unsigned itemIndex) const {
    return itemIndex < amountIndex_.size() ? amountIndex_[itemIndex] : 0;
}

unsigned Picker::amount(unsigned itemIndex) const {
    const auto& items = catalog();
    if (itemIndex >= items.size()) return 1;
    unsigned a = kAmounts[amountIndex(itemIndex)];
    return std::min<unsigned>(a, items[itemIndex].cap);
}

std::string Picker::letters() const {
    std::string s;
    for (unsigned i : visible_) {
        char c = char(std::toupper((unsigned char)catalog()[i].name[0]));
        if (s.find(c) == std::string::npos) s += c;
    }
    return s;
}

char Picker::currentLetter() const {
    const Item* it = current();
    return it ? char(std::toupper((unsigned char)it->name[0])) : 0;
}

void Picker::move(int delta) {
    int n = int(visible_.size());
    if (!n) return;
    cursor_ = (cursor_ + delta % n + n) % n;
    clampCursor();
}

void Picker::setTab(int tab) {
    tab_ = (tab % TabCount + TabCount) % TabCount;
    cursor_ = first_ = 0;
    rebuild();
}

void Picker::noteAdded(unsigned itemIndex) {
    recent_.erase(std::remove(recent_.begin(), recent_.end(), itemIndex), recent_.end());
    recent_.insert(recent_.begin(), itemIndex);
    if (recent_.size() > 12) recent_.resize(12);
    if (tab_ == TabFavourites) rebuild();
}

Request Picker::press(Button b) {
    Request req;
    int n = int(visible_.size());
    switch (b) {
        case Button::L1: setTab(tab_ - 1); break;
        case Button::R1: setTab(tab_ + 1); break;
        case Button::Up: move(-1); break;
        case Button::Down: move(1); break;
        case Button::L2:
            if (n) { cursor_ = std::max(0, cursor_ - rows_); clampCursor(); }
            break;
        case Button::R2:
            if (n) { cursor_ = std::min(n - 1, cursor_ + rows_); clampCursor(); }
            break;
        case Button::Triangle: {  // next initial letter (TMs: the next ten)
            if (!n) break;
            const auto& items = catalog();
            if (tab_ == TabTMs) {
                cursor_ = std::min(n - 1, (cursor_ / 10 + 1) * 10 % ((n + 9) / 10 * 10));
                if (cursor_ >= n) cursor_ = 0;
            } else {
                char here = char(std::toupper((unsigned char)items[visible_[size_t(cursor_)]].name[0]));
                int found = -1;
                for (int k = 1; k <= n && found < 0; k++) {
                    int j = (cursor_ + k) % n;
                    char c = char(std::toupper((unsigned char)items[visible_[size_t(j)]].name[0]));
                    if (c != here) {
                        // first item of that letter group
                        found = j;
                        while (found > 0 && std::toupper((unsigned char)items[visible_[size_t(found - 1)]].name[0]) == c && found - 1 != cursor_) found--;
                    }
                }
                if (found >= 0) cursor_ = found;
            }
            clampCursor();
            break;
        }
        case Button::Square:
            if (n) {
                unsigned i = visible_[size_t(cursor_)];
                if (!favourites_.erase(i)) favourites_.insert(i);
                if (tab_ == TabFavourites) rebuild();
            }
            break;
        case Button::Left:
        case Button::Right:
            if (n) {
                unsigned i = visible_[size_t(cursor_)];
                const Item& it = catalog()[i];
                if (it.cap <= 1) break;  // TMs: ×1 only
                int presets = 0;
                while (presets < 4 && kAmounts[presets] <= it.cap) presets++;
                int a = int(amountIndex_[i]) + (b == Button::Left ? -1 : 1);
                amountIndex_[i] = (unsigned char)((a % presets + presets) % presets);
            }
            break;
        case Button::Cross:
            if (n) {
                unsigned i = visible_[size_t(cursor_)];
                req.issued = true;
                req.index = i;
                req.amount = amount(i);
            }
            break;
        case Button::Circle: break;
    }
    return req;
}

std::string Picker::serialize() const {
    std::string out = "za-items-ui-v1\nfav";
    for (unsigned i : favourites_) out += " " + std::to_string(catalog()[i].id);
    out += "\nrecent";
    for (unsigned i : recent_) out += " " + std::to_string(catalog()[i].id);
    out += "\namounts";
    for (size_t i = 0; i < amountIndex_.size(); i++)
        if (amountIndex_[i]) out += " " + std::to_string(catalog()[i].id) + ":" + std::to_string(amountIndex_[i]);
    return out + "\n";
}

bool Picker::deserialize(const std::string& text) {
    if (text.rfind("za-items-ui-v1\n", 0) != 0) return false;
    const auto& items = catalog();
    auto indexOfId = [&](unsigned id) -> int {
        for (size_t i = 0; i < items.size(); i++)
            if (items[i].id == id) return int(i);
        return -1;
    };
    favourites_.clear();
    recent_.clear();
    std::fill(amountIndex_.begin(), amountIndex_.end(), 0);
    std::istringstream in(text.substr(15));
    std::string line;
    while (std::getline(in, line)) {
        std::istringstream words(line);
        std::string key, w;
        words >> key;
        while (words >> w) {
            if (key == "fav" || key == "recent") {
                int i = indexOfId(unsigned(std::atoi(w.c_str())));
                if (i < 0) continue;
                if (key == "fav") favourites_.insert(unsigned(i));
                else if (recent_.size() < 12) recent_.push_back(unsigned(i));
            } else if (key == "amounts") {
                size_t colon = w.find(':');
                if (colon == std::string::npos) continue;
                int i = indexOfId(unsigned(std::atoi(w.substr(0, colon).c_str())));
                int a = std::atoi(w.c_str() + colon + 1);
                if (i >= 0 && a >= 0 && a < 4 && kAmounts[a] <= items[size_t(i)].cap) amountIndex_[size_t(i)] = (unsigned char)a;
            }
        }
    }
    rebuild();
    return true;
}

}  // namespace ui::items
