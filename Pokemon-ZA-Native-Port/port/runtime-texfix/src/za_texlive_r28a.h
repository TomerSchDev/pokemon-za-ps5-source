// r28a texfix (port/runtime-texfix): textures.c's list of live game textures, consistent under a lock of its own.
//
// r28-play crashed in live_remove (backend_texture_destroyed, called by nvnTextureFinalize under exec_lock):
//     ((TexBackend *)g_live[g_nlive - 1]->backend)->reg = b->reg;      with ->backend == 0x2 (fault address 0xa2)
// The list's last entry was an NvnTexture that had been finalized and freed (its memory since reused), either
// registered again through a stale pointer (tex_backend on a texture the executor's state, a recorded command list or
// the present path still held) or left behind by an unsynchronised add / remove (the present path registered textures
// without exec_lock). Here:
//   - each entry is a pair: the texture and its backend, the backend's reg being its slot + 1. Maintenance only ever
//     dereferences the backends (textures.c allocates and frees them), never a texture entry: a stale texture pointer
//     in the list can no longer be followed by add / remove / pop;
//   - every change and every walk holds za_live_lock (changes happen when a texture gets its backend or loses it,
//     never per draw);
//   - remove checks that the backend's slot really holds it; a mismatch is reported ([za-texguard] live-list, once)
//     and repaired by a scan instead of swapping a wrong entry into place.
// Host-tested under ASan / UBSan / TSan (port/runtime-texfix/test). Included once by textures.c, after NvnTexture and
// TexBackend are defined and za_texguard_hit is declared (nvn.h).
#pragma once
#include <pthread.h>
#include <stdbool.h>
#include <stdlib.h>

static pthread_mutex_t za_live_lock = PTHREAD_MUTEX_INITIALIZER;
static NvnTexture **g_live;    // the textures - identification only, never dereferenced in this file
static TexBackend **g_live_b;  // their backends: g_live_b[i]->reg == i + 1
static int g_nlive, g_cap_live;

// false: no memory for a bigger list (the backend works, unlisted: b->reg 0; a reboot would not release it)
static bool za_live_add(NvnTexture *t, TexBackend *b) {
    bool ok = true;
    pthread_mutex_lock(&za_live_lock);
    if (g_nlive == g_cap_live) {
        int cap = g_cap_live ? g_cap_live * 2 : 1024;
        NvnTexture **nt = realloc(g_live, (size_t)cap * sizeof *nt);
        if (nt) g_live = nt;
        TexBackend **nb = nt ? realloc(g_live_b, (size_t)cap * sizeof *nb) : NULL;
        if (nb) g_live_b = nb, g_cap_live = cap;  // (both grown, or the capacity stays: the next add tries again)
        else ok = false;
    }
    if (ok) {
        g_live[g_nlive] = t;
        g_live_b[g_nlive] = b;
        b->reg = ++g_nlive;
    } else {
        b->reg = 0;
    }
    pthread_mutex_unlock(&za_live_lock);
    return ok;
}

// The entry of b goes; the last entry takes its slot. b->reg 0: not listed (nothing to do).
static void za_live_remove(NvnTexture *t, TexBackend *b) {
    pthread_mutex_lock(&za_live_lock);
    int i = -1;
    if (b->reg) {
        i = b->reg - 1;
        if (i < 0 || i >= g_nlive || g_live_b[i] != b || g_live[i] != t) {
            za_texguard_hit(ZA_TG_LIVE_LIST, t, (uint32_t)b->reg, (const void *)b);
            i = -1;
            for (int k = 0; k < g_nlive; k++)
                if (g_live_b[k] == b) { i = k; break; }
        }
    }
    if (i >= 0) {
        int last = --g_nlive;
        if (i != last) {
            g_live[i] = g_live[last];
            g_live_b[i] = g_live_b[last];
            g_live_b[i]->reg = i + 1;  // (a backend of this file: the only dereference the swap needs)
        }
        g_live[last] = NULL;
        g_live_b[last] = NULL;
    }
    b->reg = 0;
    pthread_mutex_unlock(&za_live_lock);
}

// Reboot (vk_textures_reset): the last entry, taken out of the list; false when the list is empty.
static bool za_live_pop(NvnTexture **t, TexBackend **b) {
    pthread_mutex_lock(&za_live_lock);
    bool any = g_nlive > 0;
    if (any) {
        int last = --g_nlive;
        *t = g_live[last];
        *b = g_live_b[last];
        g_live[last] = NULL;
        g_live_b[last] = NULL;
        (*b)->reg = 0;
    }
    pthread_mutex_unlock(&za_live_lock);
    return any;
}

// Every entry, under the lock (fn must not add or remove entries).
static void za_live_walk(void (*fn)(NvnTexture *t, TexBackend *b, void *arg), void *arg) {
    pthread_mutex_lock(&za_live_lock);
    for (int i = 0; i < g_nlive; i++) fn(g_live[i], g_live_b[i], arg);
    pthread_mutex_unlock(&za_live_lock);
}

static int za_live_count(void) {
    pthread_mutex_lock(&za_live_lock);
    int n = g_nlive;
    pthread_mutex_unlock(&za_live_lock);
    return n;
}
