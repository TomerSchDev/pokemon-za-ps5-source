#include "za_money.h"
#include <atomic>
#include <cstring>
#include <limits>
#ifdef ZA_MONEY_TRACE
#include <cstdio>
#endif

namespace {
constexpr uint32_t kMax = 9999999;
constexpr uint64_t kAmount = 0x00ffffffull;
constexpr uint64_t kReady = 1ull << 24, kEnabled = 1ull << 25;
constexpr uint64_t kGeneration = 1ull << 32, kEpochMask = 0xffffffff00000000ull;
std::atomic<uint64_t> state{0};
std::atomic<uint32_t> applied{0}, rejected{0}, lastValue{0};
std::atomic_flag consumer = ATOMIC_FLAG_INIT;
struct ReleaseConsumer { ~ReleaseConsumer() { consumer.clear(std::memory_order_release); } };
static_assert(std::atomic<uint64_t>::is_always_lock_free, "lock-free mailbox required");
bool validAddress(uint64_t object) {
    return object >= 0x10000 && (object & 3) == 0 &&
           object <= uint64_t(std::numeric_limits<uintptr_t>::max()) - 0x44;
}
}

extern "C" void za_money_lifecycle_reset(void) {
#ifdef ZA_MONEY_TRACE
    std::fprintf(stderr,"[r27-money] lifecycle reset\n"); std::fflush(stderr);
#endif
    uint64_t old = state.load(std::memory_order_acquire);
    while (!state.compare_exchange_weak(old, (old + kGeneration) & kEpochMask,
                                        std::memory_order_acq_rel)) {}
    // No live object pointer is ever retained. Load/Reset invalidate old requests
    // and return to OFF; a later successful lookup establishes readiness anew.
}
extern "C" int za_money_set_enabled(int enabled) {
    if (!enabled) {
        state.fetch_and(~(kEnabled | kAmount), std::memory_order_acq_rel);
        return 1;
    }
    uint64_t old = state.load(std::memory_order_acquire);
    if (!(old & kReady)) return 0;
    return state.compare_exchange_strong(old, old | kEnabled, std::memory_order_acq_rel);
}
extern "C" int za_money_request(uint32_t amount) {
    if (amount != 10000 && amount != 100000 && amount != 1000000) return 0;
    uint64_t old = state.load(std::memory_order_acquire);
    if ((old & (kReady | kEnabled)) != (kReady | kEnabled) || (old & kAmount)) return 0;
    return state.compare_exchange_strong(old, old | amount, std::memory_order_acq_rel);
}
extern "C" uint32_t za_money_pending(void) { return uint32_t(state.load() & kAmount); }
extern "C" int za_money_ready(void) { return (state.load() & kReady) != 0; }
extern "C" int za_money_enabled(void) { return (state.load() & kEnabled) != 0; }
extern "C" uint32_t za_money_applied(void) { return applied.load(); }
extern "C" uint32_t za_money_last_value(void) { return lastValue.load(); }
extern "C" uint32_t za_money_rejected(void) { return rejected.load(); }

extern "C" void za_cheat_money_component(uint64_t object) {
    // Different guest threads can perform lookups. Never read a stale balance
    // concurrently with another hook's read/modify/write; contention skips this
    // lookup and leaves any unconsumed request for the next one.
    if (consumer.test_and_set(std::memory_order_acquire)) return;
    ReleaseConsumer release;
    // Called synchronously at exact money Load/Get/Save sites or after its
    // type-checked lookup. The game's own access establishes object identity
    // and lifetime. These checks are not a general pointer validator.
    if (!validAddress(object)) { za_money_lifecycle_reset(); return; }
    auto* field = reinterpret_cast<unsigned char*>(uintptr_t(object)) + 0x40;
    uint32_t before;
    std::memcpy(&before, field, sizeof before);
    if (before > kMax) { rejected.fetch_add(1); za_money_lifecycle_reset(); return; }
    uint64_t old = state.fetch_or(kReady, std::memory_order_acq_rel);
#ifdef ZA_MONEY_TRACE
    if (!(old & kReady)) { std::fprintf(stderr,"[r27-money] ready object=0x%llx value=%u\n",static_cast<unsigned long long>(object),before); std::fflush(stderr); }
#endif
    old |= kReady;
    lastValue.store(before, std::memory_order_relaxed);
    if (!(old & kEnabled) || !(old & kAmount)) return;
    const uint32_t amount = uint32_t(old & kAmount);
    // A single CAS consumes the request. Cancellation, a lifecycle change, or a
    // concurrent consumer wins by making this CAS fail; retry at a later lookup.
    if (!state.compare_exchange_strong(old, old & ~kAmount, std::memory_order_acq_rel)) return;
    const uint64_t sum = uint64_t(before) + amount;
    const uint32_t after = sum > kMax ? kMax : uint32_t(sum);
    if (after != before) {
        std::memcpy(field, &after, sizeof after);
        applied.fetch_add(1, std::memory_order_relaxed);
    }
    lastValue.store(after, std::memory_order_relaxed);
#ifdef ZA_MONEY_TRACE
    std::fprintf(stderr, "[r27-money] object=0x%llx before=%u request=%u after=%u applied=%u\n",
                 static_cast<unsigned long long>(object), before, amount, after, applied.load());
    std::fflush(stderr);
#endif
}
