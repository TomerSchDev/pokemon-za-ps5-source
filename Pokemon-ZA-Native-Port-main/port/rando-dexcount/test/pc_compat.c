/* Zig's retained AOT objects refer to __imp__setjmp; the original delivered
 * lasgame.dll maps that import to UCRT __intrinsic_setjmp (objdump verified).
 * MSYS2 names the UCRT import explicitly. Preserve the same target via its
 * import thunk; the thunk tail-jumps and does not insert a stack frame. */
extern int __intrinsic_setjmp(void*);
int (*__imp__setjmp)(void*) = __intrinsic_setjmp;
