/*
 * shaderc-cache (PS5 port of Pokemon Legends Z-A Recomp): the part of shaderc's C API (shaderc 2025.4,
 * MSYS2's ucrt64/include/shaderc/shaderc.h) that runtime/nvn/vulkan/shaders.c uses, with the same types, enum values
 * and signatures. The implementation behind it (shaderc_cache.c) compiles nothing: it serves precompiled SPIR-V
 * from a disk cache. Functions of the real API that are not listed here do not exist in this build.
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef SHADERC_SHADERC_H_
#define SHADERC_SHADERC_H_

#ifdef __cplusplus
extern "C" {
#endif

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#include "shaderc/env.h"
#include "shaderc/status.h"
#include "shaderc/visibility.h"

typedef enum {
    shaderc_source_language_glsl,
    shaderc_source_language_hlsl,
} shaderc_source_language;

/* the complete enum, in shaderc's order: the values are implicit and must stay the same */
typedef enum {
    shaderc_vertex_shader,
    shaderc_fragment_shader,
    shaderc_compute_shader,
    shaderc_geometry_shader,
    shaderc_tess_control_shader,
    shaderc_tess_evaluation_shader,

    shaderc_glsl_vertex_shader = shaderc_vertex_shader,
    shaderc_glsl_fragment_shader = shaderc_fragment_shader,
    shaderc_glsl_compute_shader = shaderc_compute_shader,
    shaderc_glsl_geometry_shader = shaderc_geometry_shader,
    shaderc_glsl_tess_control_shader = shaderc_tess_control_shader,
    shaderc_glsl_tess_evaluation_shader = shaderc_tess_evaluation_shader,

    shaderc_glsl_infer_from_source,
    shaderc_glsl_default_vertex_shader,
    shaderc_glsl_default_fragment_shader,
    shaderc_glsl_default_compute_shader,
    shaderc_glsl_default_geometry_shader,
    shaderc_glsl_default_tess_control_shader,
    shaderc_glsl_default_tess_evaluation_shader,
    shaderc_spirv_assembly,
    shaderc_raygen_shader,
    shaderc_anyhit_shader,
    shaderc_closesthit_shader,
    shaderc_miss_shader,
    shaderc_intersection_shader,
    shaderc_callable_shader,
    shaderc_glsl_raygen_shader = shaderc_raygen_shader,
    shaderc_glsl_anyhit_shader = shaderc_anyhit_shader,
    shaderc_glsl_closesthit_shader = shaderc_closesthit_shader,
    shaderc_glsl_miss_shader = shaderc_miss_shader,
    shaderc_glsl_intersection_shader = shaderc_intersection_shader,
    shaderc_glsl_callable_shader = shaderc_callable_shader,
    shaderc_glsl_default_raygen_shader,
    shaderc_glsl_default_anyhit_shader,
    shaderc_glsl_default_closesthit_shader,
    shaderc_glsl_default_miss_shader,
    shaderc_glsl_default_intersection_shader,
    shaderc_glsl_default_callable_shader,
    shaderc_task_shader,
    shaderc_mesh_shader,
    shaderc_glsl_task_shader = shaderc_task_shader,
    shaderc_glsl_mesh_shader = shaderc_mesh_shader,
    shaderc_glsl_default_task_shader,
    shaderc_glsl_default_mesh_shader,
} shaderc_shader_kind;

typedef enum {
    shaderc_profile_none,
    shaderc_profile_core,
    shaderc_profile_compatibility,
    shaderc_profile_es,
} shaderc_profile;

typedef enum {
    shaderc_optimization_level_zero,        /* no optimization */
    shaderc_optimization_level_size,        /* optimize towards reducing code size */
    shaderc_optimization_level_performance, /* optimize towards performance */
} shaderc_optimization_level;

/* An opaque handle to an object that manages all compiler state. */
typedef struct shaderc_compiler *shaderc_compiler_t;

SHADERC_EXPORT shaderc_compiler_t shaderc_compiler_initialize(void);
SHADERC_EXPORT void shaderc_compiler_release(shaderc_compiler_t);

/* An opaque handle to an object that manages options to a single compilation result. */
typedef struct shaderc_compile_options *shaderc_compile_options_t;

SHADERC_EXPORT shaderc_compile_options_t shaderc_compile_options_initialize(void);
SHADERC_EXPORT void shaderc_compile_options_release(shaderc_compile_options_t options);
SHADERC_EXPORT void shaderc_compile_options_set_optimization_level(shaderc_compile_options_t options,
                                                                   shaderc_optimization_level level);
SHADERC_EXPORT void shaderc_compile_options_set_target_env(shaderc_compile_options_t options,
                                                           shaderc_target_env target, uint32_t version);

/* An opaque handle to the results of a call to any shaderc_compile_into_*() function. */
typedef struct shaderc_compilation_result *shaderc_compilation_result_t;

SHADERC_EXPORT shaderc_compilation_result_t shaderc_compile_into_spv(
    const shaderc_compiler_t compiler, const char *source_text, size_t source_text_size,
    shaderc_shader_kind shader_kind, const char *input_file_name, const char *entry_point_name,
    const shaderc_compile_options_t additional_options);

SHADERC_EXPORT void shaderc_result_release(shaderc_compilation_result_t result);
SHADERC_EXPORT size_t shaderc_result_get_length(const shaderc_compilation_result_t result);
SHADERC_EXPORT shaderc_compilation_status shaderc_result_get_compilation_status(const shaderc_compilation_result_t);
SHADERC_EXPORT const char *shaderc_result_get_bytes(const shaderc_compilation_result_t result);
SHADERC_EXPORT const char *shaderc_result_get_error_message(const shaderc_compilation_result_t result);

#ifdef __cplusplus
}
#endif

#endif /* SHADERC_SHADERC_H_ */
