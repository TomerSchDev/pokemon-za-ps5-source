#include "run_store.hpp"
#include <cassert>
#include <fstream>
#include <iostream>
#include <filesystem>
using namespace za;using namespace za::native;
static void overwrite(const std::string& path,const std::string& data){std::ofstream f(path,std::ios::binary);f<<data;assert(f.good());}
int main(){
    char tmp[]="/tmp/za-native-run-store-XXXXXX";assert(mkdtemp(tmp));std::string root=tmp,error;
    Json assets={{"tables",{{"trainers",{{"path","trainers/table.bin"}}},{"wild",{{"path","wild/table.bin"}}},{"dlc_boss",{{"path","dlc/table.bin"}}}}}};
    Result one;one.save={1,2,3};one.tables={{"trainers",{4,5}},{"wild",{6,7}},{"dlc_boss",{8,9}}};one.report={{"seed","FIRST"},{"starter_name","Tepig"}};
    assert(publishRun(root,"r-first",assets,one,error));assert(activeRun(root)=="r-first");
    overwrite(root+"/r-first/save/save_0/main","user made progress");
    assert(selectRun(root,"r-first",error));Bytes progress;assert(readFile(root+"/r-first/save/save_0/main",progress));
    Result two=one;two.report["seed"]="SECOND";two.save={9,8,7};
    assert(publishRun(root,"r-second",assets,two,error));assert(activeRun(root)=="r-second");
    Bytes check;assert(readFile(root+"/r-first/save/save_0/main",check)&&check==progress);
    assert(selectRun(root,"r-first",error));assert(activeRun(root)=="r-first");
    assert(!publishRun(root,"r-first",assets,two,error));assert(readFile(root+"/r-first/save/save_0/main",check)&&check==progress);
    assert(makeDirs(root+"/.pending-r-interrupted"));assert(!publishRun(root,"r-interrupted",assets,one,error));assert(listRuns(root).size()==2);
    assert(!publishRun(root,"../outside",assets,one,error));assert(!selectRun(root,"../outside",error));
    auto unsafe=assets;unsafe["tables"]["wild"]["path"]="../../escape";assert(!publishRun(root,"r-unsafe",unsafe,one,error));assert(activeRun(root)=="r-first");
    overwrite(root+"/active.json","{\"id\":33}");assert(activeRun(root).empty());assert(selectRun(root,"r-first",error));
    overwrite(root+"/r-second/romfs/wild/table.bin","corrupt");assert(!selectRun(root,"r-second",error));assert(activeRun(root)=="r-first");
    assert(listRuns(root).size()==1);assert(readFile(root+"/r-first/save/save_0/main",check)&&check==progress);
    auto extended=assets;extended["tables"]["research_rewards"]={{"path","rewards/table.bin"}};
    Result four=one;four.tables["research_rewards"]={1,9,2,8};
    assert(publishRun(root,"r-with-rewards",extended,four,error));assert(activeRun(root)=="r-with-rewards");
    assert(selectRun(root,"r-first",error));assert(readFile(root+"/r-first/save/save_0/main",check)&&check==progress);
    overwrite(root+"/r-with-rewards/romfs/rewards/table.bin","corrupt reward table");
    assert(!selectRun(root,"r-with-rewards",error));assert(activeRun(root)=="r-first");
    std::cout<<"PASS: publish, save progress preserved, independent runs, duplicate refusal, interrupted generation, traversal rejection, malformed active record, immutable-table integrity, optional fourth table and old-run compatibility\n";
    // Remove only this unique test-owned tree, never a caller-supplied directory.
    assert(root.rfind("/tmp/za-native-run-store-",0)==0);std::filesystem::remove_all(root);
}
