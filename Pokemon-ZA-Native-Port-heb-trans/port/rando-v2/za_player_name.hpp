#pragma once
// Player (trainer) name for a new randomizer run, written into the Z-A 2.0.2 "main" save.
//
// The save is SwishCrypto (PKHeX: Saves/Encryption/SwishCrypto): a static 0x7F-byte xorpad over the payload,
// blocks of {u32 key, type, [length], data} each XORed with an SCXorShift32 stream seeded by its key, and a
// SHA-256 over intro salt + payload + outro salt in the last 0x20 bytes. Editing a fixed-size field keeps every
// block's length, so the writer decodes only the three blocks it touches, re-encodes them with the same stream
// and rewrites the hash. Every other byte of the file is left as it was.
//
// Fields (PKHeX SAV9ZA / MyStatus9a / Party9a / PA9 / PokeCrypto, revision 2.0.2):
//   MyStatus 0xE3E89BD1: ID32 @0x00, OT UTF-16LE @0x10, 0x1A bytes (12 chars + terminator)
//   Party    0x3AA1A9AD: 6 slots of 0x1E0, each an encrypted PA9 party entity of 0x158 then footer
//   Box      0x0D66012C: slots of 0x198 (party-format entity 0x158 + 0x40 gap), 32 boxes x 30
//   PA9 (decrypted): checksum u16 @0x06 = sum of u16 over [0x08, 0x148), ID32 @0x0C, OT @0xF8 (0x1A bytes)
// A Pokemon is the player's own when its ID32 equals MyStatus.ID32 and its OT equals the old trainer name.
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace za::native {
using SaveBytes = std::vector<uint8_t>;

constexpr size_t PlayerNameMax = 12;  // SAV9ZA.MaxStringLengthTrainer

struct PlayerNameEdit {
    std::string oldName;
    int pokemonRenamed = 0;     // party + boxes, player's own
    int pokemonKept = 0;        // present but not the player's (traded / different trainer)
    int pokemonUnreadable = 0;  // present but the decrypted checksum did not match (left untouched)
};

// 1..12 characters from the menu's set: A-Z a-z 0-9 space - . ! ? ' & ; no leading/trailing space.
bool validPlayerName(const std::string& name, std::string* why = nullptr);

// Reads MyStatus.OT of an encrypted save after checking its SwishCrypto hash.
bool readPlayerName(const SaveBytes& save, std::string& name, std::string& error);

// Renames the trainer in MyStatus and the OT of the player's own Pokemon, then rehashes.
// On failure the input is not modified.
bool applyPlayerName(SaveBytes& save, const std::string& name, PlayerNameEdit& edit, std::string& error);
}
