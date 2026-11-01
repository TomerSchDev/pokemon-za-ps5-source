// x86-64 host contexts for the fibers of runtime/hle/fiber.c on the PS5 (ZA_PS5_ASM_FIBERS, on by default): a context
// switch of the title's own, in asm, in place of libkernel's getcontext / swapcontext and libSceLibcInternal's
// makecontext - which link for a title but are unverified on the console (the gaps report, B10), and which also save
// and restore the signal mask with a syscall per switch. A context is its saved stack pointer; the callee-saved
// registers (rbx, rbp, r12-r15), MXCSR and the x87 control word sit on its stack. Nothing else is the ABI's to keep
// across a call: the caller-saved registers are the compiler's business around the call to plat_fiber_switch, and
// the guest's register file lives in the Cpu (fiber.c's frame_save / frame_load).
//
// plat_fiber_selftest, run at start-up (runtime/platform/ps5.c, plat_init) and by the probe title: a fiber on the
// given stack, entered, left, resumed and left again - its rsp inside the stack and 16-byte aligned, the main
// context's MXCSR and x87 control word unchanged by the fiber's, the fiber's own kept across its suspension.
// Implementation: runtime/platform/ps5_fiber.c.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#ifndef ZA_PS5_ASM_FIBERS
#define ZA_PS5_ASM_FIBERS 1  // -DZA_PS5_ASM_FIBERS=0: fiber.c back on ucontext
#endif

#ifdef __cplusplus
extern "C" {
#endif
typedef struct { void *sp; } PlatFiberCtx;
// ctx: a context that, switched to, runs fn(arg) on [stack, stack + size); fn never returns (it switches away for good)
void plat_fiber_make(PlatFiberCtx *ctx, void *stack, size_t size, void (*fn)(void *), void *arg);
// The running context saved into *from, *to resumed (a fresh one: its fn starts).
void plat_fiber_switch(PlatFiberCtx *from, PlatFiberCtx *to);
// false with why (the stack: 16 KiB at least).
bool plat_fiber_selftest(void *stack, size_t size, char *why, size_t why_size);
#ifdef __cplusplus
}
#endif
