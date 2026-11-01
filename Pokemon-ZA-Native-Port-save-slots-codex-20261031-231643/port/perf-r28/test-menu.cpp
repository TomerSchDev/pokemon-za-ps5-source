#include <SDL3/SDL.h>
#include <vulkan/vulkan.h>
#include "za_items.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <vector>
static unsigned requests,indexValue,amountValue,hebrewRequests,performanceRequests;
static bool pending;
static const ZaItem items[]={
#include "items.inc"
};
extern "C" {
int sceKernelDebugOutText(int,const char*){return 0;}
uint64_t renderer_present_count(){return 0;}
int za_performance_status(){return 0;}
void za_performance_request(int){++performanceRequests;}
Uint64 SDL_GetTicksNS(){return 0;}
void vkCmdClearAttachments(VkCommandBuffer,uint32_t,const VkClearAttachment*,uint32_t n,const VkClearRect *r){
 for(unsigned i=0;i<n;++i){assert(r[i].rect.offset.x>=0&&r[i].rect.offset.y>=0);assert(r[i].rect.offset.x+int(r[i].rect.extent.width)<=1280);assert(r[i].rect.offset.y+int(r[i].rect.extent.height)<=720);}
}
unsigned za_items_count(){return sizeof(items)/sizeof(items[0]);}
const ZaItem *za_items_at(unsigned i){return i<za_items_count()?&items[i]:nullptr;}
int za_items_request(unsigned i,unsigned a){if(pending)return 0;++requests;indexValue=i;amountValue=a;pending=true;return 1;}
void za_items_reset(){pending=false;}
int za_items_ready(){return 1;}
int za_items_pending(){return pending;}
const char *za_items_status(){return pending?"QUEUED - OPEN BAG":"READY";}
unsigned za_items_last_count(){return 0;}
unsigned za_items_applied(){return requests;}
int za_hebrew_trial_status(){return 1;}
int za_hebrew_trial_request(){++hebrewRequests;return 1;}
void za_cheats_init();void menu_test_open();bool menu_handle_event(const SDL_Event*);bool menu_is_open();void menu_render(void*,uint32_t,uint32_t);
}
static void press(int b){SDL_Event e{};e.gbutton.button=b;e.type=SDL_EVENT_GAMEPAD_BUTTON_DOWN;menu_handle_event(&e);e.type=SDL_EVENT_GAMEPAD_BUTTON_UP;menu_handle_event(&e);}
int main(){
 za_cheats_init();menu_test_open();menu_render(nullptr,1280,720);
 press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER);menu_render(nullptr,1280,720);
 press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);press(SDL_GAMEPAD_BUTTON_NORTH);
 press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);
 press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);press(SDL_GAMEPAD_BUTTON_SOUTH);
 assert(requests==1&&indexValue==11&&amountValue==99);
 press(SDL_GAMEPAD_BUTTON_SOUTH);assert(requests==1);menu_render(nullptr,1280,720);
 for(int i=0;i<4;++i){press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);press(SDL_GAMEPAD_BUTTON_SOUTH);menu_render(nullptr,1280,720);}
 assert(requests==1&&hebrewRequests==0&&performanceRequests==0);
 press(SDL_GAMEPAD_BUTTON_LEFT_SHOULDER);
 for(int i=0;i<4;++i)press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);
 press(SDL_GAMEPAD_BUTTON_SOUTH);assert(performanceRequests==1);
 press(SDL_GAMEPAD_BUTTON_DPAD_DOWN);press(SDL_GAMEPAD_BUTTON_SOUTH);assert(hebrewRequests==1&&!menu_is_open());
 menu_test_open();press(SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER); // page resets selection to ITEM
 for(unsigned i=0;i<za_items_count();++i){menu_render(nullptr,1280,720);press(SDL_GAMEPAD_BUTTON_DPAD_RIGHT);}
 puts("PASS: two pages, 199 item layouts, quantity/request binding, pending suppression, disabled rows, retained FPS and Hebrew buttons");
}
