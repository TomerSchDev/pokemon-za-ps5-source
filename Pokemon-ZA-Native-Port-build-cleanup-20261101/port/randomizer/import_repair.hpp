#pragma once
#include "run_store.hpp"
namespace za::native {
// Optional staged repair, executed by the title while its writable mount exists.
// Missing stage or a different active run: no change. Invalid stage: fail closed.
bool importStagedRepair(const std::string& root,const std::string& stage,
                        const Json& assets,std::string& error);
}
