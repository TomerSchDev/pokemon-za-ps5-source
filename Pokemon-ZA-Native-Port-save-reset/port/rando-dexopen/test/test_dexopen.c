/* Host tests (ASan + UBSan) for rando-dexopen.
 *
 * Runs the EXACT generated text of both patched functions, original and patched (cut out of main_287.c / main_115.c by
 * extract-functions.py), against stub callees that model the decoded game functions:
 *   f_700000421c  key maker: copies the flag descriptor (x0) into the 32-byte key at x8 (+0x18 = refcounted holder, 0
 *                 for a static descriptor; the tests also exercise a non-zero holder so the untouched release path runs)
 *   f_70000393b8  FlagManager::GetBool(manager, key) -> w0 = the flag; like any AAPCS64 callee it clobbers x1-x18 and
 *                 preserves x19-x29, x30 and sp
 *   f_7000095a40  release of the key holder's last reference
 *   f_70002bc834  item count for the Mega Dex ownership check; f_70002901a4 "species/form registered"; the virtual
 *                 type-id call of the save-accessor objects (rt_dispatch); the special-species and mode-1 callees abort
 *                 (never reached by these inputs)
 * Guest memory is host memory (as in the runtime); the absolute guest addresses the two functions read (the flag
 * manager's readiness word, the GOT slots of the singletons, the type id, the default dex record) are redirected by
 * overriding the LD8/LD16/LD32/LD64 macros of the real cpu.h.
 */
#include "cpu.h"

#include <assert.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "za_dexopen.h"

#define FLAG_HASH 0x58e63b00d271631full /* FNV-1a 64 of "FLAG_DLC_DEX_ENABLE" (the descriptor's first word) */
#define DISPATCH_PC 0x7000c0ffee00ull
#define TYPE_ID 0x5151000051510000ull

typedef struct { uint8_t bytes[0x800]; } Obj;
static Obj g_flagmgr, g_singA, g_singB, g_saveacc, g_mgr, g_listobj, g_dexobj;
static uint64_t g_vtable[1] = {DISPATCH_PC};
static uint32_t g_default_record;
static const struct { uint64_t slot; Obj *obj; } k_got[] = {
    {0x7003ec3328ull, &g_flagmgr}, {0x7003ec32b0ull, &g_singA}, {0x7003ec32b8ull, &g_singB}, {0x7003ec28d8ull, &g_saveacc}};

static inline uint64_t tmem_ld64(uint64_t a) {
    for (size_t i = 0; i < sizeof k_got / sizeof k_got[0]; i++)
        if (a == k_got[i].slot) return (uint64_t)(uintptr_t)k_got[i].obj;
    if (a == 0x7003ec8498ull) return TYPE_ID;
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD64 %llx\n", (unsigned long long)a); abort(); }
    return *(const u64u *)(uintptr_t)a;
}
static inline uint32_t tmem_ld32(uint64_t a) {
    if (a == 0x700610e100ull) return *(uint32_t *)(g_flagmgr.bytes + 0x200); /* site 1 reads the readiness word by address */
    if (a == 0x7006135808ull) return g_default_record;
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD32 %llx\n", (unsigned long long)a); abort(); }
    return *(const u32u *)(uintptr_t)a;
}
static inline uint16_t tmem_ld16(uint64_t a) {
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD16 %llx\n", (unsigned long long)a); abort(); }
    return *(const u16u *)(uintptr_t)a;
}
static inline uint8_t tmem_ld8(uint64_t a) {
    if (a >= 0x7000000000ull && a < 0x7008000000ull) { fprintf(stderr, "unmapped guest LD8 %llx\n", (unsigned long long)a); abort(); }
    return *(const u8a *)(uintptr_t)a;
}
#undef LD64
#define LD64(a) tmem_ld64((uint64_t)(a))
#undef LD32
#define LD32(a) tmem_ld32((uint64_t)(a))
#undef LD16
#define LD16(a) tmem_ld16((uint64_t)(a))
#undef LD8
#define LD8(a) tmem_ld8((uint64_t)(a))

volatile int g_fnprof = 0;
void fnprof_hit(uint64_t a, uint64_t lr, uint64_t x0) { (void)a, (void)lr, (void)x0; }

static int failures;
#define CHECK(x) do { if (!(x)) { fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #x); failures++; } } while (0)

/* ---- stub callees ---- */
static void clobber(Cpu *c) {
    for (int r = 1; r <= 18; r++) c->x[r] = 0xdead0000ull + (uint64_t)r;
    c->nzcv = 0xf0000000ull;
}
static uint32_t s_flag;
static uint64_t s_holder;                 /* what the key maker puts at key+0x18 */
static int s_keymaker, s_getter, s_free, s_items, s_registered, s_dispatches;
static uint64_t s_keymaker_desc, s_getter_mgr, s_getter_key, s_free_obj, s_items_mgr;

void f_700000421c(Cpu *c) { /* key from descriptor: 24 bytes copied, +0x18 = holder */
    s_keymaker++;
    s_keymaker_desc = c->x[0];
    uint8_t *key = (uint8_t *)(uintptr_t)c->x[8];
    memset(key, 0, 0x20);
    *(uint64_t *)key = FLAG_HASH;
    *(uint64_t *)(key + 0x18) = s_holder;
    clobber(c);
}
void f_70000393b8(Cpu *c) { /* FlagManager::GetBool */
    s_getter++;
    s_getter_mgr = c->x[0];
    s_getter_key = c->x[1];
    CHECK(*(uint64_t *)(uintptr_t)c->x[1] == FLAG_HASH);
    clobber(c);
    c->x[0] = s_flag;
}
void f_7000095a40(Cpu *c) { s_free++; s_free_obj = c->x[0]; clobber(c); }
void f_70002bc834(Cpu *c) { /* item count: x0 = singleton A, x1 = item id */
    s_items++;
    s_items_mgr = c->x[0];
    uint32_t item = (uint32_t)c->x[1];
    clobber(c);
    c->x[0] = (item == 777 || item == 778) ? 1u : 0u;
}
void f_70002901a4(Cpu *c) { s_registered++; clobber(c); c->x[0] = 1; }
void f_700033fe14(Cpu *c) { (void)c; fprintf(stderr, "special species path reached\n"); abort(); }
void f_7000290030(Cpu *c) { (void)c; fprintf(stderr, "special species path reached\n"); abort(); }
void f_700033ff54(Cpu *c) { (void)c; fprintf(stderr, "mode-1 exclusion path reached\n"); abort(); }
void rt_dispatch(Cpu *c) { /* the save-accessor object's virtual type id */
    s_dispatches++;
    CHECK(c->pc == DISPATCH_PC);
    CHECK(c->x[0] == (uint64_t)(uintptr_t)(g_dexobj.bytes + 40));
    clobber(c);
    c->x[0] = TYPE_ID;
}

/* the generated functions, renamed */
#include "getter_orig.inc"
#include "getter_patched.inc"
#include "megadex_orig.inc"
#include "megadex_patched.inc"

/* ---- harness ---- */
static uint64_t g_stack[2048];

static void prep_cpu(Cpu *c) {
    memset(c, 0, sizeof *c);
    c->sp = (uint64_t)(uintptr_t)&g_stack[1024];
    for (int r = 19; r <= 29; r++) c->x[r] = 0x1900000000ull + (uint64_t)r;
    c->x[30] = 0x7000123456ull;
}
static void check_abi(const Cpu *c, uint64_t sp) {
    CHECK(c->sp == sp);
    for (int r = 19; r <= 29; r++) CHECK(c->x[r] == 0x1900000000ull + (uint64_t)r);
    CHECK(c->x[30] == 0x7000123456ull);
}
static void reset_counters(void) {
    s_keymaker = s_getter = s_free = s_items = s_registered = s_dispatches = 0;
    s_keymaker_desc = s_getter_mgr = s_getter_key = s_free_obj = s_items_mgr = 0;
}

typedef struct { uint64_t word; uint32_t rc; uint32_t aux; uint8_t aux2; uint8_t pad[7]; } Holder; /* +8 refcount */

/* site 1: DLC::IsHyperspaceDexEnabled */
static uint32_t getter(void (*fn)(Cpu *), uint32_t ready, uint32_t flag, Holder *holder) {
    static Cpu c;
    prep_cpu(&c);
    *(uint32_t *)(g_flagmgr.bytes + 0x200) = ready;
    s_flag = flag;
    s_holder = (uint64_t)(uintptr_t)holder;
    reset_counters();
    uint64_t sp = c.sp;
    fn(&c);
    check_abi(&c, sp);
    CHECK(c.x[0] <= 1);
    if (ready) {
        CHECK(s_keymaker == 1 && s_keymaker_desc == 0x7003e26880ull);
        CHECK(s_getter == 1 && s_getter_mgr == (uint64_t)(uintptr_t)&g_flagmgr && s_getter_key == sp - 0x40);
    } else {
        CHECK(s_keymaker == 0 && s_getter == 0 && s_free == 0);
    }
    return (uint32_t)c.x[0];
}

/* site 2: Pokedex::GetMegaDexCount - rows of the dex list as flatbuffer tables (fields: 1 species u32, 2 form, 4 bool
 * "Hyperspace row", 5 bool "counted without ownership"), ownership records, the save accessor's objects and records */
typedef struct __attribute__((packed)) { int32_t soff; uint32_t species; uint32_t form; uint8_t hyper, always; uint8_t pad[2]; } Row;
typedef struct { uint16_t vtsize, tblsize, off[6]; } VT;
static VT g_vt = {16, 16, {0, 4, 8, 0, 12, 13}};
static Row g_rows[8];
static uint64_t g_rowptrs[8];
typedef struct { uint16_t species, form; uint32_t item; } Own;
static Own g_own[8];
static uint64_t g_objptrs[1];
static uint8_t g_records[64][0x84];

static void row(int i, uint32_t species, uint32_t form, int hyper, int always) {
    g_rows[i].soff = (int32_t)((intptr_t)&g_rows[i] - (intptr_t)&g_vt);
    g_rows[i].species = species;
    g_rows[i].form = form;
    g_rows[i].hyper = (uint8_t)hyper;
    g_rows[i].always = (uint8_t)always;
    g_rowptrs[i] = (uint64_t)(uintptr_t)&g_rows[i];
}

static void setup_megadex(int nrows, int nown, int singA_ready, int singB_ready) {
    memset(&g_mgr, 0, sizeof g_mgr), memset(&g_listobj, 0, sizeof g_listobj), memset(&g_dexobj, 0, sizeof g_dexobj);
    memset(&g_singA, 0, sizeof g_singA), memset(&g_singB, 0, sizeof g_singB), memset(&g_saveacc, 0, sizeof g_saveacc);
    *(uint64_t *)(g_mgr.bytes + 0x60) = (uint64_t)(uintptr_t)&g_listobj;
    *(uint64_t *)(g_listobj.bytes + 256) = (uint64_t)(uintptr_t)&g_rowptrs[0];
    *(uint64_t *)(g_listobj.bytes + 264) = (uint64_t)(uintptr_t)&g_rowptrs[nrows];
    *(uint64_t *)(g_mgr.bytes + 16) = (uint64_t)(uintptr_t)&g_own[0];
    *(uint64_t *)(g_mgr.bytes + 24) = (uint64_t)(uintptr_t)&g_own[nown];
    *(uint32_t *)(g_singA.bytes + 0x140) = singA_ready ? 1u : 0u;
    *(uint32_t *)(g_singB.bytes + 0x140) = singB_ready ? 1u : 0u;
    *(uint32_t *)(g_saveacc.bytes + 0x400) = 1u;
    g_objptrs[0] = (uint64_t)(uintptr_t)&g_dexobj;
    *(uint64_t *)(g_saveacc.bytes + 0x190) = (uint64_t)(uintptr_t)&g_objptrs[0];
    *(uint64_t *)(g_saveacc.bytes + 0x198) = (uint64_t)(uintptr_t)&g_objptrs[1];
    *(uint64_t *)(g_dexobj.bytes + 40) = (uint64_t)(uintptr_t)g_vtable;
    *(uint64_t *)(g_dexobj.bytes + 0x40) = (uint64_t)(uintptr_t)&g_records[0][0];
}

static uint32_t megadex(void (*fn)(Cpu *), uint32_t fm_ready, uint32_t flag, uint32_t mode, Holder *holder) {
    static Cpu c;
    prep_cpu(&c);
    *(uint32_t *)(g_flagmgr.bytes + 0x200) = fm_ready;
    s_flag = flag;
    s_holder = (uint64_t)(uintptr_t)holder;
    reset_counters();
    c.x[0] = (uint64_t)(uintptr_t)&g_mgr;
    c.x[1] = mode;
    uint64_t sp = c.sp;
    fn(&c);
    check_abi(&c, sp);
    return (uint32_t)c.x[0];
}

static void *spin(void *arg) { /* constant inputs: the counters race, the trace stays quiet after the first line */
    (void)arg;
    for (uint32_t i = 0; i < 20000; i++) {
        CHECK(za_dexopen_hyperspace_dex_enabled(1, 1) == 1);
        CHECK(za_dexopen_mega_dex_flag(1) == 1);
    }
    return NULL;
}

int main(void) {
    const int G = ZA_DEXOPEN_SITE_GETTER, M = ZA_DEXOPEN_SITE_MEGADEX;
    za_dexopen_set_enabled(1);
    /* 1. the trace fires once per site on first use, then only when the game's own flag value changes */
    CHECK(za_dexopen_trace_lines(G) == 0 && za_dexopen_last_flag(G) == ZA_DEXOPEN_FLAG_UNKNOWN);
    CHECK(getter(patched_f_70008d4178, 1, 0, NULL) == 1);
    CHECK(za_dexopen_trace_lines(G) == 1 && za_dexopen_last_flag(G) == 0 && za_dexopen_forced(G) == 1);
    for (int i = 0; i < 5; i++) CHECK(getter(patched_f_70008d4178, 1, 0, NULL) == 1);
    CHECK(za_dexopen_trace_lines(G) == 1 && za_dexopen_calls(G) == 6 && za_dexopen_forced(G) == 6);
    CHECK(getter(patched_f_70008d4178, 1, 1, NULL) == 1);
    CHECK(za_dexopen_trace_lines(G) == 2 && za_dexopen_last_flag(G) == 1 && za_dexopen_forced(G) == 6);
    CHECK(getter(patched_f_70008d4178, 0, 1, NULL) == 0); /* manager not ready: the getter is not reached */
    CHECK(za_dexopen_trace_lines(G) == 3 && za_dexopen_last_flag(G) == ZA_DEXOPEN_FLAG_UNKNOWN && za_dexopen_forced(G) == 6);
    /* 2. site 1: the original ANDs the flag in; the patch returns readiness alone */
    CHECK(getter(orig_f_70008d4178, 1, 0, NULL) == 0);
    CHECK(getter(orig_f_70008d4178, 1, 1, NULL) == 1);
    CHECK(getter(orig_f_70008d4178, 0, 0, NULL) == 0 && getter(orig_f_70008d4178, 0, 1, NULL) == 0);
    CHECK(getter(patched_f_70008d4178, 1, 0, NULL) == 1);
    CHECK(getter(patched_f_70008d4178, 1, 1, NULL) == 1);
    CHECK(getter(patched_f_70008d4178, 0, 0, NULL) == 0 && getter(patched_f_70008d4178, 0, 1, NULL) == 0);
    CHECK(getter(orig_f_70008d4178, 1, 0x101, NULL) == 1 && getter(patched_f_70008d4178, 1, 0x101, NULL) == 1); /* w8 & w19 */
    /* 3. switch off: identical to the original at both sites */
    za_dexopen_set_enabled(0);
    uint64_t forced_before = za_dexopen_forced(G);
    CHECK(getter(patched_f_70008d4178, 1, 0, NULL) == 0 && getter(patched_f_70008d4178, 1, 1, NULL) == 1);
    CHECK(getter(patched_f_70008d4178, 0, 1, NULL) == 0 && getter(patched_f_70008d4178, 1, 0x100, NULL) == 0);
    CHECK(za_dexopen_forced(G) == forced_before);
    za_dexopen_set_enabled(1);
    /* 4. the untouched release of the key holder: same calls in both (a static descriptor gives holder 0) */
    Holder h;
    for (int variant = 0; variant < 2; variant++) {
        void (*fn)(Cpu *) = variant ? patched_f_70008d4178 : orig_f_70008d4178;
        memset(&h, 0, sizeof h); h.rc = 0x401; /* flags 1, one reference: last -> f_7000095a40(holder) */
        CHECK(getter(fn, 1, 1, &h) == 1 && s_free == 1 && s_free_obj == (uint64_t)(uintptr_t)&h && h.rc == 0x1);
        memset(&h, 0, sizeof h); h.rc = 0x801; /* two references: decremented, not released */
        CHECK(getter(fn, 1, 1, &h) == 1 && s_free == 0 && h.rc == 0x401);
        memset(&h, 0, sizeof h); h.rc = 0x400; /* flag bits 0: not refcounted */
        CHECK(getter(fn, 1, 1, &h) == 1 && s_free == 0 && h.rc == 0x400);
    }
    /* 5. site 2: rows 10 (Lumiose), 20 (Hyperspace, owned), 30 (Hyperspace, counted without ownership) */
    row(0, 10, 0, 0, 0); row(1, 20, 0, 1, 0); row(2, 30, 0, 1, 1);
    g_own[0] = (Own){10, 0, 777}; g_own[1] = (Own){20, 0, 778};
    memset(g_records, 0, sizeof g_records);
    *(uint32_t *)g_records[10] = 1; *(uint32_t *)g_records[20] = 1; *(uint32_t *)g_records[30] = 1;
    setup_megadex(3, 2, 1, 1);
    uint64_t mcalls = za_dexopen_calls(M);
    CHECK(megadex(orig_f_700033f8d8, 1, 0, 0, NULL) == 1 && s_getter == 1 && s_dispatches == 1 && s_items == 1);
    CHECK(megadex(orig_f_700033f8d8, 1, 1, 0, NULL) == 3 && s_dispatches == 3 && s_items == 2);
    CHECK(za_dexopen_calls(M) == mcalls); /* the original never calls the helper */
    CHECK(megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 3 && s_getter == 1 && s_dispatches == 3 && s_items == 2);
    CHECK(za_dexopen_calls(M) == mcalls + 1 && za_dexopen_forced(M) == 1 && za_dexopen_last_flag(M) == 0 && za_dexopen_trace_lines(M) == 1);
    CHECK(megadex(patched_f_700033f8d8, 1, 1, 0, NULL) == 3 && za_dexopen_forced(M) == 1 && za_dexopen_trace_lines(M) == 2);
    for (int i = 0; i < 4; i++) CHECK(megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 3);
    CHECK(za_dexopen_trace_lines(M) == 3 && za_dexopen_calls(M) == mcalls + 6);
    /* flag manager not ready: no getter call, no helper call, Hyperspace rows filtered in both */
    CHECK(megadex(orig_f_700033f8d8, 0, 1, 0, NULL) == 1 && s_getter == 0);
    CHECK(megadex(patched_f_700033f8d8, 0, 1, 0, NULL) == 1 && s_getter == 0 && za_dexopen_calls(M) == mcalls + 6);
    /* switch off: the original count */
    za_dexopen_set_enabled(0);
    CHECK(megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 1 && megadex(patched_f_700033f8d8, 1, 1, 0, NULL) == 3);
    za_dexopen_set_enabled(1);
    /* the Pokedex singleton not ready: 0 in both before anything is read; the item singleton not ready: owned rows drop */
    setup_megadex(3, 2, 0, 1);
    CHECK(megadex(orig_f_700033f8d8, 1, 1, 0, NULL) == 0 && megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 0 && s_getter == 0);
    setup_megadex(3, 2, 1, 0);
    CHECK(megadex(orig_f_700033f8d8, 1, 1, 0, NULL) == 0 && megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 0);
    /* an empty list: 0 in both, the flag read still happens */
    setup_megadex(0, 2, 1, 1);
    CHECK(megadex(orig_f_700033f8d8, 1, 0, 0, NULL) == 0 && s_getter == 1);
    CHECK(megadex(patched_f_700033f8d8, 1, 0, 0, NULL) == 0 && s_getter == 1);
    /* the key-holder release inside site 2, untouched */
    setup_megadex(3, 2, 1, 1);
    memset(&h, 0, sizeof h); h.rc = 0x401;
    CHECK(megadex(orig_f_700033f8d8, 1, 1, 0, &h) == 3 && s_free == 1 && h.rc == 1);
    memset(&h, 0, sizeof h); h.rc = 0x401;
    CHECK(megadex(patched_f_700033f8d8, 1, 0, 0, &h) == 3 && s_free == 1 && h.rc == 1);
    /* 6. no row is ever marked: the records are read, never written */
    CHECK(*(uint32_t *)g_records[10] == 1 && *(uint32_t *)g_records[20] == 1 && *(uint32_t *)g_records[30] == 1);
    for (int s = 0; s < 64; s++) if (s != 10 && s != 20 && s != 30) CHECK(*(uint32_t *)g_records[s] == 0);
    /* 7. concurrent callers (game threads): 8 x 20000 x 2 calls, counted exactly, no new trace line after the first */
    uint64_t gc = za_dexopen_calls(G), mc = za_dexopen_calls(M);
    CHECK(za_dexopen_hyperspace_dex_enabled(1, 1) == 1 && za_dexopen_mega_dex_flag(1) == 1);
    uint64_t gl = za_dexopen_trace_lines(G), ml = za_dexopen_trace_lines(M);
    pthread_t t[8];
    for (int i = 0; i < 8; i++) CHECK(pthread_create(&t[i], NULL, spin, NULL) == 0);
    for (int i = 0; i < 8; i++) pthread_join(t[i], NULL);
    CHECK(za_dexopen_calls(G) == gc + 1 + 8 * 20000 && za_dexopen_calls(M) == mc + 1 + 8 * 20000);
    CHECK(za_dexopen_trace_lines(G) == gl && za_dexopen_trace_lines(M) == ml);
    if (failures) { fprintf(stderr, "%d failure(s)\n", failures); return 1; }
    printf("test_dexopen: all checks passed (getter calls %llu, mega-dex calls %llu, trace lines %llu + %llu)\n",
           (unsigned long long)za_dexopen_calls(G), (unsigned long long)za_dexopen_calls(M),
           (unsigned long long)za_dexopen_trace_lines(G), (unsigned long long)za_dexopen_trace_lines(M));
    return 0;
}
