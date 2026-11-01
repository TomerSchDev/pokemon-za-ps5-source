// r28a texfix (port/runtime-texfix): the [za-texguard] reports. A finalized (or never initialized) texture that reaches
// the runtime is refused where it arrives - never registered, drawn into, copied, presented or uploaded to - and
// reported here: the first time per (site, caller) as a klog line, every time in a counter, the counters once every
// ZA_TG_SUMMARY_FRAMES presented frames when they changed. Nothing here runs unless a stale texture shows up (the
// per-frame hook returns on one load while there were none).
// Included once by textures.c (after nvn.h); host-tested (port/runtime-texfix/test) with LOG / frame stand-ins.
#pragma once
#include <pthread.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

#ifndef ZA_TG_LOG
#define ZA_TG_LOG(...) LOG(__VA_ARGS__)
#endif
#ifndef ZA_TG_FRAME
#define ZA_TG_FRAME() vk_frame_counter()
#endif
#define ZA_TG_SUMMARY_FRAMES 1800  // (one minute at 30 fps)
#define ZA_TG_MAX_SEEN 64

static const char *const za_tg_names[ZA_TG_SITES] = {
    [ZA_TG_REGISTER] = "register",              // textures.c tex_backend: a backend asked for a dead texture
    [ZA_TG_SET_RT] = "set-render-targets",      // exec.c: a recorded SetRenderTargets names a dead texture
    [ZA_TG_PASS] = "render-pass",               // exec.c begin_pass: a bound target is dead (state not cleared?)
    [ZA_TG_CLEAR_TEXTURE] = "clear-texture",    // exec.c CMD_CLEAR_TEXTURE
    [ZA_TG_COPY_TO_TEX] = "copy-buffer-to-texture",
    [ZA_TG_COPY_FROM_TEX] = "copy-texture-to-buffer",
    [ZA_TG_COPY_TEX] = "copy-texture",
    [ZA_TG_PRESENT] = "present",                // device.c backend_present / backend_represent
    [ZA_TG_UPLOAD_RGBA] = "video-upload",       // textures.c renderer_upload_rgba (video thread)
    [ZA_TG_POOL_REGISTER] = "pool-register",    // objects.c nvnTexturePoolRegisterTexture / Image
    [ZA_TG_FINALIZE_AGAIN] = "finalize-again",  // objects.c nvnTextureFinalize on a texture finalized before
    [ZA_TG_LIVE_LIST] = "live-list",            // za_texlive_r28a.h: a backend's slot did not hold it (repaired)
};

static pthread_mutex_t za_tg_lock = PTHREAD_MUTEX_INITIALIZER;
static struct { int site; const void *caller; } za_tg_seen[ZA_TG_MAX_SEEN];
static int za_tg_nseen;
static uint64_t za_tg_count[ZA_TG_SITES], za_tg_reported[ZA_TG_SITES];
static uint64_t za_tg_total;  // (read without the lock by the per-frame hook: atomics)

// detail: the texture's guard word (live-list: the backend's reg); caller: a return address or NULL (the site says it)
void za_texguard_hit(int site, const void *tex, uint32_t detail, const void *caller) {
    if (site < 0 || site >= ZA_TG_SITES) site = ZA_TG_REGISTER;
    bool first = true;
    pthread_mutex_lock(&za_tg_lock);
    za_tg_count[site]++;
    __atomic_add_fetch(&za_tg_total, 1, __ATOMIC_RELAXED);
    for (int i = 0; i < za_tg_nseen; i++)
        if (za_tg_seen[i].site == site && za_tg_seen[i].caller == caller) { first = false; break; }
    if (first && za_tg_nseen < ZA_TG_MAX_SEEN) {
        za_tg_seen[za_tg_nseen].site = site;
        za_tg_seen[za_tg_nseen].caller = caller;
        za_tg_nseen++;
    } else {
        first = false;  // (seen, or the table is full: counted only)
    }
    pthread_mutex_unlock(&za_tg_lock);
    if (!first) return;
    if (site == ZA_TG_LIVE_LIST)
        ZA_TG_LOG("[za-texguard] live-list: texture %p - its backend %p (reg %u) was not in its slot; repaired by a "
                  "scan (frame %llu)\n", tex, caller, (unsigned)detail, (unsigned long long)ZA_TG_FRAME());
    else
        ZA_TG_LOG("[za-texguard] %s: texture %p is not live (guard %08x: %s) - skipped, never registered (caller %p, "
                  "frame %llu)\n", za_tg_names[site], tex, (unsigned)detail,
                  detail == NVN_TEX_DEAD ? "finalized" : "unknown / reused memory", caller,
                  (unsigned long long)ZA_TG_FRAME());
}

// Once per presented frame (device.c): every ZA_TG_SUMMARY_FRAMES frames, the counters - if any changed.
void za_texguard_frame(uint64_t frame) {
    if (!__atomic_load_n(&za_tg_total, __ATOMIC_RELAXED) || frame % ZA_TG_SUMMARY_FRAMES) return;
    char line[512];
    int n = 0;
    bool changed = false;
    pthread_mutex_lock(&za_tg_lock);
    for (int s = 0; s < ZA_TG_SITES; s++) {
        if (za_tg_count[s] != za_tg_reported[s]) changed = true;
        za_tg_reported[s] = za_tg_count[s];
        if (za_tg_count[s] && n >= 0 && n < (int)sizeof line)
            n += snprintf(line + n, sizeof line - (size_t)n, " %s=%llu", za_tg_names[s], (unsigned long long)za_tg_count[s]);
    }
    pthread_mutex_unlock(&za_tg_lock);
    if (changed) ZA_TG_LOG("[za-texguard] counts at frame %llu:%s\n", (unsigned long long)frame, line);
}
