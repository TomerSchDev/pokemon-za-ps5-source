// VideoOut tiling/presentation follows PS5_Vulkan's GPL-3.0-or-later demo_renderer.cpp.
// Native menu resources are released before the game's Vulkan WSI is initialized.
#include "menu_display.hpp"
#include "menu_font.h"
#include <ps5platform/videoout.h>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <unistd.h>
extern "C" {
int64_t sceKernelGetDirectMemorySize();
int sceKernelAllocateDirectMemory(int64_t,int64_t,size_t,size_t,int,int64_t*);
int sceKernelMapDirectMemory(void**,size_t,int,int,int64_t,size_t);
int sceKernelMunmap(void*,size_t);
int sceKernelReleaseDirectMemory(int64_t,size_t);
int sceSystemServiceHideSplashScreen();
int sceUserServiceInitialize(void*);int sceUserServiceGetForegroundUser(int*);
int scePadInit();int scePadOpen(int,int,int,const void*);int scePadClose(int);int scePadReadState(int,void*);
int sceKernelDebugOutText(int,const char*);
}
namespace za::native {
// Keep the UI in 1280x720 logical coordinates and present at the 1920x1080
// size already verified by the native demo/VideoOut implementation.
static constexpr int physicalWidth=1920,physicalHeight=1080;
static constexpr size_t frameBytes=16u<<20,memoryBytes=frameBytes*2;
static size_t tiled(unsigned x,unsigned y) {
    uint32_t o=((y<<4)&0x70)^((y<<5)&0xf00)^((y<<9)&0x1000)^((y<<8)&0x4000)^((x<<2)&0xc)^((x<<5)&0x380)^((x<<4)&0x400)^((x<<6)&0x800)^((x<<9)&0xa000);
    return size_t((y>>7)*((physicalWidth+127)>>7)+(x>>7))*65536+o;
}
uint64_t Display::milliseconds() {timespec ts{};clock_gettime(CLOCK_MONOTONIC,&ts);return uint64_t(ts.tv_sec)*1000+ts.tv_nsec/1000000;}
bool Display::open() {
    video=sceVideoOutOpen(0xff,0,0,nullptr);if(video<0)return false;
    if(sceKernelAllocateDirectMemory(0,sceKernelGetDirectMemorySize(),memoryBytes,0x200000,3,&physical)<0)return false;
    if(sceKernelMapDirectMemory(&memory,memoryBytes,0x33,0,physical,0x200000)<0)return false;
    memset(memory,0,memoryBytes);
    ps5_video_out_buffer buffers[2]={{memory,nullptr,{nullptr,nullptr}},
        {static_cast<unsigned char*>(memory)+frameBytes,nullptr,{nullptr,nullptr}}};
    alignas(16) unsigned char attributes[80]{};
    sceVideoOutSetBufferAttribute2(attributes,PS5_VIDEO_OUT_PIXEL_FORMAT_B8G8R8A8_SDR,0,physicalWidth,physicalHeight,0,0,0);
    if(sceVideoOutRegisterBuffers2(video,0,0,buffers,2,attributes,0,nullptr)<0)return false;
    sceVideoOutSetFlipRate(video,0);
    int user=-1;sceUserServiceInitialize(nullptr);if(sceUserServiceGetForegroundUser(&user))return false;
    scePadInit();pad=scePadOpen(user,0,0,nullptr);if(pad<0)return false;
    sceSystemServiceHideSplashScreen();
    sceKernelDebugOutText(0,"[za-randomizer] native controller menu opened\n");return true;
}
void Display::rect(int x,int y,int w,int h,uint32_t color) {
    if(!memory)return;
    auto* frame=static_cast<unsigned char*>(memory)+frameBytes*index;
    int right=x+w,bottom=y+h;if(right>width)right=width;if(bottom>height)bottom=height;
    if(x<0)x=0;if(y<0)y=0;
    x=x*3/2;y=y*3/2;right=right*3/2;bottom=bottom*3/2;
    for(int yy=y;yy<bottom;yy++)for(int xx=x;xx<right;xx++)*reinterpret_cast<uint32_t*>(frame+tiled(xx,yy))=color;
}
void Display::clear(){rect(0,0,width,height,0xff0b1524);rect(0,0,12,height,0xff54e3aa);}
void Display::text(int x,int y,const std::string& value,uint32_t color,int scale) {
    const int origin=x;
    for(unsigned char ch:value) {
        if(ch=='\n'){y+=9*scale;x=origin;continue;}
        if(ch>=128)continue;char c=char(std::toupper(ch));const MenuGlyph* found=nullptr;
        for(const auto& g:glyphs)if(g.character==c){found=&g;break;}
        if(found){for(int row=0;row<7;row++)for(int col=0;col<5;col++)if(found->rows[row]&(1<<(4-col)))rect(x+col*scale,y+row*scale,scale,scale,color);}
        else if(c=='-')rect(x,y+3*scale,5*scale,scale,color);
        else if(c=='.')rect(x+2*scale,y+6*scale,scale,scale,color);
        else if(c==':'){rect(x+2*scale,y+2*scale,scale,scale,color);rect(x+2*scale,y+5*scale,scale,scale,color);}
        else if(c=='/')for(int row=0;row<7;row++)rect(x+(4-row*4/6)*scale,y+row*scale,scale,scale,color);
        x+=6*scale;if(x+5*scale>=width)break;
    }
}
bool Display::present() {
    auto* frame=static_cast<unsigned char*>(memory)+frameBytes*index;
    for(size_t i=0;i<frameBytes;i+=64)__asm__ volatile("clflush (%0)"::"r"(frame+i):"memory");
    __asm__ volatile("mfence":::"memory");
    if(sceVideoOutSubmitFlip(video,index,1,++serial)<0)return false;
    const auto end=milliseconds()+2000;bool shown=false;
    while(milliseconds()<end) {uint64_t status[16]{};if(!sceVideoOutGetFlipStatus(video,status)&&int64_t(status[3])>=serial){shown=true;break;}usleep(1000);}
    index^=1;return shown;
}
uint32_t Display::buttons() {
    alignas(16) unsigned char data[256]{};
    if(scePadReadState(pad,data))return 0;
    uint32_t now=0;int connected=0;memcpy(&now,data,4);memcpy(&connected,data+0x4c,4);
    if(!connected||(now&0x80000000)){last=repeat=0;return 0;}
    uint32_t pressed=now&~last;last=now;uint32_t dirs=now&(Up|Down|Left|Right);auto ms=milliseconds();
    if(dirs!=repeat){repeat=dirs;repeatAt=ms+400;}
    else if(dirs&&ms>=repeatAt){pressed|=dirs;repeatAt=ms+110;}
    return pressed;
}
bool Display::close() {
    if(pad>=0){scePadClose(pad);pad=-1;}
    if(video>=0){
        const auto end=milliseconds()+2000;while(sceVideoOutIsFlipPending(video)>0&&milliseconds()<end)usleep(1000);
        (void)sceVideoOutUnregisterBuffers(video,0);
        if(sceVideoOutClose(video)<0)return false;video=-1;
    }
    if(memory){sceKernelMunmap(memory,memoryBytes);memory=nullptr;}
    if(physical>=0){sceKernelReleaseDirectMemory(physical,memoryBytes);physical=-1;}
    sceKernelDebugOutText(0,"[za-randomizer] native menu display released for Vulkan\n");return true;
}
}
