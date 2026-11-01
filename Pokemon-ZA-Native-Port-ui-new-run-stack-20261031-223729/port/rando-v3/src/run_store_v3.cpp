// rando-v3 copy of port/rando-music/run_store_music.cpp (SHA-256 of that file recorded in provenance.json) with one
// addition: optional extra tables (today: "personal" = avalon/data/personal_array.bin, written only when base_stats or
// catch_rate is not vanilla). They are recorded under report "native_extra_tables", NOT in "native_tables", so r27b/r28/
// r29 binaries still list and continue these runs (the runtime serves every file under romfs/ regardless); this binary
// hash-checks them on Continue like the immutable tables and the music bank. Everything else is unchanged.
#include "run_store.hpp"
#include "za_music.hpp"
#include "rando_v3.hpp"
#include <algorithm>
#include <cerrno>
#include <cstdio>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef ZA_RANDOMIZER_PS5
#include "platform/ps5_compat.h"
extern "C" int sceKernelDebugOutText(int,const char*);
#endif

namespace za::native {
static void ioFailure(const char* operation,const std::string& path) {
#ifdef ZA_RANDOMIZER_PS5
    const int saved=errno;
    char message[768];snprintf(message,sizeof message,"[za-randomizer] IO failure %s %s errno=%d\n",operation,path.c_str(),errno);sceKernelDebugOutText(0,message);
    errno=saved;
#else
    (void)operation;(void)path;
#endif
}
bool readFile(const std::string& path, Bytes& out, size_t limit) {
    out.clear(); FILE* f=fopen(path.c_str(),"rb"); if(!f)return false;
    bool ok=!fseek(f,0,SEEK_END); long n=ok?ftell(f):-1;
    ok=n>=0 && size_t(n)<=limit && !fseek(f,0,SEEK_SET);
    if(ok){out.resize(size_t(n));ok=fread(out.data(),1,out.size(),f)==out.size();}
    if(fclose(f))ok=false; if(!ok)out.clear(); return ok;
}
bool makeDirs(const std::string& path) {
    if(path.empty()||path[0]!='/'||path.find("/../")!=std::string::npos)return false;
    for(size_t i=1;i<=path.size();i++) if(i==path.size()||path[i]=='/') {
        auto p=path.substr(0,i);struct stat st{};
        // A PS5 title cannot mkdir its already-mounted /download0 root. Check
        // existing components first, following only that trusted mount alias.
        int rc=stat(p.c_str(),&st);
        if(!rc){if(!S_ISDIR(st.st_mode)){ioFailure("not a directory",p);return false;}continue;}
        if(errno!=ENOENT){ioFailure("stat",p);return false;}
        if(mkdir(p.c_str(),0755)&&errno!=EEXIST){ioFailure("mkdir",p);return false;}
        if(stat(p.c_str(),&st)||!S_ISDIR(st.st_mode)){ioFailure("created directory stat",p);return false;}
    }
    return true;
}
bool validId(const std::string& id) {
    if(id.empty()||id.size()>80)return false;
    for(unsigned char c:id)if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'))return false;
    return true;
}
static bool syncDir(const std::string& path) {
    int fd=open(path.c_str(),O_RDONLY);
    if(fd<0){ioFailure("directory open for fsync",path);return errno==EPERM||errno==ENOTSUP;}
    int rc=fsync(fd);int saved=errno;close(fd);
    // Some console filesystems do not implement directory fsync. File fsync
    // and complete-file rename are still mandatory; preserve the old active run.
    if(rc&&saved!=EINVAL&&saved!=ENOTSUP&&saved!=EPERM){errno=saved;ioFailure("directory fsync",path);}
    return !rc || saved==EINVAL || saved==ENOTSUP || saved==EPERM;
}
static bool writeNew(const std::string& path, const Bytes& data) {
    int fd=open(path.c_str(),O_WRONLY|O_CREAT|O_EXCL,0644);if(fd<0){ioFailure("exclusive create",path);return false;}
    size_t at=0;bool ok=true;
    while(at<data.size()) {ssize_t n=write(fd,data.data()+at,data.size()-at);if(n<0&&errno==EINTR)continue;if(n<=0){ok=false;break;}at+=size_t(n);}
    if(ok&&fsync(fd))ok=false;if(close(fd))ok=false;
    Bytes check;ok=ok&&readFile(path,check)&&check==data;if(!ok)ioFailure("write fsync or readback",path);return ok;
}
static Bytes encode(const Json& j) {auto s=j.dump(2);return Bytes(s.begin(),s.end());}
static bool loadRun(const std::string& root,const std::string& id,Run* info) {
    if(!validId(id))return false;
    Bytes bytes; if(!readFile(root+"/"+id+"/report.json",bytes,1u<<20))return false;
    auto j=Json::parse(bytes,nullptr,false);
    if(j.is_discarded()||!j.is_object()||!j.contains("native_run_id")||!j["native_run_id"].is_string()||
       j["native_run_id"]!=id||!j.contains("native_complete")||!j["native_complete"].is_boolean()||
       !j["native_complete"].get<bool>()||!j.contains("seed")||!j["seed"].is_string()||
       !j.contains("starter_name")||!j["starter_name"].is_string())return false;
    struct stat st{};
    if(stat((root+"/"+id+"/save/save_0/main").c_str(),&st)||!S_ISREG(st.st_mode)||st.st_size<1)return false;
    // A game save changes as progress is made. Only immutable randomized tables
    // use their original hashes on Continue; never compare the live save to its template.
    if(!j.contains("native_tables")||!j["native_tables"].is_array()||(j["native_tables"].size()!=3&&j["native_tables"].size()!=4))return false;
    for(const auto& t:j["native_tables"]) {
        if(!t.contains("path")||!t["path"].is_string()||!t.contains("sha256")||!t["sha256"].is_string())return false;
        std::string p=t["path"];
        if(p.empty()||p[0]=='/'||p.find("..")!=std::string::npos||p.find('\\')!=std::string::npos)return false;
        if(!readFile(root+"/"+id+"/romfs/"+p,bytes)||sha256(bytes)!=t["sha256"].get<std::string>())return false;
    }
    // rando-v3: optional extra tables (personal_array.bin), hash-checked like the immutable tables.
    if(j.contains("native_extra_tables")) {
        const auto& extras=j["native_extra_tables"];
        if(!extras.is_array()||extras.size()>4)return false;
        for(const auto& t:extras) {
            if(!t.is_object()||!t.contains("path")||!t["path"].is_string()||!t.contains("sha256")||!t["sha256"].is_string())return false;
            std::string p=t["path"];
            if(p.empty()||p[0]=='/'||p.find("..")!=std::string::npos||p.find('\\')!=std::string::npos)return false;
            if(!readFile(root+"/"+id+"/romfs/"+p,bytes)||sha256(bytes)!=t["sha256"].get<std::string>())return false;
        }
    }
    // r29-music: an optional shuffled music bank at one fixed path, hash-checked like the immutable tables.
    if(j.contains("native_music")) {
        const auto& m=j["native_music"];
        if(!m.is_object()||!m.contains("path")||!m["path"].is_string()||m["path"]!=MusicBankPath||
           !m.contains("sha256")||!m["sha256"].is_string())return false;
        if(!readFile(root+"/"+id+"/romfs/"+std::string(MusicBankPath),bytes)||sha256(bytes)!=m["sha256"].get<std::string>())return false;
    }
    if(info)*info={id,j.value("seed",""),j.value("starter_name","")};
    return true;
}
std::vector<Run> listRuns(const std::string& root) {
    std::vector<Run> result;DIR* d=opendir(root.c_str());if(!d)return result;
    while(auto* e=readdir(d)) {Run run;if(validId(e->d_name)&&loadRun(root,e->d_name,&run))result.push_back(std::move(run));}
    closedir(d);std::sort(result.begin(),result.end(),[](auto&a,auto&b){return a.id>b.id;});return result;
}
std::string activeRun(const std::string& root) {
    Bytes raw;if(!readFile(root+"/active.json",raw,4096))return {};
    auto j=Json::parse(raw,nullptr,false);if(j.is_discarded()||!j.is_object()||!j.contains("id")||!j["id"].is_string())return {};
    auto id=j.value("id","");return loadRun(root,id,nullptr)?id:std::string{};
}
bool selectRun(const std::string& root,const std::string& id,std::string& error) {
    if(!loadRun(root,id,nullptr)){error="Run is incomplete or failed integrity checks";return false;}
    const auto tmp=root+"/active-new-"+id+".json";
    // Only this one selection staging file can be stale. Existing saves and
    // complete run folders are never removed, even after interrupted generation.
    if(unlink(tmp.c_str())&&errno!=ENOENT){error="Cannot clear selection staging file";return false;}
    if(!writeNew(tmp,encode({{"id",id},{"schema",1}}))||rename(tmp.c_str(),(root+"/active.json").c_str())||!syncDir(root)) {
        error="Cannot publish active run";return false;
    }
    return true;
}
bool publishRun(const std::string& root,const std::string& id,const Json& assets,const Result& generated,std::string& error) {
    auto fail=[&](const char*s){error=s;return false;};
    // r29-music: the optional music bank is not one of the 3/4 immutable tables (see native_music in loadRun);
    // rando-v3: neither are the extra tables (native_extra_tables).
    const size_t baseTables=generated.tables.size()-generated.tables.count(MusicTableName)-generated.tables.count(za::v3::PersonalTable);
    if(!validId(id)||generated.save.empty()||(baseTables!=3&&baseTables!=4))return fail("Invalid generated run");
    if(!makeDirs(root))return fail("Cannot create run storage");
    const auto stage=root+"/.pending-"+id,final=root+"/"+id;
    struct stat st{};
    if(!stat(final.c_str(),&st)||errno!=ENOENT)return fail("Run ID already exists");
    if(mkdir(stage.c_str(),0755))return fail("Run staging already exists or cannot be created");
    Json report=generated.report;report["native_run_id"]=id;report["native_complete"]=true;report["native_tables"]=Json::array();
    for(const auto& [name,data]:generated.tables) {
        if(!assets["tables"].contains(name))return fail("Unexpected table name");
        std::string path=assets["tables"][name]["path"];
        if(path.empty()||path[0]=='/'||path.find("..")!=std::string::npos||path.find('\\')!=std::string::npos)return fail("Unsafe table path");
        const auto dst=stage+"/romfs/"+path;
        if(name==za::v3::PersonalTable) {
            if(!makeDirs(dst.substr(0,dst.rfind('/')))||!writeNew(dst,data))return fail("Cannot verify extra table");
            if(!report.contains("native_extra_tables"))report["native_extra_tables"]=Json::array();
            report["native_extra_tables"].push_back({{"path",path},{"sha256",sha256(data)}});
            continue;
        }
        if(name==MusicTableName) {
            if(path!=MusicBankPath)return fail("Unsafe music path");
            if(!makeDirs(dst.substr(0,dst.rfind('/')))||!writeNew(dst,data))return fail("Cannot verify music bank");
            report["native_music"]={{"path",path},{"sha256",sha256(data)}};
            continue;
        }
        if(!makeDirs(dst.substr(0,dst.rfind('/')))||!writeNew(dst,data))return fail("Cannot verify randomized table");
        report["native_tables"].push_back({{"path",path},{"sha256",sha256(data)}});
    }
    if(!makeDirs(stage+"/save/save_0")||!writeNew(stage+"/save/save_0/main",generated.save)||
       !writeNew(stage+"/report.json",encode(report))||!syncDir(stage))return fail("Cannot verify starting save and report");
    if(rename(stage.c_str(),final.c_str())||!syncDir(root))return fail("Cannot publish complete run");
    return selectRun(root,id,error);
}
}
