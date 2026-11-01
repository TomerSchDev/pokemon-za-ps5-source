#pragma once
// Music randomization for the native Z-A randomizer (r29-music). Portable: no game, console or filesystem calls
// except readBankFromRomfs (a plain open/pread of the game's own RomFS image).
//
// Z-A chooses field, zone and battle music inside Wwise: game code posts events listed in bgm_command.bin, those
// events set Wwise states, and each music switch container's decision tree maps the states to one looping music
// playlist. A run's music is shuffled by rewriting decision-tree leaves (u32 audio-node ids) of BGM.bnk at the
// offsets listed in the build-time plan (tools/make_music_plan.py). Nothing else in the bank changes; the file keeps
// its size. The run serves the result from its own romfs/ folder (runtime LayeredFS), like the other tables.
#include "core/randomizer.hpp"
#include <functional>
#include <string>

namespace za::native {
enum class MusicMode : int { Off = 0, Category = 1, Chaos = 2 };
inline constexpr int MusicModeCount = 3;
inline constexpr const char* MusicAlgorithm = "za202-bgm-leaf-shuffle-v1";
inline constexpr const char* MusicTableName = "music_bgm";
inline constexpr const char* MusicBankPath = "audio/wwise/bin/Switch/BGM.bnk";

const char* musicModeId(MusicMode mode);     // "off" | "category" | "chaos" (report.json)
const char* musicModeLabel(MusicMode mode);  // menu text
bool parseMusicMode(const std::string& id, MusicMode& mode);

// Pure transformation. Validates the plan text against the original bank (size, SHA-256, every slot's current id,
// every unit member being a music playlist of the bank) and returns the patched bank plus a report object.
// Off is rejected here (nothing to build). Deterministic for (plan, bank, seed, mode).
bool shuffleMusic(const std::string& planText, const Bytes& original, const std::string& seed, MusicMode mode,
                  Bytes& out, Json& report, std::string& error);

using BankReader = std::function<bool(const Json& plan, Bytes& bank)>;
// New-run generation step. Off: records {"mode":"off"} only. Category/Chaos: reads the original bank through
// `read`, shuffles it and adds result.tables["music_bgm"] and result.report["music"]. On failure the result is
// unchanged and error says why.
bool randomizeMusic(const std::string& planText, const BankReader& read, const std::string& seed, MusicMode mode,
                    Result& result, std::string& error);

// Reads plan.bank.bytes bytes at plan.bank.romfs_image_offset of the RomFS image (the hash is checked later).
bool readBankFromRomfs(const std::string& image, const Json& plan, Bytes& bank);
}
