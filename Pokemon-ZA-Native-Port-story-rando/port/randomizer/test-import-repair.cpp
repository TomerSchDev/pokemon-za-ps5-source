#include "import_repair.hpp"
#include <cassert>
#include <filesystem>
#include <fstream>
#include <iostream>
using namespace za;using namespace za::native;
static void write(const std::string& p,const Bytes& b){std::ofstream f(p,std::ios::binary);f.write(reinterpret_cast<const char*>(b.data()),b.size());assert(f.good());}
static Bytes bytes(const Json& j){auto s=j.dump(2);return Bytes(s.begin(),s.end());}
int main(){
    char temp[]="/tmp/za-repair-import-XXXXXX";assert(mkdtemp(temp));std::string base=temp;
    Json assets={{"tables",{{"wild",{{"path","wild/table.bin"}}},{"trainers",{{"path","trainers/table.bin"}}},{"dlc_boss",{{"path","dlc/table.bin"}}}}}};
    for(int mode=0;mode<7;mode++){
        auto root=base+"/case-"+std::to_string(mode),stage=root+"/stage";std::string error;assert(makeDirs(stage));
        Result old;old.save={1,2,3};old.tables={{"wild",{4}},{"trainers",{5}},{"dlc_boss",{6}}};
        old.report={{"seed","123"},{"starter",498},{"starter_name","Tepig"},{"save_sha256",sha256(old.save)},
            {"options",{{"wild",true}}},{"build_id","test"},{"progression",{{"algorithm","za202-field-capabilities-v1"}}}};
        for(auto& [name,data]:old.tables)old.report["table_sha256"][name]=sha256(data);
        assert(publishRun(root,"r-old",assets,old,error));Bytes oldReport;assert(readFile(root+"/r-old/report.json",oldReport));
        Bytes progress={8,9,10,11};write(root+"/r-old/save/save_0/main",progress);
        auto fresh=Json::parse(oldReport);fresh["native_run_id"]="r-new";
        fresh["wild_repair"]={{"original_report_sha256",sha256(oldReport)}};
        Bytes newWild={7,8,9};fresh["table_sha256"]["wild"]=sha256(newWild);
        if(mode==3)fresh["table_sha256"]["trainers"]="changed unrelated table";
        auto reportRaw=bytes(fresh);write(stage+"/report.json",reportRaw);write(stage+"/wild.bin",newWild);
        Json manifest={{"schema",1},{"title","PPSA91762"},{"source_run","r-old"},{"target_run","r-new"},
            {"source_report_sha256",sha256(oldReport)},{"source_save_sha256",sha256(progress)},
            {"target_report_sha256",sha256(reportRaw)},{"target_wild_sha256",sha256(newWild)}};
        if(mode!=5)write(stage+"/manifest.json",bytes(manifest));
        if(mode==1)write(stage+"/wild.bin",Bytes{0});
        if(mode==2){progress.push_back(12);write(root+"/r-old/save/save_0/main",progress);}
        if(mode==4)assert(makeDirs(root+"/.pending-r-new"));
        if(mode==6){old.report["seed"]="different";assert(publishRun(root,"r-other",assets,old,error));}
        bool ok=importStagedRepair(root,stage,assets,error);
        assert(ok==(mode==0||mode==5||mode==6));
        assert(activeRun(root)==(mode==0?"r-new":mode==6?"r-other":"r-old"));
        Bytes check;assert(readFile(root+"/r-old/report.json",check)&&check==oldReport);
        assert(readFile(root+"/r-old/save/save_0/main",check)&&check==progress);
        if(mode==0){
            assert(readFile(root+"/r-new/save/save_0/main",check)&&check==progress);
            assert(readFile(root+"/r-new/romfs/wild/table.bin",check)&&check==newWild);
            assert(readFile(root+"/r-new/romfs/trainers/table.bin",check)&&check==Bytes{5});
            progress.push_back(13);write(root+"/r-new/save/save_0/main",progress);
            assert(importStagedRepair(root,stage,assets,error));assert(readFile(root+"/r-new/save/save_0/main",check)&&check==progress);
        }
    }
    std::cout<<"PASS: import preserves real progress/old run; repeat never resets; corrupt payload, newer save, altered trainer table and interrupted publish refused; absent stage/different active run unchanged\n";
    assert(base.rfind("/tmp/za-repair-import-",0)==0);std::filesystem::remove_all(base);
}
