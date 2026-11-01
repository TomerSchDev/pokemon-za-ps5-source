#include "name_keyboard.hpp"

#include "za_player_name.hpp"

namespace za::native {
namespace {
// Same bit values as menu_display.hpp (kept local so the keyboard builds without the display code).
constexpr uint32_t BUp = 0x10, BRight = 0x20, BDown = 0x40, BLeft = 0x80;
constexpr uint32_t BTriangle = 0x1000, BCircle = 0x2000, BCross = 0x4000, BSquare = 0x8000;

constexpr const char* Grid[NameKeyboard::Rows] = {"ABCDEFGHIJ", "KLMNOPQRST", "UVWXYZ-.!?", "0123456789", "'&"};
}

NameKeyboard::NameKeyboard(std::string initial) : text_(std::move(initial)) {
    if (text_.size() > PlayerNameMax) text_.resize(PlayerNameMax);
}

NameKeyboard::Key NameKeyboard::keyAt(int row, int column) {
    if (row < 4 || column < 2) return Key::Char;
    if (column < 4) return Key::Case;
    if (column < 6) return Key::Space;
    if (column < 8) return Key::Delete;
    return Key::Done;
}

int NameKeyboard::keyStart(int row, int column) { return row < 4 || column < 2 ? column : column / 2 * 2; }
int NameKeyboard::keyWidth(int row, int column) { return row < 4 || column < 2 ? 1 : 2; }

std::string NameKeyboard::label(int row, int column) const {
    switch (keyAt(row, column)) {
    case Key::Case: return lower_ ? "ABC" : "abc";
    case Key::Space: return "SPACE";
    case Key::Delete: return "DEL";
    case Key::Done: return "DONE";
    case Key::Char: break;
    }
    char c = Grid[row][column];
    if (lower_ && c >= 'A' && c <= 'Z') c = char(c - 'A' + 'a');
    return std::string(1, c);
}

void NameKeyboard::move(int dRow, int dColumn) {
    if (dColumn) {
        // Wide keys in the last row move as one key.
        int c = column_;
        if (dColumn > 0) c = keyStart(row_, c) + keyWidth(row_, c);
        else c = keyStart(row_, c) - 1;
        column_ = (c % Columns + Columns) % Columns;
        column_ = keyStart(row_, column_);
    }
    if (dRow) {
        row_ = ((row_ + dRow) % Rows + Rows) % Rows;
        column_ = keyStart(row_, column_);
    }
}

void NameKeyboard::type(char c) {
    if (text_.size() >= PlayerNameMax) { message_ = "12 CHARACTERS MAXIMUM"; return; }
    if (c == ' ' && (text_.empty() || text_.back() == ' ')) return;  // no leading or double spaces
    text_ += c;
}

NameKeyboard::Action NameKeyboard::press(uint32_t buttons) {
    if (buttons & BCircle) return Action::Cancel;
    if (buttons & (BUp | BDown | BLeft | BRight | BTriangle | BSquare | BCross)) message_.clear();
    if (buttons & BUp) move(-1, 0);
    if (buttons & BDown) move(1, 0);
    if (buttons & BLeft) move(0, -1);
    if (buttons & BRight) move(0, 1);
    if (buttons & BTriangle) lower_ = !lower_;
    if (buttons & BSquare) { if (!text_.empty()) text_.pop_back(); }
    if (!(buttons & BCross)) return Action::None;
    switch (keyAt(row_, column_)) {
    case Key::Case: lower_ = !lower_; return Action::None;
    case Key::Space: type(' '); return Action::None;
    case Key::Delete: if (!text_.empty()) text_.pop_back(); return Action::None;
    case Key::Char: {
        const std::string l = label(row_, column_);
        type(l[0]);
        return Action::None;
    }
    case Key::Done: {
        std::string t = text_;
        while (!t.empty() && t.back() == ' ') t.pop_back();
        while (!t.empty() && t.front() == ' ') t.erase(t.begin());
        std::string why;
        if (!validPlayerName(t, &why)) { message_ = t.empty() ? "ENTER AT LEAST ONE CHARACTER" : "THIS NAME CANNOT BE USED"; return Action::None; }
        result_ = t;
        return Action::Done;
    }
    }
    return Action::None;
}
}
