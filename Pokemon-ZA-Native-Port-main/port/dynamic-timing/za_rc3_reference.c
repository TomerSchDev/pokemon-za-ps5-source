/* Instruction-faithful model of the RC3.0 helper (see za_rc3_reference.h). The comments quote the patched
 * instructions (research_notes/.../community-disassembly.txt). */
#include "za_rc3_reference.h"

#include <string.h>

/* The ARM code multiplies and adds in separate instructions: no fused multiply-add here. */
#pragma STDC FP_CONTRACT OFF

int32_t za_rc3_fcvtzs(float f) {
    if (f != f) return 0;
    if (f >= 2147483648.0f) return INT32_MAX;
    if (f <= -2147483648.0f) return INT32_MIN;
    return (int32_t)f;
}

void za_rc3_init(ZaRc3 *m) {
    memset(m, 0, sizeof *m);
    m->s00_hz = 19200000.0;          /* 0617a700 00000000804f7241 */
    m->s08_new = 0.05;               /* 0617a708 9a9999999999a93f */
    m->s10_old = 0.95;               /* 0617a710 666666666666ee3f */
    m->s68_sixty = 60.0f;            /* 0617a768 00007042 */
    m->s7c_threshold = 46.0f;        /* 0617a77c 00003842 */
    m->s80_ns_lo = 16666667u;        /* 0617a780 2b50fe0000000000 */
    m->s88_ns30 = 33333334u;         /* 0617a788 56a0fc0100000000 */
    m->s90_ns60 = 16666667u;         /* 0617a790 2b50fe0000000000 */
    m->sa0_mode = 0;                 /* 0617a7a0 00000000 */
    const uint64_t t[5] = {16666667u, 33333334u, 50000000u, 66666667u, 83333334u};
    memcpy(m->table, t, sizeof t);
}

ZaRc3Frame za_rc3_frame(ZaRc3 *m, uint64_t ticks, uint8_t flag) {
    ZaRc3Frame out;
    /* 1b296d8 -> 1278cc8: ldr w20, [x9, #0x7a0] (S+0xa0) */
    out.mode_used = (int32_t)m->sa0_mode;
    /* 1b296e0 -> 12789f4: the helper. 1278a28..a9c re-store the constants (same values). */
    m->s00_hz = 19200000.0;
    m->s08_new = 0.05;
    m->s10_old = 0.95;
    m->s7c_threshold = 46.0f;
    m->s88_ns30 = 33333334u;
    m->s90_ns60 = 16666667u;
    double d1 = m->s18_prev_tick;               /* ldr d1, [x9, #0x18] */
    double d0 = (double)(int64_t)ticks;         /* bl GetSystemTick; scvtf d0, x0 */
    m->s18_prev_tick = d0;                      /* str d0, [x9, #0x18] */
    double d2 = d0 - d1;                        /* fsub d2, d0, d1 */
    m->s20_prev2 = d1;                          /* str d1, [x9, #0x20] */
    double d4 = d2 / m->s00_hz;                 /* fdiv d4, d2, d3 */
    m->s28_dt_s = d4;                           /* str d4, [x9, #0x28] */
    d4 = d4 * m->s08_new;                       /* fmul d4, d4, d1 */
    double d1b = m->s30_ema_s * m->s10_old;     /* fmul d1, d2, d5 */
    d4 = d4 + d1b;                              /* fadd d4, d4, d1 */
    m->s30_ema_s = d4;                          /* str d4, [x9, #0x30] */
    double d6 = 1.0 / d4;                       /* fmov d6, #1.0; fdiv d6, d6, d4 */
    m->s38_fps = d6;
    float s6 = (float)d6;                       /* fcvt s6, d6 */
    int32_t w6 = za_rc3_fcvtzs(s6);             /* fcvtzs w6, s6 */
    s6 = (float)w6;                             /* scvtf s6, w6 */
    m->s60_fps_i = s6;                          /* str s6, [x9, #0x60] */
    m->s68_sixty = 60.0f;                       /* fmov s30, #30; fadd; str s30, [x9, #0x68] */
    m->s5c_dt_s = (float)m->s28_dt_s;           /* fcvt s29, d29; str s29, [x9, #0x5c] */
    m->s70_acc_s = m->s70_acc_s + m->s5c_dt_s;  /* fadd s3, s3, s4; str s3, [x9, #0x70] (never read) */
    uint32_t mode = s6 < m->s7c_threshold ? 1u : 0u;  /* fcmp s6, s1; csel w20, w20(1), w21(0), lt */
    m->sa0_mode = mode;                         /* str w20, [x9, #0xa0] */
    m->sa8_flag = flag;                         /* ldrb w1, [x10, #0x980]; str w1, [x9, #0xa8] */
    int32_t w1 = za_rc3_fcvtzs(s6);             /* fcvtzs w1, s6 */
    float s0 = (float)w1;                       /* scvtf s0, w1 */
    s0 = 1.0f / s0;                             /* fdiv s0, s1(1.0), s0 */
    s0 = s0 * 1e9f;                             /* fmul s0, s0, s2(0x4e6e6b28) */
    m->s80_ns_lo = (uint32_t)za_rc3_fcvtzs(s0); /* fcvtzs w1, s0; str w1, [x9, #0x80] */
    uint64_t ns = (uint64_t)m->s80_ns_lo;       /* ldr x0, [x9, #0x80] */
    uint64_t flag64 = (uint64_t)m->sa8_flag;    /* ldr x2, [x9, #0xa8] */
    if (mode == 1) {
        uint64_t x0 = s6 < 31.0f ? m->s88_ns30 : ns;  /* fcmp s0, #31.0; csel x0, x1, x0, lt */
        if (flag64) x0 = m->s88_ns30;                  /* cmp x2, #0; csel x0, x1, x0, ne */
        m->table[1] = x0;                              /* str x0, [x10, #0xe28] */
        m->table[0] = m->s90_ns60;                     /* str x1, [x10, #0xe20] */
    } else {
        uint64_t x0 = s6 >= 58.0f ? m->s90_ns60 : ns;  /* fcmp s0, 58.0; csel x0, x1, x0, ge */
        if (flag64) x0 = m->s90_ns60;
        m->table[0] = x0;
        m->table[1] = m->s88_ns30;
    }
    out.next_mode = (int32_t)mode;
    /* back at 1b296e4: w22 = w20 (cfg+0x21 == 0), present mode = w20, then SetFrameMode(i, w20) for every slot,
     * which loads table[w20] - after the rewrite above. */
    out.step_ns = m->table[out.mode_used];
    return out;
}
