/* Instruction-faithful C model of "Dynamic 60 FPS RC3.0" (Fl4sh) for Z-A 2.0.2, for host comparison only.
 *
 * It reproduces, operation by operation, the injected helper at main+0x12789f4..0x1278cc4 (entered from the
 * patched main+0x1b296e0) and the stub at main+0x1278cc8 (entered from main+0x1b296d8), including the float/double
 * mix, the truncations, the saturating fcvtzs, the 32-bit store read back as 64 bits, the start from tick 0 and the
 * one-call delay between the decision and its use. Scratch offsets are those of main+0x617a700 (S). It is NOT the
 * proposed port implementation (za_dyn_timing.c) - it exists so the tests can show where the two differ. */
#ifndef ZA_RC3_REFERENCE_H
#define ZA_RC3_REFERENCE_H
#include <stdint.h>

typedef struct {
    double s00_hz, s08_new, s10_old, s18_prev_tick, s20_prev2, s28_dt_s, s30_ema_s, s38_fps;
    float s5c_dt_s, s60_fps_i, s68_sixty, s70_acc_s, s7c_threshold;
    uint32_t s80_ns_lo;            /* written with a 32-bit str, read back with a 64-bit ldr (high half stays 0) */
    uint64_t s88_ns30, s90_ns60;
    uint32_t sa0_mode, sa8_flag;   /* sa8: 32-bit store of the byte at main+0x610b980, read with a 64-bit ldr */
    uint64_t table[5];             /* main+0x3393e20: the mod rewrites [0] and [1] */
} ZaRc3;

typedef struct {
    int32_t mode_used;   /* w20 this call: the mode the PREVIOUS helper stored at S+0xa0 */
    uint64_t step_ns;    /* what SetFrameMode(i, mode_used) reads afterwards: the rewritten table[mode_used] */
    int32_t next_mode;   /* the mode stored for the next call */
} ZaRc3Frame;

void za_rc3_init(ZaRc3 *m);  /* the patch's initial scratch values */
/* One call of f_7001b29660 with the mod: `ticks` is nn::os::GetSystemTick (19.2 MHz), `flag` the byte at
 * main+0x610b980. */
ZaRc3Frame za_rc3_frame(ZaRc3 *m, uint64_t ticks, uint8_t flag);
/* ARM fcvtzs (single -> int32): truncation toward zero, saturating, NaN -> 0. */
int32_t za_rc3_fcvtzs(float f);
/* rt_ticks(): the port's 19.2 MHz system tick from nanoseconds (runtime/kernel.c). */
static inline uint64_t za_rc3_ticks_from_ns(uint64_t ns) { return (uint64_t)((unsigned __int128)ns * 192 / 10000); }

#endif
