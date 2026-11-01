/* ui-v2: canvas -> Vulkan image -> blended quad in the window image (ui_quad.h). Compiled with the runtime's include
 * path (runtime/, for nvn/vulkan/vk.h and what it includes) and the Mesa / VMA headers, as the runtime objects are. */
#include "ui_quad.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "nvn/vulkan/vk.h"

/* device.c: the window image's rendering is suspended around copies (exec.c's post passes do the same). */
extern void vk_frame_suspend(void);
extern void vk_frame_resume(void);
extern VkExtent2D vk_frame_extent(void);

struct UiQuadLayer {
    uint32_t w, h;
    VkImage image;
    VmaAllocation mem;
    VkImageView view;
    bool layout_done;
    struct {
        VkBuffer buf;
        VmaAllocation mem;
        void *map;
        uint64_t seq;
    } staging[2];
    int slot;
};

static VkDescriptorSetLayout g_set_layout;
static VkPipelineLayout g_layout;
static VkPipeline g_pipe_over, g_pipe_fade;
static VkFormat g_pipe_format;
static uint64_t g_uploads, g_draws;

static void ui_quad_log(const char *text) { fprintf(stderr, "%s", text); }

static VkPipeline make_pipeline(VkFormat fmt, bool fade) {
    if (!g_layout) {
        VkDescriptorSetLayoutBinding b = {0, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 1, VK_SHADER_STAGE_FRAGMENT_BIT, NULL};
        VkDescriptorSetLayoutCreateInfo li = {.sType = VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO, .bindingCount = 1, .pBindings = &b};
        VK_CHECK(vkCreateDescriptorSetLayout(g_vk.dev, &li, NULL, &g_set_layout));
        VkPushConstantRange r = {VK_SHADER_STAGE_VERTEX_BIT, 0, 32};
        VkPipelineLayoutCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO, .setLayoutCount = 1,
                                         .pSetLayouts = &g_set_layout, .pushConstantRangeCount = 1, .pPushConstantRanges = &r};
        VK_CHECK(vkCreatePipelineLayout(g_vk.dev, &ci, NULL, &g_layout));
    }
    VkPipelineShaderStageCreateInfo stages[2] = {
        {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_VERTEX_BIT,
         .module = vk_builtin_shader("present.vert"), .pName = "main"},
        {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO, .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
         .module = vk_builtin_shader("texcopy.frag"), .pName = "main"}};
    VkPipelineVertexInputStateCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    VkPipelineInputAssemblyStateCreateInfo ia = {.sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
                                                 .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST};
    VkPipelineViewportStateCreateInfo vs = {.sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO, .viewportCount = 1, .scissorCount = 1};
    VkPipelineRasterizationStateCreateInfo rs = {.sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
                                                 .polygonMode = VK_POLYGON_MODE_FILL, .lineWidth = 1};
    VkPipelineMultisampleStateCreateInfo ms = {.sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
                                               .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT};
    VkPipelineColorBlendAttachmentState cba = {.blendEnable = VK_TRUE, .colorWriteMask = 0xF};
    if (fade) {  /* out = k * src + (1 - k) * dst: a crossfade (the source is opaque) */
        cba.srcColorBlendFactor = VK_BLEND_FACTOR_CONSTANT_ALPHA;
        cba.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_ALPHA;
        cba.srcAlphaBlendFactor = VK_BLEND_FACTOR_CONSTANT_ALPHA;
        cba.dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_CONSTANT_ALPHA;
    } else {     /* premultiplied over: out = src + (1 - src.a) * dst */
        cba.srcColorBlendFactor = VK_BLEND_FACTOR_ONE;
        cba.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
        cba.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
        cba.dstAlphaBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    }
    cba.colorBlendOp = VK_BLEND_OP_ADD;
    cba.alphaBlendOp = VK_BLEND_OP_ADD;
    VkPipelineColorBlendStateCreateInfo cb = {.sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO, .attachmentCount = 1,
                                              .pAttachments = &cba};
    VkDynamicState dyn[] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR, VK_DYNAMIC_STATE_BLEND_CONSTANTS};
    VkPipelineDynamicStateCreateInfo dy = {.sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
                                           .dynamicStateCount = fade ? 3 : 2, .pDynamicStates = dyn};
    VkPipelineRenderingCreateInfo ri = {.sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO, .colorAttachmentCount = 1,
                                        .pColorAttachmentFormats = &fmt};
    VkPipelineDepthStencilStateCreateInfo ds = {.sType = VK_STRUCTURE_TYPE_PIPELINE_DEPTH_STENCIL_STATE_CREATE_INFO};
    VkGraphicsPipelineCreateInfo pi = {.sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO, .pNext = &ri, .stageCount = 2,
                                       .pStages = stages, .pVertexInputState = &vi, .pInputAssemblyState = &ia, .pViewportState = &vs,
                                       .pRasterizationState = &rs, .pMultisampleState = &ms, .pDepthStencilState = &ds,
                                       .pColorBlendState = &cb, .pDynamicState = &dy, .layout = g_layout};
    VkPipeline p;
    VK_CHECK(vkCreateGraphicsPipelines(g_vk.dev, g_vk.pcache, 1, &pi, NULL, &p));
    return p;
}

static VkPipeline pipeline(bool fade) {
    VkFormat fmt = g_vk.sc_format;
    if (g_pipe_format != fmt) {  /* (the swapchain format is fixed on the console; this covers a PC recreate) */
        g_pipe_over = g_pipe_fade = VK_NULL_HANDLE;
        g_pipe_format = fmt;
    }
    VkPipeline *slot = fade ? &g_pipe_fade : &g_pipe_over;
    if (!*slot) {
        *slot = make_pipeline(fmt, fade);
        char line[160];
        snprintf(line, sizeof line, "[ui-v2] quad pipeline (%s) created for swapchain format %d\n", fade ? "fade" : "over", (int)fmt);
        ui_quad_log(line);
    }
    return *slot;
}

UiQuadLayer *ui_quad_create(uint32_t w, uint32_t h) {
    if (!g_vk.dev || !g_vk.vma || !w || !h) return NULL;
    UiQuadLayer *L = calloc(1, sizeof *L);
    if (!L) return NULL;
    L->w = w;
    L->h = h;
    VkImageCreateInfo ci = {.sType = VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO, .imageType = VK_IMAGE_TYPE_2D,
                            .format = VK_FORMAT_R8G8B8A8_UNORM, .extent = {w, h, 1}, .mipLevels = 1, .arrayLayers = 1,
                            .samples = VK_SAMPLE_COUNT_1_BIT, .tiling = VK_IMAGE_TILING_OPTIMAL,
                            .usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT,
                            .initialLayout = VK_IMAGE_LAYOUT_UNDEFINED};
    VmaAllocationCreateInfo ai = {.usage = VMA_MEMORY_USAGE_AUTO_PREFER_DEVICE};
    if (vmaCreateImage(g_vk.vma, &ci, &ai, &L->image, &L->mem, NULL) != VK_SUCCESS) {
        ui_quad_log("[ui-v2] quad image allocation failed\n");
        free(L);
        return NULL;
    }
    VkImageViewCreateInfo vi = {.sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO, .image = L->image, .viewType = VK_IMAGE_VIEW_TYPE_2D,
                                .format = VK_FORMAT_R8G8B8A8_UNORM, .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1}};
    VK_CHECK(vkCreateImageView(g_vk.dev, &vi, NULL, &L->view));
    for (int i = 0; i < 2; i++) {
        VkBufferCreateInfo bi = {.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO, .size = (VkDeviceSize)w * h * 4,
                                 .usage = VK_BUFFER_USAGE_TRANSFER_SRC_BIT};
        VmaAllocationCreateInfo ba = {.usage = VMA_MEMORY_USAGE_AUTO,
                                      .flags = VMA_ALLOCATION_CREATE_HOST_ACCESS_SEQUENTIAL_WRITE_BIT | VMA_ALLOCATION_CREATE_MAPPED_BIT};
        VmaAllocationInfo info;
        VK_CHECK(vmaCreateBuffer(g_vk.vma, &bi, &ba, &L->staging[i].buf, &L->staging[i].mem, &info));
        L->staging[i].map = info.pMappedData;
    }
    char line[160];
    snprintf(line, sizeof line, "[ui-v2] quad layer %ux%u created (%.1f MB image, 2 x %.1f MB staging)\n", w, h,
             (double)w * h * 4 / 1048576.0, (double)w * h * 4 / 1048576.0);
    ui_quad_log(line);
    return L;
}

uint32_t ui_quad_width(const UiQuadLayer *layer) { return layer ? layer->w : 0; }
uint32_t ui_quad_height(const UiQuadLayer *layer) { return layer ? layer->h : 0; }

void ui_quad_upload(UiQuadLayer *L, void *cmd, const uint8_t *rgba, uint32_t stride, int x, int y, int w, int h, bool inside_rendering) {
    if (!L || !cmd || !rgba || w <= 0 || h <= 0) return;
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if ((uint32_t)x >= L->w || (uint32_t)y >= L->h) return;
    if ((uint32_t)(x + w) > L->w) w = (int)L->w - x;
    if ((uint32_t)(y + h) > L->h) h = (int)L->h - y;
    if (w <= 0 || h <= 0) return;
    VkCommandBuffer cb = (VkCommandBuffer)cmd;
    L->slot ^= 1;
    vk_wait_seq(L->staging[L->slot].seq);  /* the submission that last read this slot (usually long done) */
    uint8_t *dst = (uint8_t *)L->staging[L->slot].map;
    size_t row = (size_t)w * 4;
    for (int r = 0; r < h; r++) memcpy(dst + (size_t)r * row, rgba + (size_t)(y + r) * stride + (size_t)x * 4, row);
    if (inside_rendering) vk_frame_suspend();
    if (!L->layout_done) {
        vk_image_init_layout(cb, L->image, VK_IMAGE_ASPECT_COLOR_BIT);
        L->layout_done = true;
    }
    vk_full_barrier(cb);
    VkBufferImageCopy rg = {.bufferOffset = 0, .bufferRowLength = (uint32_t)w, .bufferImageHeight = (uint32_t)h,
                            .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
                            .imageOffset = {x, y, 0}, .imageExtent = {(uint32_t)w, (uint32_t)h, 1}};
    vkCmdCopyBufferToImage(cb, L->staging[L->slot].buf, L->image, VK_IMAGE_LAYOUT_GENERAL, 1, &rg);
    vk_full_barrier(cb);
    if (inside_rendering) vk_frame_resume();
    L->staging[L->slot].seq = vk_pending_seq();
    g_uploads++;
}

void ui_quad_draw(UiQuadLayer *L, void *cmd, const float dst[4], const float uv[4], float alpha) {
    if (!L || !cmd || !L->layout_done || dst[2] <= 0 || dst[3] <= 0) return;
    VkCommandBuffer cb = (VkCommandBuffer)cmd;
    bool fade = alpha < 1.0f;
    VkPipeline p = pipeline(fade);
    VkDescriptorSet set = vk_alloc_set(g_set_layout);
    VkDescriptorImageInfo ii = {vk_default_sampler(true), L->view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet wr = {.sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET, .dstSet = set, .dstBinding = 0, .descriptorCount = 1,
                               .descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, .pImageInfo = &ii};
    vkUpdateDescriptorSets(g_vk.dev, 1, &wr, 0, NULL);
    vkCmdBindPipeline(cb, VK_PIPELINE_BIND_POINT_GRAPHICS, p);
    vkCmdBindDescriptorSets(cb, VK_PIPELINE_BIND_POINT_GRAPHICS, g_layout, 0, 1, &set, 0, NULL);
    VkExtent2D ext = vk_frame_extent();
    VkViewport vp = {dst[0], dst[1], dst[2], dst[3], 0, 1};
    vkCmdSetViewport(cb, 0, 1, &vp);
    /* scissor: the destination clipped to the window */
    int32_t sx0 = dst[0] < 0 ? 0 : (int32_t)dst[0], sy0 = dst[1] < 0 ? 0 : (int32_t)dst[1];
    int32_t sx1 = (int32_t)(dst[0] + dst[2] + 0.5f), sy1 = (int32_t)(dst[1] + dst[3] + 0.5f);
    if (sx1 > (int32_t)ext.width) sx1 = (int32_t)ext.width;
    if (sy1 > (int32_t)ext.height) sy1 = (int32_t)ext.height;
    if (sx1 <= sx0 || sy1 <= sy0) return;
    VkRect2D sc = {{sx0, sy0}, {(uint32_t)(sx1 - sx0), (uint32_t)(sy1 - sy0)}};
    vkCmdSetScissor(cb, 0, 1, &sc);
    /* present.vert: a.x = flip (0: the canvas's top row is the top), crop = uv origin and size */
    float pv[8] = {0, 0, 0, 0, uv[0], uv[1], uv[2] - uv[0], uv[3] - uv[1]};
    vkCmdPushConstants(cb, g_layout, VK_SHADER_STAGE_VERTEX_BIT, 0, 32, pv);
    if (fade) {
        float k = alpha < 0 ? 0 : alpha;
        float consts[4] = {k, k, k, k};
        vkCmdSetBlendConstants(cb, consts);
    }
    vkCmdDraw(cb, 3, 1, 0, 0);
    VkViewport full = {0, 0, (float)ext.width, (float)ext.height, 0, 1};
    VkRect2D fullsc = {{0, 0}, ext};
    vkCmdSetViewport(cb, 0, 1, &full);
    vkCmdSetScissor(cb, 0, 1, &fullsc);
    g_draws++;
}

uint64_t ui_quad_upload_count(void) { return g_uploads; }
uint64_t ui_quad_draw_count(void) { return g_draws; }
