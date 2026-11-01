#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
namespace za::native::cheats {
inline uint8_t trials(uint8_t original,unsigned mode) {
    if(mode<1||mode>3||!original)return original;
    return uint8_t(std::min(255u,unsigned(original)*(1u<<(2*mode))));
}
inline uint32_t shinyPID(uint32_t tid,uint32_t pid) {
    const auto xorValue=(tid&65535u)^(tid>>16)^(pid&65535u)^(pid>>16);
    return xorValue<16?pid:(pid&65535u)|(((tid&65535u)^(tid>>16)^(pid&65535u))<<16);
}
inline uint32_t captureScore(uint32_t bits,unsigned mode,bool blocked) {
    float score;std::memcpy(&score,&bits,4);
    if(!mode||mode>4||blocked||!std::isfinite(score)||score<=0)return bits;
    score=mode==4?255.f:std::min(255.f,score*float(1u<<mode));
    std::memcpy(&bits,&score,4);return bits;
}
}
