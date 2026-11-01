#include "za_money.h"
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
int main() {
    alignas(16) std::array<unsigned char, 128> object{};
    object.fill(0xa5);
    uint32_t value=2345; std::memcpy(object.data()+0x40,&value,4);
    const auto original=object;
    auto ptr=uint64_t(uintptr_t(object.data()));
    auto get=[&](){uint32_t v; std::memcpy(&v,object.data()+0x40,4);return v;};
    auto set=[&](uint32_t v){std::memcpy(object.data()+0x40,&v,4);};
    assert(!za_money_set_enabled(1)); assert(!za_money_request(10000));
    za_cheat_money_component(ptr); assert(object==original); assert(za_money_ready());
    assert(za_money_set_enabled(1)); assert(!za_money_request(1)); assert(!za_money_request(0xffffffff));
    assert(za_money_request(10000)); assert(!za_money_request(10000));
    za_cheat_money_component(ptr); assert(get()==12345); assert(za_money_applied()==1);
    za_cheat_money_component(ptr); assert(get()==12345); assert(!za_money_pending());
    assert(za_money_request(100000)); za_money_set_enabled(0); za_cheat_money_component(ptr); assert(get()==12345);
    assert(za_money_set_enabled(1)); assert(za_money_request(1000000));
    za_money_lifecycle_reset(); za_cheat_money_component(ptr); assert(!za_money_enabled()); assert(get()==12345);
    set(9999998); assert(za_money_set_enabled(1)); assert(za_money_request(10000));
    za_cheat_money_component(ptr); assert(get()==9999999); assert(za_money_applied()==2);
    assert(za_money_request(10000)); za_cheat_money_component(ptr); assert(za_money_applied()==2);
    set(10000000); assert(za_money_request(10000)); za_cheat_money_component(ptr);
    assert(get()==10000000); assert(!za_money_ready()); assert(!za_money_pending()); assert(za_money_rejected()==1);
    set(2345); za_cheat_money_component(ptr); assert(za_money_set_enabled(1)); assert(za_money_request(10000));
    za_cheat_money_component(0); assert(!za_money_pending()); assert(!za_money_ready());
    za_cheat_money_component(1); za_cheat_money_component(UINT64_MAX);
    for(size_t i=0;i<object.size();++i) if(i<0x40||i>=0x44) assert(object[i]==original[i]);
    za_cheat_money_component(ptr); assert(za_money_set_enabled(1));
    std::vector<std::thread> producers; std::atomic<unsigned> accepted{0};
    for(unsigned i=0;i<16;++i) producers.emplace_back([&](){accepted+=za_money_request(10000);});
    for(auto& t:producers)t.join(); assert(accepted==1); assert(za_money_pending()==10000);
    za_cheat_money_component(ptr); assert(get()==12345);
    set(0); const auto startApplied=za_money_applied(); std::atomic<bool> done{false};
    producers.clear();
    for(unsigned i=0;i<4;++i) producers.emplace_back([&](){while(!done) za_cheat_money_component(ptr);});
    for(unsigned i=0;i<500;++i) while(!za_money_request(10000)) std::this_thread::yield();
    while(za_money_pending()) std::this_thread::yield();
    done=true; for(auto& t:producers)t.join();
    assert(get()==5000000); assert(za_money_applied()-startApplied==500);
    std::puts("PASS: OFF identity; bounded one-shot; cancel; lifecycle; cap; invalid value; null; 16 producers; neighbor bytes");
}
