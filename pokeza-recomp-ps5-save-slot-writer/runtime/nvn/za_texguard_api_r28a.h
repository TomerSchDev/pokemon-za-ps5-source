// r28a texfix (port/runtime-texfix): an NvnTexture's lifetime guard - the values, the check, the [za-texguard] sites.
// Included by nvn.h right after NvnTexture (whose za_guard field it reads); host tests include it after a mirror of it.
// za_guard is NVN_TEX_LIVE from nvnTextureInitialize to nvnTextureFinalize, then NVN_TEX_DEAD while objects.c keeps the
// finalized object in quarantine (za_texquarantine_r28a.h). Anything else - memory freed and reused, a pointer that was
// never a texture - is not live either. Checked where a texture pointer the runtime did not just look up arrives: the
// registration of a backend (textures.c), recorded command lists (exec.c), the present (device.c), the video thread's
// upload, texture pool registration and a second finalize (objects.c). Never per draw.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define NVN_TEX_LIVE 0x5A54584Cu  // 'ZTXL'
#define NVN_TEX_DEAD 0xDEAD7E57u

static inline bool nvn_tex_live(const NvnTexture *t) { return t && t->za_guard == NVN_TEX_LIVE; }

// [za-texguard] sites (za_texguard_r28a.h names them)
enum { ZA_TG_REGISTER, ZA_TG_SET_RT, ZA_TG_PASS, ZA_TG_CLEAR_TEXTURE, ZA_TG_COPY_TO_TEX, ZA_TG_COPY_FROM_TEX,
       ZA_TG_COPY_TEX, ZA_TG_PRESENT, ZA_TG_UPLOAD_RGBA, ZA_TG_POOL_REGISTER, ZA_TG_FINALIZE_AGAIN, ZA_TG_LIVE_LIST,
       ZA_TG_SITES };
// The operation was refused; reported once per (site, caller), counted always. detail: the guard word (live-list:
// the backend's reg); caller: a return address, or NULL where the site alone says where.
void za_texguard_hit(int site, const void *tex, uint32_t detail, const void *caller);
void za_texguard_frame(uint64_t frame);  // (device.c, once per presented frame: the counts now and then)
