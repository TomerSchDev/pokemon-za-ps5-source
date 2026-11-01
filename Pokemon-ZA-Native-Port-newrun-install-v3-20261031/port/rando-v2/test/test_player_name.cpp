// Host test for za_player_name.cpp. Fixtures come from verify/ (PKHeX): plain.bin = the pinned city template,
// mixed.bin = template + a foreign party member + three boxed Pokemon (ours, same ID other name, foreign).
// Writes renamed saves to OUTDIR for the PKHeX block-level verification (verify ... verify BEFORE AFTER NAME).
#include "../za_player_name.hpp"

#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>

using namespace za::native;
static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)

static SaveBytes load(const std::string& p) {
    std::ifstream f(p, std::ios::binary);
    return SaveBytes(std::istreambuf_iterator<char>(f), {});
}
static void store(const std::string& p, const SaveBytes& b) {
    std::ofstream f(p, std::ios::binary | std::ios::trunc);
    f.write(reinterpret_cast<const char*>(b.data()), std::streamsize(b.size()));
}

int main(int argc, char** argv) {
    if (argc != 3) { std::fprintf(stderr, "usage: FIXTURES OUTDIR\n"); return 2; }
    const std::string in = argv[1], out = argv[2];
    const SaveBytes plain = load(in + "/plain.bin"), mixed = load(in + "/mixed.bin");
    CHECK(plain.size() == 3186611 && mixed.size() == plain.size());
    if (failures) return 2; // do not index or create outputs from missing fixtures

    std::string name, error;
    CHECK(readPlayerName(plain, name, error) && name == "Test");

    {  // plain template: MyStatus + the starter
        SaveBytes s = plain;
        PlayerNameEdit e;
        CHECK(applyPlayerName(s, "Ash Ketchum", e, error));
        CHECK(e.oldName == "Test" && e.pokemonRenamed == 1 && e.pokemonKept == 0 && e.pokemonUnreadable == 0);
        CHECK(readPlayerName(s, name, error) && name == "Ash Ketchum");
        CHECK(s.size() == plain.size() && s != plain);
        store(out + "/plain-ash.bin", s);

        SaveBytes again = s;  // same name again: byte-identical
        CHECK(applyPlayerName(again, "Ash Ketchum", e, error) && again == s && e.pokemonRenamed == 1);

        SaveBytes back = s;   // back to the template's name: the original file, byte for byte
        CHECK(applyPlayerName(back, "Test", e, error) && e.oldName == "Ash Ketchum");
        CHECK(back == plain);
    }
    {  // mixed: ours in party and box renamed; foreign and same-ID-other-name kept
        SaveBytes s = mixed;
        PlayerNameEdit e;
        CHECK(applyPlayerName(s, "Aa1 -.!?'&Zz", e, error));
        CHECK(e.pokemonRenamed == 2 && e.pokemonKept == 3 && e.pokemonUnreadable == 0);
        CHECK(readPlayerName(s, name, error) && name == "Aa1 -.!?'&Zz");
        store(out + "/mixed-symbols.bin", s);
        SaveBytes one = mixed;
        CHECK(applyPlayerName(one, "Q", e, error) && e.pokemonRenamed == 2);
        store(out + "/mixed-one.bin", one);
    }
    {  // refused names leave the save untouched
        const char* bad[] = {"", "ABCDEFGHIJKLM", "Bad*", " lead", "trail ", "tab\tname", "\xd7\x90"};
        for (const char* b : bad) {
            SaveBytes s = plain;
            PlayerNameEdit e;
            CHECK(!applyPlayerName(s, b, e, error) && s == plain);
        }
        CHECK(validPlayerName("ABCDEFGHIJKL") && !validPlayerName("ABCDEFGHIJKLM"));
    }
    {  // damaged or wrong files are refused
        SaveBytes s = plain;
        s[1000] ^= 1;
        PlayerNameEdit e;
        const SaveBytes damaged = s;
        CHECK(!applyPlayerName(s, "Ash", e, error) && s == damaged);
        CHECK(!readPlayerName(s, name, error));
        SaveBytes cut(plain.begin(), plain.begin() + 4096);
        CHECK(!applyPlayerName(cut, "Ash", e, error));
        SaveBytes empty;
        CHECK(!readPlayerName(empty, name, error));
    }
    std::printf("%s: %d failure(s)\n", failures ? "FAIL" : "PASS", failures);
    return failures ? 1 : 0;
}
