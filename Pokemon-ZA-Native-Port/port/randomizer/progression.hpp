#pragma once
#include "core/randomizer.hpp"
namespace za::native {
bool planRockRoute(const Json& spec,const std::string& seed,bool wild,bool rewards,Json& route,std::string& error);
bool protectProgression(const Json& spec,const Reader& read,const std::string& seed,Result& result,std::string& error);
}
