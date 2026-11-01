// Host test for the name keyboard state machine (name_keyboard.cpp).
#include "../name_keyboard.hpp"

#include <cstdio>

using namespace za::native;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)
constexpr uint32_t U = 0x10, R = 0x20, D = 0x40, L = 0x80, Tri = 0x1000, Cir = 0x2000, X = 0x4000, Sq = 0x8000;

int main() {
    {  // typing, case, delete, done
        NameKeyboard k("");
        CHECK(k.label(0, 0) == "A" && k.press(X) == NameKeyboard::Action::None && k.text() == "A");
        k.press(Tri);  // lower case
        CHECK(k.lower() && k.label(0, 0) == "a");
        k.press(R); k.press(X);  // b
        CHECK(k.text() == "Ab");
        k.press(Sq);
        CHECK(k.text() == "A");
        // go to DONE: down 4 rows (column 1 = '&'), then right over CASE, SPACE, DEL to DONE
        for (int i = 0; i < 4; i++) k.press(D);
        CHECK(k.row() == 4 && k.column() == 1);
        k.press(R); k.press(R); k.press(R); k.press(R);
        CHECK(NameKeyboard::keyAt(k.row(), k.column()) == NameKeyboard::Key::Done && k.column() == 8);
        CHECK(k.press(X) == NameKeyboard::Action::Done && k.result() == "A");
    }
    {  // wrapping and wide keys
        NameKeyboard k("x");
        k.press(L);
        CHECK(k.row() == 0 && k.column() == 9);
        k.press(U);
        CHECK(k.row() == 4 && k.column() == 8);  // J column lands on DONE's start
        k.press(R);
        CHECK(k.column() == 0);                  // wraps to the apostrophe
        k.press(L);
        CHECK(k.column() == 8);
        k.press(L);
        CHECK(NameKeyboard::keyAt(4, k.column()) == NameKeyboard::Key::Delete && k.column() == 6);
        k.press(X);
        CHECK(k.text().empty());
        k.press(L);  // SPACE
        CHECK(NameKeyboard::keyAt(4, k.column()) == NameKeyboard::Key::Space);
        k.press(X);
        CHECK(k.text().empty());  // no leading space
        k.press(L); k.press(X);   // CASE
        CHECK(k.lower());
    }
    {  // twelve characters maximum; empty and space-only names refused; trailing space trimmed
        NameKeyboard k("");
        for (int i = 0; i < 15; i++) k.press(X);
        CHECK(k.text() == "AAAAAAAAAAAA" && !k.message().empty());
        NameKeyboard e("");
        for (int i = 0; i < 4; i++) e.press(D);
        e.press(R); e.press(R); e.press(R); e.press(R); e.press(R);  // DONE
        CHECK(e.press(X) == NameKeyboard::Action::None && !e.message().empty());
        NameKeyboard t("Ash ");
        for (int i = 0; i < 4; i++) t.press(D);
        t.press(R); t.press(R); t.press(R); t.press(R); t.press(R);
        CHECK(t.press(X) == NameKeyboard::Action::Done && t.result() == "Ash");
    }
    {  // circle cancels; initial text longer than 12 is cut
        NameKeyboard k("ABCDEFGHIJKLMNOP");
        CHECK(k.text().size() == 12);
        CHECK(k.press(Cir) == NameKeyboard::Action::Cancel);
    }
    {  // every key label is drawable text
        NameKeyboard k("");
        for (int r = 0; r < NameKeyboard::Rows; r++)
            for (int c = 0; c < NameKeyboard::Columns; c++) CHECK(!k.label(r, c).empty());
        CHECK(k.label(2, 9) == "?" && k.label(4, 0) == "'" && k.label(4, 1) == "&");
    }
    std::printf("%s: %d failure(s)\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
