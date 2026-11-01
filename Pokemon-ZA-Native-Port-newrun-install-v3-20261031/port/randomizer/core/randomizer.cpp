#include "randomizer.hpp"
#include <mbedtls/sha256.h>
#include <algorithm>
#include <limits>
#include <set>

namespace za {
namespace {
constexpr const char* Build="b1f12fd919eae86ab8a978317677e64bce443d1f";
constexpr const char* Algorithm="za202-randomizer-alpha1";
std::array<uint8_t,32> digest(const uint8_t* p,size_t n) {
    std::array<uint8_t,32> out{};
    if(mbedtls_sha256(p,n,out.data(),0)!=0) std::abort();
    return out;
}
std::array<uint8_t,32> digest(const std::string& s) {return digest(reinterpret_cast<const uint8_t*>(s.data()),s.size());}
struct Seed {
    std::array<uint8_t,32> key;
    explicit Seed(const std::string& s):key(digest(Json::array({Algorithm,Build,s}).dump())){}
    uint64_t number(const std::string& domain,const Json& identity,uint64_t bound) const {
        if(!bound) std::abort();
        uint64_t rem=(UINT64_MAX%bound+1)%bound;
        for(int retry=0;retry<1000;retry++) {
            auto msg=Json::array({domain,identity,retry}).dump();
            Bytes inner(64),outer(96);
            for(size_t i=0;i<64;i++) {inner[i]=(i<32?key[i]:0)^0x36;outer[i]=(i<32?key[i]:0)^0x5c;}
            inner.insert(inner.end(),msg.begin(),msg.end());
            auto h=digest(inner.data(),inner.size());std::copy(h.begin(),h.end(),outer.begin()+64);
            h=digest(outer.data(),outer.size());uint64_t w=0;
            for(int i=0;i<8;i++)w=(w<<8)|h[i];
            if(rem==0 || w<=UINT64_MAX-rem)return w%bound;
        }
        std::abort();
    }

};
// Canonical order is computed once, then an excluded candidate is skipped in place.
// This preserves the old selection exactly without sorting/copying every row.
struct Pool {
    std::vector<Json> values;
    explicit Pool(const Json& input) {
        std::vector<std::pair<std::string,Json>> ordered;
        for(const auto& v:input)ordered.emplace_back(v.dump(),v);
        std::stable_sort(ordered.begin(),ordered.end(),[](const auto&a,const auto&b){return a.first<b.first;});
        for(auto& p:ordered)values.push_back(std::move(p.second));
    }
    template<class Reject> const Json& choose(const Seed& rng,const std::string& domain,const Json& id,Reject reject)const {
        size_t n=0;for(const auto& v:values)if(!reject(v))++n;
        if(!n)std::abort();
        auto selected=rng.number(domain,id,n);
        for(const auto& v:values)if(!reject(v)){if(selected==0)return v;--selected;}
        std::abort();
    }
    const Json& choose(const Seed& rng,const std::string& domain,const Json& id,const Json& excluded=nullptr)const {
        return choose(rng,domain,id,[&](const Json& v){return v==excluded;});
    }
};
using PersonalIndex=std::map<std::pair<int,int>,const Json*>;
bool patch(Bytes& data,const Json& field,const Json& value) {
    if(field.contains("capacity")) {
        if(!value.is_string())return false;
        auto str=value.get<std::string>();size_t p=field.at("data"),l=field.at("length"),cap=field.at("capacity");
        if(cap>1024 || str.size()>cap || p>data.size() || cap+1>data.size()-p || l>data.size() || 4>data.size()-l)return false;
        std::fill(data.begin()+p,data.begin()+p+cap+1,0);std::copy(str.begin(),str.end(),data.begin()+p);
        for(int i=0;i<4;i++)data[l+i]=uint8_t(str.size()>>(8*i));return true;
    }
    size_t p=field.at("offset"),n=field.at("bytes");bool sign=field.at("signed");
    if(!(n==1||n==2||n==4||n==8) || p>data.size() || n>data.size()-p)return false;
    if(!value.is_number_integer()&&!value.is_boolean())return false;
    int64_t v=value.is_boolean()?(value.get<bool>()?1:0):value.get<int64_t>();
    if(!sign&&v<0)return false;
    if(n<8 && (v<(sign?-(int64_t(1)<<(n*8-1)):0) || uint64_t(v>=0?v:0)>(sign?(uint64_t(1)<<(n*8-1))-1:(uint64_t(1)<<(n*8))-1)))return false;
    for(size_t i=0;i<n;i++)data[p+i]=uint8_t(uint64_t(v)>>(8*i));return true;
}
std::vector<Json> moves(const PersonalIndex& personal,int sp,int form,int level) {
    const Json* entry=nullptr;
    auto found=personal.find({sp,form});if(found!=personal.end())entry=found->second;
    if(!entry&&form)return moves(personal,sp,0,level);
    if(!entry)return {};
    std::vector<Json> learned,available;
    for(const auto& m:entry->at("learnset")) {
        int lvl=m.at("level"),move=m.at("move");
        if(!move||lvl<0)continue;
        available.push_back(m);
        if(lvl>std::max(1,level))continue;
        std::erase_if(learned,[&](const Json& x){return x.at("move")==move;});learned.push_back(m);
    }
    if(learned.empty()&&!available.empty()) {
        std::stable_sort(available.begin(),available.end(),[](const Json&a,const Json&b){return a.at("level")<b.at("level");});
        learned.push_back(available.front());
    }
    if(learned.size()>4)learned.erase(learned.begin(),learned.end()-4);
    return learned;
}
int nibble(char c){return c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:-1;}
}

std::string sha256(const Bytes& bytes) {
    auto d=digest(bytes.data(),bytes.size());std::string out;constexpr char hex[]="0123456789abcdef";
    for(auto c:d){out+=hex[c>>4];out+=hex[c&15];}return out;
}

bool generate(const Json& a,const Json& starters,const Reader& read,const std::string& seed,
              const Options& options,int starter,Result& out,const Progress& progress) {
    out={};auto fail=[&](const char* e){out.tables.clear();out.save.clear();out.error=e;return false;};
    if(a.value("schema",0)!=1||a.value("build_id","")!=Build||a.value("algorithm","")!=Algorithm)return fail("Asset/build mismatch");
    if(seed.empty()||seed.size()>64||seed.front()==' '||seed.back()==' ')return fail("Seed must be 1-64 ASCII characters without edge spaces");
    for(unsigned char c:seed)if(c<32||c>126)return fail("Only ASCII seeds are accepted by the controller menu");
    if(starters.value("schema",0)!=1||starters.value("format","")!="za-city-starter-deltas-v1")return fail("Starter asset mismatch");
    if(progress)progress(BuildStage::Index,0,1);
    Seed rng(seed);Json counts=Json::object();
    std::vector<Json> pool=a.at("pool").get<std::vector<Json>>();
    if(pool.size()<2||pool.size()>2048)return fail("Invalid species pool");
    Pool normalPool(a.at("pool")),trainerMegas(a.at("trainer_megas")),wildMegas(a.at("mega"));
    PersonalIndex personal;for(const auto& p:a.at("personal"))personal.emplace(std::make_pair(int(p.at("species")),int(p.at("form"))),&p);
    if(progress)progress(BuildStage::Index,1,1);
    std::set<int> stones;for(auto& m:a.at("mega"))if(int(m.at("item"))>0)stones.insert(m.at("item").get<int>());
    for(const auto& name:{"trainers","wild","dlc_boss"}) {
        const auto& table=a.at("tables").at(name);Bytes data;
        bool enabled=std::string(name)=="trainers"?(options.trainers||options.mega_trainers):std::string(name)=="wild"?options.wild:options.dlc_rematches;
        std::string file=enabled?table.at("file").get<std::string>():std::string(name)+".vanilla.bin";
        std::string expected=enabled?table.at("sha256").get<std::string>():table.at("vanilla_sha256").get<std::string>();
        if(file.find('/')!=std::string::npos||file.find('\\')!=std::string::npos||!read(file,data)||data.size()>16*1024*1024||sha256(data)!=expected)return fail("Table integrity failed");
        const auto stage=std::string(name)=="trainers"?BuildStage::Trainers:std::string(name)=="wild"?BuildStage::Wild:BuildStage::Dlc;
        uint32_t total=table.contains("rows")?table.at("rows").size():table.at("row_count").get<uint32_t>();
        uint32_t completed=0;
        if(progress)progress(stage,0,total);
        // Row metadata is streamed in verified batches, not one large JSON tree.
        auto visit=[&](auto apply) {
            auto batch=[&](const Json& rows){
                if(!rows.is_array())return false;
                for(const auto& row:rows){if(!apply(row))return false;++completed;if(progress&&((completed%32)==0||completed==total))progress(stage,completed,total);}
                return true;
            };
            if(table.contains("rows"))return batch(table.at("rows"));
            for(const auto& chunk:table.at("rows_files")){
                std::string file=chunk.at("file");Bytes bytes;
                if(file.find('/')!=std::string::npos||file.find('\\')!=std::string::npos||!read(file,bytes)||bytes.size()>512*1024||sha256(bytes)!=chunk.at("sha256").get<std::string>())return false;
                auto rows=Json::parse(bytes,nullptr,false);
                if(rows.is_discarded()||!rows.is_array()||rows.size()!=chunk.at("count").get<size_t>()||!batch(rows))return false;
            }
            return completed==total;
        };
        auto write=[&](const Json& fs,const std::string& f,const Json& val){return patch(data,fs.at(f),val);};
        if(enabled&&std::string(name)=="trainers") {
            if(!visit([&](const Json& r) {
                bool mega=r.at("mega");if(mega?!options.mega_trainers:!options.trainers)return true;
                int sp=r.at("species"),form=r.at("form"),item=r.at("item"),level=r.at("level");
                int next,variant=0;
                if(mega) {
                    auto m=trainerMegas.choose(rng,"trainer-mega",r.at("identity"),[&](const Json&m){return m.at("species")==sp&&m.at("form")==form;});next=m.at("species");variant=m.at("form");item=m.at("item");
                } else {
                    next=normalPool.choose(rng,"trainer",r.at("identity"),Json(sp));if(stones.contains(item))item=0;
                }
                const auto& fs=r.at("fields");
                if(!write(fs,"devId",next)||!write(fs,"formId",variant)||!write(fs,"item",item)||!write(fs,"sex",0))return fail("Invalid trainer patch");
                auto learned=moves(personal,next,variant,level);if(learned.empty())return fail("Missing moves");
                for(size_t i=0;i<4;i++) {
                    int move=i<learned.size()?int(learned[i].at("move")):0;
                    bool plus=i<learned.size()&&int(learned[i].at("mastery"))>0&&int(learned[i].at("mastery"))<=level;
                    if(!write(r.at("moves")[i],"wazaId",move)||!write(r.at("moves")[i],"isPlusWaza",plus))return fail("Invalid move patch");
                }
                auto key=mega?"trainer-mega":"trainer";
                counts[key]=counts.value(key,0)+1;return true;
            }))return fail("Trainer row generation failed");
        } else if(enabled&&std::string(name)=="wild") {
            if(!visit([&](const Json& r) {
                int sp=r.at("species"),form=r.at("form"),next=0,variant=0;Json original;
                for(const auto& m:a.at("mega"))if(m.at("species")==sp&&m.at("mega_form")==form){original=m;break;}
                std::string domain;
                if(!original.is_null()) {
                    domain="wild-mega";
                    auto m=wildMegas.choose(rng,domain,r.at("identity"),original);next=m.at("species");variant=m.at("mega_form");
                } else {
                    domain="wild";next=normalPool.choose(rng,domain,r.at("identity"),Json(sp));
                }
                const auto& fs=r.at("fields");
                if(!write(fs,"devNo",next)||!write(fs,"formNo",variant)||!write(fs,"sex",0))return fail("Invalid wild patch");
                counts[domain]=counts.value(domain,0)+1;return true;
            }))return fail("Wild row generation failed");
        } else if(enabled&&std::string(name)=="dlc_boss"&&total>1) {
            Json rows=Json::array();if(!visit([&](const Json&r){rows.push_back(r);return true;}))return fail("DLC row integrity failed");
            std::vector<std::string> ids;std::map<std::string,Json> sources;
            for(const auto& r:rows){std::string id=r.at("identity");ids.push_back(id);sources[id]=r.at("source");}
            std::sort(ids.begin(),ids.end());
            for(size_t i=ids.size()-1;i>0;i--)std::swap(ids[i],ids[rng.number("dlc-mega-rematch",i,i+1)]);
            std::map<std::string,std::string> mapping;for(size_t i=0;i<ids.size();i++)mapping[ids[i]]=ids[(i+1)%ids.size()];
            for(const auto& r:rows)for(const auto& [f,value]:sources.at(mapping.at(r.at("identity").get<std::string>())).items())if(!write(r.at("fields"),f,value))return fail("Invalid DLC patch");
            counts["dlc-mega-rematch"]=rows.size();
        }
        if(progress)progress(stage,total,total);
        out.tables[name]=std::move(data);
    }
    if(progress)progress(BuildStage::Starter,0,1);
    std::vector<Json> candidates;for(const auto& p:starters.at("entries"))candidates.push_back(p.at("species"));
    if(candidates.empty()||candidates.size()>2048)return fail("Invalid starter pool");
    int chosen=starter?starter:int(Pool(candidates).choose(rng,"city-starter-v1",0));
    const Json* entry=nullptr;for(const auto& p:starters.at("entries"))if(p.at("species")==chosen){entry=&p;break;}
    if(!entry)return fail("Selected starter is not in the validated pool");
    if(!read("city-save.bin",out.save)||out.save.size()!=size_t(starters.at("template_bytes"))||sha256(out.save)!=starters.at("template_sha256").get<std::string>())return fail("City template integrity failed");
    size_t previous=0;
    for(const auto& p:entry->at("patches")) {
        size_t pos=p.at("offset");auto h=p.at("hex").get<std::string>();
        if(h.size()%2||pos<previous||pos>out.save.size()||h.size()/2>out.save.size()-pos)return fail("Invalid starter patch range");
        for(size_t i=0;i<h.size();i+=2){int hi=nibble(h[i]),lo=nibble(h[i+1]);if(hi<0||lo<0)return fail("Invalid starter patch data");out.save[pos+i/2]=uint8_t(hi*16+lo);}
        previous=pos+h.size()/2;
    }
    if(sha256(out.save)!=entry->at("output_sha256").get<std::string>())return fail("Starter save integrity failed");
    out.report={{"schema",1},{"seed",seed},{"algorithm",Algorithm},{"build_id",Build},{"starter",chosen},
        {"starter_name",entry->at("name")},{"starter_level",7},{"counts",counts},
        {"options",{{"wild",options.wild},{"trainers",options.trainers},{"mega_trainers",options.mega_trainers},{"dlc_rematches",options.dlc_rematches}}},
        {"save_sha256",sha256(out.save)},{"in_game_verified",false},{"reset_policy","explicit_new_run_only"}};
    for(const auto& [name,data]:out.tables)out.report["table_sha256"][name]=sha256(data);
    if(progress)progress(BuildStage::Complete,1,1);
    return true;
}
}
