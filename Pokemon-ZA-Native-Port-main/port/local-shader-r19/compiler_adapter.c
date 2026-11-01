#include "../shader-prewarm/compiler.h"
#include "worker.h"
#include <glslang/Include/glslang_c_interface.h>
#include <glslang/Public/resource_limits_c.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int za_glsl_init(void) { return glslang_initialize_process(); }
void za_glsl_finish(void) { glslang_finalize_process(); }
static glsl_include_result_t *deny_include(void *ctx, const char *name, const char *from, size_t depth) {
    (void)ctx; (void)name; (void)from; (void)depth;
    return NULL;
}
static const char *text_or_empty(const char *text) { return text ? text : ""; }

int za_glsl_compile_for_api(const char *source, int stage, uint32_t api, uint32_t **words,
                    size_t *word_count, char *error, size_t error_size) {
    glslang_shader_t *shader = NULL;
    glslang_program_t *program = NULL;
    int ok = 0;
    *words = NULL; *word_count = 0;
    if (error_size) error[0] = 0;
    if (!source || stage < 0 || stage > 2 || (api != ((1u<<22)|(3u<<12)) && api != ((1u<<22)|(2u<<12)))) {
        if (error_size) snprintf(error, error_size, "Invalid source/stage");
        return 0;
    }
    const glslang_stage_t stages[] = {GLSLANG_STAGE_VERTEX, GLSLANG_STAGE_FRAGMENT, GLSLANG_STAGE_COMPUTE};
    glslang_input_t in = {0};
    in.language = GLSLANG_SOURCE_GLSL; in.stage = stages[stage];
    in.client = GLSLANG_CLIENT_VULKAN;
    in.client_version = api == ((1u<<22)|(3u<<12)) ? GLSLANG_TARGET_VULKAN_1_3 : GLSLANG_TARGET_VULKAN_1_2;
    in.target_language = GLSLANG_TARGET_SPV;
    in.target_language_version = api == ((1u<<22)|(3u<<12)) ? GLSLANG_TARGET_SPV_1_6 : GLSLANG_TARGET_SPV_1_5;
    in.code = source; in.default_version = 450; in.default_profile = GLSLANG_NO_PROFILE;
    in.messages = (glslang_messages_t)(GLSLANG_MSG_SPV_RULES_BIT | GLSLANG_MSG_VULKAN_RULES_BIT);
    in.resource = glslang_default_resource();
    in.callbacks.include_local = deny_include; in.callbacks.include_system = deny_include;
    shader = glslang_shader_create(&in);
    if (!shader) goto done;
    if (!glslang_shader_preprocess(shader, &in)) goto done;
    in.code = glslang_shader_get_preprocessed_code(shader);
    if (!glslang_shader_parse(shader, &in)) goto done;
    program = glslang_program_create();
    if (!program) goto done;
    glslang_program_add_shader(program, shader);
    if (!glslang_program_link(program, in.messages)) goto done;
    glslang_spv_options_t options = {0};
    options.disable_optimizer = true;
    glslang_program_SPIRV_generate_with_options(program, in.stage, &options);
    size_t count = glslang_program_SPIRV_get_size(program);
    if (!count || count > (16u << 20) / sizeof(uint32_t)) goto done;
    *words = malloc(count * sizeof(uint32_t));
    if (!*words) goto done;
    glslang_program_SPIRV_get(program, *words); *word_count = count; ok = 1;
done:
    if (!ok && error_size) {
        snprintf(error, error_size, "%s\n%s\n%s", shader ? text_or_empty(glslang_shader_get_info_log(shader)) : "allocation failure",
            program ? text_or_empty(glslang_program_get_info_log(program)) : "",
            program ? text_or_empty(glslang_program_SPIRV_get_messages(program)) : "");
    }
    if (program) glslang_program_delete(program);
    if (shader) glslang_shader_delete(shader);
    return ok;
}
