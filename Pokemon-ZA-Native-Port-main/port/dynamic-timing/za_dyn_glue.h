/* Port glue for the dynamic frame timing (proposal - not linked into any build yet).
 *
 * The translated units call these three functions from guarded source patches (analysis/dynamic-timing-design-HE.md,
 * "hook sites"); everything else stays the original generated C.
 *   H1 main+0x1b296d8 ldrsb w20,[x9,#0x20]  main_660.c:5580 (f_7001b29660)
 *        c->x[20] = (uint32_t)za_dt_frame_cfg((int8_t)LD8(c->x[9] + 0x20), LD8(c->x[9] + 0x21), c->x[19]);
 *   H2 main+0x1b296f0 mov w1,w20           main_660.c:5586 (f_7001b29660, argument of f_70017fafd4)
 *        c->x[1] = (uint32_t)za_dt_present_mode((uint32_t)c->x[20]);
 *   H3 main+0x1b2a0ec ldr x2,[x8,w2,sxtw #3] main_660.c:6382 (f_7001b2a0e4, SetFrameMode, 2-slot holder)
 *   H4 main+0x1b54084 (same instruction)     main_665.c:1321 (f_7001b5407c, SetFrameMode, vector holder)
 *   H5 main+0x29f421c (same instruction)     main_1049.c:13333 (f_70029f4214, SetFrameMode, 11-slot holder)
 *        ... uint64_t v = LD64(ea); c->x[2] = za_dt_step_ns((int32_t)c->x[2], v); }
 * Optional diagnostic/experiment hooks on the animation play-rate denominators (not needed for the design):
 *   H6 main+0x101537c ldr x8,[x8,x21,lsl #3] main_467.c:7938 (f_7001015260, mode = [main+0x61316c8])
 *   H7 main+0x10274e0 ldr x8,[x8,x9,lsl #3]  main_468.c:1212 (f_70010273f0, mode = [this+0x48])
 *        ... uint64_t v = LD64(ea); c->x[8] = za_dt_anim_table_ns((int32_t)c->x[21 or 9], v); }
 *   They return the table value (default) and count the calls; ZA_DT_ANIM=step returns the dynamic step instead,
 *   which reproduces RC3's rewritten-table denominator for an on-console A/B of the animation speed.
 * Threads: H1/H2 run on the game's frame thread; H3-H7 may run anywhere - they only load one atomic word. */
#ifndef ZA_DYN_GLUE_H
#define ZA_DYN_GLUE_H
#include <stdint.h>

int32_t za_dt_frame_cfg(int32_t original, uint32_t variable_flag, uint64_t clock_obj);
uint32_t za_dt_present_mode(uint32_t mode);
uint64_t za_dt_step_ns(int32_t mode, uint64_t original_ns);
uint64_t za_dt_anim_table_ns(int32_t mode, uint64_t original_ns);
/* -1: dynamic off; 0/1: the mode in effect (for the observer's mode column via a za_performance_status wrap). */
int za_dt_status(void);
/* (Re)reads the ZA_DT_* environment. Called on the first H1; tests call it directly. */
void za_dt_init_from_env(void);
/* Reads the byte RC3 uses (main+0x610b980) when honor_registry is set; replaceable by the host tests. */
extern uint8_t (*za_dt_registry_reader)(void);

#endif
