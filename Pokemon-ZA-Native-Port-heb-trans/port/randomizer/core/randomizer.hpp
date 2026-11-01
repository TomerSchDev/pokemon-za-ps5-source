#pragma once
#include <nlohmann/json.hpp>
#include <array>
#include <cstdint>
#include <functional>
#include <map>
#include <string>
#include <vector>

namespace za {
using Json=nlohmann::json;
using Bytes=std::vector<uint8_t>;
using Reader=std::function<bool(const std::string&,Bytes&)>;
struct Options {bool wild=true,trainers=true,mega_trainers=true,dlc_rematches=true;};
struct Result {std::map<std::string,Bytes> tables;Bytes save;Json report;std::string error;};
enum class BuildStage { Index, Trainers, Wild, Dlc, Starter, Complete };
using Progress=std::function<void(BuildStage,uint32_t,uint32_t)>;
std::string sha256(const Bytes& data);
bool generate(const Json& assets,const Json& starters,const Reader& read,
              const std::string& seed,const Options& options,int starter,Result& out,
              const Progress& progress={});
// starter=0 selects a deterministic species from the validated city templates.
// No filesystem writes or calls to game/emulator APIs occur in this core.
}
