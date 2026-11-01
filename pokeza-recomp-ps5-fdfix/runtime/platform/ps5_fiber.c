// The x86-64 SysV context switch for runtime/hle/fiber.c on the PS5 (ps5_fiber.h says why). Compiled into the title by
// the Makefile (PLATFORM=ps5: RT_SRC) and by tools/ps5/compile-runtime.sh; nothing of it has run on the console yet
// [TODO verify: plat_init runs plat_fiber_selftest, the probe title reads the result].
#include "ps5_fiber.h"

#include <stdio.h>
#include <stdlib.h>

// The frame plat_fiber_switch leaves on a context's stack, lowest address first - and what plat_fiber_make lays out for
// a fresh context:
//   +0   MXCSR (4 bytes), the x87 control word (2), 2 unused
//   +8   r15   +16 r14   +24 r13   +32 r12   +40 rbx   +48 rbp
//   +56  the return address: where the context continues (a fresh one: plat_fiber_trampoline)
// 64 bytes. A fresh context's sp is 16-byte aligned, so rsp = sp + 64 is too when the trampoline starts: the ABI's
// state before a call, which its `call *%r12` needs. (Inside plat_fiber_switch rsp is 8 mod 16 at entry, the return
// address pushed, and 0 mod 16 after the 48 bytes of pushes and the 8 for the FP words; the stores need no alignment.)
__asm__(
    ".text\n"
    ".globl plat_fiber_switch\n"
    ".hidden plat_fiber_switch\n"
    ".type plat_fiber_switch,@function\n"
    "plat_fiber_switch:\n"
    "    pushq %rbp\n"
    "    pushq %rbx\n"
    "    pushq %r12\n"
    "    pushq %r13\n"
    "    pushq %r14\n"
    "    pushq %r15\n"
    "    subq $8, %rsp\n"
    "    stmxcsr (%rsp)\n"
    "    fnstcw 4(%rsp)\n"
    "    movq %rsp, (%rdi)\n"
    "    movq (%rsi), %rsp\n"
    "    ldmxcsr (%rsp)\n"
    "    fldcw 4(%rsp)\n"
    "    addq $8, %rsp\n"
    "    popq %r15\n"
    "    popq %r14\n"
    "    popq %r13\n"
    "    popq %r12\n"
    "    popq %rbx\n"
    "    popq %rbp\n"
    "    ret\n"
    ".size plat_fiber_switch, .-plat_fiber_switch\n"
    // A fresh context's first run: fn in r12, its argument in r13 (plat_fiber_make), rbp 0 so a frame-pointer
    // backtrace ends here. fn returning is a bug: reported, fatal.
    ".globl plat_fiber_trampoline\n"
    ".hidden plat_fiber_trampoline\n"
    ".type plat_fiber_trampoline,@function\n"
    "plat_fiber_trampoline:\n"
    "    movq %r13, %rdi\n"
    "    call *%r12\n"
    "    call plat_fiber_returned\n"
    "    ud2\n"
    ".size plat_fiber_trampoline, .-plat_fiber_trampoline\n");

void plat_fiber_trampoline(void);  // (the asm above; never called from C)

__attribute__((used, noreturn)) static void plat_fiber_returned(void) {
    fprintf(stderr, "FATAL: [fiber] a fiber's function returned (runtime/platform/ps5_fiber.c)\n");
    abort();
}

void plat_fiber_make(PlatFiberCtx *ctx, void *stack, size_t size, void (*fn)(void *), void *arg) {
    uintptr_t top = ((uintptr_t)stack + size) & ~(uintptr_t)15;
    uint64_t *f = (uint64_t *)(top - 64);
    uint32_t mxcsr;
    uint16_t cw;
    __asm__ volatile("stmxcsr %0" : "=m"(mxcsr));
    __asm__ volatile("fnstcw %0" : "=m"(cw));
    f[0] = (uint64_t)mxcsr | ((uint64_t)cw << 32);  // the maker's FP control state, as getcontext hands it on
    f[1] = f[2] = 0;                                   // r15, r14
    f[3] = (uint64_t)(uintptr_t)arg;                   // r13
    f[4] = (uint64_t)(uintptr_t)fn;                    // r12
    f[5] = f[6] = 0;                                   // rbx, rbp
    f[7] = (uint64_t)(uintptr_t)plat_fiber_trampoline;
    ctx->sp = f;
}

// ---- the self-test
typedef struct {
    PlatFiberCtx main, fiber;
    uintptr_t lo, hi, sp;
    uint32_t csr_kept;
    int step;
} SelfTest;

static uint32_t mxcsr_get(void) { uint32_t v; __asm__ volatile("stmxcsr %0" : "=m"(v)); return v; }
static void mxcsr_set(uint32_t v) { __asm__ volatile("ldmxcsr %0" : : "m"(v)); }
static uint16_t x87cw_get(void) { uint16_t v; __asm__ volatile("fnstcw %0" : "=m"(v)); return v; }
static uintptr_t rsp_get(void) { uintptr_t v; __asm__ volatile("movq %%rsp, %0" : "=r"(v)); return v; }

static void selftest_fiber(void *p) {
    SelfTest *t = p;
    t->sp = rsp_get();
    t->step = 1;
    mxcsr_set(mxcsr_get() | 0x6000);  // round toward zero: the main context must not see it, this one must keep it
    plat_fiber_switch(&t->fiber, &t->main);
    t->csr_kept = mxcsr_get();  // (resumed)
    t->step = 2;
    plat_fiber_switch(&t->fiber, &t->main);
    t->step = 3;  // (never: the main context does not come back a third time)
    for (;;) plat_fiber_switch(&t->fiber, &t->main);
}

bool plat_fiber_selftest(void *stack, size_t size, char *why, size_t why_size) {
#define FAIL(...) return (snprintf(why, why_size, __VA_ARGS__), false)
    if (!stack || size < 16384) FAIL("no stack");
    SelfTest t = {.lo = (uintptr_t)stack, .hi = (uintptr_t)stack + size};
    uint32_t csr0 = mxcsr_get();
    uint16_t cw0 = x87cw_get();
    plat_fiber_make(&t.fiber, stack, size, selftest_fiber, &t);
    plat_fiber_switch(&t.main, &t.fiber);
    if (t.step != 1) FAIL("the fiber did not run (step %d)", t.step);
    if (t.sp < t.lo || t.sp >= t.hi)
        FAIL("the fiber's rsp %llx is outside its stack %llx+%llx", (unsigned long long)t.sp, (unsigned long long)t.lo,
             (unsigned long long)size);
    if (t.sp & 15) FAIL("the fiber's rsp %llx is not 16-byte aligned", (unsigned long long)t.sp);
    if (mxcsr_get() != csr0) FAIL("MXCSR %x after the switch back, %x before", mxcsr_get(), csr0);
    if (x87cw_get() != cw0) FAIL("x87 control word %x after the switch back, %x before", x87cw_get(), cw0);
    plat_fiber_switch(&t.main, &t.fiber);
    if (t.step != 2) FAIL("the fiber did not resume (step %d)", t.step);
    if ((t.csr_kept & 0x6000) != 0x6000) FAIL("the fiber's MXCSR %x lost its rounding mode while suspended", t.csr_kept);
    if (mxcsr_get() != csr0) FAIL("MXCSR %x after the second switch back, %x before", mxcsr_get(), csr0);
    return true;
#undef FAIL
}
