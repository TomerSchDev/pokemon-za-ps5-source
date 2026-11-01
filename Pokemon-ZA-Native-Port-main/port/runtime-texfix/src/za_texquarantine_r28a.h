// r28a texfix (port/runtime-texfix): a finalized NvnTexture is poisoned (za_guard = NVN_TEX_DEAD) and kept for the next
// ZA_TEX_QUARANTINE finalizations before free(), so a stale pointer to it - in the executor's state, a recorded command
// list, a guest copy of the texture object - meets the poison, deterministically, instead of memory already reused by
// another object (r28-play's crash: such memory read back as backend 0x2). The newest pointer pushes the oldest out.
// Callers serialize (nvnTextureFinalize holds exec_lock). 4096 x 200 bytes: ~800 KB at most.
// Included once by objects.c; host-tested (port/runtime-texfix/test).
#pragma once
#include <stdint.h>
#include <stdlib.h>

#ifndef ZA_TEX_QUARANTINE
#define ZA_TEX_QUARANTINE 4096
#endif

static void *za_quar[ZA_TEX_QUARANTINE];
static unsigned za_quar_next;
static uint64_t za_quar_total;

static void za_quarantine_push(void *p) {
    void *oldest = za_quar[za_quar_next];
    za_quar[za_quar_next] = p;
    za_quar_next = (za_quar_next + 1) % ZA_TEX_QUARANTINE;
    za_quar_total++;
    free(oldest);  // (NULL until the ring has filled once)
}
