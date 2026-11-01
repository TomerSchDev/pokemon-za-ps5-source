// r27: r26p1 L3+R3 overlay, preserving SHINY / CAPTURE / FPS COUNTER / FPS TRIAL / RESET.
// The additions retained from r26p1 are:
//   - a live FPS readout in the top-right corner, drawn every frame while it is on (menu open or not):
//     "60 FPS", the frame time "16.7 MS" and the frame mode ("60 MODE", "30 MODE", "FALLBACK", "60 FORCED",
//     "DYN SAFE"). Updated every 15 presented frames (<= 4 clock reads a second at 60 FPS; the SDL ticks are the
//     TSC with ticks=tsc); the glyph rectangles are cached and re-encoded only when the text changes.
//   - a menu row "FPS COUNTER  ON/OFF" (default from perf-r24-options.txt fps=1 -> ZA_PERF_FPS_COUNTER=1,
//     persisted as a third field of the run's cheats.txt: "za-cheats-v2\n<shiny> <capture> <fps> <money_adds>\n";
//     v1 files with two fields still load).
//   - r26p1 restores FPS TRIAL: X requests r16's existing session-only 60 trial, or restores 30.
//   - MONEY: NORMAL / PLUS 10000 / PLUS 100000 / PLUS 1000000. X queues one bounded, session-only addition.
//     The verified game save callback consumes it; ADDED counts actual balance changes, not button presses.
//     Changing selection, NORMAL, or a save load/reset cancels an unconsumed request.
// The SHINY, CAPTURE and RESET rows keep cheats.cpp's logic unchanged (their indices move: RESET is last).
#include "cheat_policy.hpp"
#include "menu_font.h"
#include "za_money.h"
#include "za_items.h"
#include <cctype>
#include "hebrew_trial.h"
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>
#include <unistd.h>
extern "C" int sceKernelDebugOutText(int,const char*);
extern "C" uint64_t renderer_present_count(void);   // runtime/nvn/vulkan/device.c: frames presented so far
extern "C" int za_performance_status(void);         // port/performance-r16: 0 original (30), 1 trial (60), 2 fallback
extern "C" void za_performance_request(int trial);
namespace {
std::atomic<unsigned> shiny{0},capture{0},specs{0},catches{0};
std::atomic<bool> opened{false},releaseGate{false};
uint32_t held=0;bool combo=false;std::atomic<int> row{0};std::string settingsPath;std::atomic<bool> saved{true};
// r26p
std::atomic<bool> fpsCounter{false};               // the readout (FPS COUNTER row)
std::atomic<unsigned> moneyChoice{0};
std::atomic<unsigned> moneyAdds{0}; // legacy v2 persisted field, retained for backward compatibility only
std::atomic<bool> moneyRequestFailed{false};
bool forced60=false,dynActive=false;               // from the environment, once
std::atomic<unsigned> page{0},itemChoice{0},amountChoice{0};
constexpr unsigned itemAmounts[]={1,10,99,999};
constexpr int kRows=7;                             // SHINY, CAPTURE, MONEY, FPS COUNTER, FPS TRIAL, RESET
[[maybe_unused]] constexpr uint32_t kMoneyAmounts[4]={0,10000,100000,1000000};
void logSettings(){char s[220];snprintf(s,sizeof s,"[za-cheats] shiny_mode=%u capture_mode=%u changed_specs=%u changed_scores=%u fps_counter=%u money_adds=%u\n",shiny.load(),capture.load(),specs.load(),catches.load(),unsigned(fpsCounter.load()),moneyAdds.load());sceKernelDebugOutText(0,s);}
void saveSettings() {
    if(settingsPath.empty()){saved=false;return;}
    auto temp=settingsPath+".new";FILE* f=fopen(temp.c_str(),"wb");
    if(!f){saved=false;return;}
    bool ok=fprintf(f,"za-cheats-v2\n%u %u %u %u\n",shiny.load(),capture.load(),unsigned(fpsCounter.load()),moneyAdds.load())>0;
    if(fflush(f)||fsync(fileno(f)))ok=false;if(fclose(f))ok=false;
    saved=ok&&!rename(temp.c_str(),settingsPath.c_str());logSettings();
}
// Loads a v1 ("za-cheats-v1\n<shiny> <capture>") or v2 file. Unknown version / malformed: nothing changes.
void loadSettingsText(const char* text,unsigned& s,unsigned& c,unsigned& fps,unsigned& adds,bool& haveFps) {
    unsigned a=0,b=0,d=0,e=0;haveFps=false;
    if(sscanf(text,"za-cheats-v1\n%u %u",&a,&b)==2){if(a<=4&&b<=4){s=a;c=b;}return;}
    int n=sscanf(text,"za-cheats-v2\n%u %u %u %u",&a,&b,&d,&e);
    if(n>=2&&a<=4&&b<=4){s=a;c=b;if(n>=3&&d<=1){fps=d;haveFps=true;}if(n>=4)adds=e;}
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
    // The glyph cells of a string (menu_font.h: 5x7 cells, 6 advance). '.' is one cell on the baseline, 3 wide
    // (not in the font; the FPS readout's "16.7"). Other unknown characters advance only, as before.
    void encode(std::vector<VkClearRect>& pixels,int x,int y,const std::string& value,int scale) const {
        for(char c:value){
            if(c=='.'){pixels.push_back(rect(x+scale,y+6*scale,scale,scale));x+=3*scale;continue;}
            const MenuGlyph* found=nullptr;for(const auto& g:glyphs)if(g.character==c){found=&g;break;}
            if(found)for(int yy=0;yy<7;yy++)for(int xx=0;xx<5;xx++)if(found->rows[yy]&(1u<<(4-xx)))pixels.push_back(rect(x+xx*scale,y+yy*scale,scale,scale));
            x+=6*scale;
        }
    }
    void text(int x,int y,const std::string& value,int scale,uint32_t color) const {
        std::vector<VkClearRect> pixels;pixels.reserve(value.size()*20);encode(pixels,x,y,value,scale);draw(pixels,color);
    }
};
int textWidth(const std::string& value,int scale){int w=0;for(char c:value)w+=(c=='.'?3:6)*scale;return w>0?w-scale:0;}
// ---- the FPS readout (render thread only: menu_render)
struct FpsReadout {
    uint64_t lastFrame=0,lastNs=0;unsigned fpsX10=0,msX10=0;int mode=-1;
    std::string line1,line2,line3;std::vector<VkClearRect> cache[3];VkClearRect back{};uint32_t cw=0,ch=0;bool dirty=true;
    static std::string u2s(unsigned v){char b[16];snprintf(b,sizeof b,"%u",v);return b;}
    // Called once a frame. Reads the clock every 15 presented frames (4x a second at 60 FPS).
    void tick(){
        uint64_t frame=renderer_present_count();
        if(!lastNs){lastNs=SDL_GetTicksNS();lastFrame=frame;return;}
        if(frame-lastFrame<15)return;
        uint64_t now=SDL_GetTicksNS(),dt=now-lastNs;unsigned frames=unsigned(frame-lastFrame);
        lastNs=now;lastFrame=frame;
        if(dt==0||frames==0)return;
        unsigned f10=unsigned((uint64_t(frames)*10000000000ull+dt/2)/dt);       // FPS x10
        unsigned m10=unsigned((dt/frames+50000)/100000);                          // ms x10
        int m=forced60?-2:dynActive?-3:za_performance_status();
        if(f10!=fpsX10||m10!=msX10||m!=mode){fpsX10=f10;msX10=m10;mode=m;dirty=true;}
    }
    void layout(const Canvas& c){
        line1=u2s((fpsX10+5)/10)+" FPS";
        line2=u2s(msX10/10)+"."+u2s(msX10%10)+" MS";
        line3=mode==-2?"60 FORCED":mode==-3?"DYN SAFE":mode==1?"60 MODE":mode==2?"FALLBACK":"30 MODE";
        const int s1=3,s2=2,right=1280-16,top=16;
        int w1=textWidth(line1,s1),w2=textWidth(line2,s2),w3=textWidth(line3,s2);
        int wmax=std::max(w1,std::max(w2,w3));
        int y1=top,y2=y1+7*s1+6,y3=y2+7*s2+4,bottom=y3+7*s2;
        for(auto& v:cache)v.clear();
        c.encode(cache[0],right-w1,y1,line1,s1);c.encode(cache[1],right-w2,y2,line2,s2);c.encode(cache[2],right-w3,y3,line3,s2);
        back=c.rect(right-wmax-8,top-6,wmax+16,bottom-top+12);cw=c.w;ch=c.h;dirty=false;
    }
    void render(const Canvas& c){
        if(dirty||cw!=c.w||ch!=c.h)layout(c);
        c.draw({back},0x101e2d);c.draw(cache[0],0x54e3aa);c.draw(cache[1],0xedf5fc);c.draw(cache[2],mode==2?0xffce80:0x91a5bb);
    }
};
FpsReadout readout;
}
extern "C" void za_cheats_init() {
    za_items_reset(); page=0; itemChoice=0; amountChoice=0;
    za_money_lifecycle_reset(); moneyChoice=0; moneyRequestFailed=false;
    (void)za_hebrew_trial_status(); // one-time disk probe; render uses cached state
    const char* fpsEnv=getenv("ZA_PERF_FPS_COUNTER");bool fpsDefault=fpsEnv&&!strcmp(fpsEnv,"1");fpsCounter=fpsDefault;
    const char* f60=getenv("ZA_PERF_FORCE60");forced60=f60&&!strcmp(f60,"1");
    const char* dyn=getenv("ZA_DT_POLICY");dynActive=dyn&&*dyn;
    const char* id=getenv("LARECOMP_RANDO_SEED");if(!id){logSettings();return;}
    std::string run=id;if(run.empty()||run.size()>80){logSettings();return;}
    for(char c:run)if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='-')){logSettings();return;}
    settingsPath="/download0/zarecomp/rando/"+run+"/cheats.txt";
    FILE* f=fopen(settingsPath.c_str(),"rb");
    if(f){char text[96]={0};size_t n=fread(text,1,sizeof text-1,f);fclose(f);text[n]=0;
        unsigned s=shiny.load(),c=capture.load(),fps=unsigned(fpsCounter.load()),adds=0;bool haveFps=false;
        loadSettingsText(text,s,c,fps,adds,haveFps);shiny=s;capture=c;moneyAdds=adds;if(haveFps)fpsCounter=fps!=0;}
    sceKernelDebugOutText(0,"[za-cheats] native menu ready; L3+R3; defaults OFF; settings scoped to selected run; r27: FPS counter and FPS TRIAL preserved"
#ifdef ZA_MONEY_HOOK
        ", r27 MONEY live-object hook; one request at a time\n"
#else
        ", MONEY row not available; FPS TRIAL restored (r26p1)\n"
#endif
        );logSettings();
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
    if(b==SDL_GAMEPAD_BUTTON_LEFT_SHOULDER||b==SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER){page=1-page.load();row=0;return true;}
    if(page==1){
        if(b==SDL_GAMEPAD_BUTTON_DPAD_UP)row=(row.load()+kRows-1)%kRows;
        if(b==SDL_GAMEPAD_BUTTON_DPAD_DOWN)row=(row.load()+1)%kRows;
        if(row==0&&b==SDL_GAMEPAD_BUTTON_NORTH){itemChoice=(itemChoice.load()+10)%za_items_count();return true;}
        if(b==SDL_GAMEPAD_BUTTON_DPAD_LEFT||b==SDL_GAMEPAD_BUTTON_DPAD_RIGHT||b==SDL_GAMEPAD_BUTTON_SOUTH){
            int direction=b==SDL_GAMEPAD_BUTTON_DPAD_LEFT?-1:1;
            if(row==0)itemChoice=(itemChoice.load()+za_items_count()+direction)%za_items_count();
            if(row==1)amountChoice=(amountChoice.load()+4+direction)%4;
            if(row==2&&b==SDL_GAMEPAD_BUTTON_SOUTH){za_items_request(itemChoice.load(),itemAmounts[amountChoice.load()]);}
        }
        return true;
    }
    if(b==SDL_GAMEPAD_BUTTON_DPAD_UP)row=(row.load()+kRows-1)%kRows;
    if(b==SDL_GAMEPAD_BUTTON_DPAD_DOWN)row=(row.load()+1)%kRows;
    if(b==SDL_GAMEPAD_BUTTON_DPAD_LEFT||b==SDL_GAMEPAD_BUTTON_DPAD_RIGHT||b==SDL_GAMEPAD_BUTTON_SOUTH){
        int direction=b==SDL_GAMEPAD_BUTTON_DPAD_LEFT?-1:1;const int r=row.load();
        if(r==4){                                                          // FPS TRIAL: session only, no settings write
            if(b==SDL_GAMEPAD_BUTTON_SOUTH&&!forced60&&!dynActive)
                za_performance_request(za_performance_status()!=1);
            return true;
        }
        if(r==5){ // temporary localization; no cheat/settings/save write
            if(b==SDL_GAMEPAD_BUTTON_SOUTH && za_hebrew_trial_request()>0)closeMenu();
            return true;
        }
        if(r==6){shiny=0;capture=0;}                                        // RESET BOTH TO NORMAL (as before)
        else if(r==0||r==1){auto& setting=r==0?shiny:capture;setting=(setting.load()+5+direction)%5;}
        else if(r==3){fpsCounter=!fpsCounter.load();}                       // FPS COUNTER ON/OFF
        else if(r==2){                                                      // MONEY
#ifdef ZA_MONEY_HOOK
            if(b==SDL_GAMEPAD_BUTTON_SOUTH){uint32_t amount=kMoneyAmounts[moneyChoice.load()];
                if(amount){
                    // Repeated X while queued is not a new failed request. Keep
                    // the pending request's acknowledgment visible when it lands.
                    if(za_money_pending())return true;
                    bool accepted=za_money_set_enabled(1)&&za_money_request(amount); moneyRequestFailed=!accepted;
                    char s[128];snprintf(s,sizeof s,"[za-cheats] money request amount=%u accepted=%u applied=%u\n",amount,unsigned(accepted),za_money_applied());sceKernelDebugOutText(0,s);}
                else {za_money_set_enabled(0);moneyRequestFailed=false;}}
            else {moneyChoice=(moneyChoice.load()+4+direction)%4;moneyRequestFailed=false;
                // Changing the amount cancels a not-yet-consumed request. X alone queues it.
                za_money_set_enabled(0);}
            return true; // session-only request; never persist or replay it on restart
#else
            return true;  // not available: nothing to change, nothing to save
#endif
        }
        saveSettings();
    }
    return true;
}
extern "C" bool menu_is_open(){return opened.load();}
extern "C" bool menu_input_captured(){return opened.load()||releaseGate.load();}
extern "C" void menu_apply_window_requests(void* window){(void)window;}
extern "C" void menu_test_open(){opened=true;}
extern "C" void menu_render(void* command,uint32_t w,uint32_t h) {
    Canvas c{reinterpret_cast<VkCommandBuffer>(command),w,h};
    if(fpsCounter.load(std::memory_order_relaxed)){readout.tick();readout.render(c);}
    if(!opened.load())return;
    c.box(100,104,1080,512,0x101e2d);c.box(100,104,1080,5,0x54e3aa);
    c.text(136,140,"Z-A RANDOMIZER - CHEATS",4,0x54e3aa);
    if(page==1){
        const ZaItem* item=za_items_at(itemChoice.load());
        std::string name=item?item->name:"UNAVAILABLE";
        for(char& ch:name)ch=char(std::toupper(static_cast<unsigned char>(ch)));
        std::string label[]={"ITEM "+FpsReadout::u2s(itemChoice.load()+1)+"/"+FpsReadout::u2s(za_items_count())+"  "+name,
            "AMOUNT  "+FpsReadout::u2s(itemAmounts[amountChoice.load()])+"    CAP "+FpsReadout::u2s(item?item->cap:0),
            std::string("ADD ITEM - X  ")+za_items_status(),"ALPHA RATE  DISABLED","EXP MULTIPLIER  DISABLED","MEGA GAUGE  DISABLED","ENCOUNTER RATE  DISABLED"};
        for(int i=0;i<kRows;i++){int y=196+i*36;if(i==row)c.box(124,y,1032,32,0x24413e);c.text(144,y+5,label[i],3,i>=3?0x91a5bb:i==row?0x54e3aa:0xedf5fc);}
        const char* reason=row==3?"ALPHA: SPAWN READER AND CAUGHT FLAG NOT PROVEN":row==4?"EXP: THE GAME FORMULA HAS NOT BEEN VERIFIED":row==5?"MEGA: NO VERIFIED LIVE GAUGE HOOK":row==6?"ENCOUNTERS: NO VERIFIED SPAWN RATE HOOK":"ADD: CLOSE THIS MENU AND OPEN SATCHEL TO APPLY";
        c.text(136,462,reason,2,0xffce80);
        c.text(136,486,"OPEN SATCHEL ONCE TO ENABLE - SAVE IN GAME AFTER ADDING",2,0x91a5bb);
        c.text(136,510,"LEFT / RIGHT ITEM OR AMOUNT - TRIANGLE JUMPS 10 ITEMS",2,0x91a5bb);
        c.text(136,534,"ONE REQUEST AT A TIME - ITEM LIMITS FOLLOW THE GAME",2,0x91a5bb);
        c.text(136,562,"PAGE 2/2 - L1 / R1 PAGE - CIRCLE CLOSE",2,0xedf5fc);
        c.text(136,586,"R28 ITEMS - SESSION REQUESTS ARE NEVER REPLAYED",2,0x91a5bb);
        return;
    }
    const char* s[]={"NORMAL","4X ROLLS","16X ROLLS","64X ROLLS","ALWAYS SHINY"};
    const char* b[]={"NORMAL","2X SCORE","4X SCORE","8X SCORE","MAX SUCCESS SCORE"};
#ifdef ZA_MONEY_HOOK
    const char* m[]={"NORMAL","PLUS 10000","PLUS 100000","PLUS 1000000"};
    std::string money=std::string("MONEY  ")+m[moneyChoice.load()];
    if(za_money_pending())money+="  QUEUED - SAVE IN GAME";
    else if(!za_money_ready())money+="  LOAD SAVE FIRST";
    else if(moneyRequestFailed.load())money+="  X RETRY";
    else if(za_money_applied())money+="  ADDED "+FpsReadout::u2s(za_money_applied())+"X";
#else
    std::string money="MONEY  NOT AVAILABLE";
#endif
    int fpsMode=za_performance_status();
    std::string trial=std::string("FPS TRIAL  ")+(forced60||dynActive?"CONTROLLED BY CONFIG":
        fpsMode==1?"60 AUTO - X STOP":fpsMode==2?"30 FALLBACK - X RETRY":"30 - X START 60");
    int hebrewMode=za_hebrew_trial_status();
    std::string hebrew=std::string("HEBREW TRIAL  ")+(hebrewMode==1?"ON - X SWITCH OFF":hebrewMode==0?"OFF - X SWITCH ON":"PACK NOT AVAILABLE");
    std::string labels[]={std::string("SHINY  ")+s[shiny.load()],std::string("CAPTURE  ")+b[capture.load()],money,
                          std::string("FPS COUNTER  ")+(fpsCounter.load()?"ON":"OFF"),trial,hebrew,"RESET BOTH TO NORMAL"};
    for(int i=0;i<kRows;i++){int y=196+i*36;if(i==row)c.box(124,y,1032,32,0x24413e);c.text(144,y+5,labels[i],3,i==row?0x54e3aa:0xedf5fc);}
    c.text(136,462,"SHINY APPLIES TO NEWLY GENERATED POKEMON",2,0x91a5bb);
    c.text(136,486,"CAPTURE BOOST KEEPS THE TARGET ELIGIBILITY CHECK",2,0x91a5bb);
#ifdef ZA_MONEY_HOOK
    if(row==5)c.text(136,510,"HEBREW: SAVE FIRST - RELOADS LAST SAVED PROGRESS",2,0xffce80);
    else c.text(136,510,"MONEY  X QUEUES / SAVE IN GAME TO APPLY / NORMAL CANCELS",2,0x91a5bb);
#else
    c.text(136,510,"MONEY  THE GAME HOOK IS NOT IN THIS BUILD",2,0x91a5bb);
#endif
    c.text(136,534,"FPS TRIAL: SESSION ONLY / AUTO RETURN TO 30",2,0xffce80);
    c.text(136,562,"PAGE 1/2 - L1 / R1 PAGE - D-PAD SELECT - CIRCLE CLOSE",2,0xedf5fc);
    c.text(136,586,saved?"SETTINGS SAVED FOR THIS RUN":"COULD NOT SAVE - SETTINGS APPLY THIS SESSION",2,0x91a5bb);
}
#ifdef ZA_CHEATS_HOST_TEST  // host test hooks (port/perf-r26/test/test_cheats_r26.cpp)
extern "C" void za_cheats_test_load(const char* text,unsigned* s,unsigned* c,unsigned* fps,unsigned* adds,bool* haveFps){loadSettingsText(text,*s,*c,*fps,*adds,*haveFps);}
extern "C" unsigned za_cheats_test_fps_x10(unsigned frames,uint64_t dtNs){return unsigned((uint64_t(frames)*10000000000ull+dtNs/2)/dtNs);}
extern "C" unsigned za_cheats_test_ms_x10(unsigned frames,uint64_t dtNs){return unsigned((dtNs/frames+50000)/100000);}
extern "C" int za_cheats_test_text_width(const char* v,int scale){return textWidth(v,scale);}
#endif
