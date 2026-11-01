/* r24-prof sampling profiler: the logic that does not touch the console (registry, ring, caller guard, file
 * layout, rotation, summary line). za_prof.c (the title) and test/test_core.c (host, ASan/UBSan) both use it.
 *
 * Signal-handler rules for everything the handler calls here: no locks, no malloc, no stdio, no thread-local
 * storage (the title's TLS is emulated: __emutls_get_address may allocate), only lock-free atomics on fixed
 * arrays allocated before the handler is installed. */
#pragma once
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define ZP_MAX_THREADS 128
#define ZP_NAME 32
#define ZP_FILE_VERSION 1u
#define ZP_HEADER_BYTES 128u
#define ZP_THREAD_BYTES 96u
#define ZP_RECORD_BYTES 24u
#define ZP_KEEP_BOOTS 2u   /* sample files of this boot and the previous one stay; older ones are deleted */
#define ZP_MAX_KEEP 200u

enum { ZP_KIND_GUEST = 0, ZP_KIND_RENDER = 1, ZP_KIND_KICK = 2, ZP_KIND_OTHER = 3 };
enum { ZP_FREE = 0, ZP_CLAIMED = 1, ZP_ACTIVE = 2, ZP_ENDED = 3 };
enum { ZP_F_IN_TEXT = 1, ZP_F_CALLER = 2, ZP_F_TEXT_KNOWN = 4 };

typedef struct {
    _Atomic int state;             /* ZP_FREE / CLAIMED (being filled) / ACTIVE (handler may use it) / ENDED */
    _Atomic uintptr_t tid;         /* pthread_self() of the thread, as an integer */
    _Atomic int kind;              /* ZP_KIND_* (a guest thread becomes RENDER at its first submission) */
    _Atomic uint32_t ended_window; /* window in which it ended: a slot is reused two windows later at the earliest */
    int32_t prio;
    uint64_t gid, entry;           /* guest thread id and entry (0 for host threads) */
    uintptr_t lo, hi;              /* host stack range; 0/0 = unknown (no caller then) */
    char name[ZP_NAME];
    _Atomic uint32_t win_samples, win_ext, win_nofp; /* this window: samples, RIP outside the text, no caller */
    uint32_t file_samples, file_ext, file_nofp;      /* (the writer's copy of the window that went to a file) */
} ZpThread;

typedef struct {
    ZpThread t[ZP_MAX_THREADS];
    _Atomic uint32_t window;  /* current window number (for slot reuse) */
    _Atomic uint32_t full;    /* registrations refused: no free slot */
} ZpRegistry;

/* ---- registry (registration: normal context; lookup: signal handler) */

/* Claims a slot (a never-used one first, else one that ended two windows ago or more); -1 when full. */
static inline int zp_claim(ZpRegistry *g) {
    uint32_t now = atomic_load_explicit(&g->window, memory_order_relaxed);
    for (int pass = 0; pass < 2; pass++)
        for (int i = 0; i < ZP_MAX_THREADS; i++) {
            ZpThread *t = &g->t[i];
            int s = atomic_load_explicit(&t->state, memory_order_acquire);
            if (pass == 0 && s != ZP_FREE) continue;
            if (pass == 1 && (s != ZP_ENDED || atomic_load_explicit(&t->ended_window, memory_order_relaxed) + 2 > now))
                continue;
            if (atomic_compare_exchange_strong_explicit(&t->state, &s, ZP_CLAIMED, memory_order_acq_rel,
                                                        memory_order_relaxed))
                return i;
        }
    atomic_fetch_add_explicit(&g->full, 1, memory_order_relaxed);
    return -1;
}

/* Fills a claimed slot and publishes it (release: the handler sees complete fields once it sees ACTIVE). */
static inline void zp_publish(ZpRegistry *g, int i, uintptr_t tid, int kind, uint64_t gid, uint64_t entry,
                              int32_t prio, uintptr_t lo, uintptr_t hi, const char *name) {
    ZpThread *t = &g->t[i];
    t->gid = gid, t->entry = entry, t->prio = prio, t->lo = lo, t->hi = hi;
    snprintf(t->name, sizeof t->name, "%s", name ? name : "?");
    atomic_store_explicit(&t->kind, kind, memory_order_relaxed);
    atomic_store_explicit(&t->win_samples, 0, memory_order_relaxed);
    atomic_store_explicit(&t->win_ext, 0, memory_order_relaxed);
    atomic_store_explicit(&t->win_nofp, 0, memory_order_relaxed);
    atomic_store_explicit(&t->tid, tid, memory_order_relaxed);
    atomic_store_explicit(&t->state, ZP_ACTIVE, memory_order_release);
}

/* Async-signal-safe: the ACTIVE slot of this thread, or -1. */
static inline int zp_lookup(const ZpRegistry *g, uintptr_t tid) {
    for (int i = 0; i < ZP_MAX_THREADS; i++) {
        const ZpThread *t = &g->t[i];
        if (atomic_load_explicit(&t->state, memory_order_acquire) == ZP_ACTIVE &&
            atomic_load_explicit(&t->tid, memory_order_relaxed) == tid)
            return i;
    }
    return -1;
}

static inline void zp_end(ZpRegistry *g, int i) {
    if (i < 0 || i >= ZP_MAX_THREADS) return;
    atomic_store_explicit(&g->t[i].ended_window, atomic_load_explicit(&g->window, memory_order_relaxed),
                          memory_order_relaxed);
    atomic_store_explicit(&g->t[i].state, ZP_ENDED, memory_order_release);
}

/* The next ACTIVE slot after `from` (round robin) other than `skip`; -1 if none. */
static inline int zp_next_target(const ZpRegistry *g, int from, int skip) {
    for (int k = 1; k <= ZP_MAX_THREADS; k++) {
        int i = (from + k) % ZP_MAX_THREADS;
        if (i != skip && atomic_load_explicit(&g->t[i].state, memory_order_acquire) == ZP_ACTIVE) return i;
    }
    return -1;
}

/* ---- the caller rule: [RBP+8] only when RBP can be a frame pointer of this thread's own stack */
static inline bool zp_caller_ok(uint64_t rsp, uint64_t rbp, uintptr_t lo, uintptr_t hi) {
    return lo && hi > lo + 16 && (rbp & 7) == 0 && rbp >= rsp && rbp >= lo && rbp <= hi - 16;
}

static inline bool zp_in_text(uint64_t rip, uint64_t text_lo, uint64_t text_hi) {
    return text_hi > text_lo && rip >= text_lo && rip < text_hi;
}

/* ---- the ring (producers: signal handlers; consumer: the sampler thread) */
typedef struct {
    _Atomic uint32_t seq;  /* low 32 bits of index + 1 once the record is complete */
    uint16_t thread, flags;
    uint64_t rip, caller;
} ZpRec;
_Static_assert(sizeof(ZpRec) == 24, "ring record");

typedef struct {
    ZpRec *rec;
    uint32_t cap;  /* power of two */
    _Atomic uint64_t w, r;
    _Atomic uint32_t dropped;
} ZpRing;

static inline bool zp_ring_push(ZpRing *g, uint16_t thread, uint16_t flags, uint64_t rip, uint64_t caller) {
    uint64_t r = atomic_load_explicit(&g->r, memory_order_acquire);
    uint64_t i = atomic_fetch_add_explicit(&g->w, 1, memory_order_acq_rel);
    if (i - r >= g->cap) {  /* the consumer is a whole ring behind: drop (that index stays unwritten) */
        atomic_fetch_add_explicit(&g->dropped, 1, memory_order_relaxed);
        return false;
    }
    ZpRec *e = &g->rec[i & (g->cap - 1)];
    e->thread = thread, e->flags = flags, e->rip = rip, e->caller = caller;
    atomic_store_explicit(&e->seq, (uint32_t)(i + 1), memory_order_release);
    return true;
}

typedef void (*ZpRecOut)(void *ctx, const ZpRec *r);

/* Consumes [r, upto): complete records go to out(); an index whose record never completed (dropped, or a handler
 * still writing - the caller waits briefly before draining) is skipped and counted. Returns records delivered. */
static inline uint32_t zp_ring_drain(ZpRing *g, uint64_t upto, ZpRecOut out, void *ctx, uint32_t *skipped) {
    uint64_t r = atomic_load_explicit(&g->r, memory_order_relaxed), end = upto;
    uint32_t n = 0, s = 0;
    if (upto - r > g->cap) {  /* indexes past r + cap were refused by push (dropped): only [r, r + cap) can hold data */
        s += (uint32_t)(upto - r - g->cap);
        end = r + g->cap;
    }
    for (; r < end; r++) {
        ZpRec *e = &g->rec[r & (g->cap - 1)];
        if (atomic_load_explicit(&e->seq, memory_order_acquire) != (uint32_t)(r + 1)) { s++; continue; }
        out(ctx, e);
        n++;
    }
    atomic_store_explicit(&g->r, upto, memory_order_release);
    if (skipped) *skipped += s;
    return n;
}

/* ---- the signal handler's body (za_prof.c passes the interrupted RIP/RSP/RBP from its ucontext; the host test
 * passes Linux's). read() loads the caller slot; it is only called when zp_caller_ok holds. Returns the slot. */
typedef uint64_t (*ZpReadFn)(uint64_t addr);
static inline int zp_on_sample(ZpRegistry *g, ZpRing *ring, uintptr_t self, uint64_t rip, uint64_t rsp, uint64_t rbp,
                               uint64_t text_lo, uint64_t text_hi, ZpReadFn read, _Atomic uint32_t *unknown) {
    int i = zp_lookup(g, self);
    if (i < 0) { atomic_fetch_add_explicit(unknown, 1, memory_order_relaxed); return -1; }
    ZpThread *t = &g->t[i];
    uint64_t caller = zp_caller_ok(rsp, rbp, t->lo, t->hi) ? read(rbp + 8) : 0;
    uint16_t flags = caller ? ZP_F_CALLER : 0;
    if (text_hi) {
        flags |= ZP_F_TEXT_KNOWN;
        if (zp_in_text(rip, text_lo, text_hi)) flags |= ZP_F_IN_TEXT;
        else atomic_fetch_add_explicit(&t->win_ext, 1, memory_order_relaxed);
    }
    if (!caller) atomic_fetch_add_explicit(&t->win_nofp, 1, memory_order_relaxed);
    atomic_fetch_add_explicit(&t->win_samples, 1, memory_order_relaxed);
    zp_ring_push(ring, (uint16_t)i, flags, rip, caller);
    return i;
}

/* ---- sample file (little endian; x86-64 hosts write it natively)
 * header (128 bytes) | thread table (thread_count x 96) | records (record_count x 24)
 * header:  0 magic "ZAPROF1\0" | 8 u32 version | 12 u32 header_bytes (128 + table) | 16 u64 boot | 24 u64 window |
 *         32 u64 t_start_ns | 40 u64 t_end_ns (CLOCK_MONOTONIC) | 48 u64 anchor (runtime address of za_prof_anchor)
 *         | 56 u64 text_lo | 64 u64 text_hi (sceKernelVirtualQuery of the anchor; 0/0 = unknown) | 72 u32 period_us
 *         | 76 u32 thread_count | 80 u32 record_count | 84 u32 dropped | 88 u32 skipped | 92 u32 kill_errors
 *         | 96 u32 flags (1: render only) | 100 u32 sent | 104 u32 render_slot (0xffffffff: none) | 108.. zero
 * thread:  0 u32 index | 4 u32 kind | 8 u64 gid | 16 u64 entry | 24 u64 stack_lo | 32 u64 stack_hi | 40 i32 prio
 *         | 44 u32 samples | 48 u32 ext | 52 u32 nofp | 56 char name[32] | 88.. zero
 * record:  0 u16 thread | 2 u16 flags (ZP_F_*) | 4 u32 zero | 8 u64 rip | 16 u64 caller (0: none) */
typedef struct {
    uint64_t boot, window, t_start_ns, t_end_ns, anchor, text_lo, text_hi;
    uint32_t period_us, thread_count, record_count, dropped, skipped, kill_errors, flags, sent, render_slot;
} ZpFileHeader;

static inline void zp_put32(uint8_t *p, uint32_t v) { memcpy(p, &v, 4); }
static inline void zp_put64(uint8_t *p, uint64_t v) { memcpy(p, &v, 8); }

static inline void zp_write_header(uint8_t out[ZP_HEADER_BYTES], const ZpFileHeader *h) {
    memset(out, 0, ZP_HEADER_BYTES);
    memcpy(out, "ZAPROF1", 8);
    zp_put32(out + 8, ZP_FILE_VERSION);
    zp_put32(out + 12, ZP_HEADER_BYTES + h->thread_count * ZP_THREAD_BYTES);
    zp_put64(out + 16, h->boot), zp_put64(out + 24, h->window), zp_put64(out + 32, h->t_start_ns);
    zp_put64(out + 40, h->t_end_ns), zp_put64(out + 48, h->anchor), zp_put64(out + 56, h->text_lo);
    zp_put64(out + 64, h->text_hi);
    zp_put32(out + 72, h->period_us), zp_put32(out + 76, h->thread_count), zp_put32(out + 80, h->record_count);
    zp_put32(out + 84, h->dropped), zp_put32(out + 88, h->skipped), zp_put32(out + 92, h->kill_errors);
    zp_put32(out + 96, h->flags), zp_put32(out + 100, h->sent), zp_put32(out + 104, h->render_slot);
}

static inline void zp_write_thread(uint8_t out[ZP_THREAD_BYTES], uint32_t index, const ZpThread *t) {
    memset(out, 0, ZP_THREAD_BYTES);
    zp_put32(out, index);
    zp_put32(out + 4, (uint32_t)atomic_load_explicit(&t->kind, memory_order_relaxed));
    zp_put64(out + 8, t->gid), zp_put64(out + 16, t->entry), zp_put64(out + 24, t->lo), zp_put64(out + 32, t->hi);
    zp_put32(out + 40, (uint32_t)t->prio);
    zp_put32(out + 44, t->file_samples), zp_put32(out + 48, t->file_ext), zp_put32(out + 52, t->file_nofp);
    memcpy(out + 56, t->name, strnlen(t->name, ZP_NAME));
}

static inline void zp_write_record(uint8_t out[ZP_RECORD_BYTES], const ZpRec *r) {
    memset(out, 0, ZP_RECORD_BYTES);
    memcpy(out, &r->thread, 2);
    memcpy(out + 2, &r->flags, 2);
    zp_put64(out + 8, r->rip);
    zp_put64(out + 16, r->caller);
}

/* ---- files: <dir>/samples-b<boot>-s<slot>.bin, slot = window % keep (the oldest of this boot is overwritten);
 * at start the files of boot - ZP_KEEP_BOOTS are deleted (every slot up to ZP_MAX_KEEP) */
static inline unsigned zp_slot(uint64_t window, unsigned keep) { return keep ? (unsigned)(window % keep) : 0; }
static inline int zp_file_name(char *out, size_t cap, const char *dir, uint64_t boot, unsigned slot) {
    return snprintf(out, cap, "%s/samples-b%llu-s%03u.bin", dir, (unsigned long long)boot, slot);
}
/* Upper bound of the bytes the sample files of the kept boots can take on disk. */
static inline uint64_t zp_disk_bound(unsigned keep, uint32_t ring_cap) {
    return (uint64_t)ZP_KEEP_BOOTS * keep *
           (ZP_HEADER_BYTES + (uint64_t)ZP_MAX_THREADS * ZP_THREAD_BYTES + (uint64_t)ring_cap * ZP_RECORD_BYTES);
}

/* ---- the per-window klog line: the busiest `top` threads as name=samples/ext%/nofp% (ext: RIP outside the eboot's
 * text - system modules, mostly libkernel waits and syscalls; nofp: no caller recorded). */
static inline int zp_summary(char *out, size_t cap, const ZpRegistry *g, int top, bool text_known) {
    int idx[16], n = 0, w = 0;
    if (top > 16) top = 16;
    for (int i = 0; i < ZP_MAX_THREADS; i++) {
        uint32_t s = g->t[i].file_samples;
        if (!s) continue;
        int at = n < top ? n++ : top;
        while (at > 0 && g->t[idx[at - 1]].file_samples < s) { if (at < top) idx[at] = idx[at - 1]; at--; }
        if (at < top) idx[at] = i;
    }
    out[0] = 0;
    for (int k = 0; k < n && w >= 0 && (size_t)w < cap; k++) {
        const ZpThread *t = &g->t[idx[k]];
        uint32_t s = t->file_samples;
        int kind = atomic_load_explicit(&t->kind, memory_order_relaxed);
        const char *tag = kind == ZP_KIND_RENDER ? "R:" : "";
        if (text_known)
            w += snprintf(out + w, cap - (size_t)w, " %s%s=%u/%u%%/%u%%", tag, t->name, s,
                          (unsigned)((uint64_t)t->file_ext * 100 / s), (unsigned)((uint64_t)t->file_nofp * 100 / s));
        else
            w += snprintf(out + w, cap - (size_t)w, " %s%s=%u/?/%u%%", tag, t->name, s,
                          (unsigned)((uint64_t)t->file_nofp * 100 / s));
    }
    return w;
}
