#pragma once
#include "core/randomizer.hpp"

namespace za::native {
struct Run { std::string id, seed, starter; };
bool readFile(const std::string&, Bytes&, size_t limit=16u*1024u*1024u);
bool makeDirs(const std::string&);
bool validId(const std::string&);
std::vector<Run> listRuns(const std::string& root);
bool selectRun(const std::string& root, const std::string& id, std::string& error);
std::string activeRun(const std::string& root);
// Publishes a completely new run. Never changes or resets an existing run/save.
bool publishRun(const std::string& root, const std::string& id,
                const Json& assets, const Result& generated, std::string& error);
}
