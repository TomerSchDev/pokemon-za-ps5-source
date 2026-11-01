// Applies a trainer name to a copy of a save (host tool for the PKHeX cross-check of real starter saves).
//   rename_tool IN OUT NAME
#include "../za_player_name.hpp"

#include <cstdio>
#include <fstream>
#include <iterator>

int main(int argc, char** argv) {
    if (argc != 4) { std::fprintf(stderr, "usage: IN OUT NAME\n"); return 2; }
    std::ifstream f(argv[1], std::ios::binary);
    za::native::SaveBytes s(std::istreambuf_iterator<char>(f), {});
    za::native::PlayerNameEdit e;
    std::string error;
    if (!za::native::applyPlayerName(s, argv[3], e, error)) { std::fprintf(stderr, "refused: %s\n", error.c_str()); return 1; }
    std::ofstream o(argv[2], std::ios::binary | std::ios::trunc);
    o.write(reinterpret_cast<const char*>(s.data()), std::streamsize(s.size()));
    std::printf("{\"old\":\"%s\",\"renamed\":%d,\"kept\":%d,\"unreadable\":%d}\n", e.oldName.c_str(), e.pokemonRenamed,
                e.pokemonKept, e.pokemonUnreadable);
    return 0;
}
