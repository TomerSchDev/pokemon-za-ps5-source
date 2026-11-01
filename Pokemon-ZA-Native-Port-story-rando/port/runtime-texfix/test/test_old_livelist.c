// Negative control: r28-play's live list (runtime/nvn/vulkan/textures.c, live_add / live_remove verbatim) in the
// scenario test_texfix.c runs on r28a's - the list's last entry is a texture that was freed (mode "uaf", ASan build:
// a heap-use-after-free report is expected) or whose memory was reused with 0x2 where its backend pointer was (mode
// "reuse", plain build: SIGSEGV at 0xa2 expected - r28-play's klog: "[za-native-fault] sig=11 fa=a2").
#define _GNU_SOURCE
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "texfix_mirror.h"

// ---- r28-play, textures.c lines 397-411
static NvnTexture **g_live;
static int g_nlive, g_cap_live;
static void live_add(NvnTexture *t, TexBackend *b) {
    if (g_nlive == g_cap_live) { g_cap_live = g_cap_live ? g_cap_live * 2 : 1024; g_live = realloc(g_live, g_cap_live * sizeof *g_live); }
    g_live[g_nlive++] = t;
    b->reg = g_nlive;
}
static void live_remove(TexBackend *b) {
    if (!b->reg) return;
    NvnTexture *last = g_live[--g_nlive];
    g_live[b->reg - 1] = last;
    if (last->backend) ((TexBackend *)last->backend)->reg = b->reg;
    b->reg = 0;
}
// ----

static void on_segv(int sig, siginfo_t *si, void *uc) {
    (void)sig, (void)uc;
    char line[96];
    int n = snprintf(line, sizeof line, "old live list: SIGSEGV, fault address %p\n", si->si_addr);
    if (write(2, line, (size_t)n) < 0) _exit(43);
    _exit(42);
}

int main(int argc, char **argv) {
    const char *mode = argc > 1 ? argv[1] : "uaf";
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = on_segv;
    sa.sa_flags = SA_SIGINFO;
    sigaction(SIGSEGV, &sa, NULL);
    NvnTexture *a = calloc(1, sizeof *a), *s = calloc(1, sizeof *s);
    TexBackend *ba = calloc(1, sizeof *ba), *bs = calloc(1, sizeof *bs);
    a->backend = ba, s->backend = bs;
    live_add(a, ba);
    live_add(s, bs);  // (s: registered, then finalized behind the list's back - the stale entry)
    if (!strcmp(mode, "uaf")) {
        free(s);
    } else {
        memset(s, 0, sizeof *s);  // (its memory reused by another object: 0x2 where ->backend was)
        s->backend = (void *)(uintptr_t)0x2;
    }
    fprintf(stderr, "old live list: removing the first entry, the stale one is last\n");
    live_remove(ba);  // r28-play: backend_texture_destroyed -> live_remove
    fprintf(stderr, "old live list: no fault (unexpected)\n");
    return 0;
}
