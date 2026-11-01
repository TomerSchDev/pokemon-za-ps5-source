#include "menu_display.hpp"
#include "run_store.hpp"
#include "research_rewards.hpp"
#include "progression.hpp"
#include "import_repair.hpp"
#include "assets_hashes.h"
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <ctime>
#include <fcntl.h>
#include <pthread.h>
#include <sys/stat.h>
#include <unistd.h>
extern "C" int sceKernelDebugOutText(int,const char*);
namespace za::native {
static constexpr const char* Root="/download0/zarecomp/rando";
static constexpr const char* AssetRoot="/app0/randomizer-assets/";
static constexpr uint32_t Green=0xff54e3aa,Muted=0xff91a5bb,White=0xffedf5fc;
static bool readAsset(const std::string& name,Bytes& bytes) {
    if(name.empty()||name.find('/')!=std::string::npos||name.find('\\')!=std::string::npos||name.find("..")!=std::string::npos)return false;
    return readFile(std::string(AssetRoot)+name,bytes);
}
static bool jsonAsset(const char* name,const char* expected,Json& out) {
    Bytes bytes;char message[300];
    if(!readAsset(name,bytes)){snprintf(message,sizeof message,"[za-randomizer] asset read failed %s errno=%d\n",name,errno);sceKernelDebugOutText(0,message);return false;}
    auto digest=sha256(bytes);
    if(digest!=expected){snprintf(message,sizeof message,"[za-randomizer] asset hash mismatch %s actual=%s expected=%s\n",name,digest.c_str(),expected);sceKernelDebugOutText(0,message);return false;}
    out=Json::parse(bytes,nullptr,false);bool ok=!out.is_discarded()&&out.is_object();
    snprintf(message,sizeof message,"[za-randomizer] asset verified %s bytes=%zu parsed=%d\n",name,bytes.size(),int(ok));sceKernelDebugOutText(0,message);return ok;
}
static std::string freshSeed() {
    const uint64_t value=(uint64_t(arc4random())<<32)|arc4random();
    return std::to_string(value%10000000000ULL);
}
struct StarterChoice {int species;const char* name;};
static constexpr StarterChoice starterChoices[]={
    {0,"RANDOM FROM SEED"},{152,"CHIKORITA"},{498,"TEPIG"},{158,"TOTODILE"}
};
static constexpr int starterCount=sizeof starterChoices/sizeof *starterChoices;
struct Job {
    const Json* assets=nullptr;const Json* starters=nullptr;const Json* rewards=nullptr;const Json* progression=nullptr;Options options;bool researchRewards=true;
    std::string seed,id,error;int starter=0;bool success=false;
    std::atomic<int> stage{0},done{0},total{1};std::atomic<bool> finished{false};
};
static void* generateJob(void* arg) {
    auto& j=*static_cast<Job*>(arg);Result result;
    auto progress=[&](BuildStage s,uint32_t d,uint32_t n){j.total=int(n);j.done=int(d);j.stage=int(s);};
    if(generate(*j.assets,*j.starters,readAsset,j.seed,j.options,j.starter,result,progress)) {
        result.report["options"]["research_rewards"]=j.researchRewards;
        if(protectProgression(*j.progression,readAsset,j.seed,result,j.error)&&
           (!j.researchRewards||randomizeResearchRewards(*j.rewards,readAsset,j.seed,result,j.error)))
            j.success=publishRun(Root,j.id,*j.assets,result,j.error);
    } else j.error=result.error;
    char message[256];snprintf(message,sizeof message,"[za-randomizer] generation %s seed=%s run=%s starter=%d\n",j.success?"complete":"FAILED",j.seed.c_str(),j.id.c_str(),j.success?result.report.value("starter",0):0);
    sceKernelDebugOutText(0,message);j.finished.store(true,std::memory_order_release);return nullptr;
}
static void heading(Display& d,const char* subtitle) {
    d.clear();d.text(56,36,"POKEMON LEGENDS Z-A",Green,4);d.text(56,83,"RANDOMIZER",White,3);
    d.text(56,123,subtitle,Muted,2);d.rect(56,155,1168,2,0xff293c51);
}
static void seedPipelineCache() {
    const std::string target="/download0/zarecomp/cache/vk_pipelines.bin";
    // access() is refused for native titles, even for existing files.
    struct stat existing{};if(!stat(target.c_str(),&existing)||errno!=ENOENT)return;
    Bytes bytes;if(!readFile("/app0/cache/vk_pipelines.bin",bytes,256u<<20)||bytes.size()<32)return;
    if(!makeDirs("/download0/zarecomp/cache"))return;
    const auto temp=target+".initial";int fd=open(temp.c_str(),O_WRONLY|O_CREAT|O_EXCL,0644);if(fd<0)return;
    size_t at=0;bool ok=true;
    while(at<bytes.size()){ssize_t n=write(fd,bytes.data()+at,bytes.size()-at);if(n<0&&errno==EINTR)continue;if(n<=0){ok=false;break;}at+=size_t(n);}
    if(ok&&fsync(fd))ok=false;if(close(fd))ok=false;
    Bytes check;if(ok&&readFile(temp,check,256u<<20)&&check==bytes&&!rename(temp.c_str(),target.c_str()))
        sceKernelDebugOutText(0,"[za-randomizer] initial PS5 pipeline cache copied; runtime will validate its device UUID\n");
}
int bootMenu() {
    Display display;if(!display.open()){sceKernelDebugOutText(0,"[za-randomizer] display or controller initialization failed\n");display.close();return 1;}
    Json assets,starters,rewards,progression;
    heading(display,"LOADING RANDOMIZER DATA");display.present();
    bool assetsOK=jsonAsset("tables.json",ZA_TABLES_SHA256,assets)&&jsonAsset("starter-deltas.json",ZA_STARTERS_SHA256,starters)&&
                  jsonAsset("research-rewards.json",ZA_REWARDS_SHA256,rewards)&&jsonAsset("progression.json",ZA_PROGRESSION_SHA256,progression);
    bool storageOK=assetsOK&&makeDirs(Root);
    if(!assetsOK||!storageOK) {
        char detail[160];snprintf(detail,sizeof detail,"[za-randomizer] startup assets=%d storage=%d errno=%d\n",int(assetsOK),int(storageOK),errno);sceKernelDebugOutText(0,detail);
        heading(display,"RANDOMIZER DATA COULD NOT BE LOADED");display.text(56,240,"PLEASE CLOSE THIS APP FROM THE PS5 HOME SCREEN",Muted,2);display.present();
        sceKernelDebugOutText(0,"[za-randomizer] asset integrity or run storage failure\n");while(true)usleep(100000);
    }
    assets["tables"]["research_rewards"]={{"path","ik_event/bin/research_lv/research_lv.bin"}};
    std::string repairError;
    if(!importStagedRepair(Root,"/app0/run-repair",assets,repairError)) {
        heading(display,"RUN REPAIR COULD NOT BE VERIFIED");display.text(56,240,repairError,0xffffaa90,2);
        display.text(56,320,"ORIGINAL RUN AND SAVE HAVE BEEN RETAINED",Muted,2);display.present();
        sceKernelDebugOutText(0,("[za-randomizer] repair REFUSED: "+repairError+"\n").c_str());
        while(true)usleep(100000);
    }
    sceKernelDebugOutText(0,"[za-randomizer] optional staged repair checked; run storage ready\n");
    std::vector<Run> runs=listRuns(Root);std::string active=activeRun(Root),selected;
    std::string seed=freshSeed(),seedInput,error;Options options;bool researchRewards=true;int starterIndex=0,row=active.empty()?1:0;
    enum Page{Main,Seed,Saved,Confirm,Generating,Error};Page page=Main;
    int keypad=0,runIndex=0;bool replaceSeed=true,dirty=true;Job job;pthread_t thread{};bool threadStarted=false;
    int previousProgress=-1,previousStage=-1;
    while(selected.empty()) {
        uint32_t key=display.buttons();
        if(page==Generating) {
            if(job.finished.load(std::memory_order_acquire)) {
                pthread_join(thread,nullptr);threadStarted=false;
                if(job.success){selected=job.id;break;}
                error=job.error;page=Error;dirty=true;
            } else if(previousProgress!=job.done||previousStage!=job.stage){previousProgress=job.done;previousStage=job.stage;dirty=true;}
        } else if(key) {
            dirty=true;
            if(page==Error){if(key&(Circle|Cross)){error.clear();page=Main;}}
            else if(page==Seed) {
                if(key&Circle)page=Main;
                else {
                    if(key&Left)keypad=keypad/3*3+(keypad%3+2)%3;
                    if(key&Right)keypad=keypad/3*3+(keypad%3+1)%3;
                    if(key&Up)keypad=(keypad+9)%12;if(key&Down)keypad=(keypad+3)%12;
                    if(key&Square){if(!seedInput.empty())seedInput.pop_back();replaceSeed=false;}
                    if(key&Triangle){seedInput=freshSeed();replaceSeed=true;}
                    if(key&Cross) {
                        if(keypad==9){seedInput.clear();replaceSeed=false;}
                        else if(keypad==11) {
                            if(!seedInput.empty()) {
                                auto first=seedInput.find_first_not_of('0');
                                seed=first==std::string::npos?"0":seedInput.substr(first);page=Main;
                            }
                        } else {
                            if(replaceSeed){seedInput.clear();replaceSeed=false;}
                            if(seedInput.size()<16)seedInput+=keypad==10?'0':char('1'+keypad);
                        }
                    }
                }
            } else if(page==Saved) {
                if(key&Circle)page=Main;
                if(!runs.empty()) {
                    if(key&Up)runIndex=(runIndex+int(runs.size())-1)%int(runs.size());
                    if(key&Down)runIndex=(runIndex+1)%int(runs.size());
                    if(key&Cross){if(selectRun(Root,runs[runIndex].id,error))selected=runs[runIndex].id;else page=Error;}
                }
            } else if(page==Confirm) {
                if(key&Circle)page=Main;
                if(key&Cross) {
                    job.assets=&assets;job.starters=&starters;job.rewards=&rewards;job.researchRewards=researchRewards;
                    job.progression=&progression;
                    job.seed=seed;job.options=options;job.error.clear();job.success=false;
                    job.starter=starterChoices[starterIndex].species;
                    char id[64];snprintf(id,sizeof id,"r%016llx-%08x",static_cast<unsigned long long>(time(nullptr)),arc4random());job.id=id;
                    job.finished=false;job.done=0;job.total=1;job.stage=0;previousProgress=previousStage=-1;
                    if(pthread_create(&thread,nullptr,generateJob,&job)){error="Could not start generation";page=Error;}
                    else{threadStarted=true;page=Generating;}
                }
            } else {
                if(key&Up)row=(row+9)%10;if(key&Down)row=(row+1)%10;
                if(row==3&&(key&(Left|Right|Cross)))starterIndex=(starterIndex+starterCount+((key&Left)?-1:1))%starterCount;
                if(row==3&&(key&Triangle))starterIndex=0;
                if(row>=4&&row<=7&&(key&(Left|Right|Cross))) {
                    bool* settings[]={&options.wild,&options.trainers,&options.mega_trainers,&options.dlc_rematches};*settings[row-4]=!*settings[row-4];
                }
                if(row==8&&(key&(Left|Right|Cross)))researchRewards=!researchRewards;
                if(key&Cross) {
                    if(row==0&&!active.empty()){if(selectRun(Root,active,error))selected=active;else page=Error;}
                    else if(row==1)page=Confirm;
                    else if(row==2){seedInput=seed;keypad=0;replaceSeed=true;page=Seed;}
                    else if(row==9){runs=listRuns(Root);runIndex=0;page=Saved;}
                }
            }
        }
        if(dirty&&selected.empty()) {
            if(page==Main) {
                heading(display,"CREATE A NEW RUN OR CONTINUE AN EXISTING SAVE");
                auto starter=std::string(starterChoices[starterIndex].name);
                std::string labels[]={active.empty()?"CONTINUE - NO RUN YET":"CONTINUE CURRENT RUN","START NEW RUN","SEED  "+seed,"STARTER  "+starter,
                    std::string("WILD POKEMON  ")+(options.wild?"ON":"OFF"),std::string("TRAINERS  ")+(options.trainers?"ON":"OFF"),
                    std::string("MEGA TRAINERS  ")+(options.mega_trainers?"ON":"OFF"),std::string("DLC REMATCHES  ")+(options.dlc_rematches?"ON":"OFF"),
                    std::string("RESEARCH REWARDS  ")+(researchRewards?"ON":"OFF"),"SAVED RUNS  "+std::to_string(runs.size())};
                for(int i=0;i<10;i++){int y=180+i*42;if(i==row)display.rect(44,y-8,1180,38,0xff24413e);display.text(64,y,labels[i],i==row?Green:White,3);}
                display.text(56,633,"D-PAD MOVE / CHANGE    CROSS SELECT    TRIANGLE RANDOM STARTER",Muted,2);
                display.text(56,668,"EARLY ROCK GUARD ON. ALL OTHER ORDINARY SPAWNS RANDOM.",Muted,2);
            } else if(page==Seed) {
                heading(display,"ENTER A SEED USING THE NUMBER KEYPAD - UP TO 16 DIGITS");
                display.rect(280,185,720,68,0xff192b3d);
                display.text(304,205,seedInput.empty()?"ENTER A NUMBER":seedInput,seedInput.empty()?Muted:Green,4);
                const char* keys[]={"1","2","3","4","5","6","7","8","9","CLEAR","0","DONE"};
                for(int i=0;i<12;i++) {
                    int x=320+(i%3)*216,y=280+(i/3)*78;
                    display.rect(x,y,200,64,i==keypad?0xff244f43:0xff192b3d);
                    display.text(x+100-int(std::string(keys[i]).size())*9,y+21,keys[i],i==keypad?Green:White,3);
                }
                display.text(56,620,"D-PAD MOVE    CROSS ENTER    SQUARE DELETE",White,2);
                display.text(56,663,"TRIANGLE RANDOM SEED    CIRCLE CANCEL",Muted,2);
            } else if(page==Saved) {
                heading(display,"SELECT A SAVED RUN TO CONTINUE");int start=runIndex/8*8;
                for(int i=start;i<int(runs.size())&&i<start+8;i++){int y=190+(i-start)*50;if(i==runIndex)display.rect(44,y-9,1180,46,0xff24413e);display.text(64,y,runs[i].seed+"  "+runs[i].starter,i==runIndex?Green:White,2);}
                if(runs.empty())display.text(64,240,"NO SAVED RUNS YET",Muted,3);
                display.text(56,652,"UP / DOWN SELECT    CROSS CONTINUE    CIRCLE BACK",Muted,2);
            } else if(page==Confirm) {
                heading(display,"START A FRESH RANDOMIZED RUN");display.text(56,220,"SEED  "+seed,Green,4);
                display.text(56,268,std::string("STARTER  ")+starterChoices[starterIndex].name,Green,3);
                display.text(56,310,"START IN THE CITY WITH A LEVEL 7 PARTNER.",White,3);
                display.text(56,370,"YOUR PREVIOUS RUNS WILL REMAIN IN SAVED RUNS.",Muted,2);
                display.text(56,422,researchRewards?"RESEARCH TMs PROTECTED; OTHER REWARDS RANDOMIZED":"ORIGINAL RESEARCH REWARDS",Muted,2);
                display.text(56,458,"EARLY ROCK PROVIDER RETAINED. SIDE QUESTS NOT GUARANTEED.",Muted,2);
                display.text(56,570,"CROSS CREATE AND PLAY    CIRCLE BACK",Green,3);
            } else if(page==Generating) {
                const char* names[]={"PREPARING SPECIES","RANDOMIZING TRAINERS","RANDOMIZING WILD POKEMON","RANDOMIZING DLC","PREPARING STARTER SAVE","SAVING NEW RUN"};
                int stage=job.stage.load();if(stage<0||stage>5)stage=0;
                heading(display,"CREATING YOUR RUN");display.text(56,260,names[stage],Green,4);
                int total=job.total.load(),done=job.done.load();if(done>total)done=total;
                display.rect(56,355,1168,22,0xff293c51);if(total>0)display.rect(56,355,int(1168LL*done/total),22,Green);
                display.text(56,407,std::to_string(done)+" / "+std::to_string(total),White,3);
                display.text(56,570,"PREPARING DATA AND A SEPARATE SAVE FOR THIS SEED",Muted,2);
            } else {
                heading(display,"COULD NOT START THIS RUN");display.text(56,260,error,0xffffaa90,2);
                display.text(56,580,"CROSS OR CIRCLE TO RETURN",Muted,3);
            }
            if(!display.present()){sceKernelDebugOutText(0,"[za-randomizer] menu flip failed\n");if(threadStarted)pthread_join(thread,nullptr);display.close();return 1;}dirty=false;
        }
        usleep(10000);
    }
    heading(display,"STARTING YOUR RANDOMIZED RUN");display.text(56,260,"YOUR SAVE AND RANDOMIZED DATA ARE READY",Green,3);display.present();
    seedPipelineCache();setenv("LARECOMP_RANDO_SEED",selected.c_str(),1);unsetenv("LARECOMP_SAVE_DIR");
    char message[180];snprintf(message,sizeof message,"[za-randomizer] boot selected run=%s\n",selected.c_str());sceKernelDebugOutText(0,message);
    return display.close()?0:1;
}
}
extern "C" int za_randomizer_boot(){return za::native::bootMenu();}
