/* ui-v2: an RGBA8 (premultiplied) canvas as a Vulkan image, composited into the window image.
 *
 * One blend pipeline on the runtime's own built-in shaders (present.vert + texcopy.frag, runtime/nvn/vulkan/shaders.c)
 * and its exported helpers (vk.h: vk_cmd, vk_alloc_set, vk_default_sampler, vk_builtin_shader, vk_image_init_layout,
 * vk_full_barrier, vk_pending_seq / vk_wait_seq, g_vk) - nothing in the runtime changes for this. Two blend variants:
 *   "over":  premultiplied source over the destination (the overlay panel, toasts, the FPS readout);
 *   "fade":  crossfade by a constant k between the destination and an OPAQUE source (the launcher's last frame fading
 *            into the game's first frames; blend constants, so no shader of its own).
 * Uploads copy only the dirty rectangle from a mapped staging ring (two slots, reused once the submission that read
 * them completed). A layer is created once and lives for the process (also across an in-place reboot).
 * Called on whichever thread owns the command buffer: the launcher's loop (main thread, before the game) or the render
 * thread inside menu_render; the caller passes the command buffer.
 */
#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct UiQuadLayer UiQuadLayer;

/* A layer of w x h pixels. NULL when Vulkan is not up (the host tests stub this module). */
UiQuadLayer *ui_quad_create(uint32_t w, uint32_t h);
uint32_t ui_quad_width(const UiQuadLayer *layer);
uint32_t ui_quad_height(const UiQuadLayer *layer);

/* Copies rows [y, y+h) x [x, x+w) of `rgba` (premultiplied RGBA8, `stride` bytes per row, the canvas's own layout:
 * the pointer is the canvas origin) into the image. `inside_rendering`: the command buffer is inside the window
 * image's rendering (menu_render), so it is suspended around the copy (device.c vk_frame_suspend / vk_frame_resume);
 * false in the launcher loop, where the upload is recorded before vk_frame_begin. */
void ui_quad_upload(UiQuadLayer *layer, void *cmd, const uint8_t *rgba, uint32_t stride, int x, int y, int w, int h,
                    bool inside_rendering);

/* Draws the layer's region uv (u0, v0, u1, v1 in 0..1) into dst (x, y, w, h in window pixels), inside the window
 * image's rendering. alpha < 1: the "fade" variant (crossfade by alpha; the source must be opaque); alpha >= 1: "over".
 * Restores the full-window viewport and scissor afterwards. */
void ui_quad_draw(UiQuadLayer *layer, void *cmd, const float dst[4], const float uv[4], float alpha);

/* How many uploads and draws happened (for the tests and the klog line). */
uint64_t ui_quad_upload_count(void);
uint64_t ui_quad_draw_count(void);

#ifdef __cplusplus
}
#endif
