#include "research_rewards.hpp"
#include <algorithm>
#include <limits>
namespace za::native {
static uint64_t choose(const std::string& seed,int level,uint64_t bound) {
    uint64_t rem=(UINT64_MAX%bound+1)%bound;
    for(int attempt=0;attempt<1000;attempt++) {
        const auto text=Json::array({"za202-research-rewards-v3","b1f12fd919eae86ab8a978317677e64bce443d1f",seed,level,attempt}).dump();
        const auto hash=sha256(Bytes(text.begin(),text.end()));uint64_t word=0;
        for(int i=0;i<16;i++)word=(word<<4)|uint64_t(hash[i]<='9'?hash[i]-'0':hash[i]-'a'+10);
        if(!rem||word<=UINT64_MAX-rem)return word%bound;
    }
    std::abort();
}
static uint32_t read32(const Bytes& data,size_t p) {
    return uint32_t(data[p])|(uint32_t(data[p+1])<<8)|(uint32_t(data[p+2])<<16)|(uint32_t(data[p+3])<<24);
}
static void write32(Bytes& data,size_t p,uint32_t n){for(int i=0;i<4;i++)data[p+i]=uint8_t(n>>(8*i));}
bool randomizeResearchRewards(const Json& spec,const Reader& read,const std::string& seed,Result& result,std::string& error) {
    auto fail=[&](const char* message){error=message;return false;};Bytes data;
    if(spec.value("schema",0)!=3||spec.value("algorithm","")!="za202-research-rewards-v3"||spec.value("build_id","")!="b1f12fd919eae86ab8a978317677e64bce443d1f"||
       spec.value("path","")!="ik_event/bin/research_lv/research_lv.bin"||spec.value("file","")!="research-rewards.bin")return fail("Reward asset version mismatch");
    if(!read("research-rewards.bin",data)||data.size()!=spec.at("bytes").get<size_t>()||sha256(data)!=spec.at("sha256").get<std::string>())return fail("Reward table integrity failed");
    if(spec.at("rows").size()!=49||spec.at("pool").size()<49||spec.at("pool").size()>2048)return fail("Invalid reward pool");
    auto pool=spec.at("pool").get<std::vector<Json>>();Json changes=Json::array();int locked=0,expectedLevel=2;
    for(const auto& row:spec.at("rows"))if(row.value("locked",false))
        std::erase_if(pool,[&](const Json& item){return item.at("item")==row.at("item");});
    for(const auto& row:spec.at("rows")) {
        int level=row.at("level");size_t ip=row.at("item_offset"),qp=row.at("quantity_offset");
        if(level!=expectedLevel++||ip>data.size()||data.size()-ip<4||qp>data.size()||data.size()-qp<4||
           read32(data,ip)!=row.at("item").get<uint32_t>()||read32(data,qp)!=row.at("quantity").get<uint32_t>())return fail("Invalid research reward offsets");
        if(row.value("locked",false)){locked++;continue;}
        int required=0;
        if(row.value("rock_route_reward",false)) {
            if(!result.report.contains("rock_route"))return fail("Missing early rock route");
            const auto& route=result.report.at("rock_route");
            if(route.value("mode","")=="tm")required=route.at("tm_item");
            else if(route.value("mode","")!="natural")return fail("Invalid early rock route");
        }
        std::vector<size_t> eligible;
        for(size_t i=0;i<pool.size();i++)if((required?pool[i].at("item")==required:pool[i].at("item")!=row.at("item"))&&
            (!row.contains("allowed_items")||std::find(row.at("allowed_items").begin(),row.at("allowed_items").end(),pool[i].at("item"))!=row.at("allowed_items").end()))eligible.push_back(i);
        if(eligible.empty())return fail("Research reward pool exhausted");
        size_t selected=eligible[choose(seed,level,eligible.size())];const Json item=pool[selected];pool.erase(pool.begin()+selected);
        int id=item.at("item"),maximum=item.at("max_quantity"),pocket=item.at("pocket");
        if(id<=0||maximum<=0||maximum>999||pocket<0||pocket>7||pocket==4)return fail("Unsupported reward item");
        int quantity=std::min(row.at("quantity").get<int>(),maximum);if(quantity<1)return fail("Invalid reward quantity");
        write32(data,ip,uint32_t(id));write32(data,qp,uint32_t(quantity));
        changes.push_back({{"level",level},{"from_item",row.at("item")},{"from_quantity",row.at("quantity")},
                           {"item",id},{"quantity",quantity},{"name",item.at("name")}});
    }
    result.tables["research_rewards"]=std::move(data);
    result.report["table_sha256"]["research_rewards"]=sha256(result.tables.at("research_rewards"));
    result.report["research_rewards"]={{"algorithm","za202-research-rewards-v3"},{"pool_size",spec.at("pool").size()},
        {"randomized_levels",changes.size()},{"protected_levels",locked},{"changes",changes}};
    return true;
}
}
