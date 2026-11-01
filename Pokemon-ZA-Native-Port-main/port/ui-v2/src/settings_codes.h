// Portable, seed-independent word identifiers for the seven launcher settings categories.
//
// Protocol za-settings-words-1:
//  - Project only the known rows below, resolving absent values to model::defaults().
//  - Enums use stable option IDs, picks use national species IDs, numbers use decimal,
//    and player_name uses its exact UTF-8 bytes (including case). Display labels, seed,
//    navigation state and unknown/future keys never enter this protocol.
//  - A random starter's hidden last-selected partner is canonical null.
//  - Hash domain includes Schema, the versioned word-bank hash, the actual generator
//    algorithm ID and pinned game build ID. Legacy callers pass their recorded algorithm;
//    an empty algorithm/game build yields unavailable identifiers. Cosmetic UI builds
//    do not enter the domain. A changed word bank with a stale hash also fails closed.
//  - The first four SHA-256 bytes each select one word from a fixed bank of 256 words:
//    four ordinary words, separated by hyphens, containing 32 bits of comparison data.
//    Example shape: Blue-Panda-Moon-Lake. The bank is locally authored in settings_words.inc;
//    its exact order is versioned and its word+LF serialization is SHA-256 pinned below.
//    Matching settings still require the same seed to reproduce a run. A different
//    player name changes only the Player and overall identifiers.
//
// Canonical byte encoding, also used by the fixed test vectors:
//   "ZA-SETTINGS-WORDS\n" + pair("schema", Schema) + pair("wordbank", WordBankVersion)
//   + pair("wordbank_sha256", WordBankSha256) + pair("algorithm", algorithm)
//   + pair("game_build", gameBuild) + pair("category", categoryId)
//   + sorted known (key, typed-value) pairs.
// pair(k,v) = decimal(byte_length(k)) + ":" + k + decimal(byte_length(v)) + ":" + v.
// Typed values are "e:" + enum ID, "n:" + decimal, "s:" + raw text, or "null".
// The overall identifier uses categoryId="configuration" and sorted categoryId.rowId keys.
// This byte protocol and its field projection must change Schema if semantics change.
#pragma once
#include <string>

#include "ui_model.h"

namespace ui::codes {

inline constexpr const char* Schema = "za-settings-words-1";
inline constexpr const char* WordBankVersion = "za-common-words-1";
inline constexpr const char* WordBankSha256 = "863995c9b345bbe185bac7b65d8de61f4df09aad5b65d4ff62bb0e296d8c9c60";
inline constexpr const char* CurrentAlgorithm = "za202-randomizer-v3";
inline constexpr const char* CurrentGameBuild = "b1f12fd919eae86ab8a978317677e64bce443d1f";

struct SettingsCodes {
    std::string wild, trainers, starter, research, music, player, cheats, overall;
};

SettingsCodes compute(const model::Values& values, const std::string& algorithm = CurrentAlgorithm,
                      const std::string& gameBuild = CurrentGameBuild);
// The seven category IDs are wild/trainers/starter/research/music/player/cheats.
// play and saved use the overall code. Unknown pages return an empty string.
const std::string& forPage(const SettingsCodes& codes, const std::string& pageId);
std::string categoryCode(const std::string& categoryId, const model::Values& values,
                         const std::string& algorithm = CurrentAlgorithm,
                         const std::string& gameBuild = CurrentGameBuild);
std::string configurationCode(const model::Values& values,
                              const std::string& algorithm = CurrentAlgorithm,
                              const std::string& gameBuild = CurrentGameBuild);

}  // namespace ui::codes
