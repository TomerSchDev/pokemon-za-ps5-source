#include "cheat_policy.hpp"
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>
static std::string root;static bool failRename=false;
static std::string mapped(const char* path){
    const std::string p=path,prefix="/download0/zarecomp/rando/";
    assert(p.rfind(prefix,0)==0&&p.find("..") == std::string::npos);
    return root+"/"+p.substr(prefix.size());
}
extern "C" {
FILE* __real_fopen(const char*,const char*);
int __real_rename(const char*,const char*);
FILE* __wrap_fopen(const char* p,const char* mode){auto q=mapped(p);return __real_fopen(q.c_str(),mode);}
int __wrap_rename(const char* a,const char* b){if(failRename){errno=EIO;return -1;}auto x=mapped(a),y=mapped(b);return __real_rename(x.c_str(),y.c_str());}
int sceKernelDebugOutText(int,const char*){return 0;}
VKAPI_ATTR void VKAPI_CALL vkCmdClearAttachments(VkCommandBuffer,uint32_t,const VkClearAttachment*,uint32_t,const VkClearRect*){}
bool menu_handle_event(const SDL_Event*);
void za_cheats_init();
uint32_t za_cheat_spec_before(uint64_t);void za_cheat_spec_after(uint64_t,uint32_t);
uint32_t za_cheat_capture_score(uint32_t,uint64_t);
}
static void event(int b,bool down){SDL_Event e{};e.gbutton.type=down?SDL_EVENT_GAMEPAD_BUTTON_DOWN:SDL_EVENT_GAMEPAD_BUTTON_UP;e.gbutton.button=uint8_t(b);menu_handle_event(&e);}
static void click(int b){event(b,true);event(b,false);}
static void openMenu(){event(SDL_GAMEPAD_BUTTON_LEFT_STICK,true);event(SDL_GAMEPAD_BUTTON_RIGHT_STICK,true);event(SDL_GAMEPAD_BUTTON_LEFT_STICK,false);event(SDL_GAMEPAD_BUTTON_RIGHT_STICK,false);}
static void check(unsigned shiny,unsigned capture){
    std::array<uint8_t,256> p{};p[0x28]=1;uint64_t target=1;memcpy(p.data()+0x10,&target,8);
    auto token=za_cheat_spec_before(uint64_t(p.data()));assert(p[0x28]==za::native::cheats::trials(1,shiny));
    za_cheat_spec_after(uint64_t(p.data()),token);assert(p[0x28]==1);
    float score=30;uint32_t bits;memcpy(&bits,&score,4);
    assert(za_cheat_capture_score(bits,uint64_t(p.data()))==za::native::cheats::captureScore(bits,capture,false));
}
int main(int argc,char** argv){
    assert(argc==4);root=argv[1];std::string run=argv[2],mode=argv[3];
    std::filesystem::create_directories(root+"/"+run);setenv("LARECOMP_RANDO_SEED",run.c_str(),1);
    const std::string file=root+"/"+run+"/cheats.txt";
    if(mode=="corrupt"){
        auto* f=__real_fopen(file.c_str(),"wb");assert(f);fputs("za-cheats-v1\n999 999\n",f);fclose(f);
    }
    za_cheats_init();
    if(mode=="set"){
        check(0,0);openMenu();click(SDL_GAMEPAD_BUTTON_SOUTH);click(SDL_GAMEPAD_BUTTON_SOUTH);
        click(SDL_GAMEPAD_BUTTON_DPAD_DOWN);click(SDL_GAMEPAD_BUTTON_SOUTH);check(2,1);
    }else if(mode=="verify")check(2,1);
    else if(mode=="fail"){
        check(2,1);failRename=true;openMenu();click(SDL_GAMEPAD_BUTTON_SOUTH);check(3,1);
    }else if(mode=="default"||mode=="corrupt")check(0,0);
    else assert(false);
    printf("PASS: settings %s, run %s\n",mode.c_str(),run.c_str());
}
