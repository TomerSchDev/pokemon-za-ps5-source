"""r28a texfix: apply the texture-lifetime fix to a runtime tree (a copy - never a reference tree).

    python3 apply-runtime-texfix.py <runtime dir> [--check]

<runtime dir> is a tree's runtime/ (PS5 work copies: <work>/source/runtime; the PC build: <src>/runtime). Exact-text
edits: every anchor must occur exactly once (alternatives: exactly one of them); replaced blocks are recognised by
their SHA-256. A tree that already has an edit keeps it (idempotent). --check verifies without writing.

The mechanism and the fix: port/runtime-texfix/README-HE.md. In short:
  nvn/nvn.h           NvnTexture.za_guard in the struct's tail padding (layout and size asserted unchanged), the
                      liveness check, the [za-texguard] sites
  nvn/objects.c       the guard set at nvnTextureInitialize, poisoned at nvnTextureFinalize; finalized textures kept
                      in a quarantine ring before free(); a second finalize and pool registration of a dead texture
                      refused; exec_lock offered to device.c
  nvn/vulkan/textures.c  the live list as (texture, backend) pairs under its own lock (za_texlive_r28a.h), remove
                      validated, a dead texture never registered (tex_backend), its references dropped on destroy,
                      the video thread's upload under the lock the destroy detaches with; reports (za_texguard_r28a.h)
  nvn/vulkan/exec.c   a finalized texture leaves the bound render targets and snapshots; recorded lists naming one
                      skip it (SetRenderTargets, clear-texture, copies); begin_pass never registers one
  nvn/vulkan/device.c the present path under exec_lock (as list execution and finalize), never a dead texture;
                      the last presented texture forgotten when finalized
"""
import hashlib
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEW_FILES = {  # (copied into the tree)
    'nvn/za_texguard_api_r28a.h': HERE / 'src/za_texguard_api_r28a.h',
    'nvn/za_texquarantine_r28a.h': HERE / 'src/za_texquarantine_r28a.h',
    'nvn/vulkan/za_texlive_r28a.h': HERE / 'src/za_texlive_r28a.h',
    'nvn/vulkan/za_texguard_r28a.h': HERE / 'src/za_texguard_r28a.h',
}

# ---------------------------------------------------------------------------------------------------- nvn/nvn.h
NVN_H = [
    ('replace', ['#include "../hle.h"\n'], '#include <stddef.h>\n#include "../hle.h"\n'),
    ('replace', ['    bool in_pool;  // registered in a texture pool once (its entries are cleared when it\'s finalized: objects.c)\n'
                 '} NvnTexture;\n'],
     '    bool in_pool;  // registered in a texture pool once (its entries are cleared when it\'s finalized: objects.c)\n'
     '    uint32_t za_guard;  // r28a (port/runtime-texfix): NVN_TEX_LIVE while initialized, NVN_TEX_DEAD once finalized\n'
     '} NvnTexture;\n'
     '// r28a: za_guard sits in the tail padding - every offset and the size stay r28-play\'s, which the objects that are\n'
     '// not rebuilt were compiled against\n'
     '_Static_assert(offsetof(NvnTexture, backend) == 112 && offsetof(NvnTexture, in_pool) == 192 &&\n'
     '               offsetof(NvnTexture, za_guard) == 196 && sizeof(NvnTexture) == 200, "r28a: NvnTexture layout changed");\n'
     '#include "za_texguard_api_r28a.h"  // r28a: the guard\'s values, nvn_tex_live, the [za-texguard] sites\n'),
]

# ---------------------------------------------------------------------------------------------------- nvn/objects.c
OBJECTS_C = [
    ('replace', ['#include "nvn.h"\n'], '#include "nvn.h"\n#include "za_texquarantine_r28a.h"  // r28a (port/runtime-texfix)\n'),
    ('replace', ['static void exec_lock_give(void) { pthread_mutex_unlock(&exec_lock); }\n'],
     'static void exec_lock_give(void) { pthread_mutex_unlock(&exec_lock); }\n'
     '// r28a (port/runtime-texfix): the same lock for device.c\'s present and re-present - they register and read textures,\n'
     '// views and the deferred-destruction list that nvnTextureFinalize changes on other threads\n'
     'void za_nvn_exec_lock(void) { exec_lock_take(); }\n'
     'void za_nvn_exec_unlock(void) { exec_lock_give(); }\n'),
    ('replace', ['    t->debug_id = next_debug_id++;\n    return t;\n}\n'],
     '    t->debug_id = next_debug_id++;\n'
     '    t->za_guard = NVN_TEX_LIVE;  // r28a (port/runtime-texfix): live until nvnTextureFinalize\n'
     '    static int za_armed;\n'
     '    if (!__atomic_fetch_add(&za_armed, 1, __ATOMIC_RELAXED))\n'
     '        LOG("[za-texguard] r28a texfix active: live list locked, finalized textures guarded and quarantined (%d), "\n'
     '            "present under exec_lock\\n", ZA_TEX_QUARANTINE);\n'
     '    return t;\n}\n'),
    ('replace', ['        exec_lock_take();  // (not while a submitted list may be reading it: nvnQueueSubmitCommands)\n'],
     '        exec_lock_take();  // (not while a submitted list may be reading it: nvnQueueSubmitCommands)\n'
     '        if (t->za_guard != NVN_TEX_LIVE) {  // r28a: finalized before (a guest copy of the object): never twice\n'
     '            za_texguard_hit(ZA_TG_FINALIZE_AGAIN, t, t->za_guard, NULL);\n'
     '            exec_lock_give();\n'
     '            SET_HOST(A(0), 0);\n'
     '            return;\n'
     '        }\n'),
    ('replace', ['        backend_texture_destroyed(t);\n        free(t);\n        exec_lock_give();\n'],
     '        backend_texture_destroyed(t);  // (r28a: the runtime\'s references to it go too - textures.c)\n'
     '        t->za_guard = NVN_TEX_DEAD;    // r28a: a stale pointer to it is refused from here on (nvn.h nvn_tex_live)\n'
     '        za_quarantine_push(t);         // r28a: freed ZA_TEX_QUARANTINE finalizations later, not now\n'
     '        exec_lock_give();\n'),
    ('replace', ['    e->tex = HOST(NvnTexture, A(2));\n    if (e->tex) e->tex->in_pool = true;\n'],
     '    e->tex = HOST(NvnTexture, A(2));\n'
     '    if (e->tex && !nvn_tex_live(e->tex)) {  // r28a: a finalized texture (a stale guest copy): an empty slot instead\n'
     '        za_texguard_hit(ZA_TG_POOL_REGISTER, e->tex, e->tex->za_guard, NULL);\n'
     '        e->tex = NULL;\n'
     '    }\n'
     '    if (e->tex) e->tex->in_pool = true;\n'),
]

# ---------------------------------------------------------------------------------------------------- nvn/vulkan/textures.c
TEXTURES_LIVE_BLOCK = '''// Live game textures: an in-place reboot (vk_textures_reset) destroys them all.
// r28a (port/runtime-texfix): the list - (texture, backend) pairs under a lock of its own - is za_texlive_r28a.h, the
// guard's reports za_texguard_r28a.h. A texture gets a backend only while it is live (nvn.h NVN_TEX_LIVE, objects.c):
// a stale pointer to a finalized one is refused here and reported, never registered again.
static pthread_mutex_t pending_lock = PTHREAD_MUTEX_INITIALIZER;  // (r28a: here - a destroy detaches under it too)
#include "za_texguard_r28a.h"
#include "za_texlive_r28a.h"

// r28a: what a refused (dead) texture gets, should a caller still ask for its image: a 1x1 black RGBA8 image of its
// own - never listed, never freed, never uploaded to from the dead texture's memory. (exec.c and device.c refuse dead
// textures before they ask; this keeps a missed path from registering one.)
static TexBackend *za_dead_backend(void) {
    static TexBackend d;
    if (!d.image) {
        VkImageCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                                .format = VK_FORMAT_R8G8B8A8_UNORM, .extent = {1, 1, 1}, .mipLevels = 1, .arrayLayers = 1,
                                .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                                .usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT |
                                         VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT,
                                .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED};
        VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
        VK_CHECK(vmaCreateImage(g_vk.vma, &ci, &ai, &d.image, &d.mem, NULL));
        VkCommandBuffer cb = vk_upload_cmd();
        vk_image_init_layout(cb, d.image, VK_IMAGE_ASPECT_COLOR_BIT);
        VkClearColorValue black = {{0, 0, 0, 1}};
        VkImageSubresourceRange all = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        vkCmdClearColorImage(cb, d.image, VK_IMAGE_LAYOUT_GENERAL, &black, 1, &all);
        d.format = VK_FORMAT_R8G8B8A8_UNORM;
        d.base_type = VK_IMAGE_VIEW_TYPE_2D;
        d.width = d.height = d.depth = d.layers = d.levels = d.samples = 1;
        d.aspect = VK_IMAGE_ASPECT_COLOR_BIT;
        d.gpu_owned = d.uploaded = true;
        d.sx = d.sy = 1;
    }
    return &d;
}

// caller: the return address of the public function asking (vk_tex, vk_view, ...) - the [za-texguard] line's caller
static TexBackend *tex_backend_at(NvnTexture *t, const void *caller) {
    TexBackend *b = t->backend;
    if (b) {
        if (b->scalable && (b->sx != g_rs_x || b->sy != g_rs_y)) {  // output resolution changed: reallocate
            destroy_image(b);
            create_image(t, b);
        }
        return b;
    }
    if (!nvn_tex_live(t)) {  // r28a: finalized (or never initialized): refused - not created, not listed, t not written
        za_texguard_hit(ZA_TG_REGISTER, t, t->za_guard, caller);
        return za_dead_backend();
    }
    vk_collect_dead();
    b = calloc(1, sizeof *b);
    b->scalable = tex_scalable(t);
    create_image(t, b);
    t->backend = b;
    za_live_add(t, b);
    return b;
}
#define tex_backend(t) tex_backend_at((t), __builtin_return_address(0))

static void hd_forget(NvnTexture *t);  // (HD texture packs, below)
// A texture finalized (objects.c, under exec_lock) or released by a reboot: its backend goes, and with it every
// reference the runtime keeps to the texture itself (r28a: exec.c's bound targets and snapshots, device.c's last
// presented texture) - nothing is left to follow the pointer once objects.c poisons it.
void backend_texture_destroyed(NvnTexture *t) {
    extern void vk_exec_texture_destroyed(NvnTexture *t);     // r28a (exec.c)
    extern void vk_present_texture_destroyed(NvnTexture *t);  // r28a (device.c)
    vk_exec_texture_destroyed(t);
    vk_present_texture_destroyed(t);
    TexBackend *b = t->backend;
    if (b) {
        extern void vk_alias_texture_destroyed(NvnTexture *t);  // (exec.c copy aliases: a source's contents handed over)
        vk_alias_texture_destroyed(t);
        hd_forget(t);
        pthread_mutex_lock(&pending_lock);  // r28a: renderer_upload_rgba (the video thread) finds the backend under it
        t->backend = NULL;
        void *pending = b->pending_rgba;
        b->pending_rgba = NULL;
        pthread_mutex_unlock(&pending_lock);
        za_live_remove(t, b);
        destroy_image(b);
        free(pending);
        free(b);
    }
    t->backend = NULL;
}

// r28a: a listed backend whose texture is not live any more or has another backend (not expected): its image, views
// and memory only - the texture is not followed
static void za_backend_drop(TexBackend *b) {
    destroy_image(b);
    free(b->pending_rgba);
    free(b);
}

// Reboot (device.c backend_reset; GPU idle): every game texture and its views go.
void vk_textures_reset(void) {
    int n = 0;
    extern void vk_alias_reset(void);
    vk_alias_reset();
    NvnTexture *t;
    TexBackend *b;
    while (za_live_pop(&t, &b)) {  // (r28a: each pair out of the list first)
        n++;
        if (nvn_tex_live(t) && t->backend == b) backend_texture_destroyed(t);
        else za_backend_drop(b);
    }
    vk_collect_dead();
    LOG("[vk] reboot: %d textures released\\n", n);
}
'''

TEXTURES_HD_BLOCK = '''    HdWalk w = {was, 0};
    za_live_walk(hd_switch_one, &w);  // (r28a: under the list's lock)
    LOG("[tex] textures: %s (%d re-uploaded)\\n", hd_on ? "HD" : "original", w.n);
'''

TEXTURES_UPLOAD_BLOCK = '''void renderer_upload_rgba(NvnTexture *t, const void *rgba, uint32_t w, uint32_t h, uint32_t stride) {
    if (!t || !t->backend) return;  // the game binds the texture before decoding into it; first frames may arrive earlier
    void *copy = malloc((size_t)stride * h);
    memcpy(copy, rgba, (size_t)stride * h);
    void *old = NULL;
    pthread_mutex_lock(&pending_lock);
    // r28a: the backend looked up again under the lock backend_texture_destroyed detaches it with (this is the video
    // thread; a finalize runs on another): never a freed backend, never a finalized texture
    TexBackend *b = nvn_tex_live(t) ? t->backend : NULL;
    if (b) {
        old = b->pending_rgba;
        b->pending_rgba = copy;
        b->pending_w = w; b->pending_h = h; b->pending_stride = stride;
        b->gpu_owned = true;
        copy = NULL;
    }
    pthread_mutex_unlock(&pending_lock);
    free(old);
    if (copy) {
        free(copy);
        za_texguard_hit(ZA_TG_UPLOAD_RGBA, t, 0, __builtin_return_address(0));
    }
}
'''

TEXTURES_C = [
    ('block', ('// Live game textures: an in-place reboot (vk_textures_reset) destroys them all.\n',
               '    LOG("[vk] reboot: %d textures released\\n", n);\n}\n'),
     ['da6b7b6c6c3f147aaa54b05000c4181f37c11013a462feae60ffdeda049d1ce9'], TEXTURES_LIVE_BLOCK),
    ('replace', ['// F1 > Textures (setting tex_hd) changed: between frames, every live texture goes back to the game\'s image or is\n'],
     '// r28a: one entry of hd_switch\'s walk (under the list\'s lock): the list\'s own backend; its texture only while live\n'
     'typedef struct { bool was; int n; } HdWalk;\n'
     'static void hd_switch_one(NvnTexture *t, TexBackend *b, void *arg) {\n'
     '    HdWalk *w = arg;\n'
     '    if (!nvn_tex_live(t) || t->backend != b) return;\n'
     '    if (w->was && !hd_on && b->hd && !(hd_sets[0].n && bsearch(&b->data_hash, hd_sets[0].h, hd_sets[0].n, sizeof b->data_hash, hd_cmp))) {\n'
     '        destroy_image(b);\n'
     '        b->hd = false;\n'
     '        create_image(t, b);\n'
     '        b->uploaded = false;\n'
     '        w->n++;\n'
     '    } else if (hd_on && !b->hd && !b->dynamic) {\n'
     '        b->uploaded = false;\n'
     '        w->n++;\n'
     '    }\n'
     '}\n'
     '\n'
     '// F1 > Textures (setting tex_hd) changed: between frames, every live texture goes back to the game\'s image or is\n'),
    ('block', ('    int n = 0;\n    for (int i = 0; i < g_nlive; i++) {\n',
               '    LOG("[tex] textures: %s (%d re-uploaded)\\n", hd_on ? "HD" : "original", n);\n'),
     ['65157249c32900061f11289d883f90d5779fb78329c416fd93b2de598d3b1f0b'], TEXTURES_HD_BLOCK),
    ('replace', ['static pthread_mutex_t pending_lock = PTHREAD_MUTEX_INITIALIZER;\n\nstatic void upload_pending(TexBackend *b) {\n'],
     '// (pending_lock: defined with the live list above - r28a)\nstatic void upload_pending(TexBackend *b) {\n'),
    ('replace', ['TexBackend *vk_tex(NvnTexture *t, bool for_render) {\n    TexBackend *b = tex_backend(t);\n'],
     '// r28a: vk_tex_at - vk_tex with the caller the [za-texguard] line names (vk_view / vk_render_view pass theirs)\n'
     'static TexBackend *vk_tex_at(NvnTexture *t, bool for_render, const void *caller);\n'
     'TexBackend *vk_tex(NvnTexture *t, bool for_render) { return vk_tex_at(t, for_render, __builtin_return_address(0)); }\n'
     'static TexBackend *vk_tex_at(NvnTexture *t, bool for_render, const void *caller) {\n'
     '    TexBackend *b = tex_backend_at(t, caller);\n'),
    ('block', ('void renderer_upload_rgba(NvnTexture *t, const void *rgba, uint32_t w, uint32_t h, uint32_t stride) {\n',
               '    pthread_mutex_unlock(&pending_lock);\n}\n'),
     ['ec82e3f706ffc9f36bc36f2caf2bfbac26deb4c4adb52e24d7fec1d373a4cf35'], TEXTURES_UPLOAD_BLOCK),
    ('replace', ['    TexBackend *b = vk_tex(t, true);\n    if (!has_view) v = NULL;\n    if (layers) *layers = 1;\n'],
     '    TexBackend *b = vk_tex_at(t, true, __builtin_return_address(0));  // (r28a: the caller, for [za-texguard])\n'
     '    if (!has_view) v = NULL;\n    if (layers) *layers = 1;\n'),
    ('replace', ['    if (render) return vk_render_view(t, v, has_view, NULL);\n    TexBackend *b = vk_tex(t, render);\n'],
     '    if (render) return vk_render_view(t, v, has_view, NULL);\n'
     '    TexBackend *b = vk_tex_at(t, render, __builtin_return_address(0));  // (r28a: the caller, for [za-texguard])\n'),
]

# ---------------------------------------------------------------------------------------------------- nvn/vulkan/exec.c
EXEC_C = [
    ('replace', ['static Snap snaps[16];\nstatic int nsnaps;\n'],
     'static Snap snaps[16];\nstatic int nsnaps;\n'
     '\n'
     '// r28a (port/runtime-texfix): textures.c backend_texture_destroyed, under exec_lock - a finalized texture leaves the\n'
     '// executor\'s state. The bound render targets outlive their list: a later list drawing without SetRenderTargets of\n'
     '// its own would hand the freed pointer to begin_pass, which registered it again - one way freed memory reached\n'
     '// textures.c\'s live list (r28-play\'s crash). The snapshots are keyed by the pointer.\n'
     'void vk_exec_texture_destroyed(NvnTexture *t) {\n'
     '    bool bound = false;\n'
     '    for (int i = 0; i < 8; i++)\n'
     '        if (st.rt.color[i] == t) st.rt.color[i] = NULL, bound = true;\n'
     '    if (st.rt.depth == t) st.rt.depth = NULL, bound = true;\n'
     '    if (bound) st.rt_dirty = true;\n'
     '    for (int i = 0; i < 4; i++)\n'
     '        if (feedback_tex[i] == t) feedback_tex[i] = NULL;\n'
     '    for (int i = 0; i < 8; i++)\n'
     '        if (snap_tex[i] == t) snap_tex[i] = NULL, snap_ok[i] = false;\n'
     '    for (int i = 0; i < nsnaps; i++)\n'
     '        if (snaps[i].key == t) snaps[i].key = NULL;\n'
     '}\n'),
    ('replace', ['            st.rt.has_dview = rt->has_dview;\n'],
     '            st.rt.has_dview = rt->has_dview;\n'
     '            for (int i = 0; i < st.rt.ncolor; i++)  // r28a: a recorded target finalized since: not drawn into\n'
     '                if (st.rt.color[i] && !nvn_tex_live(st.rt.color[i])) {\n'
     '                    za_texguard_hit(ZA_TG_SET_RT, st.rt.color[i], st.rt.color[i]->za_guard, NULL);\n'
     '                    st.rt.color[i] = NULL;\n'
     '                }\n'
     '            if (st.rt.depth && !nvn_tex_live(st.rt.depth)) {\n'
     '                za_texguard_hit(ZA_TG_SET_RT, st.rt.depth, st.rt.depth->za_guard, NULL);\n'
     '                st.rt.depth = NULL;\n'
     '            }\n'),
    ('replace', ['        pass_color[i] = VK_FORMAT_UNDEFINED;\n        if (!t) continue;\n'],
     '        pass_color[i] = VK_FORMAT_UNDEFINED;\n'
     '        if (t && !nvn_tex_live(t)) {  // r28a: never registered again (SetRenderTargets and finalize keep these live)\n'
     '            za_texguard_hit(ZA_TG_PASS, t, t->za_guard, NULL);\n'
     '            st.rt.color[i] = t = NULL;\n'
     '        }\n'
     '        if (!t) continue;\n'),
    ('replace', ['    if (st.rt.depth) {\n        renderer_mark_gpu_owned(st.rt.depth);\n'],
     '    if (st.rt.depth && !nvn_tex_live(st.rt.depth)) {  // r28a (as the colour targets)\n'
     '        za_texguard_hit(ZA_TG_PASS, st.rt.depth, st.rt.depth->za_guard, NULL);\n'
     '        st.rt.depth = NULL;\n'
     '    }\n'
     '    if (st.rt.depth) {\n        renderer_mark_gpu_owned(st.rt.depth);\n'),
    ('replace', ['            NvnTexture *t = (NvnTexture *)(uintptr_t)ct->tex;\n            if (!t) break;\n'],
     '            NvnTexture *t = (NvnTexture *)(uintptr_t)ct->tex;\n            if (!t) break;\n'
     '            if (!nvn_tex_live(t)) { za_texguard_hit(ZA_TG_CLEAR_TEXTURE, t, t->za_guard, NULL); break; }  // r28a\n'),
    ('replace', ['    NvnTexture *t = (NvnTexture *)(uintptr_t)dst->tex;\n    if (!t || !src) return;\n'],
     '    NvnTexture *t = (NvnTexture *)(uintptr_t)dst->tex;\n    if (!t || !src) return;\n'
     '    if (!nvn_tex_live(t)) { za_texguard_hit(ZA_TG_COPY_TO_TEX, t, t->za_guard, NULL); return; }  // r28a\n'),
    ('replace', ['    NvnTexture *t = (NvnTexture *)(uintptr_t)src->tex;\n    if (!t || !dst || dst < GUEST_LO) return;\n'],
     '    NvnTexture *t = (NvnTexture *)(uintptr_t)src->tex;\n    if (!t || !dst || dst < GUEST_LO) return;\n'
     '    if (!nvn_tex_live(t)) { za_texguard_hit(ZA_TG_COPY_FROM_TEX, t, t->za_guard, NULL); return; }  // r28a\n'),
    ('replace', ['    if (!st_ || !dt) return;\n'],
     '    if (!st_ || !dt) return;\n'
     '    if (!nvn_tex_live(st_) || !nvn_tex_live(dt)) {  // r28a: a side finalized since the list was recorded\n'
     '        NvnTexture *x = nvn_tex_live(st_) ? dt : st_;\n'
     '        za_texguard_hit(ZA_TG_COPY_TEX, x, x->za_guard, NULL);\n'
     '        return;\n'
     '    }\n'),
]

# ---------------------------------------------------------------------------------------------------- nvn/vulkan/device.c
DEVICE_C = [
    ('replace', ['static NvnTexture *g_last_presented;\n'],
     'static NvnTexture *g_last_presented;\n'
     '// r28a (port/runtime-texfix): textures.c backend_texture_destroyed, under exec_lock - a finalized texture is never\n'
     '// re-presented (backend_represent), nor registered again through it\n'
     'void vk_present_texture_destroyed(NvnTexture *t) { if (g_last_presented == t) g_last_presented = NULL; }\n'),
    ('replace', [  # (PS5 work copies: with r17's observer flag; the PC tree: without)
        'void backend_represent(void) {\n'
        '    za_observer_representing = true;\n'
        '    if (g_last_presented) backend_present(g_last_presented);\n'
        '    else SDL_Delay(16);\n'
        '    za_observer_representing = false;\n'
        '}\n',
        'void backend_represent(void) {\n'
        '    if (g_last_presented) backend_present(g_last_presented);\n'
        '    else SDL_Delay(16);\n'
        '}\n'],
     None),  # (the replacement is chosen per alternative below)
    ('replace', ['void backend_present(NvnTexture *t) {\n'],
     'static void backend_present_locked(NvnTexture *t);\n'
     '// r28a (port/runtime-texfix): presenting runs under objects.c\'s exec_lock, as list execution and nvnTextureFinalize\n'
     '// do (it registers and reads textures, creates views and collects the deferred destructions a finalize on another\n'
     '// thread changes), and never takes a finalized texture\n'
     'void backend_present(NvnTexture *t) {\n'
     '    extern void za_nvn_exec_lock(void), za_nvn_exec_unlock(void);\n'
     '    za_nvn_exec_lock();\n'
     '    if (nvn_tex_live(t)) {\n'
     '        backend_present_locked(t);\n'
     '    } else {\n'
     '        za_texguard_hit(ZA_TG_PRESENT, t, t ? t->za_guard : 0, __builtin_return_address(0));\n'
     '        if (g_last_presented == t) g_last_presented = NULL;\n'
     '    }\n'
     '    za_nvn_exec_unlock();\n'
     '    za_texguard_frame(renderer_present_count());\n'
     '}\n'
     'static void backend_present_locked(NvnTexture *t) {\n'),
]
REPRESENT_NEW = [
    'void backend_represent(void) {\n'
    '    extern void za_nvn_exec_lock(void), za_nvn_exec_unlock(void);  // r28a: as backend_present (same lock, recursive)\n'
    '    za_observer_representing = true;\n'
    '    za_nvn_exec_lock();\n'
    '    NvnTexture *t = g_last_presented;  // (r28a: read under the lock a finalize clears it under)\n'
    '    if (t) backend_present(t);\n'
    '    za_nvn_exec_unlock();\n'
    '    if (!t) SDL_Delay(16);\n'
    '    za_observer_representing = false;\n'
    '}\n',
    'void backend_represent(void) {\n'
    '    extern void za_nvn_exec_lock(void), za_nvn_exec_unlock(void);  // r28a: as backend_present (same lock, recursive)\n'
    '    za_nvn_exec_lock();\n'
    '    NvnTexture *t = g_last_presented;  // (r28a: read under the lock a finalize clears it under)\n'
    '    if (t) backend_present(t);\n'
    '    za_nvn_exec_unlock();\n'
    '    if (!t) SDL_Delay(16);\n'
    '}\n',
]

EDITS = {
    'nvn/nvn.h': NVN_H,
    'nvn/objects.c': OBJECTS_C,
    'nvn/vulkan/textures.c': TEXTURES_C,
    'nvn/vulkan/exec.c': EXEC_C,
    'nvn/vulkan/device.c': DEVICE_C,
}


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def apply_edit(text, edit, rel, k):
    kind = edit[0]
    if kind == 'replace':
        _, olds, new = edit
        if new is None:  # backend_represent: one replacement per alternative
            news = REPRESENT_NEW
            if any(text.count(n) == 1 for n in news):
                return text, 'already'
            hits = [(o, n) for o, n in zip(olds, news) if text.count(o) == 1]
            assert len(hits) == 1, '%s edit %d: anchor alternatives found %d times' % (rel, k, len(hits))
            return text.replace(hits[0][0], hits[0][1]), 'edited'
        if text.count(new) == 1:
            return text, 'already'
        hits = [o for o in olds if text.count(o) == 1]
        counts = [text.count(o) for o in olds]
        assert len(hits) == 1, '%s edit %d: anchor counts %s (want exactly one alternative once): %r' % (
            rel, k, counts, olds[0][:90])
        return text.replace(hits[0], new), 'edited'
    if kind == 'block':
        _, (start, end), hashes, new = edit
        if text.count(new) == 1:
            return text, 'already'
        assert text.count(start) == 1, '%s edit %d: block start found %d times' % (rel, k, text.count(start))
        a = text.index(start)
        assert text.count(end, a) >= 1, '%s edit %d: block end missing' % (rel, k)
        b = text.index(end, a) + len(end)
        old = text[a:b]
        h = sha(old)
        if hashes:
            assert h in hashes, '%s edit %d: block differs from the reviewed one (sha256 %s)' % (rel, k, h)
        return text[:a] + new + text[b:], 'edited (block sha256 %s)' % h
    raise ValueError(kind)


# Reference trees (r28-play and the trees its objects came from, the runtime repository): read, never edited
REFERENCE_TREES = ('/ps5-za-native/r28-play-20261030/', '/ps5-za-native/perf-r26-20261029/',
                   '/ps5-za-native/r27b-play-20261029/', '/ps5-za-native/perf-r26p1-20261029/', '/pokeza-recomp-ps5/')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    root = Path(sys.argv[1]).resolve()
    check = '--check' in sys.argv[2:]
    assert (root / 'nvn/vulkan/textures.c').is_file(), '%s is not a runtime/ directory' % root
    posix = root.as_posix() + '/'
    if not check and any(r in posix for r in REFERENCE_TREES):
        sys.exit('refusing to edit a reference tree: %s (apply to a copy)' % root)
    out = {}
    for rel, edits in EDITS.items():
        path = root / rel
        text = path.read_text(encoding='utf-8').replace('\r\n', '\n')  # (a Windows checkout: matched as LF, written LF)
        notes = []
        for k, edit in enumerate(edits):
            text, note = apply_edit(text, edit, rel, k)
            notes.append(note)
        out[rel] = text
        print('%s: %s' % (rel, ', '.join(notes)))
    for rel, src in NEW_FILES.items():
        dst = root / rel
        state = 'same' if dst.is_file() and dst.read_bytes() == src.read_bytes() else ('differs' if dst.exists() else 'new')
        print('%s: %s' % (rel, state))
    if check:
        print('check only: nothing written')
        return
    for rel, text in out.items():
        path = root / rel
        if path.read_text(encoding='utf-8') != text:
            with path.open('w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    for rel, src in NEW_FILES.items():
        shutil.copyfile(src, root / rel)
    print('applied to %s' % root)


if __name__ == '__main__':
    main()
