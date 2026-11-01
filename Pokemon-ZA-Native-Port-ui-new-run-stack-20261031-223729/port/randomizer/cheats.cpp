#include "cheat_policy.hpp"
#include "menu_font.h"
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
#include <unistd.h>
extern "C" int sceKernelDebugOutText(int,const char*);
namespace {
std::atomic<unsigned> shiny{0},capture{0},specs{0},catches{0};
std::atomic<bool> opened{false},releaseGate{false};
uint32_t held=0;bool combo=false;std::atomic<int> row{0};std::string settingsPath;std::atomic<bool> saved{true};
void logSettings(){char s[180];snprintf(s,sizeof s,"[za-cheats] shiny_mode=%u capture_mode=%u changed_specs=%u changed_scores=%u\n",shiny.load(),capture.load(),specs.load(),catches.load());sceKernelDebugOutText(0,s);}
void saveSettings() {
    if(settingsPath.empty()){saved=false;return;}
    auto temp=settingsPath+".new";FILE* f=fopen(temp.c_str(),"wb");
    if(!f){saved=false;return;}
    bool ok=fprintf(f,"za-cheats-v1\n%u %u\n",shiny.load(),capture.load())>0;
    if(fflush(f)||fsync(fileno(f)))ok=false;if(fclose(f))ok=false;
    saved=ok&&!rename(temp.c_str(),settingsPath.c_str());logSettings();
}
void closeMenu(){opened=false;releaseGate=true;logSettings();}
struct Canvas {
    VkCommandBuffer cb;uint32_t w,h;
    VkClearRect rect(int x,int y,int rw,int rh) const {
        VkClearRect r{};r.rect.offset={int32_t(int64_t(x)*w/1280),int32_t(int64_t(y)*h/720)};
        r.rect.extent={uint32_t(int64_t(rw)*w/1280),uint32_t(int64_t(rh)*h/720)};r.layerCount=1;return r;
    }
    void draw(const std::vector<VkClearRect>& rects,uint32_t color) const {
        if(rects.empty())return;VkClearAttachment a{};a.aspectMask=VK_IMAGE_ASPECT_COLOR_BIT;a.colorAttachment=0;
        a.clearValue.color.float32[0]=float((color>>16)&255)/255.f;
        a.clearValue.color.float32[1]=float((color>>8)&255)/255.f;
        a.clearValue.color.float32[2]=float(color&255)/255.f;a.clearValue.color.float32[3]=1.f;
        vkCmdClearAttachments(cb,1,&a,uint32_t(rects.size()),rects.data());
    }
    void box(int x,int y,int rw,int rh,uint32_t color) const {draw({rect(x,y,rw,rh)},color);}
    void text(int x,int y,const std::string& value,int scale,uint32_t color) const {
        std::vector<VkClearRect> pixels;pixels.reserve(value.size()*20);
        for(char c:value){const MenuGlyph* found=nullptr;for(const auto& g:glyphs)if(g.character==c){found=&g;break;}
            if(found)for(int yy=0;yy<7;yy++)for(int xx=0;xx<5;xx++)if(found->rows[yy]&(1u<<(4-xx)))pixels.push_back(rect(x+xx*scale,y+yy*scale,scale,scale));
            x+=6*scale;
        }draw(pixels,color);
    }
};
}
extern "C" void za_cheats_init() {
    const char* id=getenv("LARECOMP_RANDO_SEED");if(!id)return;
    std::string run=id;if(run.empty()||run.size()>80)return;
    for(char c:run)if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-'))return;
    settingsPath="/download0/zarecomp/rando/"+run+"/cheats.txt";
    FILE* f=fopen(settingsPath.c_str(),"rb");if(f){unsigned s=0,c=0;if(fscanf(f,"za-cheats-v1\n%u %u",&s,&c)==2&&s<=4&&c<=4){shiny=s;capture=c;}fclose(f);}
    sceKernelDebugOutText(0,"[za-cheats] native menu ready; L3+R3; defaults OFF; settings scoped to selected run\n");logSettings();
}
extern "C" uint32_t za_cheat_spec_before(uint64_t ptr) {
    if(!ptr)return 0;auto* p=reinterpret_cast<uint8_t*>(uintptr_t(ptr));
    uint8_t old=p[0x28],next=za::native::cheats::trials(old,shiny.load(std::memory_order_relaxed));p[0x28]=next;
    return uint32_t(old)|(uint32_t(next)<<8);
}
extern "C" void za_cheat_spec_after(uint64_t ptr,uint32_t token) {
    if(!ptr)return;auto* p=reinterpret_cast<uint8_t*>(uintptr_t(ptr));
    if(p[0x28]==uint8_t(token>>8))p[0x28]=uint8_t(token);
    if(shiny.load(std::memory_order_relaxed)==4){uint32_t tid,pid;memcpy(&tid,p+0x18,4);memcpy(&pid,p+0x20,4);
        uint32_t next=za::native::cheats::shinyPID(tid,pid);memcpy(p+0x20,&next,4);specs.fetch_add(next!=pid,std::memory_order_relaxed);}
}
extern "C" uint32_t za_cheat_capture_score(uint32_t bits,uint64_t ptr) {
    if(!ptr)return bits;auto* p=reinterpret_cast<const uint8_t*>(uintptr_t(ptr));
    uint64_t target;memcpy(&target,p+0x10,8);
    auto next=za::native::cheats::captureScore(bits,capture.load(std::memory_order_relaxed),p[0x2e]!=0||!target);
    if(next!=bits)catches.fetch_add(1,std::memory_order_relaxed);return next;
}
extern "C" bool menu_handle_event(const SDL_Event* e) {
    bool wasOpen=opened.load(),wasGate=releaseGate.load();
    if(e->type==SDL_EVENT_GAMEPAD_REMOVED){opened=false;releaseGate=false;held=0;combo=false;return false;}
    if(e->type!=SDL_EVENT_GAMEPAD_BUTTON_DOWN&&e->type!=SDL_EVENT_GAMEPAD_BUTTON_UP)return false;
    if(e->gbutton.button>=32)return wasOpen||wasGate;
    uint32_t bit=1u<<e->gbutton.button;bool down=e->type==SDL_EVENT_GAMEPAD_BUTTON_DOWN;
    if(down)held|=bit;else held&=~bit;
    constexpr uint32_t chord=(1u<<SDL_GAMEPAD_BUTTON_LEFT_STICK)|(1u<<SDL_GAMEPAD_BUTTON_RIGHT_STICK);
    bool nowCombo=(held&chord)==chord;
    if(nowCombo&&!combo){if(wasOpen)closeMenu();else{opened=true;releaseGate=true;sceKernelDebugOutText(0,"[za-cheats] overlay opened\n");}}
    combo=nowCombo;if(!held)releaseGate=false;
    if(!down||!wasOpen||nowCombo)return wasOpen||wasGate||opened.load();
    const int b=e->gbutton.button;
    if(b==SDL_GAMEPAD_BUTTON_EAST){closeMenu();return true;}
    if(b==SDL_GAMEPAD_BUTTON_DPAD_UP)row=(row.load()+2)%3;
    if(b==SDL_GAMEPAD_BUTTON_DPAD_DOWN)row=(row.load()+1)%3;
    if(b==SDL_GAMEPAD_BUTTON_DPAD_LEFT||b==SDL_GAMEPAD_BUTTON_DPAD_RIGHT||b==SDL_GAMEPAD_BUTTON_SOUTH){
        int direction=b==SDL_GAMEPAD_BUTTON_DPAD_LEFT?-1:1;
        if(row==2){shiny=0;capture=0;}else{auto& setting=row==0?shiny:capture;setting=(setting.load()+5+direction)%5;}
        saveSettings();
    }
    return true;
}
extern "C" bool menu_is_open(){return opened.load();}
extern "C" bool menu_input_captured(){return opened.load()||releaseGate.load();}
extern "C" void menu_apply_window_requests(void* window){(void)window;}
extern "C" void menu_test_open(){opened=true;}
extern "C" void menu_render(void* command,uint32_t w,uint32_t h) {
    if(!opened.load())return;Canvas c{reinterpret_cast<VkCommandBuffer>(command),w,h};
    c.box(100,104,1080,512,0x101e2d);c.box(100,104,1080,5,0x54e3aa);
    c.text(136,140,"Z-A RANDOMIZER - CHEATS",4,0x54e3aa);
    const char* s[]={"NORMAL","4X ROLLS","16X ROLLS","64X ROLLS","ALWAYS SHINY"};
    const char* b[]={"NORMAL","2X SCORE","4X SCORE","8X SCORE","MAX SUCCESS SCORE"};
    std::string labels[]={std::string("SHINY  ")+s[shiny.load()],std::string("CAPTURE  ")+b[capture.load()],"RESET BOTH TO NORMAL"};
    for(int i=0;i<3;i++){if(i==row)c.box(124,211+i*68,1032,51,0x24413e);c.text(144,225+i*68,labels[i],3,i==row?0x54e3aa:0xedf5fc);}
    c.text(136,436,"SHINY APPLIES TO NEWLY GENERATED POKEMON",2,0x91a5bb);
    c.text(136,464,"CAPTURE BOOST KEEPS THE TARGET ELIGIBILITY CHECK",2,0x91a5bb);
    c.text(136,492,"THE WORLD KEEPS RUNNING WHILE THIS MENU IS OPEN",2,0xffce80);
    c.text(136,539,"D-PAD SELECT / CHANGE   CIRCLE CLOSE   L3+R3 TOGGLE",2,0xedf5fc);
    c.text(136,578,saved?"SETTINGS SAVED FOR THIS RUN":"COULD NOT SAVE - SETTINGS APPLY THIS SESSION",2,0x91a5bb);
}
