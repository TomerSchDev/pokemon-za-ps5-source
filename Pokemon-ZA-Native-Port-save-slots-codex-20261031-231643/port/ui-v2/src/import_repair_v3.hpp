// Existing staged-repair implementation, declared against the v3 core types. Its legacy header includes a second
// run_store.hpp by relative path; including that header alongside v3 would define Run and the core types twice.
#pragma once
#include "rando_v3.hpp"
namespace za::native {
bool importStagedRepair(const std::string& root, const std::string& stage, const Json& assets, std::string& error);
}
