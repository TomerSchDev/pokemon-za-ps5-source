// r28a texfix host tests: the live list (za_texlive_r28a.h), the lifetime guard and its reports
// (za_texguard_api_r28a.h, za_texguard_r28a.h) and the quarantine (za_texquarantine_r28a.h) - the very files the PS5
// build copies into the runtime - under ASan + UBSan and under TSan (run-host-tests.sh). The registration and
// finalize paths are modelled on textures.c tex_backend_at / backend_texture_destroyed / vk_textures_reset and
// objects.c nvnTextureFinalize as r28a has them, without the Vulkan work.
#define _GNU_SOURCE
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "texfix_mirror.h"

static int g_log_lines;
static char g_last_log[512];
static pthread_mutex_t g_log_lock = PTHREAD_MUTEX_INITIALIZER;
static void test_log(const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    pthread_mutex_lock(&g_log_lock);
    vsnprintf(g_last_log, sizeof g_last_log, fmt, ap);
    g_log_lines++;
    fputs(g_last_log, stderr);
    pthread_mutex_unlock(&g_log_lock);
    va_end(ap);
}
static int log_lines(void) {
    pthread_mutex_lock(&g_log_lock);
    int n = g_log_lines;
    pthread_mutex_unlock(&g_log_lock);
    return n;
}
static uint64_t g_frame;

#define ZA_TG_LOG(...) test_log(__VA_ARGS__)
#define ZA_TG_FRAME() g_frame
#include "../src/za_texguard_api_r28a.h"
#include "../src/za_texguard_r28a.h"
#include "../src/za_texlive_r28a.h"
#define ZA_TEX_QUARANTINE 64  // (the runtime's 4096; small here, so the ring wraps many times)
#include "../src/za_texquarantine_r28a.h"

#define CHECK(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)

static NvnTexture *tex_new(void) {
    NvnTexture *t = calloc(1, sizeof *t);
    CHECK(t);
    t->za_guard = NVN_TEX_LIVE;  // (objects.c texture_from_builder)
    return t;
}

// textures.c tex_backend_at, its registration half (r28a): a backend only for a live texture
static TexBackend g_dead_dummy;
static TexBackend *model_tex_backend(NvnTexture *t, const void *caller) {
    TexBackend *b = t->backend;
    if (b) return b;
    if (!nvn_tex_live(t)) {
        za_texguard_hit(ZA_TG_REGISTER, t, t->za_guard, caller);
        return &g_dead_dummy;
    }
    b = calloc(1, sizeof *b);
    CHECK(b);
    t->backend = b;
    CHECK(za_live_add(t, b));
    return b;
}

// objects.c nvnTextureFinalize + textures.c backend_texture_destroyed (r28a), serialized by the caller (exec_lock)
static void model_finalize(NvnTexture *t) {
    if (t->za_guard != NVN_TEX_LIVE) {
        za_texguard_hit(ZA_TG_FINALIZE_AGAIN, t, t->za_guard, NULL);
        return;
    }
    TexBackend *b = t->backend;
    if (b) {
        t->backend = NULL;
        void *pending = b->pending_rgba;
        b->pending_rgba = NULL;
        za_live_remove(t, b);
        free(pending);
        free(b);
    }
    t->za_guard = NVN_TEX_DEAD;
    za_quarantine_push(t);
}

// textures.c vk_textures_reset (r28a)
static int model_reset(void) {
    int n = 0;
    NvnTexture *t;
    TexBackend *b;
    while (za_live_pop(&t, &b)) {
        n++;
        CHECK(b->reg == 0);
        if (nvn_tex_live(t) && t->backend == b) {
            t->backend = NULL;
            free(b);
        } else {
            free(b);  // (za_backend_drop: the texture is not followed)
        }
    }
    return n;
}

// the list's invariant: slot i holds a backend whose reg is i + 1 (never dereferences a texture entry)
static void check_list(void) {
    pthread_mutex_lock(&za_live_lock);
    for (int i = 0; i < g_nlive; i++) {
        CHECK(g_live[i] != NULL);
        CHECK(g_live_b[i] != NULL);
        CHECK(g_live_b[i]->reg == i + 1);
    }
    for (int i = 0; i < g_nlive; i++)
        for (int k = i + 1; k < g_nlive && k < i + 8; k++) CHECK(g_live_b[i] != g_live_b[k]);
    pthread_mutex_unlock(&za_live_lock);
}

static uint64_t rng = 88172645463325252ull;
static uint32_t rnd(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)rng; }

// 1. add / remove / swap, the list growing past 1024 and 2048 entries, finalizes in random order; after each
//    finalize, the stale pointer asks for a backend again (r28-play's way in): refused, not listed, not written
static void test_add_remove(void) {
    enum { N = 3000 };
    static NvnTexture *t[N];
    static int order[N];
    for (int i = 0; i < N; i++) {
        t[i] = tex_new();
        CHECK(model_tex_backend(t[i], NULL) != &g_dead_dummy);
        order[i] = i;
    }
    CHECK(za_live_count() == N);
    check_list();
    for (int i = N - 1; i > 0; i--) {
        int j = (int)(rnd() % (uint32_t)(i + 1)), x = order[i];
        order[i] = order[j], order[j] = x;
    }
    int lines = log_lines();
    for (int k = 0; k < N; k++) {
        NvnTexture *s = t[order[k]];
        model_finalize(s);
        int before = za_live_count();
        CHECK(model_tex_backend(s, (const void *)0x1111) == &g_dead_dummy);  // (s is in quarantine: readable, DEAD)
        CHECK(model_tex_backend(s, (const void *)0x2222) == &g_dead_dummy);
        CHECK(s->backend == NULL);
        CHECK(za_live_count() == before);
        if (k % 61 == 0) check_list();
    }
    CHECK(za_live_count() == 0);
    CHECK(log_lines() == lines + 2);  // (once per (site, caller): two callers, 6000 refusals)
    CHECK(za_tg_count[ZA_TG_REGISTER] >= 2 * N);
    printf("ok 1 add/remove/swap: %d textures, %d stale registrations refused, 2 lines\n", N, 2 * N);
}

// 2. reboot: every pair popped, nothing followed that is not live
static void test_reset(void) {
    enum { N = 1500 };
    for (int i = 0; i < N; i++) model_tex_backend(tex_new(), NULL);
    static NvnTexture *keep[N];
    pthread_mutex_lock(&za_live_lock);
    for (int i = 0; i < g_nlive; i++) keep[i] = g_live[i];
    pthread_mutex_unlock(&za_live_lock);
    CHECK(model_reset() == N);
    CHECK(za_live_count() == 0);
    for (int i = 0; i < N; i++) {
        CHECK(keep[i]->backend == NULL);
        free(keep[i]);
    }
    printf("ok 2 reset: %d pairs released\n", N);
}

// 3. remove with a wrong reg: reported once, repaired by a scan, the other entries intact
static void test_mismatch(void) {
    NvnTexture *a = tex_new(), *b = tex_new(), *c = tex_new();
    TexBackend *ba = model_tex_backend(a, NULL), *bb = model_tex_backend(b, NULL), *bc = model_tex_backend(c, NULL);
    int lines = log_lines();
    bb->reg = 77;  // out of range
    za_live_remove(b, bb);
    CHECK(log_lines() == lines + 1 && strstr(g_last_log, "live-list"));
    CHECK(bb->reg == 0 && za_live_count() == 2);
    check_list();
    b->backend = NULL;
    free(bb);
    // a reg naming another entry's slot: that entry stays
    TexBackend *bb2 = model_tex_backend(b, NULL);
    bb2->reg = ba->reg;
    za_live_remove(b, bb2);
    CHECK(za_live_count() == 2);
    check_list();
    pthread_mutex_lock(&za_live_lock);
    bool a_in = false, c_in = false, b_in = false;
    for (int i = 0; i < g_nlive; i++) a_in |= g_live_b[i] == ba, c_in |= g_live_b[i] == bc, b_in |= g_live_b[i] == bb2;
    pthread_mutex_unlock(&za_live_lock);
    CHECK(a_in && c_in && !b_in);
    b->backend = NULL;
    free(bb2);
    // a backend never listed (reg 0): nothing happens
    TexBackend lone = {0};
    za_live_remove(b, &lone);
    CHECK(za_live_count() == 2);
    model_finalize(a);
    model_finalize(c);
    model_finalize(b);
    CHECK(za_live_count() == 0);
    printf("ok 3 mismatch: reported, repaired, neighbours intact\n");
}

// 4. r28-play's crash: the list's last entry is a texture whose memory was freed and reused (0x2 where its backend
//    pointer was). r28-play's live_remove read that entry's backend and wrote to 0x2 + 0xa0. Here the list never
//    follows a texture entry: removing another entry and the reboot's pop touch only the backends (ASan: no report
//    for the freed texture; the reused one is never read)
static void test_stale_entry_never_followed(void) {
    NvnTexture *a = tex_new();
    TexBackend *ba = model_tex_backend(a, NULL);
    NvnTexture *s = tex_new();
    TexBackend *bs = model_tex_backend(s, NULL);
    free(s);  // behind the list's back (the old way: freed while listed) - any access to s now is an ASan report
    a->backend = NULL;
    za_live_remove(a, ba);  // the swap moves s's pair into slot 0 through bs only
    free(ba);
    model_finalize(a);
    check_list();
    CHECK(bs->reg == 1 && za_live_count() == 1);
    NvnTexture *t;
    TexBackend *b;
    CHECK(za_live_pop(&t, &b) && t == s && b == bs && za_live_count() == 0);
    free(bs);
    // the same with the memory reused (not freed): 0x2 at ->backend, no guard; the reboot drops the pair without
    // following the texture
    NvnTexture *r = tex_new();
    TexBackend *br = model_tex_backend(r, NULL);
    NvnTexture *q = tex_new();
    TexBackend *bq = model_tex_backend(q, NULL);
    memset(r, 0, sizeof *r);
    r->backend = (void *)(uintptr_t)0x2;
    q->backend = NULL;
    za_live_remove(q, bq);  // r's pair (last) moves into q's slot: bq / br only
    free(bq);
    model_finalize(q);
    CHECK(br->reg == 1);
    CHECK(model_reset() == 1);  // (r not live: br dropped, r->backend - 0x2 - never followed)
    free(r);
    printf("ok 4 stale texture entry (freed / reused with backend 0x2) never followed\n");
}

// 5. finalize twice (a guest copy of the object): refused, quarantined once; the quarantine wraps many times
static void test_quarantine(void) {
    uint64_t total = za_quar_total;
    int lines = log_lines();
    for (int i = 0; i < 10 * ZA_TEX_QUARANTINE; i++) {
        NvnTexture *t = tex_new();
        model_tex_backend(t, NULL);
        model_finalize(t);
        CHECK(t->za_guard == NVN_TEX_DEAD);  // (still in the ring: readable)
        model_finalize(t);                   // second finalize: refused (would be a double free once evicted)
        CHECK(model_tex_backend(t, (const void *)0x3333) == &g_dead_dummy);
    }
    CHECK(za_quar_total == total + 10 * ZA_TEX_QUARANTINE);
    CHECK(log_lines() == lines + 2);  // finalize-again and register (caller 0x3333): once each
    CHECK(za_live_count() == 0);
    printf("ok 5 quarantine: %d finalizes, wrapped %dx, double finalize refused\n", 10 * ZA_TEX_QUARANTINE, 10);
}

// 6. the counts: a line at a summary frame when they changed, none when they did not
static void test_summary(void) {
    int lines = log_lines();
    za_texguard_frame(ZA_TG_SUMMARY_FRAMES * 3 + 1);  // (not a summary frame)
    CHECK(log_lines() == lines);
    za_texguard_frame(ZA_TG_SUMMARY_FRAMES * 3);
    CHECK(log_lines() == lines + 1 && strstr(g_last_log, "counts at frame") && strstr(g_last_log, "register="));
    za_texguard_frame(ZA_TG_SUMMARY_FRAMES * 4);  // (unchanged)
    CHECK(log_lines() == lines + 1);
    za_texguard_hit(ZA_TG_PRESENT, NULL, 0, (const void *)0x4444);
    za_texguard_frame(ZA_TG_SUMMARY_FRAMES * 5);
    CHECK(log_lines() == lines + 3 && strstr(g_last_log, "present=1"));
    printf("ok 6 summary lines only when the counts changed\n");
}

// 7. threads: textures created, registered, finalized on several threads at once (the present path and finalizes
//    on game threads), a walker (hd_switch) and reports alongside; TSan sees every access ordered by the lock
static int walk_bad;
static void walk_check(NvnTexture *t, TexBackend *b, void *arg) {
    (void)t;
    int *n = arg;
    (*n)++;
    if (b->reg != *n) walk_bad++;  // (a walk sees slot i's backend with reg i + 1)
}
static void *walker(void *arg) {
    int *stop = arg;
    uint64_t f = 0;
    while (!__atomic_load_n(stop, __ATOMIC_ACQUIRE)) {
        int n = 0;
        za_live_walk(walk_check, &n);
        za_texguard_frame(++f * ZA_TG_SUMMARY_FRAMES);
    }
    return NULL;
}
static void *worker(void *arg) {
    uint64_t r = (uintptr_t)arg * 0x9E3779B97F4A7C15ull + 1;
    NvnTexture *mine[48];
    int n = 0;
    for (int it = 0; it < 30000; it++) {
        r ^= r << 13, r ^= r >> 7, r ^= r << 17;
        if (n < 48 && (r & 1)) {
            NvnTexture *t = tex_new();
            TexBackend *b = calloc(1, sizeof *b);
            t->backend = b;
            CHECK(za_live_add(t, b));
            mine[n++] = t;
        } else if (n) {
            int k = (int)((r >> 8) % (uint64_t)n);
            NvnTexture *t = mine[k];
            mine[k] = mine[--n];
            TexBackend *b = t->backend;
            t->backend = NULL;
            za_live_remove(t, b);
            free(b);
            free(t);
        }
        if ((r & 0x3ff) == 7) za_texguard_hit(ZA_TG_SET_RT, NULL, 0, (const void *)(uintptr_t)(0x5000 + (r & 0x30)));
    }
    while (n) {
        NvnTexture *t = mine[--n];
        TexBackend *b = t->backend;
        za_live_remove(t, b);
        free(b);
        free(t);
    }
    return NULL;
}
static void test_threads(void) {
    enum { W = 8 };
    pthread_t th[W], wk;
    int stop = 0;
    CHECK(!pthread_create(&wk, NULL, walker, &stop));
    for (int i = 0; i < W; i++) CHECK(!pthread_create(&th[i], NULL, worker, (void *)(uintptr_t)(i + 1)));
    for (int i = 0; i < W; i++) pthread_join(th[i], NULL);
    __atomic_store_n(&stop, 1, __ATOMIC_RELEASE);
    pthread_join(wk, NULL);
    CHECK(walk_bad == 0);
    CHECK(za_live_count() == 0);
    check_list();
    printf("ok 7 threads: %d workers x 30000 add/remove, a walker and reports - consistent\n", W);
}

int main(void) {
    test_add_remove();
    test_reset();
    test_mismatch();
    test_stale_entry_never_followed();
    test_quarantine();
    test_summary();
    test_threads();
    free(g_live);
    free(g_live_b);
    printf("ALL TESTS PASSED\n");
    return 0;
}
