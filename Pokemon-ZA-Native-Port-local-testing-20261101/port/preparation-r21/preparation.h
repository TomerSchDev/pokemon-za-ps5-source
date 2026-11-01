#ifndef ZA_PREPARATION_R21_H
#define ZA_PREPARATION_R21_H
/* VkBindingInfo and Vulkan descriptor enums are provided by shaders.h.
 * Immutable CPU metadata only. No handles, contents or GPU ownership cached. */
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define ZA_PREP_MAX_BIND 96
#define ZA_PREP_PLAN 1u
#define ZA_PREP_LAZY 2u
typedef enum {
    ZA_PREP_SKIP, ZA_PREP_TEXTURE, ZA_PREP_CBUF, ZA_PREP_STORAGE,
    ZA_PREP_RSCALE, ZA_PREP_TINT, ZA_PREP_GMAP
} ZaPrepKind;
typedef struct { uint8_t source, kind; } ZaPrepItem;
typedef struct {
    ZaPrepItem ordinary[ZA_PREP_MAX_BIND], special[ZA_PREP_MAX_BIND];
    uint8_t nordinary, nspecial;
    bool has_rscale;
} ZaPrepStage;
typedef struct { ZaPrepStage stage[2]; } ZaPrepRecipe;
static inline ZaPrepKind za_prep_kind(const VkBindingInfo *b) {
    if (b->type == VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER && b->binding >= 32) return ZA_PREP_TEXTURE;
    if (b->type == VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER && b->binding < 17) return ZA_PREP_CBUF;
    if (b->type == VK_DESCRIPTOR_TYPE_STORAGE_BUFFER) return ZA_PREP_STORAGE;
    if (b->type == VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER) {
        if (b->binding == 18) return ZA_PREP_RSCALE;
        if (b->binding == 19) return ZA_PREP_TINT;
        if (b->binding == GMAP_BUFFER_INDEX) return ZA_PREP_GMAP;
    }
    return ZA_PREP_SKIP;
}
static inline bool za_prep_build(ZaPrepRecipe *out, const VkBindingInfo *bindings, int n) {
    memset(out, 0, sizeof *out);
    if (n < 0 || n > ZA_PREP_MAX_BIND || (n && !bindings)) return false;
    for (int i = 0; i < n; ++i) {
        const VkBindingInfo *b = &bindings[i];
        if (b->set >= 2) continue;
        ZaPrepKind kind = za_prep_kind(b);
        ZaPrepStage *s = &out->stage[b->set];
        ZaPrepItem item = {(uint8_t)i, (uint8_t)kind};
        if (kind >= ZA_PREP_TEXTURE && kind <= ZA_PREP_STORAGE) s->ordinary[s->nordinary++] = item;
        else if (kind >= ZA_PREP_RSCALE && kind <= ZA_PREP_GMAP) s->special[s->nspecial++] = item;
        s->has_rscale |= kind == ZA_PREP_RSCALE;
    }
    return true;
}
static inline int za_prep_parse(const char *name) {
    if (!name) return -1;
    if (!strcmp(name, "baseline")) return 0;
    if (!strcmp(name, "plan-only")) return ZA_PREP_PLAN;
    if (!strcmp(name, "lazy-only")) return ZA_PREP_LAZY;
    if (!strcmp(name, "optimized")) return ZA_PREP_PLAN | ZA_PREP_LAZY;
    return -1;
}
static inline const char *za_prep_name(unsigned flags) {
    static const char *const names[] = {"baseline", "plan-only", "lazy-only", "optimized"};
    return flags < 4 ? names[flags] : "invalid";
}
#endif
