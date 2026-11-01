#ifndef ZA_R16_CACHE_TABLE_H
#define ZA_R16_CACHE_TABLE_H
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <stddef.h>
#ifndef ZA_CACHE_CALLOC
#define ZA_CACHE_CALLOC calloc
#endif
/* Single render-thread ownership. Jobs own the pointed-to allocations, never
 * entries: growth may move this array without moving a Prog/Pipe. Key zero is
 * reserved. All probe loops are bounded, including allocation failure. */
typedef struct { uint64_t key; void *value; } ZaCacheEntry;
typedef struct { ZaCacheEntry *entries; size_t capacity, count; } ZaCacheTable;
static inline size_t za_cache_slot(uint64_t key, size_t cap) {
    return (size_t)(key ^ (key >> 31)) & (cap - 1);
}
static inline ZaCacheEntry *za_cache_probe(ZaCacheTable *t, uint64_t key) {
    if (!key || !t->capacity) return NULL;
    size_t i = za_cache_slot(key, t->capacity);
    for (size_t n = 0; n < t->capacity; ++n, i = (i + 1) & (t->capacity - 1))
        if (!t->entries[i].key || t->entries[i].key == key) return &t->entries[i];
    return NULL;
}
static inline bool za_cache_grow(ZaCacheTable *t, size_t minimum) {
    size_t cap = t->capacity ? t->capacity : 16;
    if (cap > SIZE_MAX / 2) return false;
    if (t->capacity) cap *= 2;
    while (cap < minimum) { if (cap > SIZE_MAX / 2) return false; cap *= 2; }
    if (cap > SIZE_MAX / sizeof(ZaCacheEntry)) return false;
    ZaCacheEntry *entries = ZA_CACHE_CALLOC(cap, sizeof *entries);
    if (!entries) return false;
    ZaCacheTable next = {entries, cap, t->count};
    for (size_t n = 0; n < t->capacity; ++n) {
        if (!t->entries[n].key) continue;
        ZaCacheEntry *dst = za_cache_probe(&next, t->entries[n].key);
        if (!dst) { free(entries); return false; }
        *dst = t->entries[n];
    }
    free(t->entries); *t = next;
    return true;
}
static inline void *za_cache_get(ZaCacheTable *t, uint64_t key) {
    ZaCacheEntry *e = za_cache_probe(t, key);
    return e && e->key ? e->value : NULL;
}
static inline bool za_cache_put(ZaCacheTable *t, uint64_t key, void *value) {
    if (!key || !value) return false;
    ZaCacheEntry *e = za_cache_probe(t, key);
    if (e && e->key) { e->value = value; return true; }
    if (!t->capacity || t->count >= t->capacity / 2) {
        if (!za_cache_grow(t, 16)) return false;
        e = za_cache_probe(t, key);
    }
    if (!e) return false;
    *e = (ZaCacheEntry){key, value}; ++t->count;
    return true;
}
static inline void za_cache_reset(ZaCacheTable *t) {
    if (t->entries) memset(t->entries, 0, t->capacity * sizeof *t->entries);
    t->count = 0;
}
#endif
