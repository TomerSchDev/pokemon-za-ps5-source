#pragma once
// On-screen keyboard for the player name (randomizer menu, before Vulkan starts). Pure state machine:
// the menu passes the pad's edge-triggered buttons and draws from the getters. Host-testable.
//
// Grid, 10 columns x 5 rows (row 4 holds two symbols and four wide action keys):
//   A B C D E F G H I J        (a..j when lower case)
//   K L M N O P Q R S T
//   U V W X Y Z - . ! ?
//   0 1 2 3 4 5 6 7 8 9
//   ' & [CASE ] [SPACE] [ DEL ] [DONE ]
// Buttons: D-pad move (wraps), Cross press, Square delete, Triangle toggle case, Circle cancel.
#include <cstdint>
#include <string>

namespace za::native {
class NameKeyboard {
public:
    enum class Action { None, Done, Cancel };
    static constexpr int Columns = 10, Rows = 5;
    enum class Key { Char, Case, Space, Delete, Done };

    explicit NameKeyboard(std::string initial = {});
    // buttons: za::native::{Up,Right,Down,Left,Triangle,Circle,Cross,Square} bits (edge-triggered).
    Action press(uint32_t buttons);

    const std::string& text() const { return text_; }
    // The name that Done accepted (trimmed, validated); valid after Action::Done.
    const std::string& result() const { return result_; }
    // Set when Done was refused (empty / invalid); cleared by the next edit.
    const std::string& message() const { return message_; }
    bool lower() const { return lower_; }
    int row() const { return row_; }
    int column() const { return column_; }

    // What the key at (row, column) is, and its label ("A", "a", "CASE", ...).
    static Key keyAt(int row, int column);
    std::string label(int row, int column) const;
    // First column of the (possibly wide) key at (row, column), and its width in columns.
    static int keyStart(int row, int column);
    static int keyWidth(int row, int column);

private:
    void move(int dRow, int dColumn);
    void type(char c);
    std::string text_, result_, message_;
    bool lower_ = false;
    int row_ = 0, column_ = 0;
};
}
