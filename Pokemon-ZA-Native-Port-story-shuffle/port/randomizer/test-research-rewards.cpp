#include "research_rewards.hpp"
#include "progression.hpp"
#include "run_store.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
using namespace za;using namespace za::native;
int main(int argc,char**argv) {
    assert(argc==3);std::string root=argv[1],out=argv[2];Bytes raw;
    assert(readFile(root+"/research-rewards.json",raw));auto spec=Json::parse(raw);
    assert(readFile(root+"/progression.json",raw));auto progression=Json::parse(raw);
    auto reader=[&](const std::string& name,Bytes& data){return readFile(root+"/"+name,data);};
    Json reports=Json::array();
    for(int i=0;i<100;i++) {
        std::string seed=std::to_string(i);Result first,second;std::string error;
        assert(planRockRoute(progression,seed,true,true,first.report["rock_route"],error));second.report=first.report;
        assert(randomizeResearchRewards(spec,reader,seed,first,error));
        assert(randomizeResearchRewards(spec,reader,seed,second,error));
        assert(first.tables==second.tables&&first.report==second.report);
        const auto& data=first.tables.at("research_rewards");
        std::ofstream file(out+"/"+seed+".bin",std::ios::binary);file.write(reinterpret_cast<const char*>(data.data()),data.size());assert(file.good());
        reports.push_back({{"seed",seed},{"report",first.report}});
    }
    std::ofstream report(out+"/reports.json");report<<reports.dump();assert(report.good());
    Result failed;std::string error;auto bad=spec;bad["rows"][0]["item_offset"]=99999;
    assert(!randomizeResearchRewards(bad,reader,"1",failed,error));
    auto corrupt=[&](const std::string& name,Bytes& data){bool ok=reader(name,data);if(ok&&!data.empty())data[0]^=1;return ok;};
    assert(!randomizeResearchRewards(spec,corrupt,"1",failed,error));
    std::cout<<"PASS: 100 deterministic seeds; corrupt table and out-of-bounds metadata rejected\n";
}
