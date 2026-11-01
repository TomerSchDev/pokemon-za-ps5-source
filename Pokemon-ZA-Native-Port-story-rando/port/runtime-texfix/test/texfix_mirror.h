// Host tests (port/runtime-texfix/test): mirrors of r28-play's NvnTexture (runtime/nvn/nvn.h, with r28a's za_guard)
// and TexBackend (runtime/nvn/vulkan/vk.h) - plain types in place of the Vulkan / VMA handles, the same layout on
// x86-64 (asserted: backend at 112, a TexBackend's reg at 0xa0, so a backend pointer of 0x2 faults at 0xa2 as on the
// console). The headers under test (../src) are the files the build copies into the runtime, unchanged.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef struct { uint8_t bpb, bw, bh, kind; } FormatInfo;
typedef struct {
    uint32_t width, height, depth, layers, levels;
    const FormatInfo *fmt;
    uint32_t block_height_log2, block_depth_log2;
} TexLayout;

typedef struct NvnTexture {
    TexLayout layout;
    uint32_t target, format, flags, width, height, depth, levels, samples, ds_mode;
    uint8_t swizzle[4];
    uint64_t stride;
    uint64_t addr;
    void *pool;
    uint64_t pool_offset;
    void *backend;
    uint64_t debug_id;
    char label[64];
    bool in_pool;
    uint32_t za_guard;
} NvnTexture;
_Static_assert(offsetof(NvnTexture, backend) == 112 && offsetof(NvnTexture, in_pool) == 192 &&
               offsetof(NvnTexture, za_guard) == 196 && sizeof(NvnTexture) == 200, "the r28a NvnTexture layout");

typedef struct TexBackend {
    uint64_t image;  // VkImage
    void *mem;       // VmaAllocation
    int32_t format, base_type;
    uint32_t width, height, depth, layers, levels, samples;
    uint32_t aspect;
    bool gpu_owned, uploaded, dynamic;
    uint64_t data_hash, sample_hash, checked_frame, full_frame;
    uint32_t wgen;
    bool scalable, presented;
    uint64_t touched_frame, frame_cleared;
    uint32_t level_gen;
    float sx, sy;
    void *pending_rgba;
    uint32_t pending_w, pending_h, pending_stride;
    uint8_t astc_bw, astc_bh;
    bool astc_srgb;
    int tp;
    uint32_t tp_gen;
    int reg;
    bool hd;
} TexBackend;
_Static_assert(offsetof(TexBackend, reg) == 0xa0 && sizeof(TexBackend) == 168, "r28-play's TexBackend layout");
