// third_party/ps5-stubs: MINIMAL STUB of shaderc's C API for compile-only checks of the ZA Recomp runtime on the PS5
// target when no real shaderc header is at hand. NOT the real header, NO implementation: only what
// runtime/nvn/vulkan/shaders.c uses, with shaderc's real values. The real one: MSYS2's ucrt64/include/shaderc/shaderc.h.
#pragma once
#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct shaderc_compiler *shaderc_compiler_t;
typedef struct shaderc_compile_options *shaderc_compile_options_t;
typedef struct shaderc_compilation_result *shaderc_compilation_result_t;

typedef enum {
    shaderc_vertex_shader = 0, shaderc_fragment_shader = 1, shaderc_compute_shader = 2, shaderc_geometry_shader = 3,
    shaderc_tess_control_shader = 4, shaderc_tess_evaluation_shader = 5,
    shaderc_glsl_vertex_shader = shaderc_vertex_shader, shaderc_glsl_fragment_shader = shaderc_fragment_shader,
    shaderc_glsl_compute_shader = shaderc_compute_shader, shaderc_glsl_infer_from_source = 6,
} shaderc_shader_kind;

typedef enum {
    shaderc_target_env_vulkan = 0, shaderc_target_env_opengl = 1, shaderc_target_env_opengl_compat = 2,
    shaderc_target_env_webgpu = 3, shaderc_target_env_default = shaderc_target_env_vulkan,
} shaderc_target_env;

typedef enum {
    shaderc_env_version_vulkan_1_0 = (1u << 22), shaderc_env_version_vulkan_1_1 = (1u << 22) | (1 << 12),
    shaderc_env_version_vulkan_1_2 = (1u << 22) | (2 << 12), shaderc_env_version_vulkan_1_3 = (1u << 22) | (3 << 12),
    shaderc_env_version_vulkan_1_4 = (1u << 22) | (4 << 12), shaderc_env_version_opengl_4_5 = 450,
} shaderc_env_version;

typedef enum {
    shaderc_optimization_level_zero = 0, shaderc_optimization_level_size = 1, shaderc_optimization_level_performance = 2,
} shaderc_optimization_level;

typedef enum {
    shaderc_compilation_status_success = 0, shaderc_compilation_status_invalid_stage = 1,
    shaderc_compilation_status_compilation_error = 2, shaderc_compilation_status_internal_error = 3,
    shaderc_compilation_status_null_result_object = 4, shaderc_compilation_status_invalid_assembly = 5,
    shaderc_compilation_status_validation_error = 6, shaderc_compilation_status_transformation_error = 7,
    shaderc_compilation_status_configuration_error = 8,
} shaderc_compilation_status;

shaderc_compiler_t shaderc_compiler_initialize(void);
void shaderc_compiler_release(shaderc_compiler_t compiler);
shaderc_compile_options_t shaderc_compile_options_initialize(void);
void shaderc_compile_options_release(shaderc_compile_options_t options);
void shaderc_compile_options_set_target_env(shaderc_compile_options_t options, shaderc_target_env target, uint32_t version);
void shaderc_compile_options_set_optimization_level(shaderc_compile_options_t options, shaderc_optimization_level level);
shaderc_compilation_result_t shaderc_compile_into_spv(const shaderc_compiler_t compiler, const char *source_text,
                                                      size_t source_text_size, shaderc_shader_kind shader_kind,
                                                      const char *input_file_name, const char *entry_point_name,
                                                      const shaderc_compile_options_t additional_options);
void shaderc_result_release(shaderc_compilation_result_t result);
size_t shaderc_result_get_length(const shaderc_compilation_result_t result);
const char *shaderc_result_get_bytes(const shaderc_compilation_result_t result);
shaderc_compilation_status shaderc_result_get_compilation_status(const shaderc_compilation_result_t result);
const char *shaderc_result_get_error_message(const shaderc_compilation_result_t result);

#ifdef __cplusplus
}
#endif
