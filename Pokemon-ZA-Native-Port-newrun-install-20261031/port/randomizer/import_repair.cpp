#include "import_repair.hpp"
#include <cerrno>
#include <set>
#include <sys/stat.h>
namespace za::native {
bool importStagedRepair(const std::string& root,const std::string& stage,const Json& assets,std::string& error){
    auto fail=[&](const char* s){error=s;return false;};
    struct stat st{};const std::string manifest=stage+"/manifest.json";
    if(stat(manifest.c_str(),&st)){if(errno==ENOENT)return true;return fail("Cannot inspect staged repair");}
    Bytes raw;if(!readFile(manifest,raw,65536))return fail("Cannot read repair manifest");
    auto m=Json::parse(raw,nullptr,false);
    if(m.is_discarded()||!m.is_object()||m.value("schema",0)!=1||m.value("title","")!="PPSA91762")return fail("Invalid repair manifest");
    const std::string oldId=m.value("source_run",""),newId=m.value("target_run","");
    if(!validId(oldId)||!validId(newId)||oldId==newId)return fail("Invalid repair run identity");
    const auto active=activeRun(root);
    // Once imported, never reset this or another run, including after gameplay.
    if(active!=oldId)return true;
    if(!readFile(root+"/"+oldId+"/report.json",raw,1u<<20)||sha256(raw)!=m.value("source_report_sha256",""))return fail("Source report changed; repair postponed");
    auto old=Json::parse(raw,nullptr,false);
    if(old.is_discarded()||old.value("native_run_id","")!=oldId||old.at("progression").value("algorithm","")!="za202-field-capabilities-v1")return fail("Unexpected source run");
    Bytes reportRaw;if(!readFile(stage+"/report.json",reportRaw,1u<<20)||sha256(reportRaw)!=m.value("target_report_sha256",""))return fail("Repair report integrity failed");
    auto report=Json::parse(reportRaw,nullptr,false);
    if(report.is_discarded()||report.value("native_run_id","")!=newId||!report.contains("wild_repair"))return fail("Unexpected repair report");
    for(const char* key:{"seed","starter","starter_name","save_sha256","options","build_id"})
        if(!report.contains(key)||report.at(key)!=old.at(key))return fail("Repair changed run identity or options");
    if(report.at("wild_repair").value("original_report_sha256","")!=m.value("source_report_sha256",""))return fail("Repair source mismatch");
    Result result;result.report=report;
    if(!readFile(root+"/"+oldId+"/save/save_0/main",result.save)||sha256(result.save)!=m.value("source_save_sha256",""))return fail("Progress changed; refresh repair snapshot");
    std::set<std::string> names;
    for(const auto& entry:old.at("native_tables")){
        const std::string path=entry.at("path");std::string name;
        for(auto it=assets.at("tables").begin();it!=assets.at("tables").end();++it)if(it.value().at("path")==path)name=it.key();
        if(name.empty()||!names.insert(name).second||path.empty()||path[0]=='/'||path.find("..")!=std::string::npos||path.find('\\')!=std::string::npos)return fail("Unexpected source table");
        Bytes bytes;if(!readFile(root+"/"+oldId+"/romfs/"+path,bytes,32u<<20)||sha256(bytes)!=entry.at("sha256").get<std::string>())return fail("Source table integrity failed");
        if(name=="wild"){
            if(!readFile(stage+"/wild.bin",bytes,32u<<20)||sha256(bytes)!=m.value("target_wild_sha256",""))return fail("Repair wild table integrity failed");
        }
        if(sha256(bytes)!=report.at("table_sha256").at(name).get<std::string>())return fail("Repair changed unrelated table");
        result.tables[name]=std::move(bytes);
    }
    if(!names.count("wild"))return fail("Repair is missing wild encounters");
    Bytes recheck;if(!readFile(root+"/"+oldId+"/save/save_0/main",recheck)||recheck!=result.save)return fail("Save changed during repair");
    return publishRun(root,newId,assets,result,error);
}
}
