#include "progression.hpp"
#include <algorithm>
#include <set>
namespace za::native {
static size_t chooseRock(const std::string& seed,const std::string& domain,size_t size) {
    const uint64_t rem=(UINT64_MAX%size+1)%size;
    for(int retry=0;retry<1000;retry++) {
        auto text=Json::array({"za202-rock-route-v1",seed,domain,retry}).dump();auto hash=sha256(Bytes(text.begin(),text.end()));uint64_t word=0;
        for(int i=0;i<16;i++)word=(word<<4)|uint64_t(hash[i]<='9'?hash[i]-'0':hash[i]-'a'+10);
        if(!rem||word<=UINT64_MAX-rem)return size_t(word%size);
    }std::abort();
}
bool planRockRoute(const Json& spec,const std::string& seed,bool wild,bool rewards,Json& route,std::string& error) {
    if(spec.value("schema",0)!=4){error="Rock route asset mismatch";return false;}
    const auto& rock=spec.at("rock");const auto& natural=rock.at("natural_candidates");const auto& tms=rock.at("tm_routes");
    if(natural.empty()||tms.size()!=2){error="Rock route pool missing";return false;}
    if(wild&&chooseRock(seed,"route",2)==0) {
        route=natural[chooseRock(seed,"natural-species",natural.size())];route["mode"]="natural";route["tm_item"]=0;
    } else {
        const auto& tm=tms[rewards?chooseRock(seed,"tm-item",tms.size()):0];
        if(tm.at("candidates").empty()){error="No compatible early TM Pokemon";return false;}
        route=wild?tm.at("candidates")[chooseRock(seed,"tm-species",tm.at("candidates").size())]:Json{{"species",659},{"name","Bunnelby"}};
        route["mode"]="tm";route["tm_item"]=tm.at("item");route["tm_name"]=tm.at("name");route["move"]=tm.at("move");
    }
    route["locations"]=rock.at("locations");route["algorithm"]="za202-rock-route-v1";return true;
}
static bool put(Bytes& data,const Json& field,int value) {
    size_t p=field.at("offset"),n=field.at("bytes");
    if(n!=4||p>data.size()||data.size()-p<4)return false;
    for(int i=0;i<4;i++)data[p+i]=uint8_t(uint32_t(value)>>(8*i));return true;
}
static bool get(const Bytes& data,const Json& field,int& value) {
    size_t p=field.at("offset"),n=field.at("bytes");if(n!=4||p>data.size()||data.size()-p<4)return false;
    uint32_t v=0;for(int i=0;i<4;i++)v|=uint32_t(data[p+i])<<(8*i);value=int32_t(v);return true;
}
bool protectProgression(const Json& spec,const Reader& read,const std::string& seed,Result& result,std::string& error) {
    auto fail=[&](const char* message){error=message;return false;};
    if(spec.value("schema",0)!=4||spec.value("build_id","")!="b1f12fd919eae86ab8a978317677e64bce443d1f"||
       spec.value("algorithm","")!="za202-story-guard-v2"||spec.value("wild_template_file","")!="progression-wild.bin")return fail("Progression asset version mismatch");
    if(!planRockRoute(spec,seed,result.report.at("options").value("wild",false),result.report.at("options").value("research_rewards",false),result.report["rock_route"],error))return false;
    auto found=result.tables.find("wild");if(found==result.tables.end())return fail("Missing wild table");
    auto& data=found->second;
    if(!result.report.at("options").value("wild",false)) {
        result.report["progression"]={{"algorithm","za202-story-guard-v2"},{"wild","original table unchanged"},
            {"tm_catalog_count",spec.at("tm_count")},{"limitations",spec.at("limitations")}};
        return true;
    }
    if(data.size()!=spec.at("source_bytes").get<size_t>())return fail("Progression input size mismatch");
    const Bytes generated=data;
    if(!read("progression-wild.bin",data)||data.size()!=spec.at("wild_bytes").get<size_t>()||
       sha256(data)!=spec.at("wild_template_sha256").get<std::string>())return fail("Progression template integrity failed");
    Json changes=Json::array();int retained=0;
    std::set<size_t> offsets;std::set<std::string> identities;
    for(const auto& g:spec.at("guards")) {
        const std::string id=g.at("identity");int original=g.at("species"),form=g.at("form"),next=original;
        if(!identities.insert(id).second)return fail("Duplicate progression identity");
        int sex=g.at("original_sex");
        if(g.value("rock_provider",false)){next=result.report.at("rock_route").at("species");form=0;sex=0;}
        else if(g.at("fixed").get<bool>())retained++;
        else if(!get(generated,g.at("generated_fields").at("devNo"),next)||
                !get(generated,g.at("generated_fields").at("formNo"),form)||
                !get(generated,g.at("generated_fields").at("sex"),sex))return fail("Invalid generated encounter offsets");
        const auto& fields=g.at("fields");
        for(const auto& name:{"devNo","formNo","sex"})if(!offsets.insert(fields.at(name).at("offset").get<size_t>()).second)return fail("Overlapping progression offsets");
        if(!put(data,fields.at("devNo"),next)||!put(data,fields.at("formNo"),form)||
           !put(data,fields.at("sex"),sex))return fail("Invalid progression offsets");
        if(next!=original)changes.push_back({{"id",id},{"from",original},{"species",next}});
    }
    result.report["table_sha256"]["wild"]=sha256(data);
    result.report["progression"]={{"algorithm","za202-story-guard-v2"},{"tm_catalog_count",spec.at("tm_count")},
        {"guarded_encounters",spec.at("guards").size()},{"retained_original_encounters",retained},{"changes",changes},
        {"scope","Seeded early rock provider plus authored move sets; all other encounters use the original seeded randomizer output"},
        {"limitations",spec.at("limitations")}};
    return true;
}
}
