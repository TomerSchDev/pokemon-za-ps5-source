/*
 * shaderc-cache hash parity: compiled and run on the host (not on the PS5) by build-check.sh, together with
 * shaderc_cache.c and runtime_src_hash.inc - the text of src_hash() cut verbatim out of the recomp's
 * runtime/nvn/vulkan/shaders.c. For the same GLSL, stage and Vulkan version, za_shaderc_cache_hash must give
 * exactly what the runtime computes, or the cache can never hit.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

/* what src_hash needs from the runtime's headers */
#define VK_API_VERSION_1_2 ((1u << 22) | (2u << 12))
#define VK_API_VERSION_1_3 ((1u << 22) | (3u << 12))
static struct { uint32_t api; } g_vkc;
#include "runtime_src_hash.inc" /* static uint64_t src_hash(const char *src, int stage) */

uint64_t za_shaderc_cache_hash(const char *src, size_t len, int stage, uint32_t api);

int main(void)
{
    static const char *const sources[] = {
        "",
        "#version 450\nvoid main() {}\n",
        "#version 450\nlayout(push_constant) uniform P { vec4 a; vec4 crop; } pc;\nlayout(location = 0) out vec2 uv;\n"
        "void main() {\n  vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);\n"
        "  gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);\n}\n",
        "    { ulong ga = (ulong(r0) + ulong(0)) - 0x7000000000ul; bool ok = ga < 0x320000000ul;\n",
        "bytes above 127: \x80\xff\xfe\x7f and a tab\t",
        "x",
    };
    static const uint32_t apis[] = {VK_API_VERSION_1_3, VK_API_VERSION_1_2};
    int compared = 0, bad = 0;
    for (size_t a = 0; a < sizeof apis / sizeof apis[0]; a++) {
        g_vkc.api = apis[a];
        for (int stage = 0; stage <= 5; stage++)
            for (size_t s = 0; s < sizeof sources / sizeof sources[0]; s++) {
                uint64_t runtime = src_hash(sources[s], stage);
                uint64_t ours = za_shaderc_cache_hash(sources[s], strlen(sources[s]), stage, apis[a]);
                compared++;
                if (runtime != ours) {
                    bad++;
                    printf("mismatch: api %#x stage %d source %zu: runtime %016llx, cache %016llx\n", apis[a], stage, s,
                           (unsigned long long)runtime, (unsigned long long)ours);
                }
            }
    }
    printf("hash parity: %d comparisons, %d mismatches\n", compared, bad);
    return bad != 0;
}
