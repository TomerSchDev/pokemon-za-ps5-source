/* Executes the actual candidate helper plus baseline/patched call-site fragments
 * extracted by generate.py. No Vulkan driver or guest memory is involved. */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>

typedef uintptr_t VkBuffer;
typedef struct { VkBuffer buf; uint64_t off; uint8_t *ptr; } VkSpan;
typedef struct { VkBuffer buffer; uint64_t offset, range; } VkDescriptorBufferInfo;
typedef struct { uint64_t addr, size; } Range;
#define VK_NULL_HANDLE ((VkBuffer)0)
static struct { struct { struct { uint64_t maxUniformBufferRange; } limits; } props; } g_vk;
static uint8_t arena[16u << 20];
static uint64_t pending_sequence, used, allocations, allocated_bytes, last_size, last_align;
static unsigned fail_next, log_lines;
static uint64_t vk_pending_seq(void) { return pending_sequence; }
static VkSpan vk_transient(uint64_t size, uint64_t align) {
    if (fail_next) _exit(91); /* fatal allocator outcome propagates through the original copy path */
    last_size=size;last_align=align;
    if(align<16)align=16;
    uint64_t off=(used+align-1)&~(align-1);
    assert(off+size<=sizeof arena);
    used=off+size;++allocations;allocated_bytes+=size;
    return (VkSpan){1,off,arena+off};
}
#include "extracted-copy.inc"
#define LOG(...) do { ++log_lines; } while (0)
/* Consume every LOG argument to preserve -Werror checks on the real helper. */
#undef LOG
static void test_log(const char *fmt,...) { (void)fmt; ++log_lines; }
#define LOG(...) test_log(__VA_ARGS__)
#include "runtime/nvn/vulkan/za_immutable_spans_r22.inc"
#include "extracted-sites.inc"

static void all_zero(const uint8_t *p,uint64_t size) {
    for(uint64_t i=0;i<size;++i)assert(p[i]==0);
}
static void descriptor_equal(VkDescriptorBufferInfo a,VkDescriptorBufferInfo b) {
    assert(a.buffer==1 && b.buffer==1 && a.range==b.range);
    assert(a.offset%256==0 && b.offset%256==0);
    assert(!memcmp(arena+a.offset,arena+b.offset,(size_t)a.range));
}
static void reset_fixture(void) {
    za_immutable_spans_set_enabled(false);
    za_immutable_spans_reset();
    memset(za_immutable_stats,0,sizeof za_immutable_stats);
    memset(arena,0xcd,sizeof arena);
    pending_sequence=used=allocations=allocated_bytes=last_size=last_align=0;
    fail_next=log_lines=0;g_vk.props.limits.maxUniformBufferRange=65536;
}
static void test_real_sites_and_descriptor_ranges(void) {
    reset_fixture();
    const uint64_t sizes[]={1,15,16,17,255,256,257,512,4096,65536};
    for(unsigned mode=0;mode<2;++mode) {
        za_immutable_spans_set_enabled(mode!=0);
        for(unsigned i=0;i<sizeof sizes/sizeof sizes[0];++i) {
            uint64_t size=sizes[i];
            VkDescriptorBufferInfo a=original_ubo(size),b=candidate_ubo(size);
            descriptor_equal(a,b);all_zero(arena+b.offset,size);
            assert(last_size==size && last_align==256);
            uint64_t before=allocations;
            VkDescriptorBufferInfo c=candidate_ubo(size);
            descriptor_equal(b,c);
            assert(mode ? c.offset==b.offset && allocations==before : c.offset!=b.offset && allocations==before+1);
        }
        VkSpan a=original_default(),b=candidate_default();
        assert(a.off%16==0 && b.off%16==0 && !memcmp(a.ptr,b.ptr,16));
        float value[4];memcpy(value,b.ptr,sizeof value);
        assert(value[0]==0 && value[1]==0 && value[2]==0 && value[3]==1);
        VkSpan c=original_vertex_zero(),d=candidate_vertex_zero();
        assert(c.off%16==0 && d.off%16==0 && !memcmp(c.ptr,d.ptr,256));all_zero(d.ptr,256);
        assert(b.off!=d.off); /* w=1 must never alias the all-zero content kind */
    }
    g_vk.props.limits.maxUniformBufferRange=128;
    descriptor_equal(original_ubo(256),candidate_ubo(256));
    assert(candidate_ubo(256).range==128); /* unchanged real ubo_span clamp */
    puts("real baseline/patched call sites: UBO contents/ranges/alignment and both vertex literals equal");
}
static void test_sequence_reset_and_kind_keys(void) {
    reset_fixture();za_immutable_spans_set_enabled(true);
    VkSpan first=candidate_default();assert(allocations==1); /* seq=0 must be a real miss */
    VkSpan repeated=candidate_default();assert(allocations==1 && first.off==repeated.off);
    unsigned physical_batch=1;
    ++physical_batch; /* Physical queue grouping is deliberately not a cache key. */
    assert(candidate_default().off==first.off && physical_batch==2);
    ++pending_sequence; /* New logical list, still in the same physical batch. */
    uint8_t snapshot[16];memcpy(snapshot,first.ptr,16);
    VkSpan next=candidate_default();assert(next.off!=first.off && allocations==2);
    assert(!memcmp(first.ptr,snapshot,16));
    za_immutable_spans_reset();
    VkSpan after_reset=candidate_default();assert(after_reset.off!=next.off && allocations==3);
    pending_sequence=0;za_immutable_spans_reset();
    assert(candidate_default().off!=first.off && allocations==4);
    static const uint8_t zero[65536];
    VkSpan zero16=za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,16,16);
    VkSpan default16=candidate_default();
    assert(zero16.off!=default16.off);all_zero(zero16.ptr,16);
    float w;memcpy(&w,default16.ptr+12,4);assert(w==1);
    VkSpan ubo256=za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,256,16);
    VkSpan vb256=candidate_vertex_zero();assert(ubo256.off!=vb256.off);
    assert(!memcmp(ubo256.ptr,vb256.ptr,256));
    puts("valid-bit cold seq0, logical sequence, reset, sequence reuse and content-kind isolation passed");
}
static void test_exact_keys_eviction_and_baseline(void) {
    reset_fixture();za_immutable_spans_set_enabled(true);
    static const uint8_t zero[65537];
    const uint64_t alignments[]={8,16,32,64,256,512,1024};
    for(unsigned i=0;i<sizeof alignments/sizeof alignments[0];++i) {
        uint64_t align=alignments[i],before=allocations;
        VkSpan a=za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,129,align);
        VkSpan b=za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,129,align);
        assert(a.off==b.off && allocations==before+1 && a.off%align==0);all_zero(a.ptr,129);
    }
    /* More exact sizes than slots: replacement must never turn a collision into a hit. */
    za_immutable_spans_reset();
    for(uint64_t n=100;n<200;++n) {
        uint64_t before=allocations;
        VkSpan a=za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,n,256);
        assert(allocations==before+1);all_zero(a.ptr,n);
        assert(za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,n,256).off==a.off);
    }
    assert(za_immutable_stats[ZA_IMM_UBO_ZERO].collisions>0);
    uint64_t before=allocations;
    for(unsigned i=0;i<2;++i) {
        za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,0,256);
        za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,65537,256);
        za_immutable_span_copy(ZA_IMM_VERTEX_DEFAULT,zero,15,16);
        za_immutable_span_copy(ZA_IMM_VERTEX_ZERO,zero,16,16);
        za_immutable_span_copy(ZA_IMM_UBO_ZERO,zero,16,0);
        za_immutable_span_copy(ZA_IMM_KINDS,zero,16,16);
    }
    assert(allocations==before+12); /* unknown requests retain original fallback */
    za_immutable_spans_set_enabled(false);
    before=allocations;candidate_default();candidate_default();assert(allocations==before+2);
    za_immutable_spans_set_enabled(true);
    before=allocations;candidate_default();candidate_default();assert(allocations==before+1);
    puts("exact size/alignment keys, bounded collisions, original fallback and baseline opt-out passed");
}
static void test_counters_and_failure_passthrough(void) {
    reset_fixture();za_immutable_spans_set_enabled(true);
    candidate_ubo(256);candidate_ubo(256);candidate_default();candidate_default();candidate_vertex_zero();candidate_vertex_zero();
    assert(allocations==3 && allocated_bytes==528);
    for(unsigned i=0;i<ZA_IMM_KINDS;++i) {
        uint64_t bytes=i==ZA_IMM_VERTEX_DEFAULT?16:256;
        assert(za_immutable_stats[i].requests==2 && za_immutable_stats[i].hits==1 && za_immutable_stats[i].misses==1);
        assert(za_immutable_stats[i].copied_bytes==bytes && za_immutable_stats[i].avoided_bytes==bytes);
    }
    fail_next=1;candidate_default();assert(fail_next==1);fail_next=0; /* hit makes no allocator call */
    for(unsigned mode=0;mode<2;++mode) {
        pid_t pid=fork();assert(pid>=0);
        if(!pid) {
            za_immutable_spans_set_enabled(mode!=0);za_immutable_spans_reset();fail_next=1;
            candidate_default();_exit(99);
        }
        int status;assert(waitpid(pid,&status,0)==pid);
        assert(WIFEXITED(status) && WEXITSTATUS(status)==91);
    }
    za_immutable_spans_report();assert(log_lines==ZA_IMM_KINDS);
    for(unsigned i=0;i<ZA_IMM_KINDS;++i)assert(!za_immutable_stats[i].requests);
    puts("per-kind request/copy/reuse byte counters and original allocation failure passthrough passed");
}
int main(void) {
    test_real_sites_and_descriptor_ranges();
    test_sequence_reset_and_kind_keys();
    test_exact_keys_eviction_and_baseline();
    test_counters_and_failure_passthrough();
    puts("TB1 immutable-span candidate: all extracted-code host tests passed; no GPU performance claim");
}
