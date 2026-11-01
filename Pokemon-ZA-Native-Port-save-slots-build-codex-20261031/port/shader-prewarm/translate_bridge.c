/* Host-only wrapper around the exact installed runtime translator.
 * Caller serializes calls. No game execution or graphics driver access. */
#include "shader.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

char *za_translate(const unsigned char *code, size_t size, int stage,
                   unsigned vs_mask, unsigned flip_y, unsigned depth, unsigned stencil,
                   unsigned sint, unsigned *out_mask, unsigned *attr_mask, char *error, size_t cap) {
    if ((stage != 0 && stage != 1 && stage != 5) || size < (stage == 5 ? 0x110 : 0x90) || size > (4u << 20)) {
        snprintf(error, cap, "Unsupported stage or program length"); return NULL;
    }
    ShaderKey key = {0};
    key.glsl = 1; key.flip_y = flip_y != 0; key.depth_minus_one = depth != 0;
    key.vs_out_mask = vs_mask; key.stencil_slots = stencil; key.sint_slots = sint;
    maxwell_gmem_base = 0x7676b00000ull; maxwell_gmem_size = 0xc9500000ull;
    ShaderInfo *info = maxwell_translate(code, size, stage, &key);
    if (!info) { snprintf(error, cap, "Translator allocation failed"); return NULL; }
    *out_mask = info->out_mask; *attr_mask = info->attr_mask;
    char *source = info->msl;
    if (!source) snprintf(error, cap, "%s", info->error);
    info->msl = NULL; maxwell_free(info);
    return source;
}
void za_translate_free(char *source) { free(source); }
