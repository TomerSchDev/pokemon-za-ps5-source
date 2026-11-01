#pragma once
#include "core/randomizer.hpp"

namespace za::native {
inline constexpr const char* PlayerNameAlgorithm = "za202-trainer-name-v1";

// Only call on a newly generated starting save, before publishRun. Never call on
// a continued run or the current progressed save during repair.
bool nameRun(const std::string& name, Result& result, std::string& error);

// Reproduce the optional name step on a fresh host-core result. An old report
// with no name leaves it byte-identical. Invalid/unknown metadata fails closed.
bool replayRunName(const Json& report, Result& result, std::string& error);

// Display helper only: absent/invalid metadata is blank, preserving old runs.
std::string reportPlayerName(const Json& report);

// Preference only; independent of existing runs. Read returns blank if missing
// or invalid. Write is validated, fsynced, read back and atomically renamed.
std::string rememberedPlayerName(const std::string& root);
bool rememberPlayerName(const std::string& root, const std::string& name);
}
