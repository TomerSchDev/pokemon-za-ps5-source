#include "progression.hpp"
#include "research_rewards.hpp"
#include "run_store.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
using namespace za;using namespace za::native;
int main(int argc,char** argv) {
    assert(argc==4);std::string base=argv[1],guardRoot=argv[2],out=argv[3];Bytes raw;
    auto read=[&](const std::string& name,Bytes& bytes){return readFile(base+"/"+name,bytes);};
    assert(read("tables.json",raw));auto assets=Json::parse(raw);
    assert(read("starter-deltas.json",raw));auto starters=Json::parse(raw);
    assert(readFile(guardRoot+"/progression.json",raw));auto spec=Json::parse(raw);
    auto guardRead=[&](const std::string& name,Bytes& bytes){return readFile(guardRoot+"/"+name,bytes);};
    Json reports=Json::array();
    for(int i=0;i<16;i++) {
        std::string seed=std::to_string(i);Result result;Options options;options.wild=i<14;
        assert(generate(assets,starters,read,seed,options,0,result));
        result.report["options"]["research_rewards"]=bool(i%2);
        auto before=result;std::string error;
        assert(protectProgression(spec,guardRead,seed,result,error));
        auto repeat=before;assert(protectProgression(spec,guardRead,seed,repeat,error));
        assert(result.tables==repeat.tables&&result.report==repeat.report);
        assert(result.save==before.save&&result.tables["trainers"]==before.tables["trainers"]&&result.tables["dlc_boss"]==before.tables["dlc_boss"]);
        if(!options.wild)assert(result.tables["wild"]==before.tables["wild"]);
        for(const auto& [tag,bytes]:std::vector<std::pair<std::string,Bytes>>{{"before",before.tables["wild"]},{"after",result.tables["wild"]}}) {
            std::ofstream f(out+"/"+seed+"-"+tag+".bin",std::ios::binary);f.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());assert(f.good());
        }
        reports.push_back(result.report);
        if(i==0) {
            auto invalid=spec;invalid["guards"][0]["fields"]["devNo"]["offset"]=result.tables["wild"].size();
            result=before;
            assert(!protectProgression(invalid,guardRead,seed,result,error));
            auto corrupt=[&](const std::string& name,Bytes& bytes){bool ok=guardRead(name,bytes);if(ok)bytes[0]^=1;return ok;};
            result=before;assert(!protectProgression(spec,corrupt,seed,result,error));
        }
    }
    std::ofstream f(out+"/reports.json");f<<reports.dump(2);assert(f.good());
    std::cout<<"PASS: 16 seeds, all wild/reward toggle combinations, determinism, vanilla-off, unrelated tables/save intact, invalid bounds and corrupt template rejected\n";
}
