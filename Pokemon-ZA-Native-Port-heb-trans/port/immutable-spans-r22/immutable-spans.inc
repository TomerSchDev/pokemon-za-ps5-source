#include "za_immutable_spans_r22.h"
/* TB1/r22: copies of the three immutable zero/default literals only.
 * This cache belongs to the existing executor owner, like the transient ring.
 * Never use for guest memory or mutable constants. Each entry expires when
 * vk_pending_seq() changes (the logical sequence, not the batch4 queue call).
 * The span remains owned/retired by the original transient allocator. */
enum { ZA_IMM_UBO_ZERO, ZA_IMM_VERTEX_DEFAULT, ZA_IMM_VERTEX_ZERO, ZA_IMM_KINDS };
enum { ZA_IMM_SLOTS = 8 };
typedef struct {
    bool valid;
    uint64_t sequence, size, align;
    VkSpan span;
} ZaImmutableEntry;
typedef struct {
    uint64_t requests, hits, misses, bypass, copied_bytes, avoided_bytes, collisions;
} ZaImmutableStats;
static ZaImmutableEntry za_immutable_entries[ZA_IMM_KINDS][ZA_IMM_SLOTS];
static ZaImmutableStats za_immutable_stats[ZA_IMM_KINDS];
static bool za_immutable_enabled; /* baseline until the owner explicitly opts in */
static uint64_t za_immutable_resets;

static void za_immutable_spans_reset(void) {
    memset(za_immutable_entries, 0, sizeof za_immutable_entries);
    ++za_immutable_resets;
}

/* Reserved integration hook: call only on the executor owner, under the
 * existing execution lock. No observer command/profile contract is added here.
 * Profile experiments may use the same already-drained boundary as r21. */
void za_immutable_spans_set_enabled(bool enabled) {
    if (enabled != za_immutable_enabled) {
        za_immutable_spans_reset();
        za_immutable_enabled = enabled;
    }
}

static VkSpan za_immutable_span_copy(unsigned kind, const void *literal, uint64_t size, uint64_t align) {
    /* Invalid/unexpected requests retain the original allocation/copy path.
     * Exact size and requested alignment are part of the key, even when the
     * allocator would round two different alignments to the same value. */
    if (kind >= ZA_IMM_KINDS) return vk_transient_copy(literal, size, align);
    ZaImmutableStats *stats = &za_immutable_stats[kind];
    ++stats->requests;
    bool eligible = size && align && !(align & (align - 1)) &&
        (kind == ZA_IMM_UBO_ZERO ? size <= 0x10000 :
         kind == ZA_IMM_VERTEX_DEFAULT ? size == 16 : size == 256);
    if (!za_immutable_enabled || !eligible) {
        ++stats->bypass;
        stats->copied_bytes += size;
        return vk_transient_copy(literal, size, align);
    }
    uint64_t sequence = vk_pending_seq();
    uint64_t hash = size * UINT64_C(0x9e3779b97f4a7c15) ^ align * UINT64_C(0xc2b2ae3d27d4eb4f);
    unsigned slot = (unsigned)(hash ^ (hash >> 32)) & (ZA_IMM_SLOTS - 1);
    ZaImmutableEntry *entry = &za_immutable_entries[kind][slot];
    if (entry->valid && entry->sequence == sequence && entry->size == size && entry->align == align) {
        ++stats->hits;
        stats->avoided_bytes += size;
        return entry->span;
    }
    ++stats->misses;
    if (entry->valid && entry->sequence == sequence) ++stats->collisions;
    VkSpan span = vk_transient_copy(literal, size, align);
    stats->copied_bytes += size;
    /* The original allocator owns failures; do not manufacture a replacement
     * buffer, new usage flags, or a successful cache entry for a failed span. */
    *entry = (ZaImmutableEntry){.valid = span.buf != VK_NULL_HANDLE && span.ptr != NULL,
        .sequence = sequence, .size = size, .align = align, .span = span};
    return span;
}

static void za_immutable_spans_report(void) {
    static const char *const names[ZA_IMM_KINDS] = {"ubo-zero", "vertex-default-w1", "vertex-zero"};
    for (unsigned i = 0; i < ZA_IMM_KINDS; ++i) {
        const ZaImmutableStats *s = &za_immutable_stats[i];
        LOG("[za-r22-immutable] enabled=%u kind=%s requests=%llu hits=%llu misses=%llu bypass=%llu copied_bytes=%llu avoided_bytes=%llu collisions=%llu resets=%llu\n",
            (unsigned)za_immutable_enabled, names[i], (unsigned long long)s->requests,
            (unsigned long long)s->hits, (unsigned long long)s->misses, (unsigned long long)s->bypass,
            (unsigned long long)s->copied_bytes, (unsigned long long)s->avoided_bytes,
            (unsigned long long)s->collisions, (unsigned long long)za_immutable_resets);
    }
    memset(za_immutable_stats, 0, sizeof za_immutable_stats);
    za_immutable_resets = 0;
}
