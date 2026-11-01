/* Executes the real translated getter, setter and map lookup, using synthetic
 * flag maps and redirected singleton/descriptor loads. No game/save data. */
#include "cpu.h"
#include "simd.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned ready, setter_calls, getter_calls, descriptor_ok = 1;
static unsigned hook_calls;
static uint64_t slot;
static uint8_t manager[0x200] __attribute__((aligned(16)));
static uint8_t node[0x20] __attribute__((aligned(16)));
static uint8_t other_node[0x20] __attribute__((aligned(16)));
static uint64_t predecessor, bucket;
static const uint64_t target_hash = 0x58e63b00d271631full;

static uint64_t rd64(uint64_t a) {
    if (a == 0x7003ec3328ull) return slot;
    if (a == 0x7003e26880ull) return descriptor_ok ? target_hash : 0;
    assert(!(a >= 0x7000000000ull && a < 0x7008000000ull));
    return *(const u64u *)(uintptr_t)a;
}
static uint32_t rd32(uint64_t a) {
    if (a == 0x700610e100ull) return ready;
    assert(!(a >= 0x7000000000ull && a < 0x7008000000ull));
    return *(const u32u *)(uintptr_t)a;
}
#undef LD64
#define LD64(a) rd64((uint64_t)(a))
#undef LD32
#define LD32(a) rd32((uint64_t)(a))

volatile int g_fnprof;
void fnprof_hit(uint64_t a, uint64_t b, uint64_t d) { (void)a; (void)b; (void)d; }
void f_70000393b8(Cpu *);
void f_70009d0114(Cpu *);
void f_7002ab3298(Cpu *);
void f_700000421c(Cpu *c) {
    assert(c->x[0] == 0x7003e26880ull);
    ST64(c->x[8], target_hash);
    ST64(c->x[8] + 8, 0);
    ST64(c->x[8] + 16, 0x13);
    ST64(c->x[8] + 24, 0); /* unowned descriptor, no release callback */
}
void f_7000095a40(Cpu *c) { (void)c; abort(); }

#define za_dlc_dex_unlock_pump real_hook
#include "../za_dlc_dex_unlock.c"
#undef za_dlc_dex_unlock_pump
unsigned za_dlc_dex_unlock_pump(Cpu *c) { ++hook_calls; return real_hook(c); }
#include "actual_functions.inc"
void f_70009d0114(Cpu *c) { ++setter_calls; native_setter(c); }

static void fixture(unsigned which_map, unsigned on, unsigned present) {
    ready = 1; descriptor_ok = 1; setter_calls = getter_calls = hook_calls = 0;
    slot = (uintptr_t)manager;
    memset(manager, 0xa6, sizeof manager);
    /* The three maps start at 0x48, 0x80, 0xb8; erase counts first. */
    ST64((uintptr_t)manager + 0x50, 0);
    ST64((uintptr_t)manager + 0x88, 0);
    ST64((uintptr_t)manager + 0xc0, 0);
    memset(node, 0, sizeof node);
    memset(other_node, 0, sizeof other_node);
    ST64((uintptr_t)node + 8, target_hash);
    ST64((uintptr_t)node + 16, target_hash);
    ST8((uintptr_t)node + 24, on);
    ST64((uintptr_t)other_node + 8, 0x706997594f6c5b74ull);
    ST64((uintptr_t)other_node + 16, 0x706997594f6c5b74ull);
    ST8((uintptr_t)other_node + 24, 0);
    /* One bucket containing target followed by another DLC flag. */
    ST64((uintptr_t)node, (uintptr_t)other_node);
    predecessor = present ? (uintptr_t)node : (uintptr_t)other_node;
    bucket = (uintptr_t)&predecessor;
    ST64((uintptr_t)manager + 0x48 + which_map * 0x38, (uintptr_t)&bucket);
    ST64((uintptr_t)manager + 0x50 + which_map * 0x38, 1);
}

static Cpu make_cpu(uint8_t *stack, size_t n) {
    Cpu c;
    for (size_t i = 0; i < sizeof c; ++i) ((uint8_t *)&c)[i] = (uint8_t)(i * 37 + 19);
    c.sp = (uintptr_t)(stack + n - 0x100);
    return c;
}
static unsigned direct_get(Cpu *c) {
    Cpu saved = *c;
    c->x[0] = slot; c->x[1] = 0x7003e26880ull;
    f_70000393b8(c);
    unsigned value = (unsigned)c->x[0];
    *c = saved;
    return value;
}
int main(void) {
    uint8_t stack[0x2000] __attribute__((aligned(16)));
    Cpu c = make_cpu(stack, sizeof stack), saved;
    uint8_t original_manager[sizeof manager], original_node[sizeof node], original_other[sizeof other_node];
    for (unsigned m = 0; m < 3; ++m) {
        fixture(m, 0, 1);
        memcpy(original_manager, manager, sizeof manager);
        memcpy(original_node, node, sizeof node);
        memcpy(original_other, other_node, sizeof other_node);
        saved = c;
        assert(real_hook(&c) == 1);
        assert(memcmp(&saved, &c, sizeof c) == 0); /* every byte, including SIMD, NZCV, exclusive monitor */
        assert(setter_calls == 1 && direct_get(&c) == 1);
        original_node[24] = 1;
        assert(memcmp(original_manager, manager, sizeof manager) == 0);
        assert(memcmp(original_node, node, sizeof node) == 0);
        assert(memcmp(original_other, other_node, sizeof other_node) == 0);
        assert(real_hook(&c) == 1 && setter_calls == 1); /* idempotence */
        ST8((uintptr_t)node + 24, 0); /* new save / same process: no stale enabled cache */
        assert(real_hook(&c) == 1 && setter_calls == 2);
    }
    fixture(0, 0, 1); ready = 0; saved = c;
    assert(real_hook(&c) == 0 && setter_calls == 0 && memcmp(&saved, &c, sizeof c) == 0);
    fixture(0, 0, 1); slot = 0;
    assert(real_hook(&c) == 0 && setter_calls == 0);
    fixture(0, 0, 1); descriptor_ok = 0;
    assert(real_hook(&c) == 0 && setter_calls == 0);
    fixture(0, 0, 0);
    assert(real_hook(&c) == 0 && setter_calls == 1 && direct_get(&c) == 0); /* no new record */
    fixture(0, 0, 1);
    assert(!atomic_flag_test_and_set(&consumer));
    assert(real_hook(&c) == 0 && setter_calls == 0); /* reentry returns without blocking */
    atomic_flag_clear(&consumer);

    fixture(0, 1, 1);
    Cpu original = c;
    original_dex_getter(&original);
    patched_dex_getter(&c);
    assert(c.x[0] == 1 && memcmp(&original, &c, sizeof c) == 0);
    assert(hook_calls == 0 && setter_calls == 0); /* already enabled skips hook completely */
    fixture(0, 0, 1); c = make_cpu(stack, sizeof stack);
    patched_dex_getter(&c);
    assert(c.x[0] == 1 && setter_calls == 1 && hook_calls == 1 && direct_get(&c) == 1);
    fixture(0, 0, 1); ready = 0; c = make_cpu(stack, sizeof stack);
    patched_dex_getter(&c);
    assert(c.x[0] == 0 && setter_calls == 0 && hook_calls == 0);
    puts("PASS: real getter/setter, 3 maps, target-only byte diff, Cpu preservation, readiness, missing record, reentry, reload, original/patched integration, enabled fast path");
    return 0;
}
