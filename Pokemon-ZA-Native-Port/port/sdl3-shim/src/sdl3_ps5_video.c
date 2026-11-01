/*
 * SDL3 shim for the PS5 port of Pokemon Legends Z-A Recomp: the window and the
 * Vulkan surface.
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * There is no window system: the one SDL_Window is the console's display, a
 * VK_KHR_display plane on VideoOut at the display's physical resolution, created
 * exactly as vk-probe/src/za_vk_probe.c create_surface() does (r3/r4 on 13.60:
 * "PS5 VideoOut", 3840x2160 physical, 3 modes, the first 3840x2160 at 59.940 Hz,
 * currentExtent 3840x2160, 2..5 images, usage 0x9f). Every Vulkan command comes
 * from RADV's ICD entry point, vk_icdGetInstanceProcAddr, as in the probe: the
 * title links the RADV archive and has no loader.
 */
#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include "sdl3_ps5_internal.h"

#include <SDL3/SDL_vulkan.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* RADV's ICD entry point, as a title that links the archive gets it (the probe declares it the same way). */
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance, const char *name);
int sceSystemServiceHideSplashScreen(void);

#define DEFAULT_WIDTH 3840
#define DEFAULT_HEIGHT 2160

struct SDL_Window {
    bool created;
    char title[64];
    int w, h;             /* logical size (the same as the pixel size: the display's) */
    int pixel_w, pixel_h; /* SDL_GetWindowSizeInPixels: must equal the swapchain's currentExtent */
    SDL_WindowFlags flags;
    bool size_from_display; /* false until SDL_Vulkan_CreateSurface read the display */
    char display_name[96];
    uint32_t refresh_mhz;
};

static struct SDL_Window the_window;
static PFN_vkGetInstanceProcAddr get_instance_proc_addr;
static const char *const instance_extensions[2] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_DISPLAY_EXTENSION_NAME};

static bool window_valid(const SDL_Window *window)
{
    return window == &the_window && the_window.created;
}

static void default_size(int *w, int *h)
{
    *w = DEFAULT_WIDTH;
    *h = DEFAULT_HEIGHT;
    const char *env = sdl3_ps5_env("SDL3_PS5_WINDOW");
    int ew = 0, eh = 0;
    if (env && sscanf(env, "%dx%d", &ew, &eh) == 2 && ew > 0 && eh > 0) {
        *w = ew;
        *h = eh;
    }
}

SDL_Window *SDL_CreateWindow(const char *title, int w, int h, SDL_WindowFlags flags)
{
    if (the_window.created) {
        SDL_SetError("SDL_CreateWindow: the PS5 shim has one window, and it exists");
        return NULL;
    }
    memset(&the_window, 0, sizeof(the_window));
    snprintf(the_window.title, sizeof(the_window.title), "%s", title ? title : "");
    /* The requested size is the PC default (1280x720); the window here is the display. Until the surface
     * exists its size is the console's known mode (overridable with SDL3_PS5_WINDOW=WxH). */
    default_size(&the_window.w, &the_window.h);
    the_window.pixel_w = the_window.w;
    the_window.pixel_h = the_window.h;
    the_window.flags = (flags & ~SDL_WINDOW_HIDDEN) | SDL_WINDOW_FULLSCREEN | SDL_WINDOW_INPUT_FOCUS | SDL_WINDOW_MOUSE_FOCUS;
    if (flags & SDL_WINDOW_VULKAN)
        SDL_Vulkan_LoadLibrary(NULL);
    the_window.created = true;
    /* VK_KHR_display alone leaves the shell artwork on top. Confirmed by the
     * r6 visual probe: hiding it reveals frames and delivers controller input. */
    const int splash_rc = sceSystemServiceHideSplashScreen();
    sdl3_ps5_log("sceSystemServiceHideSplashScreen rc=0x%08x", (unsigned)splash_rc);
    sdl3_ps5_log("window \"%s\": requested %dx%d, reporting %dx%d until the display surface exists (flags 0x%llx)",
                 the_window.title, w, h, the_window.pixel_w, the_window.pixel_h, (unsigned long long)the_window.flags);
    return &the_window;
}

void SDL_DestroyWindow(SDL_Window *window)
{
    if (window_valid(window))
        the_window.created = false;
}

void sdl3_ps5_video_quit(void)
{
    the_window.created = false;
}

SDL_WindowFlags SDL_GetWindowFlags(SDL_Window *window)
{
    return window_valid(window) ? the_window.flags : 0;
}

bool SDL_GetWindowSize(SDL_Window *window, int *w, int *h)
{
    if (!window_valid(window))
        return SDL_SetError("SDL_GetWindowSize: invalid window");
    if (w)
        *w = the_window.w;
    if (h)
        *h = the_window.h;
    return true;
}

bool SDL_GetWindowSizeInPixels(SDL_Window *window, int *w, int *h)
{
    if (!window_valid(window))
        return SDL_SetError("SDL_GetWindowSizeInPixels: invalid window");
    if (w)
        *w = the_window.pixel_w;
    if (h)
        *h = the_window.pixel_h;
    return true;
}

bool SDL_SetWindowFullscreen(SDL_Window *window, bool fullscreen)
{
    (void)fullscreen; /* the display is always the whole screen */
    if (!window_valid(window))
        return SDL_SetError("SDL_SetWindowFullscreen: invalid window");
    return true;
}

bool SDL_SetWindowIcon(SDL_Window *window, SDL_Surface *icon)
{
    (void)icon; /* nowhere to show it */
    if (!window_valid(window))
        return SDL_SetError("SDL_SetWindowIcon: invalid window");
    return true;
}

bool SDL_ShowWindow(SDL_Window *window)
{
    if (!window_valid(window))
        return SDL_SetError("SDL_ShowWindow: invalid window");
    the_window.flags &= ~SDL_WINDOW_HIDDEN;
    return true;
}

/* ------------------------------------------------------------------ Vulkan */

bool SDL_Vulkan_LoadLibrary(const char *path)
{
    if (path && *path)
        sdl3_ps5_log("SDL_Vulkan_LoadLibrary(%s): no loader on the console; the linked RADV ICD is used", path);
    get_instance_proc_addr = (PFN_vkGetInstanceProcAddr)vk_icdGetInstanceProcAddr;
    return true;
}

SDL_FunctionPointer SDL_Vulkan_GetVkGetInstanceProcAddr(void)
{
    if (!get_instance_proc_addr)
        SDL_Vulkan_LoadLibrary(NULL);
    return (SDL_FunctionPointer)(uintptr_t)get_instance_proc_addr;
}

void SDL_Vulkan_UnloadLibrary(void)
{
    /* The ICD is part of the title: nothing to unload. */
}

char const *const *SDL_Vulkan_GetInstanceExtensions(Uint32 *count)
{
    if (count)
        *count = 2;
    return instance_extensions;
}

bool SDL_Vulkan_CreateSurface(SDL_Window *window, VkInstance instance, const struct VkAllocationCallbacks *allocator,
                              VkSurfaceKHR *surface)
{
    if (surface)
        *surface = VK_NULL_HANDLE;
    if (!window_valid(window))
        return SDL_SetError("SDL_Vulkan_CreateSurface: invalid window");
    if (!instance || !surface)
        return SDL_SetError("SDL_Vulkan_CreateSurface: NULL instance or surface");
    if (!get_instance_proc_addr)
        SDL_Vulkan_LoadLibrary(NULL);

#define LOAD(name)                                                                              \
    PFN_vk##name p##name = (PFN_vk##name)get_instance_proc_addr(instance, "vk" #name);           \
    if (!p##name)                                                                               \
        return SDL_SetError("SDL_Vulkan_CreateSurface: vk" #name " is missing from the ICD (is VK_KHR_display enabled?)");
    LOAD(EnumeratePhysicalDevices)
    LOAD(GetPhysicalDeviceDisplayPropertiesKHR)
    LOAD(GetDisplayModePropertiesKHR)
    LOAD(CreateDisplayPlaneSurfaceKHR)
#undef LOAD

    /* The probe's create_surface, step for step: one physical device, its one display, the first mode. */
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    uint32_t count = 1;
    VkResult result = pEnumeratePhysicalDevices(instance, &count, &physical);
    if ((result != VK_SUCCESS && result != VK_INCOMPLETE) || count < 1 || physical == VK_NULL_HANDLE)
        return SDL_SetError("SDL_Vulkan_CreateSurface: vkEnumeratePhysicalDevices rc=%d count=%u", (int)result, count);

    VkDisplayPropertiesKHR display;
    memset(&display, 0, sizeof(display));
    count = 1;
    result = pGetPhysicalDeviceDisplayPropertiesKHR(physical, &count, &display);
    if ((result != VK_SUCCESS && result != VK_INCOMPLETE) || count < 1)
        return SDL_SetError("SDL_Vulkan_CreateSurface: vkGetPhysicalDeviceDisplayPropertiesKHR rc=%d count=%u", (int)result,
                            count);

    VkDisplayModePropertiesKHR modes[4];
    memset(modes, 0, sizeof(modes));
    count = 4;
    result = pGetDisplayModePropertiesKHR(physical, display.display, &count, modes);
    if ((result != VK_SUCCESS && result != VK_INCOMPLETE) || count < 1)
        return SDL_SetError("SDL_Vulkan_CreateSurface: vkGetDisplayModePropertiesKHR rc=%d count=%u", (int)result, count);

    /* The first mode is what the surface takes; the swapchain is made at the display's physical resolution. */
    const VkExtent2D extent = display.physicalResolution;
    const VkDisplaySurfaceCreateInfoKHR info = {
        .sType = VK_STRUCTURE_TYPE_DISPLAY_SURFACE_CREATE_INFO_KHR,
        .displayMode = modes[0].displayMode,
        .transform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR,
        .alphaMode = VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR,
        .imageExtent = extent,
    };
    result = pCreateDisplayPlaneSurfaceKHR(instance, &info, allocator, surface);
    if (result != VK_SUCCESS) {
        *surface = VK_NULL_HANDLE;
        return SDL_SetError("SDL_Vulkan_CreateSurface: vkCreateDisplayPlaneSurfaceKHR rc=%d", (int)result);
    }

    the_window.pixel_w = the_window.w = (int)extent.width;
    the_window.pixel_h = the_window.h = (int)extent.height;
    the_window.size_from_display = true;
    the_window.refresh_mhz = modes[0].parameters.refreshRate;
    snprintf(the_window.display_name, sizeof(the_window.display_name), "%s", display.displayName ? display.displayName : "");
    sdl3_ps5_log("surface: %s, %ux%u physical, %u mode(s), the first %ux%u at %.3f Hz; the window is %dx%d",
                 the_window.display_name, extent.width, extent.height, count, modes[0].parameters.visibleRegion.width,
                 modes[0].parameters.visibleRegion.height, modes[0].parameters.refreshRate / 1000.0, the_window.pixel_w,
                 the_window.pixel_h);
    return true;
}

void SDL_Vulkan_DestroySurface(VkInstance instance, VkSurfaceKHR surface, const struct VkAllocationCallbacks *allocator)
{
    if (!instance || surface == VK_NULL_HANDLE)
        return;
    if (!get_instance_proc_addr)
        SDL_Vulkan_LoadLibrary(NULL);
    PFN_vkDestroySurfaceKHR destroy = (PFN_vkDestroySurfaceKHR)get_instance_proc_addr(instance, "vkDestroySurfaceKHR");
    if (destroy)
        destroy(instance, surface, allocator);
}

bool SDL_Vulkan_GetPresentationSupport(VkInstance instance, VkPhysicalDevice physicalDevice, Uint32 queueFamilyIndex)
{
    (void)instance;
    (void)physicalDevice;
    (void)queueFamilyIndex;
    return true; /* the probe: vkGetPhysicalDeviceSurfaceSupportKHR answered 1 for the graphics+compute family */
}
