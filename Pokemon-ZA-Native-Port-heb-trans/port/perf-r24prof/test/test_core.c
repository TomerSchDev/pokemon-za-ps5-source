/* Host test of za_prof_core.h (registry, ring, caller rule, the handler body, file layout, rotation, summary) and of
 * the handler under real signals: SIGPROF sent with pthread_kill to registered threads, as the title's sampler
 * does, with Linux's ucontext. Build: clang -fsanitize=address,undefined -pthread (test.sh).
 * Writes out/c-sample.bin, which test_symbolize.py reads back (one file layout for the C writer and the reader). */
#define _GNU_SOURCE
#include <assert.h>
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <ucontext.h>
#include <unistd.h>

#include "../za_prof_core.h"

static uint64_t read_u64(uint64_t a) { return *(const volatile uint64_t *)(uintptr_t)a; }

/* ---- registry */
static void test_registry(void) {
    static ZpRegistry g;
    memset(&g, 0, sizeof g);
    int a = zp_claim(&g);
    assert(a == 0);
    zp_publish(&g, a, 0x1111, ZP_KIND_GUEST, 0x51, 0x7100001000, 44, 0x1000, 0x9000, "g51");
    int b = zp_claim(&g);
    zp_publish(&g, b, 0x2222, ZP_KIND_GUEST, 0x52, 0x7100002000, 44, 0, 0, "g52");
    assert(zp_lookup(&g, 0x1111) == a && zp_lookup(&g, 0x2222) == b && zp_lookup(&g, 0x3333) == -1);
    assert(zp_next_target(&g, -1, -1) == a && zp_next_target(&g, a, -1) == b && zp_next_target(&g, b, -1) == a);
    assert(zp_next_target(&g, a, b) == a);  /* (skip the render slot) */
    zp_end(&g, a);
    assert(zp_lookup(&g, 0x1111) == -1 && zp_next_target(&g, b, b) == -1);
    /* an ended slot is reused only two windows later, never-used slots first */
    int c = zp_claim(&g);
    assert(c == 2);
    zp_publish(&g, c, 0x3333, ZP_KIND_GUEST, 0x53, 0, 0, 0, 0, "g53");
    for (int i = 3; i < ZP_MAX_THREADS; i++) { int k = zp_claim(&g); assert(k == i); zp_publish(&g, k, 0x10000 + (uintptr_t)i, 0, 0, 0, 0, 0, 0, "x"); }
    assert(zp_claim(&g) == -1 && atomic_load(&g.full) == 1);
    atomic_store(&g.window, 1);
    assert(zp_claim(&g) == -1);
    atomic_store(&g.window, 2);
    assert(zp_claim(&g) == a);
    puts("  registry: claim/publish/lookup/end, round robin with skip, reuse after two windows, full");
}

/* ---- caller rule and text range */
static void test_rules(void) {
    assert(zp_caller_ok(0x5000, 0x5008, 0x1000, 0x9000));
    assert(!zp_caller_ok(0x5000, 0x4ff8, 0x1000, 0x9000));   /* below RSP: not a live frame */
    assert(!zp_caller_ok(0x5000, 0x8ff8, 0x1000, 0x9000));   /* +8 would read past the top */
    assert(zp_caller_ok(0x5000, 0x8ff0, 0x1000, 0x9000));
    assert(!zp_caller_ok(0x5000, 0x5004, 0x1000, 0x9000));   /* misaligned */
    assert(!zp_caller_ok(0x5000, 0x5008, 0, 0));             /* stack unknown */
    assert(!zp_caller_ok(0x0800, 0x0800, 0x1000, 0x9000));   /* outside the stack */
    assert(zp_in_text(0x400000, 0x400000, 0x500000) && !zp_in_text(0x500000, 0x400000, 0x500000));
    assert(!zp_in_text(0x450000, 0, 0));
    puts("  rules: caller only for an aligned RBP in [RSP, stack top - 16] of a known stack; text range half-open");
}

/* ---- ring */
static uint32_t got, last_rip;
static void count(void *ctx, const ZpRec *r) { (void)ctx; got++; last_rip = (uint32_t)r->rip; }
static void test_ring(void) {
    static ZpRec rec[8];
    ZpRing g = {rec, 8, 0, 0, 0};
    for (uint32_t i = 0; i < 5; i++) assert(zp_ring_push(&g, 1, 0, 100 + i, 0));
    uint32_t skipped = 0;
    got = 0;
    assert(zp_ring_drain(&g, atomic_load(&g.w), count, NULL, &skipped) == 5 && got == 5 && last_rip == 104 && !skipped);
    for (uint32_t i = 0; i < 10; i++) zp_ring_push(&g, 1, 0, 200 + i, 0);  /* 8 fit, 2 dropped */
    assert(atomic_load(&g.dropped) == 2);
    got = 0;
    assert(zp_ring_drain(&g, atomic_load(&g.w), count, NULL, &skipped) == 8 && skipped == 2 && last_rip == 207);
    /* an index taken but never completed (a handler interrupted mid-push, or dropped) is skipped, not waited for */
    atomic_fetch_add(&g.w, 1);
    zp_ring_push(&g, 1, 0, 300, 0);
    skipped = 0, got = 0;
    assert(zp_ring_drain(&g, atomic_load(&g.w), count, NULL, &skipped) == 1 && skipped == 1 && last_rip == 300);
    puts("  ring: order, drop when a whole ring behind, incomplete indexes skipped");
}

/* ---- the handler body with a fake context */
static void test_on_sample(void) {
    static ZpRegistry g;
    static ZpRec rec[16];
    memset(&g, 0, sizeof g);
    ZpRing ring = {rec, 16, 0, 0, 0};
    _Atomic uint32_t unknown = 0;
    uint64_t stack[64] = {0};
    uintptr_t lo = (uintptr_t)stack, hi = (uintptr_t)(stack + 64);
    stack[11] = 0xabcdef;  /* [RBP+8] with RBP = &stack[10] */
    int i = zp_claim(&g);
    zp_publish(&g, i, 7, ZP_KIND_RENDER, 0, 0, 0, lo, hi, "R");
    assert(zp_on_sample(&g, &ring, 7, 0x401000, (uint64_t)(uintptr_t)&stack[2], (uint64_t)(uintptr_t)&stack[10],
                        0x400000, 0x500000, read_u64, &unknown) == i);
    assert(zp_on_sample(&g, &ring, 7, 0x900000, (uint64_t)(uintptr_t)&stack[2], 0x10, 0x400000, 0x500000, read_u64, &unknown) == i);
    assert(zp_on_sample(&g, &ring, 8, 0x401000, 0, 0, 0x400000, 0x500000, read_u64, &unknown) == -1 && unknown == 1);
    assert(rec[0].caller == 0xabcdef && rec[0].flags == (ZP_F_CALLER | ZP_F_TEXT_KNOWN | ZP_F_IN_TEXT));
    assert(rec[1].caller == 0 && rec[1].flags == ZP_F_TEXT_KNOWN);
    assert(g.t[i].win_samples == 2 && g.t[i].win_ext == 1 && g.t[i].win_nofp == 1);
    puts("  handler body: caller from [RBP+8], flags, per-thread window counters, unknown threads counted");
}

/* ---- real signals: registered threads interrupted with pthread_kill(SIGPROF), handler = zp_on_sample */
static ZpRegistry g_reg;
static ZpRing g_ring;
static _Atomic uint32_t g_unknown;
static _Atomic int g_stop;
static void handler(int sig, siginfo_t *si, void *ctx) {
    (void)sig, (void)si;
    ucontext_t *uc = ctx;
    zp_on_sample(&g_reg, &g_ring, (uintptr_t)pthread_self(), (uint64_t)uc->uc_mcontext.gregs[REG_RIP],
                 (uint64_t)uc->uc_mcontext.gregs[REG_RSP], (uint64_t)uc->uc_mcontext.gregs[REG_RBP], 0, 0, read_u64,
                 &g_unknown);
}
__attribute__((noinline)) static uint64_t spin(uint64_t x) {
    for (int i = 0; i < 1000; i++) x = x * 6364136223846793005ull + 1442695040888963407ull;
    return x;
}
static void *worker(void *arg) {
    (void)arg;
    pthread_attr_t a;
    void *addr;
    size_t size;
    pthread_getattr_np(pthread_self(), &a);
    pthread_attr_getstack(&a, &addr, &size);
    pthread_attr_destroy(&a);
    int i = zp_claim(&g_reg);
    zp_publish(&g_reg, i, (uintptr_t)pthread_self(), ZP_KIND_GUEST, (uint64_t)i, 0, 0, (uintptr_t)addr,
               (uintptr_t)addr + size, "w");
    volatile uint64_t x = 1;
    while (!atomic_load(&g_stop)) {
        x = spin(x);
        usleep(10);  /* (also interrupted in a syscall: SA_RESTART) */
    }
    zp_end(&g_reg, i);
    return NULL;
}
typedef struct { uint32_t n; } Count;
static void sink(void *ctx, const ZpRec *r) { Count *c = ctx; (void)r; c->n++; }
static void test_signals(void) {
    g_ring.cap = 1 << 12;
    g_ring.rec = calloc(g_ring.cap, sizeof(ZpRec));
    struct sigaction sa;
    memset(&sa, 0, sizeof sa);
    sa.sa_sigaction = handler;
    sa.sa_flags = SA_SIGINFO | SA_RESTART;
    sigemptyset(&sa.sa_mask);
    assert(sigaction(SIGPROF, &sa, NULL) == 0);
    pthread_t t[6];
    for (int i = 0; i < 6; i++) pthread_create(&t[i], NULL, worker, NULL);
    sigset_t block;  /* (after creating them: a new thread inherits the creator's mask; the title's sampler, too, */
    sigemptyset(&block);  /* blocks SIGPROF only in itself) */
    sigaddset(&block, SIGPROF);
    pthread_sigmask(SIG_BLOCK, &block, NULL);
    usleep(20000);
    uint32_t sent = 0, err = 0;
    Count c = {0};
    uint32_t skipped = 0;
    int rr = -1;
    for (int k = 0; k < 4000; k++) {
        int i = zp_next_target(&g_reg, rr, -1);
        if (i < 0) continue;
        rr = i;
        if (pthread_kill((pthread_t)atomic_load(&g_reg.t[i].tid), SIGPROF) == 0) sent++; else err++;
        if (k % 500 == 499) { usleep(2000); zp_ring_drain(&g_ring, atomic_load(&g_ring.w), sink, &c, &skipped); }
        usleep(50);
    }
    usleep(5000);
    zp_ring_drain(&g_ring, atomic_load(&g_ring.w), sink, &c, &skipped);
    atomic_store(&g_stop, 1);
    for (int i = 0; i < 6; i++) pthread_join(t[i], NULL);
    uint32_t samples = 0, nofp = 0;
    for (int i = 0; i < ZP_MAX_THREADS; i++) samples += g_reg.t[i].win_samples, nofp += g_reg.t[i].win_nofp;
    printf("  signals: sent %u errors %u, samples %u, records %u, dropped %u, skipped %u, unknown %u, no caller %u\n",
           sent, err, samples, c.n, atomic_load(&g_ring.dropped), skipped, atomic_load(&g_unknown), nofp);
    /* (two SIGPROF pending at one thread merge into one - standard signals don't queue - so a few may be missing) */
    assert(sent > 3000 && !err && samples <= sent && samples >= sent - sent / 50);
    assert(c.n + atomic_load(&g_ring.dropped) + skipped >= samples - 1 && c.n <= samples);
    free(g_ring.rec);
}

/* ---- file layout, rotation, summary; writes out/c-sample.bin for test_symbolize.py */
static void test_file(void) {
    static ZpRegistry g;
    memset(&g, 0, sizeof g);
    int a = zp_claim(&g), b = zp_claim(&g);
    zp_publish(&g, a, 1, ZP_KIND_RENDER, 0x58, 0x7100abc000, 44, 0x1000, 0x9000, "g58");
    zp_publish(&g, b, 2, ZP_KIND_KICK, 0, 0, 0, 0, 0, "radv-kick");
    g.t[a].file_samples = 900, g.t[a].file_ext = 90, g.t[a].file_nofp = 450;
    g.t[b].file_samples = 100, g.t[b].file_ext = 100, g.t[b].file_nofp = 100;
    char line[256];
    zp_summary(line, sizeof line, &g, 6, true);
    assert(!strcmp(line, " R:g58=900/10%/50% radv-kick=100/100%/100%"));
    zp_summary(line, sizeof line, &g, 6, false);
    assert(!strcmp(line, " R:g58=900/?/50% radv-kick=100/?/100%"));
    assert(zp_slot(31, 30) == 1 && zp_slot(5, 30) == 5);
    zp_file_name(line, sizeof line, "/download0/zarecomp/r24prof", 7, 3);
    assert(!strcmp(line, "/download0/zarecomp/r24prof/samples-b7-s003.bin"));
    assert(zp_disk_bound(30, 1u << 16) == 2ull * 30 * (128 + 128 * 96 + 65536ull * 24));
    /* the file: header | 2 threads | 3 records */
    uint8_t buf[ZP_HEADER_BYTES + 2 * ZP_THREAD_BYTES + 3 * ZP_RECORD_BYTES];
    ZpFileHeader h = {7, 42, 1000, 21000000000ull, 0x400000 + 0x1230, 0x400000, 0x500000, 1000, 2, 3, 4, 5, 6, 0, 1000, (uint32_t)a};
    zp_write_header(buf, &h);
    zp_write_thread(buf + ZP_HEADER_BYTES, (uint32_t)a, &g.t[a]);
    zp_write_thread(buf + ZP_HEADER_BYTES + ZP_THREAD_BYTES, (uint32_t)b, &g.t[b]);
    ZpRec r[3] = {{0, (uint16_t)a, ZP_F_IN_TEXT | ZP_F_TEXT_KNOWN | ZP_F_CALLER, 0x400000 + 0x1100, 0x400000 + 0x1200},
                  {0, (uint16_t)a, ZP_F_IN_TEXT | ZP_F_TEXT_KNOWN, 0x400000 + 0x1100, 0},
                  {0, (uint16_t)b, ZP_F_TEXT_KNOWN, 0x7fff0000, 0}};
    for (int i = 0; i < 3; i++) zp_write_record(buf + ZP_HEADER_BYTES + 2 * ZP_THREAD_BYTES + i * ZP_RECORD_BYTES, &r[i]);
    assert(!memcmp(buf, "ZAPROF1", 8));
    uint32_t hb;
    memcpy(&hb, buf + 12, 4);
    assert(hb == ZP_HEADER_BYTES + 2 * ZP_THREAD_BYTES);
    mkdir("out", 0755);
    FILE *f = fopen("out/c-sample.bin", "wb");
    assert(f && fwrite(buf, 1, sizeof buf, f) == sizeof buf);
    fclose(f);
    puts("  file: header/thread/record layout (out/c-sample.bin), slot rotation, file names, disk bound, summary line");
}

int main(void) {
    setvbuf(stdout, NULL, _IONBF, 0);
    test_registry();
    test_rules();
    test_ring();
    test_on_sample();
    test_file();
    test_signals();
    puts("PASS test_core");
    return 0;
}
