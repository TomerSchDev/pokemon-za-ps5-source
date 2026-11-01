/*
 * shaderc-cache: a cache-only stand-in for shaderc's C API, for the PS5 port of Pokemon Legends Z-A Recomp.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * There is no GLSL compiler on the console. runtime/nvn/vulkan/shaders.c (vk_glsl_to_spirv) first looks in its own
 * cache (cache/spirv/<hash>.spv) and only then calls shaderc_compile_into_spv; this implementation looks for the
 * same file in the directories of ZA_SHADERC_CACHE_DIRS (default "cache/spirv:/app0/cache/spirv" - the runtime's own
 * cache, then one shipped with the title) and returns it as a successful result. When there is none it returns a
 * compilation error that names the shader, its stage, the hash and the Vulkan version, and writes the GLSL to
 * ZA_SHADERC_MISSING_DIR (default "cache/spirv-missing", fallback /download0/za-spirv-missing) as <hash>.<stage>
 * so the shader can be compiled on the PC into cache/spirv/<hash>.spv (tools/compile-missing.sh, README.md).
 *
 * The hash is shaders.c's src_hash, verbatim (test/hash-parity.c compares it with the runtime's source text):
 *   h = (0xcbf29ce484222325 ^ stage) + 3;  if (api < VK_API_VERSION_1_3) h ^= api << 32;  FNV-1a over the GLSL bytes
 * where stage is the runtime's STAGE_* number (runtime/nvn/maxwell/shader.h: vertex 0, fragment 1, compute 5) and
 * api the Vulkan version the runtime chose (g_vkc.api: 1.3, or 1.2 under LARECOMP_VK_COMPAT), which it passes here
 * through shaderc_compile_options_set_target_env - the shaderc_env_version_vulkan_* values are VK_API_VERSION_*.
 * The "+ 3" is the version of shaders.c's post-processing (no_contraction) and must follow it.
 */
#define _POSIX_C_SOURCE 200809L
#include <shaderc/shaderc.h>

#include <errno.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>

#define ZSC_LOG(...) (fprintf(stderr, "[shaderc-cache] " __VA_ARGS__), fflush(stderr))

#define ZSC_HASH_VERSION 3u                        /* shaders.c src_hash: "+ 3" */
#define ZSC_VK_API_1_3 ((1u << 22) | (3u << 12))   /* VK_API_VERSION_1_3 == shaderc_env_version_vulkan_1_3 */
#define ZSC_SPIRV_MAGIC 0x07230203u
#define ZSC_MAX_DIRS 8

/* the runtime's stage numbers (runtime/nvn/maxwell/shader.h), part of the hash */
enum { ZSC_STAGE_VERTEX = 0, ZSC_STAGE_FRAGMENT = 1, ZSC_STAGE_GEOMETRY = 2, ZSC_STAGE_TESS_CTRL = 3,
       ZSC_STAGE_TESS_EVAL = 4, ZSC_STAGE_COMPUTE = 5 };
static const char *const zsc_stage_ext[] = {"vert", "frag", "geom", "tesc", "tese", "comp"};

struct shaderc_compiler { int unused; };
struct shaderc_compile_options {
    shaderc_target_env target;
    uint32_t version;
    shaderc_optimization_level level;
};
struct shaderc_compilation_result {
    shaderc_compilation_status status;
    char *bytes;   /* SPIR-V words, malloc'd */
    size_t length; /* bytes */
    char *error;   /* malloc'd message, or NULL */
};

static struct shaderc_compiler zsc_compiler;
static pthread_once_t zsc_once = PTHREAD_ONCE_INIT;
static char *zsc_dirs[ZSC_MAX_DIRS];
static int zsc_ndirs;
static const char *zsc_missing_dir;
static bool zsc_trace;
static atomic_int zsc_hits, zsc_misses, zsc_dumped;

static const char *zsc_env(const char *name)
{
    const char *v = getenv(name);
    return v && *v ? v : NULL;
}

static char *zsc_strdup(const char *s) /* (strdup is POSIX, not C11: the host build of the parity test is strict) */
{
    size_t n = strlen(s) + 1;
    char *copy = malloc(n);
    if (copy) memcpy(copy, s, n);
    return copy;
}

static void zsc_init(void)
{
    const char *dirs = zsc_env("ZA_SHADERC_CACHE_DIRS");
    char *list = zsc_strdup(dirs ? dirs : "cache/spirv:/app0/cache/spirv");
    for (char *p = list ? strtok(list, ":") : NULL; p && zsc_ndirs < ZSC_MAX_DIRS; p = strtok(NULL, ":"))
        if (*p) zsc_dirs[zsc_ndirs++] = p; /* (the strtok'd copy lives forever) */
    const char *m = zsc_env("ZA_SHADERC_MISSING_DIR");
    zsc_missing_dir = m ? m : "cache/spirv-missing";
    const char *t = zsc_env("ZA_SHADERC_TRACE");
    zsc_trace = t && strcmp(t, "0") != 0;
    ZSC_LOG("cache only (no GLSL compiler): %d cache dir(s):", zsc_ndirs);
    for (int i = 0; i < zsc_ndirs; i++) fprintf(stderr, " %s", zsc_dirs[i]);
    fprintf(stderr, "; misses are written to %s\n", zsc_missing_dir);
    fflush(stderr);
}

/* runtime/nvn/vulkan/shaders.c src_hash, for the same source, stage and Vulkan version */
uint64_t za_shaderc_cache_hash(const char *src, size_t len, int stage, uint32_t api)
{
    uint64_t h = (0xcbf29ce484222325ull ^ (uint64_t)stage) + ZSC_HASH_VERSION;
    if (api < ZSC_VK_API_1_3) h ^= (uint64_t)api << 32; /* (SPIR-V 1.5 for Vulkan 1.2: other files) */
    for (size_t i = 0; i < len && src[i]; i++) {
        h ^= (uint8_t)src[i];
        h *= 0x100000001B3ull;
    }
    return h;
}

static int zsc_stage_of(shaderc_shader_kind kind)
{
    switch (kind) {
    case shaderc_vertex_shader: return ZSC_STAGE_VERTEX;
    case shaderc_fragment_shader: return ZSC_STAGE_FRAGMENT;
    case shaderc_compute_shader: return ZSC_STAGE_COMPUTE;
    case shaderc_geometry_shader: return ZSC_STAGE_GEOMETRY;
    case shaderc_tess_control_shader: return ZSC_STAGE_TESS_CTRL;
    case shaderc_tess_evaluation_shader: return ZSC_STAGE_TESS_EVAL;
    default: return -1;
    }
}

/* a cached module: the validation of shaders.c cache_load (more than 20 bytes, whole words, the SPIR-V magic) */
static char *zsc_load(const char *path, size_t *length)
{
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    char *data = NULL;
    if (fseek(f, 0, SEEK_END) == 0) {
        long n = ftell(f);
        if (n > 20 && n % 4 == 0 && fseek(f, 0, SEEK_SET) == 0) {
            data = malloc((size_t)n);
            if (data && fread(data, 1, (size_t)n, f) != (size_t)n) {
                free(data);
                data = NULL;
            }
            if (data) {
                uint32_t magic;
                memcpy(&magic, data, 4);
                if (magic != ZSC_SPIRV_MAGIC) {
                    free(data);
                    data = NULL;
                }
            }
            if (data) *length = (size_t)n;
        }
    }
    fclose(f);
    return data;
}

static bool zsc_mkdir_p(const char *dir)
{
    char path[512];
    if (snprintf(path, sizeof path, "%s", dir) >= (int)sizeof path) return false;
    for (char *p = path + 1; *p; p++)
        if (*p == '/') {
            *p = 0;
            mkdir(path, 0755);
            *p = '/';
        }
    mkdir(path, 0755);
    struct stat st;
    return stat(path, &st) == 0 && S_ISDIR(st.st_mode);
}

/* the GLSL of a miss, for the PC: <dir>/<hash>.<stage>, and a line in <dir>/index.txt; the path written, or NULL */
static const char *zsc_dump(const char *src, size_t len, uint64_t hash, int stage, uint32_t api, const char *name,
                            char *out, size_t out_size)
{
    const char *dirs[2] = {zsc_missing_dir, "/download0/za-spirv-missing"};
    for (int d = 0; d < 2; d++) {
        if (d == 1 && !strcmp(dirs[0], dirs[1])) break;
        if (!zsc_mkdir_p(dirs[d])) continue;
        snprintf(out, out_size, "%s/%016llx.%s", dirs[d], (unsigned long long)hash, zsc_stage_ext[stage]);
        FILE *f = fopen(out, "wb");
        if (!f) continue;
        bool ok = fwrite(src, 1, len, f) == len;
        if (fclose(f) != 0) ok = false;
        if (!ok) {
            remove(out);
            continue;
        }
        char index[512];
        snprintf(index, sizeof index, "%s/index.txt", dirs[d]);
        FILE *ix = fopen(index, "ab");
        if (ix) {
            fprintf(ix, "%016llx\t%s\tvulkan%u.%u\t%s\n", (unsigned long long)hash, zsc_stage_ext[stage],
                    (api >> 22) & 0x7f, (api >> 12) & 0x3ff, name ? name : "?");
            fclose(ix);
        }
        atomic_fetch_add(&zsc_dumped, 1);
        return out;
    }
    return NULL;
}

static shaderc_compilation_result_t zsc_fail(shaderc_compilation_result_t r, shaderc_compilation_status status,
                                             const char *message)
{
    r->status = status;
    r->error = zsc_strdup(message);
    return r;
}

/* ------------------------------------------------------------------ the API */

shaderc_compiler_t shaderc_compiler_initialize(void)
{
    pthread_once(&zsc_once, zsc_init);
    return &zsc_compiler; /* never NULL: shaders.c vk_shaders_init is FATAL otherwise */
}

void shaderc_compiler_release(shaderc_compiler_t compiler)
{
    (void)compiler;
}

shaderc_compile_options_t shaderc_compile_options_initialize(void)
{
    shaderc_compile_options_t o = calloc(1, sizeof *o);
    if (o) {
        o->target = shaderc_target_env_vulkan;
        o->version = shaderc_env_version_vulkan_1_3; /* (shaders.c always sets it; shaderc's own default is 1.0) */
        o->level = shaderc_optimization_level_zero;
    }
    return o;
}

void shaderc_compile_options_release(shaderc_compile_options_t options)
{
    free(options);
}

void shaderc_compile_options_set_target_env(shaderc_compile_options_t options, shaderc_target_env target,
                                            uint32_t version)
{
    if (!options) return;
    options->target = target;
    options->version = version;
}

void shaderc_compile_options_set_optimization_level(shaderc_compile_options_t options,
                                                    shaderc_optimization_level level)
{
    /* recorded only: the cache has whatever the PC compiled with (shaders.c: zero unless LARECOMP_VK_OPT) */
    if (options) options->level = level;
}

shaderc_compilation_result_t shaderc_compile_into_spv(const shaderc_compiler_t compiler, const char *source_text,
                                                      size_t source_text_size, shaderc_shader_kind shader_kind,
                                                      const char *input_file_name, const char *entry_point_name,
                                                      const shaderc_compile_options_t additional_options)
{
    (void)compiler;
    (void)entry_point_name;
    pthread_once(&zsc_once, zsc_init);
    shaderc_compilation_result_t r = calloc(1, sizeof *r);
    if (!r) return NULL; /* (shaderc_result_* treat NULL as shaderc_compilation_status_null_result_object) */
    const char *name = input_file_name ? input_file_name : "?";
    char msg[1024];
    if (!source_text) return zsc_fail(r, shaderc_compilation_status_internal_error, "no source text");
    int stage = zsc_stage_of(shader_kind);
    if (stage < 0) {
        snprintf(msg, sizeof msg, "%s: shader kind %d is not one the cache knows (vertex, fragment, compute, "
                 "geometry, tessellation)", name, (int)shader_kind);
        return zsc_fail(r, shaderc_compilation_status_invalid_stage, msg);
    }
    uint32_t api = additional_options ? additional_options->version : (uint32_t)shaderc_env_version_vulkan_1_3;
    if (additional_options && additional_options->target != shaderc_target_env_vulkan) {
        snprintf(msg, sizeof msg, "%s: target environment %d is not Vulkan", name, (int)additional_options->target);
        return zsc_fail(r, shaderc_compilation_status_configuration_error, msg);
    }
    uint64_t hash = za_shaderc_cache_hash(source_text, source_text_size, stage, api);
    char path[512];
    for (int i = 0; i < zsc_ndirs; i++) {
        snprintf(path, sizeof path, "%s/%016llx.spv", zsc_dirs[i], (unsigned long long)hash);
        size_t length = 0;
        char *data = zsc_load(path, &length);
        if (!data) continue;
        r->status = shaderc_compilation_status_success;
        r->bytes = data;
        r->length = length;
        int hits = atomic_fetch_add(&zsc_hits, 1) + 1;
        if (zsc_trace) ZSC_LOG("hit %s: %s (%zu bytes, hit %d)\n", name, path, length, hits);
        return r;
    }
    int misses = atomic_fetch_add(&zsc_misses, 1) + 1;
    char dumped[512];
    const char *where = zsc_dump(source_text, source_text_size, hash, stage, api, name, dumped, sizeof dumped);
    /* Optional development bridge: a host watches the dumped source and publishes
     * validated SPIR-V atomically. Normal cache-only builds still fail immediately.
     * Bounded waiting keeps a missing host from hanging a title forever. */
    const char *wait_env = zsc_env("ZA_SHADERC_HOST_WAIT_MS");
    long wait_ms = wait_env ? strtol(wait_env, NULL, 10) : 0;
    if (wait_ms > 120000) wait_ms = 120000;
    if (where && wait_ms > 0) {
        ZSC_LOG("waiting for host: %016llx.%s, at most %ld ms\n",
                (unsigned long long)hash, zsc_stage_ext[stage], wait_ms);
        for (long elapsed = 0; elapsed < wait_ms; elapsed += 250) {
            const struct timespec delay = {.tv_sec = 0, .tv_nsec = 250000000};
            nanosleep(&delay, NULL);
            for (int i = 0; i < zsc_ndirs; i++) {
                snprintf(path, sizeof path, "%s/%016llx.spv", zsc_dirs[i], (unsigned long long)hash);
                size_t length = 0;
                char *data = zsc_load(path, &length);
                if (!data) continue;
                r->status = shaderc_compilation_status_success;
                r->bytes = data;
                r->length = length;
                atomic_fetch_add(&zsc_hits, 1);
                ZSC_LOG("host supplied %016llx (%zu bytes)\n", (unsigned long long)hash, length);
                return r;
            }
        }
    }
    snprintf(msg, sizeof msg,
             "no precompiled SPIR-V for %s (stage %s, hash %016llx, Vulkan %u.%u, miss %d): looked for "
             "%016llx.spv in %d cache dir(s)%s%s; %s%s - compile it on the PC into cache/spirv/%016llx.spv "
             "(port/shaderc-cache/tools/compile-missing.sh, README.md)",
             name, zsc_stage_ext[stage], (unsigned long long)hash, (api >> 22) & 0x7f, (api >> 12) & 0x3ff, misses,
             (unsigned long long)hash, zsc_ndirs, zsc_ndirs ? ": " : "", zsc_ndirs ? zsc_dirs[0] : "",
             where ? "the GLSL was written to " : "the GLSL could not be written (", where ? where : zsc_missing_dir,
             (unsigned long long)hash);
    if (!where) strncat(msg, ")", sizeof msg - strlen(msg) - 1);
    return zsc_fail(r, shaderc_compilation_status_compilation_error, msg);
}

void shaderc_result_release(shaderc_compilation_result_t result)
{
    if (!result) return;
    free(result->bytes);
    free(result->error);
    free(result);
}

size_t shaderc_result_get_length(const shaderc_compilation_result_t result)
{
    return result ? result->length : 0;
}

shaderc_compilation_status shaderc_result_get_compilation_status(const shaderc_compilation_result_t result)
{
    return result ? result->status : shaderc_compilation_status_null_result_object;
}

const char *shaderc_result_get_bytes(const shaderc_compilation_result_t result)
{
    return result ? result->bytes : NULL;
}

const char *shaderc_result_get_error_message(const shaderc_compilation_result_t result)
{
    if (!result) return "null result object";
    return result->error ? result->error : "";
}

/* for the port's diagnostics (not a shaderc name) */
void za_shaderc_cache_report(void)
{
    ZSC_LOG("report: %d hits, %d misses, %d GLSL files written to %s\n", atomic_load(&zsc_hits),
            atomic_load(&zsc_misses), atomic_load(&zsc_dumped), zsc_missing_dir ? zsc_missing_dir : "?");
}
