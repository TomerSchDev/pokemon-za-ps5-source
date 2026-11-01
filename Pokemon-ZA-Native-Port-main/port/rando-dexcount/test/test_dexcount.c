/* Host tests (ASan + UBSan) for rando-dexcount.
 *
 * Runs the EXACT generated text of both hooked functions, original and patched (cut out of main_310.c / main_261.c
 * by extract-evaluator.py), against stub callees that model the decoded game functions:
 *   f_7000a11604  argument parser of the condition: x0 = op | arg0 << 32, x1 = arg1
 *   f_700033e770  Pokedex count(manager, kind, mode): returns the count of the asked list and, like any AAPCS64
 *                 callee, clobbers x1-x18 while preserving x19-x29, x30 and sp
 *   f_7000a11670  comparator, op codes decoded from its jump table (4 '<', 7 '>=', ...)
 *   the other panel callees (types 0, 1, 15, 16, 17, generic) return recognisable values
 * Guest memory is host memory (as in the runtime); the absolute guest addresses the two functions read (GOT slots of
 * the singletons and the panel's 4-entry jump table, whose real bytes are 0,18,26,34) are redirected by overriding
 * the LD8/LD64 macros of the real cpu.h.
 */
#include "cpu.h"

#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "za_dexcount.h"

typedef struct { uint8_t bytes[0x400]; } Obj;
static Obj g_mgr, g_o37c8, g_o3328, g_o3760, g_o33a0, g_o32b0, g_o3268;
static const struct { uint64_t slot; Obj *obj; } k_got[] = {
    {0x7003ec6230ull, &g_mgr},   {0x7003ec37c8ull, &g_o37c8}, {0x7003ec3328ull, &g_o3328}, {0x7003ec3760ull, &g_o3760},
    {0x7003ec33a0ull, &g_o33a0}, {0x7003ec32b0ull, &g_o32b0}, {0x7003ec3268ull, &g_o3268}};
static const uint8_t k_jump[4] = {0, 18, 26, 34}; /* image bytes at 0x70033a02e4 */
static inline uint64_t tmem_ld64(uint64_t a) {
    for (size_t i = 0; i < sizeof k_got / sizeof k_got[0]; i++)
        if (a == k_got[i].slot) return (uint64_t)(uintptr_t)k_got[i].obj;
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD64 %llx\n", (unsigned long long)a); abort(); }
    return *(const u64u *)(uintptr_t)a;
}
static inline uint8_t tmem_ld8(uint64_t a) {
    if (a >= 0x70033a02e4ull && a < 0x70033a02e8ull) return k_jump[a - 0x70033a02e4ull];
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD8 %llx\n", (unsigned long long)a); abort(); }
    return *(const u8a *)(uintptr_t)a;
}
#undef LD64
#define LD64(a) tmem_ld64((uint64_t)(a))
#undef LD8
#define LD8(a) tmem_ld8((uint64_t)(a))

volatile int g_fnprof = 0;
void fnprof_hit(uint64_t a, uint64_t lr, uint64_t x0) { (void)a, (void)lr, (void)x0; }
void rt_dispatch(Cpu *c) { (void)c; fprintf(stderr, "unexpected indirect dispatch\n"); abort(); }

/* ---- stub callees ---- */
static uint32_t s_op, s_arg0, s_arg1, s_count[2];
static int s_calls;
static uint64_t s_call_mgr[4];
static uint32_t s_call_kind[4], s_call_mode[4];

static void clobber(Cpu *c) {
    for (int r = 1; r <= 18; r++) c->x[r] = 0xdead0000ull + (uint64_t)r;
    c->nzcv = 0xf0000000ull;
}
void f_7000a11604(Cpu *c) { c->x[0] = (uint64_t)s_op | ((uint64_t)s_arg0 << 32); c->x[1] = s_arg1; }
void f_700033e770(Cpu *c) {
    assert(s_calls < 4);
    s_call_mgr[s_calls] = c->x[0];
    s_call_kind[s_calls] = (uint32_t)c->x[1];
    s_call_mode[s_calls] = (uint32_t)c->x[2];
    uint32_t kind = (uint32_t)c->x[1];
    s_calls++;
    clobber(c);
    c->x[0] = kind < 2 ? s_count[kind] : 0xffffffffull;
}
void f_7000a11670(Cpu *c) { /* runtime op codes, decoded from the jump table at 0x7003393e84 */
    uint32_t op = (uint32_t)c->x[0], v = *(uint32_t *)(uintptr_t)c->x[1];
    uint32_t a = *(uint32_t *)(uintptr_t)c->x[2], b = *(uint32_t *)(uintptr_t)c->x[3];
    uint32_t r;
    switch (op) {
    case 0: r = 1; break;
    case 2: r = v == a; break;
    case 3: r = v != a; break;
    case 4: r = v < a; break;
    case 5: r = v <= a; break;
    case 6: r = v > a; break;
    case 7: r = v >= a; break;
    case 8: r = a < v && v < b; break;
    case 9: r = a <= v && v <= b; break;
    default: r = 0; break;
    }
    c->x[0] = r;
}
/* panel callees for the other item types: distinct markers */
void f_70002bc834(Cpu *c) { clobber(c); c->x[0] = 1000; } /* type 0 */
void f_700082521c(Cpu *c) { clobber(c); c->x[0] = 1001; } /* type 1 */
void f_70001f0570(Cpu *c) { clobber(c); c->x[0] = 1015; } /* type 15 */
void f_700023c98c(Cpu *c) { clobber(c); c->x[0] = 1016; } /* type 16 */
void f_700067d564(Cpu *c) { clobber(c); c->x[0] = 1017; } /* type 17 */
void f_700082b728(Cpu *c) { clobber(c); c->x[0] = 1999; } /* generic / not ready */

/* the generated functions, renamed */
#include "evaluator_orig.inc"
#include "evaluator_patched.inc"
#include "panel_orig.inc"
#include "panel_patched.inc"

/* ---- harness ---- */
static uint64_t g_stack[512];
static int failures;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)

static void ready_all(int on) {
    *(uint32_t *)(g_mgr.bytes + 0xc0) = on ? 1u : 0u;
    *(uint32_t *)(g_o37c8.bytes + 0x200) = 1u;
    *(uint32_t *)(g_o3328.bytes + 0x200) = 1u;
    *(uint32_t *)(g_o3760.bytes + 0x40) = 1u;
    *(uint32_t *)(g_o33a0.bytes + 0x100) = 1u;
    *(uint32_t *)(g_o32b0.bytes + 0x140) = 1u;
    *(uint32_t *)(g_o3268.bytes + 0x180) = 1u;
}

static void prep_cpu(Cpu *c) {
    memset(c, 0, sizeof *c);
    c->sp = (uint64_t)(uintptr_t)&g_stack[480];
    for (int r = 19; r <= 29; r++) c->x[r] = 0x1900000000ull + (uint64_t)r;
    c->x[30] = 0x7000123456ull;
}
static void check_abi(const Cpu *c, uint64_t sp) {
    CHECK(c->sp == sp);
    for (int r = 19; r <= 29; r++) CHECK(c->x[r] == 0x1900000000ull + (uint64_t)r);
    CHECK(c->x[30] == 0x7000123456ull);
}

static int eval(void (*fn)(Cpu *), int ready, uint32_t lumiose, uint32_t hyper, uint32_t op, uint32_t thr) {
    static Cpu c;
    prep_cpu(&c);
    ready_all(ready);
    s_op = op, s_arg0 = thr, s_arg1 = 0, s_count[0] = lumiose, s_count[1] = hyper, s_calls = 0;
    c.x[1] = 0x1234; /* condition data pointer (only forwarded to the parser stub) */
    uint64_t sp = c.sp;
    fn(&c);
    check_abi(&c, sp);
    CHECK(c.x[0] <= 1);
    return (int)c.x[0];
}

static uint32_t panel(void (*fn)(Cpu *), int ready, uint32_t type, uint32_t lumiose, uint32_t hyper) {
    static Cpu c;
    static uint8_t item[0x100];
    prep_cpu(&c);
    ready_all(ready);
    memset(item, 0, sizeof item);
    *(uint32_t *)(item + 0x28) = type;
    s_count[0] = lumiose, s_count[1] = hyper, s_calls = 0;
    c.x[0] = (uint64_t)(uintptr_t)item;
    uint64_t sp = c.sp;
    fn(&c);
    check_abi(&c, sp);
    return (uint32_t)c.x[0];
}

static void *spin(void *arg) {
    (void)arg;
    for (uint32_t i = 0; i < 20000; i++) {
        CHECK(za_dexcount_combine(i % 233, i % 133) == i % 233 + i % 133);
        CHECK(za_dexcount_display(i % 233, i % 133) == i % 233 + i % 133);
    }
    return NULL;
}

int main(void) {
    za_dexcount_set_enabled(1);
    /* 1. evaluator: the bug and the fix (1 Lumiose + 5 Hyperspace, threshold 5) */
    CHECK(eval(orig_f_7000a1158c, 1, 1, 5, 7, 5) == 0);
    CHECK(s_calls == 1 && s_call_kind[0] == 0 && s_call_mode[0] == 0);
    CHECK(eval(patched_f_7000a1158c, 1, 1, 5, 7, 5) == 1);
    CHECK(s_calls == 2 && s_call_kind[0] == 0 && s_call_kind[1] == 1 && s_call_mode[1] == 0);
    CHECK(s_call_mgr[0] == (uint64_t)(uintptr_t)&g_mgr && s_call_mgr[1] == s_call_mgr[0]);
    CHECK(za_dexcount_last_lumiose() == 1 && za_dexcount_last_hyperspace() == 5 && za_dexcount_last_combined() == 6);
    /* 2. the "not yet" trigger (op '<') stops firing once the combined count is reached */
    CHECK(eval(orig_f_7000a1158c, 1, 1, 5, 4, 5) == 1);
    CHECK(eval(patched_f_7000a1158c, 1, 1, 5, 4, 5) == 0);
    CHECK(eval(patched_f_7000a1158c, 1, 1, 3, 4, 5) == 1);
    /* 3. disabled: identical to the original, one call */
    za_dexcount_set_enabled(0);
    uint64_t before = za_dexcount_evaluations(), dbefore = za_dexcount_displays();
    CHECK(eval(patched_f_7000a1158c, 1, 1, 5, 7, 5) == 0 && s_calls == 1);
    CHECK(panel(patched_f_700082b5c4, 1, 2, 3, 4) == 3 && s_calls == 1 && s_call_kind[0] == 0);
    CHECK(za_dexcount_evaluations() == before && za_dexcount_displays() == dbefore);
    za_dexcount_set_enabled(1);
    /* 4. manager not ready: evaluator makes no extra call; panel falls back to the generic path in both */
    CHECK(eval(patched_f_7000a1158c, 0, 1, 5, 7, 5) == 0 && s_calls == 1 && s_call_mgr[0] == 0);
    CHECK(panel(orig_f_700082b5c4, 0, 2, 3, 4) == 1999 && panel(patched_f_700082b5c4, 0, 2, 3, 4) == 1999);
    /* 5. panel: type 2 (have_pokemon_encyclopedia_total) shows the sum; every other type is unchanged */
    CHECK(panel(orig_f_700082b5c4, 1, 2, 3, 4) == 3 && s_calls == 1 && s_call_kind[0] == 0);
    CHECK(panel(patched_f_700082b5c4, 1, 2, 3, 4) == 7 && s_calls == 2 && s_call_kind[0] == 0 && s_call_kind[1] == 1);
    CHECK(s_call_mgr[0] == (uint64_t)(uintptr_t)&g_mgr && s_call_mgr[1] == s_call_mgr[0] && s_call_mode[1] == 0);
    for (uint32_t t = 0; t <= 20; t++) {
        if (t == 2) continue;
        uint32_t o = panel(orig_f_700082b5c4, 1, t, 3, 4), p = panel(patched_f_700082b5c4, 1, t, 3, 4);
        CHECK(o == p);
    }
    CHECK(panel(patched_f_700082b5c4, 1, 18, 3, 4) == 4);   /* Hyperspace dex's own item: Hyperspace only */
    CHECK(panel(patched_f_700082b5c4, 1, 0, 3, 4) == 1000);
    CHECK(panel(patched_f_700082b5c4, 1, 15, 3, 4) == 1015);
    CHECK(panel(patched_f_700082b5c4, 1, 99, 3, 4) == 1999);
    /* 6. exhaustive over the real ranges (232 Lumiose, 132 Hyperspace) and every research threshold 5..230 */
    for (uint32_t thr = 5; thr <= 230; thr += 5)
        for (uint32_t l = 0; l <= 232; l += 7)
            for (uint32_t h = 0; h <= 132; h += 11) {
                CHECK(eval(orig_f_7000a1158c, 1, l, h, 7, thr) == (l >= thr));
                CHECK(eval(patched_f_7000a1158c, 1, l, h, 7, thr) == (l + h >= thr));
                CHECK(eval(patched_f_7000a1158c, 1, l, h, 4, thr) == (l + h < thr));
                if (thr == 5) CHECK(panel(patched_f_700082b5c4, 1, 2, l, h) == l + h);
            }
    CHECK(eval(patched_f_7000a1158c, 1, 232, 132, 7, 230) == 1 && za_dexcount_last_combined() == 364);
    /* 7. saturating, never wraps */
    CHECK(za_dexcount_combine(UINT32_MAX - 1, 5) == UINT32_MAX && za_dexcount_display(UINT32_MAX, 1) == UINT32_MAX);
    CHECK(za_dexcount_combine(0, 0) == 0);
    /* 8. concurrent callers (game threads) */
    pthread_t t[8];
    for (int i = 0; i < 8; i++) CHECK(pthread_create(&t[i], NULL, spin, NULL) == 0);
    for (int i = 0; i < 8; i++) pthread_join(t[i], NULL);
    if (failures) { fprintf(stderr, "%d failure(s)\n", failures); return 1; }
    printf("test_dexcount: all checks passed (%llu evaluations, %llu panel reads)\n",
           (unsigned long long)za_dexcount_evaluations(), (unsigned long long)za_dexcount_displays());
    return 0;
}
