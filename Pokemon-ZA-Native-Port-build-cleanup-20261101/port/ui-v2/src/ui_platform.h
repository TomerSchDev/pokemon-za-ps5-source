// ui-v2: the few things that differ between the PS5 title and the PC proof build (paths, logging, randomness).
// The title defines ZA_PS5 (as every title object does); the PC build of the same sources defines nothing.
#pragma once
#include <cstdint>
#include <string>

namespace ui::platform {

// A log line (with its newline): klog on the console, stderr on the PC.
void log(const char* line);
void logf(const char* fmt, ...) __attribute__((format(printf, 1, 2)));
// The runs' folder, the randomizer assets (trailing slash), the game image, the staged repair folder (empty = none).
std::string runRoot();
std::string assetsDir();
std::string gameImage(const char* gameRoot);
std::string repairStage();
// The global favourites file of the item picker (one file in the title's writable root, not per run).
std::string itemsUiPath();
// Random seed digits / 32 random bits / wall clock seconds.
std::string freshSeed();
uint32_t random32();
uint64_t unixTime();
// Monotonic milliseconds.
uint64_t nowMs();

}  // namespace ui::platform
