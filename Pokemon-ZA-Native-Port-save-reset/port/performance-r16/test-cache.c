#include <stdlib.h>
#include <assert.h>
#include <stdio.h>
static int fail;
static void *test_calloc(size_t a,size_t b) { return fail?NULL:calloc(a,b); }
#define ZA_CACHE_CALLOC test_calloc
#include "cache_table.h"
int main(void) {
    ZaCacheTable t={0};
    fail=1; assert(!za_cache_put(&t,1,(void*)1) && !t.capacity);
    fail=0;
    for(uint64_t i=1;i<=24000;i++) assert(za_cache_put(&t,i<<16,(void*)(uintptr_t)i));
    assert(t.count==24000 && t.capacity>=48000);
    for(uint64_t i=1;i<=24000;i++) assert(za_cache_get(&t,i<<16)==(void*)(uintptr_t)i);
    assert(!za_cache_get(&t,UINT64_C(0xeeeeeeee)));
    assert(za_cache_put(&t,UINT64_C(1)<<16,(void*)42)); assert(t.count==24000);
    za_cache_reset(&t); assert(t.count==0 && !za_cache_get(&t,UINT64_C(1)<<16));
    free(t.entries); t=(ZaCacheTable){0};
    for(uint64_t i=1;i<=8;i++) assert(za_cache_put(&t,i,(void*)(uintptr_t)i));
    fail=1; assert(!za_cache_put(&t,9,(void*)9));
    for(uint64_t i=1;i<=8;i++) assert(za_cache_get(&t,i)==(void*)(uintptr_t)i);
    /* Deliberately full table, including absent lookup: bounded even if OOM. */
    for(size_t i=0;i<t.capacity;i++) t.entries[i]=(ZaCacheEntry){i+1,(void*)(i+1)};
    t.count=t.capacity; assert(!za_cache_get(&t,100)); assert(!za_cache_put(&t,100,(void*)100));
    free(t.entries);
    puts("PASS cache: 24000 colliding keys, growth past both former limits, lookup, replacement, reset, OOM preserves contents, full-table termination");
}
