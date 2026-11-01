#pragma once
#include <cstdint>
#include <string>
namespace za::native {
class Display {
    int video=-1,pad=-1,index=0;int64_t physical=-1,serial=0;void* memory=nullptr;
    uint32_t last=0,repeat=0;uint64_t repeatAt=0;
public:
    static constexpr int width=1280,height=720;
    bool open();bool close();void clear();
    void rect(int,int,int,int,uint32_t);
    void text(int,int,const std::string&,uint32_t=0xffedf5fc,int=3);
    bool present();uint32_t buttons();
    static uint64_t milliseconds();
};
constexpr uint32_t Up=0x10,Right=0x20,Down=0x40,Left=0x80,Triangle=0x1000,Circle=0x2000,Cross=0x4000,Square=0x8000;
}
