#include "cheat_policy.hpp"
#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include <array>
#include <cassert>
#include <cstdio>
extern "C" {
bool menu_handle_event(const SDL_Event*);bool menu_is_open();bool menu_input_captured();
void menu_render(void*,uint32_t,uint32_t);
uint32_t za_cheat_spec_before(uint64_t);void za_cheat_spec_after(uint64_t,uint32_t);
uint32_t za_cheat_capture_score(uint32_t,uint64_t);
int sceKernelDebugOutText(int,const char*){return 0;}
static unsigned rectCount=0;
VKAPI_ATTR void VKAPI_CALL vkCmdClearAttachments(VkCommandBuffer,uint32_t n,const VkClearAttachment* a,uint32_t count,const VkClearRect* r) {
    assert(n==1&&a->aspectMask==VK_IMAGE_ASPECT_COLOR_BIT);
    for(unsigned i=0;i<count;i++){assert(r[i].layerCount==1&&r[i].rect.offset.x>=0&&r[i].rect.offset.y>=0);
        assert(unsigned(r[i].rect.offset.x)+r[i].rect.extent.width<=1920&&unsigned(r[i].rect.offset.y)+r[i].rect.extent.height<=1080);}
    rectCount+=count;
}
}
static void event(int b,bool down){SDL_Event e{};e.gbutton.type=down?SDL_EVENT_GAMEPAD_BUTTON_DOWN:SDL_EVENT_GAMEPAD_BUTTON_UP;e.gbutton.button=uint8_t(b);menu_handle_event(&e);}
static void click(int b){event(b,true);event(b,false);}
static uint32_t bits(float x){uint32_t n;memcpy(&n,&x,4);return n;}
int main() {
    using namespace za::native::cheats;
    for(unsigned v=0;v<256;v++)for(unsigned m=0;m<6;m++) {
        auto x=trials(uint8_t(v),m);assert((!v||!m||m>3)?x==v:(x>=v&&x<=255));
    }
    for(uint32_t i=0;i<65536;i++) {
        uint32_t tid=i*1664525u+1013904223u,pid=(i*2654435761u)^0x5981af33;
        auto n=shinyPID(tid,pid);assert((n&65535)==(pid&65535));
        assert(((tid&65535)^(tid>>16)^(n&65535)^(n>>16))<16);
        assert(shinyPID(tid,n)==n);
    }
    assert(!menu_is_open()&&!menu_input_captured());
    event(SDL_GAMEPAD_BUTTON_LEFT_STICK,true);event(SDL_GAMEPAD_BUTTON_RIGHT_STICK,true);
    assert(menu_is_open()&&menu_input_captured());
    event(SDL_GAMEPAD_BUTTON_LEFT_STICK,false);event(SDL_GAMEPAD_BUTTON_RIGHT_STICK,false);
    std::array<uint8_t,256> memory{};memory[0x28]=100;auto original=memory;
    click(SDL_GAMEPAD_BUTTON_SOUTH); // 4x rolls
    auto token=za_cheat_spec_before(uint64_t(memory.data()));assert(memory[0x28]==255);
    za_cheat_spec_after(uint64_t(memory.data()),token);assert(memory==original);
    click(SDL_GAMEPAD_BUTTON_SOUTH);click(SDL_GAMEPAD_BUTTON_SOUTH);click(SDL_GAMEPAD_BUTTON_SOUTH); // ALWAYS
    uint32_t tid=0x19487652,pid=0x2388ffab;memcpy(memory.data()+0x18,&tid,4);memcpy(memory.data()+0x20,&pid,4);original=memory;
    token=za_cheat_spec_before(uint64_t(memory.data()));za_cheat_spec_after(uint64_t(memory.data()),token);
    uint32_t actual;memcpy(&actual,memory.data()+0x20,4);assert(actual==shinyPID(tid,pid));
    for(size_t i=0;i<memory.size();i++)if(i<0x20||i>=0x24)assert(memory[i]==original[i]);
    click(SDL_GAMEPAD_BUTTON_DPAD_DOWN);
    uint64_t target=123;memcpy(memory.data()+0x10,&target,8);memory[0x2e]=0;
    for(unsigned mode=1;mode<=4;mode++) {
        click(SDL_GAMEPAD_BUTTON_SOUTH);
        for(float score:{-2.f,0.f,1.f,35.f,127.5f,254.f,255.f}) {
            assert(za_cheat_capture_score(bits(score),uint64_t(memory.data()))==captureScore(bits(score),mode,false));
            memory[0x2e]=1;assert(za_cheat_capture_score(bits(score),uint64_t(memory.data()))==bits(score));memory[0x2e]=0;
        }
    }
    menu_render(reinterpret_cast<void*>(uintptr_t(1)),1920,1080);assert(rectCount>1000);
    SDL_Event quit{};quit.type=SDL_EVENT_QUIT;assert(!menu_handle_event(&quit));
    event(SDL_GAMEPAD_BUTTON_EAST,true);assert(!menu_is_open()&&menu_input_captured());
    event(SDL_GAMEPAD_BUTTON_EAST,false);assert(!menu_input_captured());
    puts("PASS: 65536 shiny PIDs; bounded rolls; score boosts/zero/blocked preservation; actual menu chord/navigation/release gate and draw bounds");
}
