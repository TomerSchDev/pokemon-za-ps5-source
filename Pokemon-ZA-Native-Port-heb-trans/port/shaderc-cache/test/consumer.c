/*
 * shaderc-cache consumer: uses the shaderc API exactly as runtime/nvn/vulkan/shaders.c does (vk_shaders_init and
 * vk_glsl_to_spirv), so build-check.sh can compile it as C11 and as C++20 against include/shaderc and compare its
 * imports with what shaderc_cache.c defines. Compile-only.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#include <shaderc/shaderc.h>

#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#define VK_API_VERSION_1_3 ((1u << 22) | (3u << 12))

void shaderc_cache_consumer_init(void)
{
    shaderc_compiler_t c = shaderc_compiler_initialize();
    if (!c) abort(); /* shaders.c: FATAL */
    shaderc_compiler_release(c);
}

uint32_t *shaderc_cache_consumer(const char *src, int stage, const char *name, uint32_t api, size_t *nwords)
{
    static __thread shaderc_compiler_t comp; /* one per thread, as the runtime (emulated TLS on the PS5) */
    if (!comp) comp = shaderc_compiler_initialize();
    shaderc_compile_options_t o = shaderc_compile_options_initialize();
    shaderc_compile_options_set_target_env(o, shaderc_target_env_vulkan,
                                           api >= VK_API_VERSION_1_3 ? shaderc_env_version_vulkan_1_3 : shaderc_env_version_vulkan_1_2);
    shaderc_compile_options_set_optimization_level(o, getenv("LARECOMP_VK_OPT") ? shaderc_optimization_level_performance
                                                                                   : shaderc_optimization_level_zero);
    shaderc_shader_kind kind = stage == 0 ? shaderc_vertex_shader : stage == 1 ? shaderc_fragment_shader : shaderc_compute_shader;
    shaderc_compilation_result_t r = shaderc_compile_into_spv(comp, src, strlen(src), kind, name, "main", o);
    shaderc_compile_options_release(o);
    uint32_t *out = NULL;
    if (shaderc_result_get_compilation_status(r) != shaderc_compilation_status_success) {
        const char *message = shaderc_result_get_error_message(r);
        (void)message;
    } else {
        size_t n = shaderc_result_get_length(r);
        out = (uint32_t *)malloc(n);
        memcpy(out, shaderc_result_get_bytes(r), n);
        *nwords = n / 4;
    }
    shaderc_result_release(r);
    return out;
}
