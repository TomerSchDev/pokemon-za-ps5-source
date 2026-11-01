/*
 * ZA Native Probe - Vulkan, controller and audio feasibility test for the PS5
 * (milestone A: step 11b, then the pad and audio items).
 * SPDX-License-Identifier: GPL-3.0-or-later
 *
 * Modeled on PS5_Vulkan's radv/radv_smoke.c (Mihawk-99, GPL-3.0-or-later):
 * the title links the RADV archive, takes every command from
 * vk_icdGetInstanceProcAddr / vkGetDeviceProcAddr, and proves one capability
 * at a time: instance, device, VK_KHR_display on VideoOut, a swapchain, a
 * graphics pipeline with dynamic rendering, presented frames, a pixel readback,
 * and a clean shutdown. r4 adds the DualSense through libScePad (presses
 * counted, any held button draws the triangle white, OPTIONS ends the run),
 * a 440 Hz tone and a beep per press through libSceAudioOut on a thread, and
 * RADV's shader cache under /download0 (/app0 is read-only to the title).
 * Every result goes to klog, a text log and a one-line JSON status file, each
 * written to /download0 twice: the live file and a keep copy named after the run.
 *
 * It also records which Vulkan extensions and features the Pokemon Legends Z-A
 * recomp runtime asks for (runtime/nvn/vulkan/device.c) are reported here.
 * Nothing in this file is game content, and no Wine is involved.
 */

#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>

#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <math.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#include "za_vk_shaders.h"

#ifndef ZA_BUILD_ID
#define ZA_BUILD_ID "za-vk-probe-a0-20261027-r4"
#endif

/* RADV's ICD entry point, as a title that links the archive gets it. */
VKAPI_ATTR PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance, const char *name);
/* libkernel's klog writer, and ps5platform/klog.h: stderr lines into klog. */
int sceKernelDebugOutText(int channel, const char *text);
int ps5_klog_capture_stderr(const char *prefix);

/* libSceUserService, libScePad and libSceAudioOut: the payload SDK ships their
 * stub libraries (target/lib) but no headers. These declarations follow the
 * interoperability headers ProsperoEden runs on this console
 * (third_party/ps5_pad.hpp and native_audio.hpp): the pad record is 120 bytes
 * with the buttons first and the connected flag at 0x4c; only those two fields
 * are read here, into a buffer twice the record's size. */
int sceUserServiceInitialize(const void *params);
int sceUserServiceGetForegroundUser(int *user_id);
int sceUserServiceGetInitialUser(int *user_id);
int sceUserServiceTerminate(void);
int scePadInit(void);
int scePadOpen(int user_id, int port_type, int index, const void *params);
int scePadGetHandle(int user_id, int port_type, int index);
int scePadClose(int handle);
int scePadReadState(int handle, void *record);
int scePadSetLightBar(int handle, const void *colour);
int scePadResetLightBar(int handle);
int sceAudioOutInit(void);
int sceAudioOutOpen(int user_id, int port_type, int index, uint32_t grain, uint32_t frequency, uint32_t format);
int sceAudioOutClose(int handle);
int sceAudioOutOutput(int handle, const void *samples);
int sceAudioOutSetVolume(int handle, int flags, const int *volumes);

struct pad_record {
   uint32_t buttons;
   uint8_t left_x, left_y, right_x, right_y;
   uint8_t l2, r2, analog_reserved[2];
   float orientation[4];
   float acceleration[3];
   float angular_velocity[3];
   uint8_t touch[24];
   int32_t connected;
   uint64_t timestamp_us;
   uint8_t extension[16];
   uint8_t connected_count;
   uint8_t reserved[2];
   uint8_t device_unique_data_length;
   uint8_t device_unique_data[12];
};
_Static_assert(sizeof(struct pad_record) == 120, "the pad record is 120 bytes");
_Static_assert(offsetof(struct pad_record, connected) == 0x4c, "connected is at 0x4c");
_Static_assert(offsetof(struct pad_record, timestamp_us) == 0x50, "the timestamp is at 0x50");

#define PAD_PORT_TYPE_STANDARD 0
#define PAD_BUTTON_OPTIONS 0x00000008u
#define PAD_BUTTON_INTERCEPTED 0x80000000u /* the system took the input (the PS button's menu) */
#define USER_ID_SYSTEM 0xff
#define AUDIO_PORT_MAIN 0
#define AUDIO_FORMAT_S16_STEREO 1
#define AUDIO_VOLUME_BOTH 3 /* the left and right channel flags */
#define AUDIO_VOLUME_0DB 0x8000

/* The title converter needs .data.rel.ro to begin its RELRO segment; keep a
 * relocatable read-only manifest so the section exists (native-probe/probe.cpp). */
static const char build_id[] = ZA_BUILD_ID;
__attribute__((used, section(".data.rel.ro")))
const char *const za_build_manifest[] = {build_id, "PS5 native Vulkan probe; no game content"};

#define LIVE_LOG "/download0/za-vk-probe.log"
#define LIVE_JSON "/download0/za-vk-probe.json"
#define KEEP_LOG "/download0/za-vk-probe-r4.log"
#define KEEP_JSON "/download0/za-vk-probe-r4.json"
#define STOP_FILE "/download0/za-vk-probe.stop"
#define SHADER_CACHE_DIR "/download0/radv-shader-cache"
#define RUN_SECONDS 180.0
#define READBACK_FRAME 90
#define WINDOW 60
#define AUDIO_RATE 48000
#define AUDIO_GRAIN 256      /* samples per sceAudioOutOutput: 5.3 ms, the pacing unit */
#define TONE_GRAINS 188u     /* 1.0 s of 440 Hz when the frames start */
#define BEEP_GRAINS 19u      /* 0.1 s of 880 Hz per button press */
#define PRESS_REPORTS 12u    /* presses reported one by one; every tenth after that */

/* ------------------------------------------------------------------ status */

static FILE *logs[2];
static unsigned passed, failed;
static char failures[1024];
static const char *stage = "start";
static const char *exit_reason = "running";
static uint64_t boot_ns, heartbeat;
static bool asset_ok;

static struct {
   double instance, device, surface, swapchain, pipeline, first_present;
} stage_ms;

static struct {
   int instance_rc, swapchain_rc, pipeline_rc, last_present_rc;
   char api_version[32], device_name[VK_MAX_PHYSICAL_DEVICE_NAME_SIZE], driver_name[VK_MAX_DRIVER_NAME_SIZE],
      driver_info[VK_MAX_DRIVER_INFO_SIZE], display_name[96];
   uint32_t queue_family, instance_extension_count, device_extension_count, display_w, display_h, refresh_mhz,
      swapchain_images, frames_presented;
   uint64_t device_local_bytes, host_visible_bytes;
   bool surface_supported, readback_ok;
   double frame_min, frame_avg, frame_max;
   uint32_t readback_center, readback_corner;
} vk;

static struct {
   int mkdir_rc, mkdir_errno, setenv_rc;
   bool exists_after_enumerate, exists_at_end;
   uint32_t entries_after_enumerate, entries_at_end;
   char entries[160];
} cache;

static struct {
   int user_service_rc, foreground_rc, initial_rc, user_id, init_rc, open_rc, handle, read_rc, lightbar_rc, close_rc;
   int32_t connected;
   uint32_t reads, read_failures, held, press_count, buttons_seen, first_press_frame, first_press_buttons;
   double first_press_ms;
   bool options_stop;
} pad = {.user_id = -1, .handle = -1};

/* The counters the submission thread writes are atomic; the main thread reads
 * them for the status file and the beep requests go the other way. */
static struct {
   int init_rc, open_rc, handle, user_id_used, volume_rc, thread_rc, drain_rc, close_rc;
   const char *mode;
   bool thread_started;
   pthread_t thread;
   _Atomic bool running, tone_complete;
   _Atomic int last_output_rc;
   _Atomic uint32_t beeps_pending, grains_written, tone_grains, tone_failures, beeps_played, beep_grains,
      output_failures;
} audio = {.handle = -1, .mode = "none"};

/* What runtime/nvn/vulkan/device.c of the recomp asks the driver for. */
static const char *const game_extensions[] = {
   VK_KHR_SWAPCHAIN_EXTENSION_NAME,          VK_KHR_DYNAMIC_RENDERING_EXTENSION_NAME,
   VK_KHR_SYNCHRONIZATION_2_EXTENSION_NAME,  VK_EXT_EXTENDED_DYNAMIC_STATE_EXTENSION_NAME,
   VK_EXT_EXTENDED_DYNAMIC_STATE_2_EXTENSION_NAME, VK_EXT_CUSTOM_BORDER_COLOR_EXTENSION_NAME,
   VK_EXT_VERTEX_ATTRIBUTE_DIVISOR_EXTENSION_NAME, VK_EXT_EXTERNAL_MEMORY_HOST_EXTENSION_NAME,
   VK_EXT_DEVICE_FAULT_EXTENSION_NAME,
};
#define GAME_EXTENSIONS (sizeof(game_extensions) / sizeof(game_extensions[0]))
static bool game_extension_present[GAME_EXTENSIONS];

struct game_feature {
   const char *name;
   bool present;
};
static struct game_feature game_features[] = {
   {"storageBuffer16BitAccess", false},
   {"timelineSemaphore", false},
   {"shaderInt8", false},
   {"samplerMirrorClampToEdge", false},
   {"uniformAndStorageBuffer8BitAccess", false},
   {"storageBuffer8BitAccess", false},
   {"scalarBlockLayout", false},
   {"shaderOutputLayer", false},
   {"samplerFilterMinmax", false},
   {"shaderOutputViewportIndex", false},
   {"dynamicRendering", false},
   {"synchronization2", false},
   {"subgroupSizeControl", false},
   {"shaderDemoteToHelperInvocation", false},
   {"shaderTerminateInvocation", false},
   {"maintenance4", false},
   {"independentBlend", false},
   {"dualSrcBlend", false},
   {"fillModeNonSolid", false},
   {"samplerAnisotropy", false},
   {"textureCompressionBC", false},
   {"shaderInt64", false},
   {"depthBiasClamp", false},
   {"depthClamp", false},
   {"largePoints", false},
   {"wideLines", false},
   {"imageCubeArray", false},
   {"sampleRateShading", false},
   {"fragmentStoresAndAtomics", false},
   {"vertexPipelineStoresAndAtomics", false},
   {"robustBufferAccess", false},
   {"shaderClipDistance", false},
   {"geometryShader", false},
};
#define GAME_FEATURES (sizeof(game_features) / sizeof(game_features[0]))

static uint64_t
now_ns(void)
{
   struct timespec t;
   clock_gettime(CLOCK_MONOTONIC, &t);
   return (uint64_t)t.tv_sec * 1000000000ull + (uint64_t)t.tv_nsec;
}

static double
since_ms(uint64_t start)
{
   return (double)(now_ns() - start) / 1e6;
}

static void
report(const char *format, ...)
{
   char line[512];
   va_list args;
   va_start(args, format);
   vsnprintf(line, sizeof(line), format, args);
   va_end(args);
   fprintf(stderr, "[za-vk] %s\n", line);
   fflush(stderr);
   char klog_line[600];
   snprintf(klog_line, sizeof(klog_line), "[za-vk] %s\n", line);
   sceKernelDebugOutText(0, klog_line);
   for (int i = 0; i < 2; i++) {
      if (logs[i]) {
         fprintf(logs[i], "%8.1f %s\n", since_ms(boot_ns), line);
         fflush(logs[i]);
      }
   }
}

static bool
check(bool ok, const char *what)
{
   report("%s %s", ok ? "PASS" : "FAIL", what);
   if (ok) {
      passed++;
   } else {
      failed++;
      size_t used = strlen(failures);
      snprintf(failures + used, sizeof(failures) - used, "%s%s", used ? ";" : "", what);
   }
   return ok;
}

static void
set_stage(const char *name)
{
   stage = name;
   report("stage %s", name);
}

/* JSON text for a string: quotes and backslashes escaped, control bytes dropped. */
static const char *
json_string(const char *value, char *out, size_t size)
{
   size_t n = 0;
   for (const unsigned char *p = (const unsigned char *)value; *p && n + 3 < size; p++) {
      if (*p == '"' || *p == '\\') {
         out[n++] = '\\';
         out[n++] = (char)*p;
      } else if (*p >= 0x20) {
         out[n++] = (char)*p;
      }
   }
   out[n] = '\0';
   return out;
}

static size_t
format_status(char *out, size_t size)
{
   char esc[4][256];
   size_t n = 0;
#define PUT(...)                                                                                   \
   do {                                                                                            \
      int w = snprintf(out + n, n < size ? size - n : 0, __VA_ARGS__);                             \
      if (w > 0)                                                                                   \
         n += (size_t)w;                                                                           \
   } while (0)
   PUT("{\"build\":\"%s\",\"pid\":%d,\"boot_monotonic_ns\":%llu,\"uptime_ms\":%llu,\"heartbeat\":%llu,"
       "\"stage\":\"%s\",\"asset_read_ok\":%s,",
       build_id, (int)getpid(), (unsigned long long)boot_ns, (unsigned long long)((now_ns() - boot_ns) / 1000000ull),
       (unsigned long long)heartbeat, stage, asset_ok ? "true" : "false");
   PUT("\"stage_ms\":{\"instance\":%.1f,\"device\":%.1f,\"surface\":%.1f,\"swapchain\":%.1f,\"pipeline\":%.1f,"
       "\"first_present\":%.1f},",
       stage_ms.instance, stage_ms.device, stage_ms.surface, stage_ms.swapchain, stage_ms.pipeline,
       stage_ms.first_present);
   PUT("\"vulkan\":{\"instance_rc\":%d,\"api_version\":\"%s\",\"device_name\":\"%s\",\"driver_name\":\"%s\","
       "\"driver_info\":\"%s\",\"queue_family\":%u,\"device_local_bytes\":%llu,\"host_visible_bytes\":%llu,"
       "\"instance_extension_count\":%u,\"device_extension_count\":%u,\"display_name\":\"%s\",\"display_w\":%u,"
       "\"display_h\":%u,\"refresh_mhz\":%u,\"surface_supported\":%s,\"swapchain_rc\":%d,\"swapchain_images\":%u,"
       "\"pipeline_rc\":%d,\"frames_presented\":%u,\"last_present_rc\":%d,\"frame_ms_min\":%.3f,"
       "\"frame_ms_avg\":%.3f,\"frame_ms_max\":%.3f,\"readback_ok\":%s,\"readback_center\":\"0x%08x\","
       "\"readback_corner\":\"0x%08x\"},",
       vk.instance_rc, vk.api_version, json_string(vk.device_name, esc[0], sizeof(esc[0])),
       json_string(vk.driver_name, esc[1], sizeof(esc[1])), json_string(vk.driver_info, esc[2], sizeof(esc[2])),
       vk.queue_family, (unsigned long long)vk.device_local_bytes, (unsigned long long)vk.host_visible_bytes,
       vk.instance_extension_count, vk.device_extension_count, json_string(vk.display_name, esc[3], sizeof(esc[3])),
       vk.display_w, vk.display_h, vk.refresh_mhz, vk.surface_supported ? "true" : "false", vk.swapchain_rc,
       vk.swapchain_images, vk.pipeline_rc, vk.frames_presented, vk.last_present_rc, vk.frame_min, vk.frame_avg,
       vk.frame_max, vk.readback_ok ? "true" : "false", vk.readback_center, vk.readback_corner);
   PUT("\"shader_cache\":{\"dir\":\"%s\",\"mkdir_rc\":%d,\"mkdir_errno\":%d,\"setenv_rc\":%d,"
       "\"exists_after_enumerate\":%s,\"entries_after_enumerate\":%u,\"exists_at_end\":%s,\"entries_at_end\":%u,"
       "\"entries\":\"%s\"},",
       SHADER_CACHE_DIR, cache.mkdir_rc, cache.mkdir_errno, cache.setenv_rc,
       cache.exists_after_enumerate ? "true" : "false", cache.entries_after_enumerate,
       cache.exists_at_end ? "true" : "false", cache.entries_at_end, json_string(cache.entries, esc[0], sizeof(esc[0])));
   PUT("\"pad\":{\"user_service_rc\":\"0x%08x\",\"foreground_rc\":\"0x%08x\",\"initial_rc\":\"0x%08x\",\"user_id\":%d,"
       "\"init_rc\":\"0x%08x\",\"open_rc\":\"0x%08x\",\"handle\":%d,\"reads\":%u,\"read_failures\":%u,"
       "\"read_rc\":\"0x%08x\",\"connected\":%d,\"press_count\":%u,\"buttons_seen\":\"0x%08x\","
       "\"first_press_frame\":%u,\"first_press_buttons\":\"0x%08x\",\"first_press_ms\":%.0f,\"options_stop\":%s,"
       "\"lightbar_rc\":\"0x%08x\",\"close_rc\":\"0x%08x\"},",
       (unsigned)pad.user_service_rc, (unsigned)pad.foreground_rc, (unsigned)pad.initial_rc, pad.user_id,
       (unsigned)pad.init_rc, (unsigned)pad.open_rc, pad.handle, pad.reads, pad.read_failures, (unsigned)pad.read_rc,
       (int)pad.connected, pad.press_count, pad.buttons_seen, pad.first_press_frame, pad.first_press_buttons,
       pad.first_press_ms, pad.options_stop ? "true" : "false", (unsigned)pad.lightbar_rc, (unsigned)pad.close_rc);
   PUT("\"audio\":{\"init_rc\":\"0x%08x\",\"open_rc\":\"0x%08x\",\"handle\":%d,\"user_id_used\":%d,"
       "\"volume_rc\":\"0x%08x\",\"mode\":\"%s\",\"thread_rc\":%d,\"grains_written\":%u,\"tone_grains\":%u,"
       "\"tone_failures\":%u,\"tone_complete\":%s,\"beeps_played\":%u,\"beep_grains\":%u,\"output_failures\":%u,"
       "\"last_output_rc\":\"0x%08x\",\"drain_rc\":\"0x%08x\",\"close_rc\":\"0x%08x\"},",
       (unsigned)audio.init_rc, (unsigned)audio.open_rc, audio.handle, audio.user_id_used, (unsigned)audio.volume_rc,
       audio.mode, audio.thread_rc, atomic_load(&audio.grains_written), atomic_load(&audio.tone_grains),
       atomic_load(&audio.tone_failures), atomic_load(&audio.tone_complete) ? "true" : "false",
       atomic_load(&audio.beeps_played), atomic_load(&audio.beep_grains), atomic_load(&audio.output_failures),
       (unsigned)atomic_load(&audio.last_output_rc), (unsigned)audio.drain_rc, (unsigned)audio.close_rc);
   PUT("\"game_requirements\":{\"extensions\":{");
   for (size_t i = 0; i < GAME_EXTENSIONS; i++)
      PUT("%s\"%s\":%s", i ? "," : "", game_extensions[i], game_extension_present[i] ? "true" : "false");
   PUT("},\"features\":{");
   for (size_t i = 0; i < GAME_FEATURES; i++)
      PUT("%s\"%s\":%s", i ? "," : "", game_features[i].name, game_features[i].present ? "true" : "false");
   PUT("}},\"passed\":%u,\"failed\":%u,\"failures\":\"%s\",\"exit_reason\":\"%s\",\"visual_verified\":false,"
       "\"controller_tested\":%s,\"audio_tested\":%s,\"game_code_executed\":false,\"wine_used\":false}\n",
       passed, failed, failures, exit_reason, pad.press_count > 0 ? "true" : "false",
       atomic_load(&audio.tone_complete) ? "true" : "false");
#undef PUT
   return n < size ? n : 0;
}

/* The status file is written whole under a temporary name and renamed over
 * the old one, so a reader never sees a partial line. */
static void
persist_one(const char *path, const char *text, size_t count)
{
   char temp[128];
   snprintf(temp, sizeof(temp), "%s.tmp", path);
   int fd = open(temp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
   if (fd < 0)
      return;
   fchmod(fd, 0644);
   size_t done = 0;
   while (done < count) {
      ssize_t w = write(fd, text + done, count - done);
      if (w < 0 && errno == EINTR)
         continue;
      if (w <= 0)
         break;
      done += (size_t)w;
   }
   close(fd);
   if (done == count)
      rename(temp, path);
   else
      unlink(temp);
}

static void
persist(void)
{
   static char text[8192];
   const size_t count = format_status(text, sizeof(text));
   if (!count)
      return;
   persist_one(LIVE_JSON, text, count);
   persist_one(KEEP_JSON, text, count);
}

static FILE *
open_log(const char *path)
{
   FILE *f = fopen(path, "w");
   if (f) {
      chmod(path, 0644);
      setvbuf(f, NULL, _IOLBF, 0);
   }
   return f;
}

/* The shader cache directory: whether it exists and what RADV put in it. */
static void
cache_snapshot(bool *exists, uint32_t *entries)
{
   struct stat st;
   *exists = stat(SHADER_CACHE_DIR, &st) == 0 && S_ISDIR(st.st_mode);
   *entries = 0;
   cache.entries[0] = '\0';
   DIR *dir = opendir(SHADER_CACHE_DIR);
   if (!dir)
      return;
   size_t used = 0;
   for (struct dirent *entry; (entry = readdir(dir)) != NULL;) {
      if (entry->d_name[0] == '.')
         continue;
      (*entries)++;
      if (used + strlen(entry->d_name) + 2 < sizeof(cache.entries)) {
         const int w = snprintf(cache.entries + used, sizeof(cache.entries) - used, "%s%s", used ? "," : "",
                                entry->d_name);
         if (w > 0)
            used += (size_t)w;
      }
   }
   closedir(dir);
}

/* ------------------------------------------------------------ entry points */

#define INSTANCE_COMMANDS(X)                                                                       \
   X(DestroyInstance)                                                                              \
   X(EnumeratePhysicalDevices)                                                                     \
   X(GetPhysicalDeviceProperties2)                                                                 \
   X(GetPhysicalDeviceQueueFamilyProperties)                                                       \
   X(GetPhysicalDeviceMemoryProperties)                                                            \
   X(GetPhysicalDeviceFeatures2)                                                                   \
   X(CreateDevice)                                                                                 \
   X(EnumerateDeviceExtensionProperties)                                                           \
   X(GetDeviceProcAddr)

#define DISPLAY_INSTANCE_COMMANDS(X)                                                               \
   X(GetPhysicalDeviceDisplayPropertiesKHR)                                                        \
   X(GetDisplayModePropertiesKHR)                                                                  \
   X(CreateDisplayPlaneSurfaceKHR)                                                                 \
   X(DestroySurfaceKHR)                                                                            \
   X(GetPhysicalDeviceSurfaceSupportKHR)                                                           \
   X(GetPhysicalDeviceSurfaceCapabilitiesKHR)                                                      \
   X(GetPhysicalDeviceSurfaceFormatsKHR)

#define DEVICE_COMMANDS(X)                                                                         \
   X(DestroyDevice)                                                                                \
   X(GetDeviceQueue)                                                                               \
   X(QueueSubmit)                                                                                  \
   X(DeviceWaitIdle)                                                                               \
   X(CreateFence)                                                                                  \
   X(DestroyFence)                                                                                 \
   X(WaitForFences)                                                                                \
   X(ResetFences)                                                                                  \
   X(CreateSemaphore)                                                                              \
   X(DestroySemaphore)                                                                             \
   X(CreateCommandPool)                                                                            \
   X(DestroyCommandPool)                                                                           \
   X(AllocateCommandBuffers)                                                                       \
   X(BeginCommandBuffer)                                                                           \
   X(EndCommandBuffer)                                                                             \
   X(ResetCommandBuffer)                                                                           \
   X(CreateBuffer)                                                                                 \
   X(DestroyBuffer)                                                                                \
   X(GetBufferMemoryRequirements)                                                                  \
   X(AllocateMemory)                                                                               \
   X(FreeMemory)                                                                                   \
   X(BindBufferMemory)                                                                             \
   X(MapMemory)                                                                                    \
   X(CreateImageView)                                                                              \
   X(DestroyImageView)                                                                             \
   X(CreateShaderModule)                                                                           \
   X(DestroyShaderModule)                                                                          \
   X(CreatePipelineLayout)                                                                         \
   X(DestroyPipelineLayout)                                                                        \
   X(CreateGraphicsPipelines)                                                                      \
   X(DestroyPipeline)                                                                              \
   X(CmdPipelineBarrier2)                                                                          \
   X(CmdBeginRendering)                                                                            \
   X(CmdEndRendering)                                                                              \
   X(CmdBindPipeline)                                                                              \
   X(CmdPushConstants)                                                                             \
   X(CmdSetViewport)                                                                               \
   X(CmdSetScissor)                                                                                \
   X(CmdDraw)                                                                                      \
   X(CmdCopyImageToBuffer)                                                                         \
   X(CreateSwapchainKHR)                                                                           \
   X(DestroySwapchainKHR)                                                                          \
   X(GetSwapchainImagesKHR)                                                                        \
   X(AcquireNextImageKHR)                                                                          \
   X(QueuePresentKHR)

#define DECLARE(name) static PFN_vk##name vk##name;
INSTANCE_COMMANDS(DECLARE)
DISPLAY_INSTANCE_COMMANDS(DECLARE)
DEVICE_COMMANDS(DECLARE)
static PFN_vkCreateInstance vkCreateInstance;
static PFN_vkEnumerateInstanceExtensionProperties vkEnumerateInstanceExtensionProperties;

static bool
load_instance(VkInstance instance, bool display)
{
   bool ok = true;
#define LOAD(name)                                                                                 \
   vk##name = (PFN_vk##name)vk_icdGetInstanceProcAddr(instance, "vk" #name);                       \
   if (!vk##name) {                                                                                \
      report("missing vk" #name);                                                                  \
      ok = false;                                                                                  \
   }
   INSTANCE_COMMANDS(LOAD)
   if (display) {
      DISPLAY_INSTANCE_COMMANDS(LOAD)
   }
#undef LOAD
   return ok;
}

static bool
load_device(VkDevice device)
{
   bool ok = true;
#define LOAD(name)                                                                                 \
   vk##name = (PFN_vk##name)vkGetDeviceProcAddr(device, "vk" #name);                               \
   if (!vk##name) {                                                                                \
      report("missing vk" #name);                                                                  \
      ok = false;                                                                                  \
   }
   DEVICE_COMMANDS(LOAD)
#undef LOAD
   return ok;
}

/* ----------------------------------------------------------------- context */

struct buffer {
   VkBuffer buffer;
   VkDeviceMemory memory;
   void *map;
};

struct context {
   VkInstance instance;
   VkPhysicalDevice physical;
   VkPhysicalDeviceMemoryProperties memory;
   uint32_t family;
   VkDevice device;
   VkQueue queue;
   VkCommandPool pool;
   VkCommandBuffer cmd;
   VkFence fence;
   VkSemaphore acquired, rendered;
   bool display;
   VkSurfaceKHR surface;
   VkExtent2D extent;
   VkSwapchainKHR swapchain;
   uint32_t image_count;
   VkImage images[8];
   VkImageView views[8];
   VkPipelineLayout layout;
   VkPipeline pipeline;
   VkShaderModule vert, frag;
   struct buffer readback;
};

static uint32_t
memory_type(const struct context *c, uint32_t bits, VkMemoryPropertyFlags wanted)
{
   for (uint32_t i = 0; i < c->memory.memoryTypeCount; i++) {
      if ((bits & (1u << i)) && (c->memory.memoryTypes[i].propertyFlags & wanted) == wanted)
         return i;
   }
   return UINT32_MAX;
}

static bool
buffer_create(struct context *c, VkDeviceSize size, VkBufferUsageFlags usage, struct buffer *out)
{
   *out = (struct buffer){0};
   const VkBufferCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
      .size = size,
      .usage = usage,
      .sharingMode = VK_SHARING_MODE_EXCLUSIVE,
   };
   if (vkCreateBuffer(c->device, &info, NULL, &out->buffer) != VK_SUCCESS)
      return false;
   VkMemoryRequirements req;
   vkGetBufferMemoryRequirements(c->device, out->buffer, &req);
   const uint32_t type = memory_type(c, req.memoryTypeBits,
                                     VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
   const VkMemoryAllocateInfo alloc = {
      .sType = VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO,
      .allocationSize = req.size,
      .memoryTypeIndex = type,
   };
   return type != UINT32_MAX && vkAllocateMemory(c->device, &alloc, NULL, &out->memory) == VK_SUCCESS &&
          vkBindBufferMemory(c->device, out->buffer, out->memory, 0) == VK_SUCCESS &&
          vkMapMemory(c->device, out->memory, 0, VK_WHOLE_SIZE, 0, &out->map) == VK_SUCCESS;
}

/* --------------------------------------------------------------- instance */

static bool
create_instance(struct context *c)
{
   set_stage("instance");
   const uint64_t start = now_ns();
   vkCreateInstance = (PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(VK_NULL_HANDLE, "vkCreateInstance");
   vkEnumerateInstanceExtensionProperties = (PFN_vkEnumerateInstanceExtensionProperties)vk_icdGetInstanceProcAddr(
      VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
   if (!check(vkCreateInstance && vkEnumerateInstanceExtensionProperties, "instance: the ICD entry points"))
      return false;

   VkExtensionProperties extensions[64];
   uint32_t count = sizeof(extensions) / sizeof(extensions[0]);
   c->display = false;
   if (vkEnumerateInstanceExtensionProperties(NULL, &count, extensions) >= VK_SUCCESS) {
      vk.instance_extension_count = count;
      for (uint32_t i = 0; i < count; i++)
         c->display |= strcmp(extensions[i].extensionName, VK_KHR_DISPLAY_EXTENSION_NAME) == 0;
   }
   report("instance: %u extensions, VK_KHR_display %s", vk.instance_extension_count,
          c->display ? "reported" : "not reported");
   check(c->display, "instance: VK_KHR_display is reported");

   /* The recomp runtime creates its instance at 1.3 (runtime/nvn/vulkan/device.c). */
   const VkApplicationInfo app = {
      .sType = VK_STRUCTURE_TYPE_APPLICATION_INFO,
      .pApplicationName = "za-vk-probe",
      .pEngineName = "za-native-probe",
      .apiVersion = VK_API_VERSION_1_3,
   };
   const char *const display_extensions[] = {VK_KHR_SURFACE_EXTENSION_NAME, VK_KHR_DISPLAY_EXTENSION_NAME};
   const VkInstanceCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO,
      .pApplicationInfo = &app,
      .enabledExtensionCount = c->display ? 2 : 0,
      .ppEnabledExtensionNames = display_extensions,
   };
   vk.instance_rc = vkCreateInstance(&info, NULL, &c->instance);
   stage_ms.instance = since_ms(start);
   report("instance: vkCreateInstance rc=%d in %.1f ms", vk.instance_rc, stage_ms.instance);
   if (!check(vk.instance_rc == VK_SUCCESS, "instance: vkCreateInstance"))
      return false;
   return check(load_instance(c->instance, c->display), "instance: the instance commands");
}

/* ----------------------------------------------------------------- device */

static void
record_features(struct context *c)
{
   VkPhysicalDeviceVulkan13Features f13 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES};
   VkPhysicalDeviceVulkan12Features f12 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES,
                                           .pNext = &f13};
   VkPhysicalDeviceVulkan11Features f11 = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_1_FEATURES,
                                           .pNext = &f12};
   VkPhysicalDeviceFeatures2 f = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2, .pNext = &f11};
   vkGetPhysicalDeviceFeatures2(c->physical, &f);
   const VkBool32 values[] = {
      f11.storageBuffer16BitAccess,
      f12.timelineSemaphore,
      f12.shaderInt8,
      f12.samplerMirrorClampToEdge,
      f12.uniformAndStorageBuffer8BitAccess,
      f12.storageBuffer8BitAccess,
      f12.scalarBlockLayout,
      f12.shaderOutputLayer,
      f12.samplerFilterMinmax,
      f12.shaderOutputViewportIndex,
      f13.dynamicRendering,
      f13.synchronization2,
      f13.subgroupSizeControl,
      f13.shaderDemoteToHelperInvocation,
      f13.shaderTerminateInvocation,
      f13.maintenance4,
      f.features.independentBlend,
      f.features.dualSrcBlend,
      f.features.fillModeNonSolid,
      f.features.samplerAnisotropy,
      f.features.textureCompressionBC,
      f.features.shaderInt64,
      f.features.depthBiasClamp,
      f.features.depthClamp,
      f.features.largePoints,
      f.features.wideLines,
      f.features.imageCubeArray,
      f.features.sampleRateShading,
      f.features.fragmentStoresAndAtomics,
      f.features.vertexPipelineStoresAndAtomics,
      f.features.robustBufferAccess,
      f.features.shaderClipDistance,
      f.features.geometryShader,
   };
   _Static_assert(sizeof(values) / sizeof(values[0]) == GAME_FEATURES, "one value per named feature");
   unsigned missing = 0;
   for (size_t i = 0; i < GAME_FEATURES; i++) {
      game_features[i].present = values[i] == VK_TRUE;
      if (!game_features[i].present) {
         missing++;
         report("feature the game enables is not reported: %s", game_features[i].name);
      }
   }
   report("features: %u of %u the game asks for are reported", (unsigned)GAME_FEATURES - missing,
          (unsigned)GAME_FEATURES);
}

static bool
create_device(struct context *c)
{
   set_stage("device");
   const uint64_t start = now_ns();
   uint32_t count = 1;
   VkResult result = vkEnumeratePhysicalDevices(c->instance, &count, &c->physical);
   if (!check((result == VK_SUCCESS || result == VK_INCOMPLETE) && count == 1, "device: one physical device"))
      return false;
   /* RADV opens its disk cache with the physical device. */
   cache_snapshot(&cache.exists_after_enumerate, &cache.entries_after_enumerate);
   report("shader cache: %s %s after enumeration, %u entries [%s]", SHADER_CACHE_DIR,
          cache.exists_after_enumerate ? "exists" : "missing", cache.entries_after_enumerate, cache.entries);

   VkPhysicalDeviceDriverProperties driver = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
   VkPhysicalDeviceProperties2 props = {.sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2, .pNext = &driver};
   vkGetPhysicalDeviceProperties2(c->physical, &props);
   snprintf(vk.api_version, sizeof(vk.api_version), "%u.%u.%u", VK_API_VERSION_MAJOR(props.properties.apiVersion),
            VK_API_VERSION_MINOR(props.properties.apiVersion), VK_API_VERSION_PATCH(props.properties.apiVersion));
   snprintf(vk.device_name, sizeof(vk.device_name), "%s", props.properties.deviceName);
   snprintf(vk.driver_name, sizeof(vk.driver_name), "%s", driver.driverName);
   snprintf(vk.driver_info, sizeof(vk.driver_info), "%s", driver.driverInfo);
   report("device: %s, Vulkan %s, %s %s", vk.device_name, vk.api_version, vk.driver_name, vk.driver_info);
   check(props.properties.apiVersion >= VK_API_VERSION_1_3, "device: reports Vulkan 1.3 or later (the game's path)");

   VkQueueFamilyProperties families[8];
   count = 8;
   vkGetPhysicalDeviceQueueFamilyProperties(c->physical, &count, families);
   c->family = UINT32_MAX;
   for (uint32_t i = 0; i < count; i++) {
      const VkQueueFlags both = VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT;
      if ((families[i].queueFlags & both) == both) {
         c->family = i;
         break;
      }
   }
   vk.queue_family = c->family;
   if (!check(c->family != UINT32_MAX, "device: a graphics and compute queue family"))
      return false;

   vkGetPhysicalDeviceMemoryProperties(c->physical, &c->memory);
   for (uint32_t i = 0; i < c->memory.memoryHeapCount; i++) {
      if (c->memory.memoryHeaps[i].flags & VK_MEMORY_HEAP_DEVICE_LOCAL_BIT)
         vk.device_local_bytes += c->memory.memoryHeaps[i].size;
   }
   for (uint32_t i = 0; i < c->memory.memoryTypeCount; i++) {
      if (c->memory.memoryTypes[i].propertyFlags & VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT) {
         vk.host_visible_bytes = c->memory.memoryHeaps[c->memory.memoryTypes[i].heapIndex].size;
         break;
      }
   }
   report("device: %u heaps, %llu MiB device-local, host-visible heap %llu MiB", c->memory.memoryHeapCount,
          (unsigned long long)(vk.device_local_bytes >> 20), (unsigned long long)(vk.host_visible_bytes >> 20));

   count = 0;
   vkEnumerateDeviceExtensionProperties(c->physical, NULL, &count, NULL);
   VkExtensionProperties *extensions = calloc(count ? count : 1, sizeof(*extensions));
   bool swapchain = false;
   if (extensions && vkEnumerateDeviceExtensionProperties(c->physical, NULL, &count, extensions) >= VK_SUCCESS) {
      vk.device_extension_count = count;
      for (uint32_t i = 0; i < count; i++) {
         for (size_t g = 0; g < GAME_EXTENSIONS; g++)
            game_extension_present[g] |= strcmp(extensions[i].extensionName, game_extensions[g]) == 0;
         swapchain |= strcmp(extensions[i].extensionName, VK_KHR_SWAPCHAIN_EXTENSION_NAME) == 0;
      }
   }
   free(extensions);
   for (size_t g = 0; g < GAME_EXTENSIONS; g++) {
      if (!game_extension_present[g])
         report("extension the game asks for is not reported: %s", game_extensions[g]);
   }
   report("device: %u extensions", vk.device_extension_count);
   check(swapchain, "device: VK_KHR_swapchain is reported");
   record_features(c);

   /* Only what this probe draws with: dynamic rendering and synchronization2,
    * asked for only where reported. The game's full set is recorded above. */
   const bool dynamic_rendering = game_features[10].present, synchronization2 = game_features[11].present;
   check(dynamic_rendering && synchronization2, "device: dynamicRendering and synchronization2 are reported");
   VkPhysicalDeviceVulkan13Features enable13 = {
      .sType = VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_3_FEATURES,
      .dynamicRendering = dynamic_rendering,
      .synchronization2 = synchronization2,
   };
   const float priority = 1.0f;
   const VkDeviceQueueCreateInfo queue_info = {
      .sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO,
      .queueFamilyIndex = c->family,
      .queueCount = 1,
      .pQueuePriorities = &priority,
   };
   const char *const device_extensions[] = {VK_KHR_SWAPCHAIN_EXTENSION_NAME};
   const VkDeviceCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO,
      .pNext = &enable13,
      .queueCreateInfoCount = 1,
      .pQueueCreateInfos = &queue_info,
      .enabledExtensionCount = swapchain ? 1 : 0,
      .ppEnabledExtensionNames = device_extensions,
   };
   result = vkCreateDevice(c->physical, &info, NULL, &c->device);
   stage_ms.device = since_ms(start);
   report("device: vkCreateDevice rc=%d in %.1f ms", result, stage_ms.device);
   if (!check(result == VK_SUCCESS, "device: vkCreateDevice"))
      return false;
   if (!check(load_device(c->device), "device: the device commands"))
      return false;
   vkGetDeviceQueue(c->device, c->family, 0, &c->queue);

   const VkCommandPoolCreateInfo pool_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO,
      .flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT,
      .queueFamilyIndex = c->family,
   };
   const VkFenceCreateInfo fence_info = {.sType = VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
   const VkSemaphoreCreateInfo semaphore_info = {.sType = VK_STRUCTURE_TYPE_SEMAPHORE_CREATE_INFO};
   bool ok = vkCreateCommandPool(c->device, &pool_info, NULL, &c->pool) == VK_SUCCESS;
   const VkCommandBufferAllocateInfo cmd_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO,
      .commandPool = c->pool,
      .level = VK_COMMAND_BUFFER_LEVEL_PRIMARY,
      .commandBufferCount = 1,
   };
   ok = ok && vkAllocateCommandBuffers(c->device, &cmd_info, &c->cmd) == VK_SUCCESS &&
        vkCreateFence(c->device, &fence_info, NULL, &c->fence) == VK_SUCCESS &&
        vkCreateSemaphore(c->device, &semaphore_info, NULL, &c->acquired) == VK_SUCCESS &&
        vkCreateSemaphore(c->device, &semaphore_info, NULL, &c->rendered) == VK_SUCCESS;
   return check(ok, "device: command pool, command buffer, fence and semaphores");
}

/* ---------------------------------------------------------------- display */

static bool
create_surface(struct context *c)
{
   set_stage("surface");
   if (!check(c->display, "surface: VK_KHR_display was enabled"))
      return false;
   const uint64_t start = now_ns();
   VkDisplayPropertiesKHR display;
   uint32_t count = 1;
   VkResult result = vkGetPhysicalDeviceDisplayPropertiesKHR(c->physical, &count, &display);
   if (!check((result == VK_SUCCESS || result == VK_INCOMPLETE) && count == 1, "surface: one display"))
      return false;
   snprintf(vk.display_name, sizeof(vk.display_name), "%s", display.displayName ? display.displayName : "");
   vk.display_w = display.physicalResolution.width;
   vk.display_h = display.physicalResolution.height;
   VkDisplayModePropertiesKHR modes[4];
   count = 4;
   result = vkGetDisplayModePropertiesKHR(c->physical, display.display, &count, modes);
   if (!check((result == VK_SUCCESS || result == VK_INCOMPLETE) && count >= 1, "surface: the display's modes"))
      return false;
   vk.refresh_mhz = modes[0].parameters.refreshRate;
   /* The first mode is what the surface takes; the swapchain is made at the
    * display's physical resolution, whatever it is. */
   c->extent = display.physicalResolution;
   report("surface: %s, %ux%u physical, %u mode(s), the first %ux%u at %.3f Hz", vk.display_name, vk.display_w,
          vk.display_h, count, modes[0].parameters.visibleRegion.width, modes[0].parameters.visibleRegion.height,
          modes[0].parameters.refreshRate / 1000.0);

   const VkDisplaySurfaceCreateInfoKHR surface_info = {
      .sType = VK_STRUCTURE_TYPE_DISPLAY_SURFACE_CREATE_INFO_KHR,
      .displayMode = modes[0].displayMode,
      .transform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR,
      .alphaMode = VK_DISPLAY_PLANE_ALPHA_OPAQUE_BIT_KHR,
      .imageExtent = c->extent,
   };
   result = vkCreateDisplayPlaneSurfaceKHR(c->instance, &surface_info, NULL, &c->surface);
   if (!check(result == VK_SUCCESS, "surface: vkCreateDisplayPlaneSurfaceKHR"))
      return false;
   VkBool32 supported = VK_FALSE;
   vkGetPhysicalDeviceSurfaceSupportKHR(c->physical, c->family, c->surface, &supported);
   vk.surface_supported = supported == VK_TRUE;
   VkSurfaceCapabilitiesKHR caps;
   vkGetPhysicalDeviceSurfaceCapabilitiesKHR(c->physical, c->surface, &caps);
   report("surface: supported %d, current %ux%u, images %u..%u, usage 0x%x", (int)supported,
          caps.currentExtent.width, caps.currentExtent.height, caps.minImageCount, caps.maxImageCount,
          caps.supportedUsageFlags);
   VkSurfaceFormatKHR formats[16];
   count = 16;
   vkGetPhysicalDeviceSurfaceFormatsKHR(c->physical, c->surface, &count, formats);
   bool bgra = false;
   for (uint32_t i = 0; i < count; i++) {
      report("surface: format %d colour space %d", formats[i].format, formats[i].colorSpace);
      bgra |= formats[i].format == VK_FORMAT_B8G8R8A8_UNORM;
   }
   stage_ms.surface = since_ms(start);
   check(bgra, "surface: B8G8R8A8_UNORM is offered");
   const bool usage_ok = (caps.supportedUsageFlags &
                          (VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT)) ==
                         (VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
   return check(supported && caps.minImageCount <= 3 && (caps.maxImageCount == 0 || caps.maxImageCount >= 3) &&
                   usage_ok,
                "surface: support, three images and colour-attachment + transfer-source usage");
}

static bool
create_swapchain(struct context *c)
{
   set_stage("swapchain");
   const uint64_t start = now_ns();
   const VkSwapchainCreateInfoKHR info = {
      .sType = VK_STRUCTURE_TYPE_SWAPCHAIN_CREATE_INFO_KHR,
      .surface = c->surface,
      .minImageCount = 3,
      .imageFormat = VK_FORMAT_B8G8R8A8_UNORM,
      .imageColorSpace = VK_COLOR_SPACE_SRGB_NONLINEAR_KHR,
      .imageExtent = c->extent,
      .imageArrayLayers = 1,
      .imageUsage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
      .imageSharingMode = VK_SHARING_MODE_EXCLUSIVE,
      .preTransform = VK_SURFACE_TRANSFORM_IDENTITY_BIT_KHR,
      .compositeAlpha = VK_COMPOSITE_ALPHA_OPAQUE_BIT_KHR,
      .presentMode = VK_PRESENT_MODE_FIFO_KHR,
      .clipped = VK_TRUE,
   };
   vk.swapchain_rc = vkCreateSwapchainKHR(c->device, &info, NULL, &c->swapchain);
   report("swapchain: vkCreateSwapchainKHR rc=%d", vk.swapchain_rc);
   if (!check(vk.swapchain_rc == VK_SUCCESS, "swapchain: vkCreateSwapchainKHR"))
      return false;
   c->image_count = sizeof(c->images) / sizeof(c->images[0]);
   VkResult result = vkGetSwapchainImagesKHR(c->device, c->swapchain, &c->image_count, c->images);
   vk.swapchain_images = c->image_count;
   report("swapchain: %u images", c->image_count);
   if (!check(result == VK_SUCCESS && c->image_count >= 3 && c->image_count <= 8, "swapchain: 3 to 8 images"))
      return false;
   bool ok = true;
   for (uint32_t i = 0; i < c->image_count; i++) {
      const VkImageViewCreateInfo view_info = {
         .sType = VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO,
         .image = c->images[i],
         .viewType = VK_IMAGE_VIEW_TYPE_2D,
         .format = VK_FORMAT_B8G8R8A8_UNORM,
         .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
      };
      ok = ok && vkCreateImageView(c->device, &view_info, NULL, &c->views[i]) == VK_SUCCESS;
   }
   stage_ms.swapchain = since_ms(start);
   return check(ok, "swapchain: an image view per image");
}

/* --------------------------------------------------------------- pipeline */

struct push {
   float angle;
   float aspect;
   float white; /* 1 while a controller button is held: the triangle turns white */
};

static bool
create_pipeline(struct context *c)
{
   set_stage("pipeline");
   const uint64_t start = now_ns();
   const VkShaderModuleCreateInfo vert_info = {
      .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
      .codeSize = sizeof(za_vk_tri_vert),
      .pCode = za_vk_tri_vert,
   };
   const VkShaderModuleCreateInfo frag_info = {
      .sType = VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO,
      .codeSize = sizeof(za_vk_tri_frag),
      .pCode = za_vk_tri_frag,
   };
   bool ok = vkCreateShaderModule(c->device, &vert_info, NULL, &c->vert) == VK_SUCCESS &&
             vkCreateShaderModule(c->device, &frag_info, NULL, &c->frag) == VK_SUCCESS;
   if (!check(ok, "pipeline: the two shader modules"))
      return false;
   const VkPushConstantRange push_range = {
      .stageFlags = VK_SHADER_STAGE_VERTEX_BIT,
      .size = sizeof(struct push),
   };
   const VkPipelineLayoutCreateInfo layout_info = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO,
      .pushConstantRangeCount = 1,
      .pPushConstantRanges = &push_range,
   };
   if (!check(vkCreatePipelineLayout(c->device, &layout_info, NULL, &c->layout) == VK_SUCCESS,
              "pipeline: the pipeline layout"))
      return false;

   const VkPipelineShaderStageCreateInfo stages[2] = {
      {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage = VK_SHADER_STAGE_VERTEX_BIT,
       .module = c->vert,
       .pName = "main"},
      {.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO,
       .stage = VK_SHADER_STAGE_FRAGMENT_BIT,
       .module = c->frag,
       .pName = "main"},
   };
   const VkPipelineVertexInputStateCreateInfo vertex_input = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
   const VkPipelineInputAssemblyStateCreateInfo assembly = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO,
      .topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST,
   };
   const VkPipelineViewportStateCreateInfo viewport_state = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO,
      .viewportCount = 1,
      .scissorCount = 1,
   };
   const VkPipelineRasterizationStateCreateInfo raster = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO,
      .polygonMode = VK_POLYGON_MODE_FILL,
      .cullMode = VK_CULL_MODE_NONE,
      .frontFace = VK_FRONT_FACE_COUNTER_CLOCKWISE,
      .lineWidth = 1.0f,
   };
   const VkPipelineMultisampleStateCreateInfo multisample = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO,
      .rasterizationSamples = VK_SAMPLE_COUNT_1_BIT,
   };
   const VkPipelineColorBlendAttachmentState blend_attachment = {.colorWriteMask = 0xf};
   const VkPipelineColorBlendStateCreateInfo blend = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO,
      .attachmentCount = 1,
      .pAttachments = &blend_attachment,
   };
   const VkDynamicState dynamic_states[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
   const VkPipelineDynamicStateCreateInfo dynamic = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO,
      .dynamicStateCount = 2,
      .pDynamicStates = dynamic_states,
   };
   const VkFormat format = VK_FORMAT_B8G8R8A8_UNORM;
   const VkPipelineRenderingCreateInfo rendering_info = {
      .sType = VK_STRUCTURE_TYPE_PIPELINE_RENDERING_CREATE_INFO,
      .colorAttachmentCount = 1,
      .pColorAttachmentFormats = &format,
   };
   const VkGraphicsPipelineCreateInfo info = {
      .sType = VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO,
      .pNext = &rendering_info,
      .stageCount = 2,
      .pStages = stages,
      .pVertexInputState = &vertex_input,
      .pInputAssemblyState = &assembly,
      .pViewportState = &viewport_state,
      .pRasterizationState = &raster,
      .pMultisampleState = &multisample,
      .pColorBlendState = &blend,
      .pDynamicState = &dynamic,
      .layout = c->layout,
   };
   vk.pipeline_rc = vkCreateGraphicsPipelines(c->device, VK_NULL_HANDLE, 1, &info, NULL, &c->pipeline);
   stage_ms.pipeline = since_ms(start);
   report("pipeline: vkCreateGraphicsPipelines rc=%d in %.1f ms (shaders compiled on the console)", vk.pipeline_rc,
          stage_ms.pipeline);
   if (!check(vk.pipeline_rc == VK_SUCCESS, "pipeline: a graphics pipeline with dynamic rendering compiles"))
      return false;
   /* Two pixels (centre and corner) of one frame, read back on the CPU. */
   return check(buffer_create(c, 64, VK_BUFFER_USAGE_TRANSFER_DST_BIT, &c->readback), "pipeline: the readback buffer");
}

/* ------------------------------------------------------------- controller */

static void
setup_pad(void)
{
   set_stage("pad");
   /* As ProsperoEden opens its pads on this console: User Service, the
    * foreground user (the initial user as the fallback), scePadInit, scePadOpen. */
   pad.user_service_rc = sceUserServiceInitialize(NULL);
   pad.foreground_rc = sceUserServiceGetForegroundUser(&pad.user_id);
   if (pad.foreground_rc < 0 || pad.user_id < 0) {
      pad.user_id = -1;
      pad.initial_rc = sceUserServiceGetInitialUser(&pad.user_id);
   }
   report("pad: sceUserServiceInitialize rc=0x%08x, foreground user rc=0x%08x, initial user rc=0x%08x, user %d",
          (unsigned)pad.user_service_rc, (unsigned)pad.foreground_rc, (unsigned)pad.initial_rc, pad.user_id);
   if (!check(pad.user_id >= 0, "pad: a user id from User Service"))
      return;
   pad.init_rc = scePadInit();
   report("pad: scePadInit rc=0x%08x", (unsigned)pad.init_rc);
   check(pad.init_rc == 0, "pad: scePadInit");
   pad.open_rc = scePadOpen(pad.user_id, PAD_PORT_TYPE_STANDARD, 0, NULL);
   pad.handle = pad.open_rc;
   if (pad.handle < 0) {
      /* A handle the process already holds for this user is reused. */
      pad.handle = scePadGetHandle(pad.user_id, PAD_PORT_TYPE_STANDARD, 0);
   }
   report("pad: scePadOpen rc=0x%08x, handle %d", (unsigned)pad.open_rc, pad.handle);
   if (!check(pad.handle >= 0, "pad: a pad handle for the user (scePadOpen, else scePadGetHandle)"))
      return;
   union {
      struct pad_record record;
      uint8_t raw[256];
   } data;
   memset(&data, 0, sizeof(data));
   pad.read_rc = scePadReadState(pad.handle, &data);
   pad.reads++;
   pad.connected = data.record.connected;
   report("pad: scePadReadState rc=0x%08x, connected %d, buttons 0x%08x", (unsigned)pad.read_rc, (int)pad.connected,
          data.record.buttons);
   check(pad.read_rc == 0, "pad: scePadReadState");
}

/* Once per frame: the latest cached state; a rising edge is a press. */
static void
poll_pad(void)
{
   if (pad.handle < 0)
      return;
   union {
      struct pad_record record;
      uint8_t raw[256];
   } data;
   memset(&data, 0, sizeof(data));
   const int rc = scePadReadState(pad.handle, &data);
   pad.read_rc = rc;
   pad.reads++;
   if (rc != 0) {
      pad.read_failures++;
      pad.held = 0;
      return;
   }
   pad.connected = data.record.connected;
   const uint32_t buttons = (data.record.buttons & PAD_BUTTON_INTERCEPTED) ? 0 : data.record.buttons;
   const uint32_t pressed = buttons & ~pad.held;
   pad.held = buttons;
   if (!pressed)
      return;
   pad.press_count++;
   pad.buttons_seen |= pressed;
   atomic_fetch_add(&audio.beeps_pending, 1);
   if (pressed & PAD_BUTTON_OPTIONS)
      pad.options_stop = true;
   if (pad.press_count == 1) {
      pad.first_press_frame = vk.frames_presented;
      pad.first_press_buttons = pressed;
      pad.first_press_ms = since_ms(boot_ns);
      const uint8_t green[4] = {0, 255, 0, 0};
      pad.lightbar_rc = scePadSetLightBar(pad.handle, green);
      report("pad: first press 0x%08x at frame %u, %.0f ms; light bar green rc=0x%08x", pressed, pad.first_press_frame,
             pad.first_press_ms, (unsigned)pad.lightbar_rc);
   }
   if (pad.press_count <= PRESS_REPORTS || pad.press_count % 10 == 0)
      report("pad: press %u buttons 0x%08x (held 0x%08x)", pad.press_count, pressed, buttons);
}

static void
teardown_pad(void)
{
   if (pad.handle >= 0) {
      if (pad.press_count)
         scePadResetLightBar(pad.handle);
      pad.close_rc = scePadClose(pad.handle);
      report("pad: scePadClose rc=0x%08x after %u reads, %u presses, buttons seen 0x%08x", (unsigned)pad.close_rc,
             pad.reads, pad.press_count, pad.buttons_seen);
      pad.handle = -1;
   }
   if (pad.user_service_rc == 0)
      sceUserServiceTerminate();
}

/* ------------------------------------------------------------------ audio */

struct audio_state {
   int16_t block[AUDIO_GRAIN * 2]; /* one grain, interleaved stereo */
   float phase;
   uint32_t tone_left, beep_left;
};

static struct audio_state audio_state;

static void
fill_tone(struct audio_state *s, float frequency)
{
   const float step = 2.0f * 3.14159265f * frequency / (float)AUDIO_RATE;
   for (uint32_t i = 0; i < AUDIO_GRAIN; i++) {
      const int16_t sample = (int16_t)(8000.0f * sinf(s->phase)); /* about -12 dBFS */
      s->block[2 * i] = sample;
      s->block[2 * i + 1] = sample;
      s->phase += step;
      if (s->phase > 2.0f * 3.14159265f)
         s->phase -= 2.0f * 3.14159265f;
   }
}

/* One grain to the port: the tone, a pending beep, or silence (which keeps the
 * port paced between beeps). sceAudioOutOutput returns when the previous grain
 * has played, so this call is the pacing. */
static void
audio_step(struct audio_state *s)
{
   enum { SILENCE, TONE, BEEP } kind = SILENCE;
   if (s->tone_left) {
      kind = TONE;
      s->tone_left--;
      fill_tone(s, 440.0f);
   } else {
      if (!s->beep_left && atomic_load(&audio.beeps_pending)) {
         atomic_fetch_sub(&audio.beeps_pending, 1);
         atomic_fetch_add(&audio.beeps_played, 1);
         s->beep_left = BEEP_GRAINS;
         s->phase = 0.0f;
      }
      if (s->beep_left) {
         kind = BEEP;
         s->beep_left--;
         fill_tone(s, 880.0f);
      } else {
         memset(s->block, 0, sizeof(s->block));
      }
   }
   const int rc = sceAudioOutOutput(audio.handle, s->block);
   atomic_store(&audio.last_output_rc, rc);
   if (rc < 0) {
      atomic_fetch_add(&audio.output_failures, 1);
      if (kind == TONE)
         atomic_fetch_add(&audio.tone_failures, 1);
      return;
   }
   atomic_fetch_add(&audio.grains_written, 1);
   if (kind == TONE) {
      if (atomic_fetch_add(&audio.tone_grains, 1) + 1 == TONE_GRAINS && atomic_load(&audio.tone_failures) == 0)
         atomic_store(&audio.tone_complete, true);
   } else if (kind == BEEP) {
      atomic_fetch_add(&audio.beep_grains, 1);
   }
}

static void *
audio_thread(void *arg)
{
   struct audio_state *s = arg;
   while (atomic_load(&audio.running)) {
      audio_step(s);
      if (atomic_load(&audio.last_output_rc) < 0) {
         if (atomic_load(&audio.output_failures) >= 64)
            break; /* the port is not taking grains; the counters say so */
         usleep(5000);
      }
   }
   return NULL;
}

static void
setup_audio(void)
{
   set_stage("audio");
   audio.init_rc = sceAudioOutInit();
   report("audio: sceAudioOutInit rc=0x%08x", (unsigned)audio.init_rc);
   /* The system user, as ProsperoEden opens its port; the pad's user as the fallback. */
   audio.user_id_used = USER_ID_SYSTEM;
   audio.open_rc = sceAudioOutOpen(USER_ID_SYSTEM, AUDIO_PORT_MAIN, 0, AUDIO_GRAIN, AUDIO_RATE, AUDIO_FORMAT_S16_STEREO);
   if (audio.open_rc < 0 && pad.user_id >= 0) {
      report("audio: sceAudioOutOpen for the system user rc=0x%08x; trying user %d", (unsigned)audio.open_rc,
             pad.user_id);
      audio.user_id_used = pad.user_id;
      audio.open_rc = sceAudioOutOpen(pad.user_id, AUDIO_PORT_MAIN, 0, AUDIO_GRAIN, AUDIO_RATE, AUDIO_FORMAT_S16_STEREO);
   }
   audio.handle = audio.open_rc >= 0 ? audio.open_rc : -1;
   report("audio: sceAudioOutOpen(user 0x%x, main port, %u samples, %u Hz, S16 stereo) rc=0x%08x",
          (unsigned)audio.user_id_used, (unsigned)AUDIO_GRAIN, (unsigned)AUDIO_RATE, (unsigned)audio.open_rc);
   if (!check(audio.handle >= 0, "audio: sceAudioOutOpen on the main port"))
      return;
   int volumes[8];
   for (size_t i = 0; i < sizeof(volumes) / sizeof(volumes[0]); i++)
      volumes[i] = AUDIO_VOLUME_0DB;
   audio.volume_rc = sceAudioOutSetVolume(audio.handle, AUDIO_VOLUME_BOTH, volumes);
   report("audio: sceAudioOutSetVolume rc=0x%08x", (unsigned)audio.volume_rc);
   check(audio.volume_rc >= 0, "audio: sceAudioOutSetVolume to 0 dB");
}

/* Called when the frames start: the tone begins at once. Threads work in a
 * title that links RADV (its smoke test makes one, and the link recipe wraps
 * pthread_create to give the thread a direct-memory stack); should the thread
 * not start, the frame loop pushes one grain per frame instead, which starves
 * the port (256 of every 800 samples) but never stalls a frame. */
static void
audio_start(void)
{
   if (audio.handle < 0)
      return;
   audio_state.tone_left = TONE_GRAINS;
   atomic_store(&audio.running, true);
   audio.thread_rc = pthread_create(&audio.thread, NULL, audio_thread, &audio_state);
   audio.thread_started = audio.thread_rc == 0;
   audio.mode = audio.thread_started ? "thread" : "frame-loop";
   report("audio: submission on the %s (pthread_create rc=%d); the 1 s tone starts", audio.mode, audio.thread_rc);
}

static void
teardown_audio(void)
{
   if (audio.thread_started) {
      atomic_store(&audio.running, false);
      pthread_join(audio.thread, NULL);
      audio.thread_started = false;
   }
   if (audio.handle >= 0) {
      audio.drain_rc = sceAudioOutOutput(audio.handle, NULL);
      audio.close_rc = sceAudioOutClose(audio.handle);
      report("audio: %u grains written (%u tone, %u beep in %u beeps), %u failures; drain rc=0x%08x, close rc=0x%08x",
             atomic_load(&audio.grains_written), atomic_load(&audio.tone_grains), atomic_load(&audio.beep_grains),
             atomic_load(&audio.beeps_played), atomic_load(&audio.output_failures), (unsigned)audio.drain_rc,
             (unsigned)audio.close_rc);
      audio.handle = -1;
   }
}

/* ----------------------------------------------------------------- frames */

static void
image_barrier(struct context *c, VkImage image, VkImageLayout from, VkImageLayout to, VkPipelineStageFlags2 src_stage,
              VkAccessFlags2 src_access, VkPipelineStageFlags2 dst_stage, VkAccessFlags2 dst_access)
{
   const VkImageMemoryBarrier2 barrier = {
      .sType = VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER_2,
      .srcStageMask = src_stage,
      .srcAccessMask = src_access,
      .dstStageMask = dst_stage,
      .dstAccessMask = dst_access,
      .oldLayout = from,
      .newLayout = to,
      .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
      .image = image,
      .subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1},
   };
   const VkDependencyInfo dependency = {
      .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO,
      .imageMemoryBarrierCount = 1,
      .pImageMemoryBarriers = &barrier,
   };
   vkCmdPipelineBarrier2(c->cmd, &dependency);
}

/* One frame: acquire, clear and draw the triangle, read two pixels back when
 * asked, present, and wait for the frame's fence (one command buffer). */
static VkResult
frame(struct context *c, float angle, bool readback, float white)
{
   uint32_t index;
   VkResult result = vkAcquireNextImageKHR(c->device, c->swapchain, UINT64_MAX, c->acquired, VK_NULL_HANDLE, &index);
   if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
      report("frame: vkAcquireNextImageKHR rc=%d", result);
      return result;
   }
   const VkImage image = c->images[index];
   const VkCommandBufferBeginInfo begin_info = {
      .sType = VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO,
      .flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT,
   };
   vkResetCommandBuffer(c->cmd, 0);
   vkBeginCommandBuffer(c->cmd, &begin_info);
   image_barrier(c, image, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
                 VK_PIPELINE_STAGE_2_TOP_OF_PIPE_BIT, 0, VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT,
                 VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT);
   const VkRenderingAttachmentInfo attachment = {
      .sType = VK_STRUCTURE_TYPE_RENDERING_ATTACHMENT_INFO,
      .imageView = c->views[index],
      .imageLayout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL,
      .loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR,
      .storeOp = VK_ATTACHMENT_STORE_OP_STORE,
      .clearValue = {.color = {.float32 = {0.06f, 0.06f, 0.25f, 1.0f}}},
   };
   const VkRenderingInfo rendering = {
      .sType = VK_STRUCTURE_TYPE_RENDERING_INFO,
      .renderArea = {{0, 0}, c->extent},
      .layerCount = 1,
      .colorAttachmentCount = 1,
      .pColorAttachments = &attachment,
   };
   vkCmdBeginRendering(c->cmd, &rendering);
   vkCmdBindPipeline(c->cmd, VK_PIPELINE_BIND_POINT_GRAPHICS, c->pipeline);
   const VkViewport viewport = {0.0f, 0.0f, (float)c->extent.width, (float)c->extent.height, 0.0f, 1.0f};
   const VkRect2D scissor = {{0, 0}, c->extent};
   vkCmdSetViewport(c->cmd, 0, 1, &viewport);
   vkCmdSetScissor(c->cmd, 0, 1, &scissor);
   const struct push push = {angle, (float)c->extent.width / (float)c->extent.height, white};
   vkCmdPushConstants(c->cmd, c->layout, VK_SHADER_STAGE_VERTEX_BIT, 0, sizeof(push), &push);
   vkCmdDraw(c->cmd, 3, 1, 0, 0);
   vkCmdEndRendering(c->cmd);
   VkImageLayout layout = VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL;
   if (readback) {
      image_barrier(c, image, layout, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                    VK_PIPELINE_STAGE_2_COLOR_ATTACHMENT_OUTPUT_BIT, VK_ACCESS_2_COLOR_ATTACHMENT_WRITE_BIT,
                    VK_PIPELINE_STAGE_2_COPY_BIT, VK_ACCESS_2_TRANSFER_READ_BIT);
      layout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
      const VkBufferImageCopy copies[2] = {
         {.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1},
          .imageOffset = {(int32_t)(c->extent.width / 2), (int32_t)(c->extent.height / 2), 0},
          .imageExtent = {1, 1, 1}},
         {.bufferOffset = 4, .imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1}, .imageExtent = {1, 1, 1}},
      };
      vkCmdCopyImageToBuffer(c->cmd, image, layout, c->readback.buffer, 2, copies);
      const VkMemoryBarrier2 host = {
         .sType = VK_STRUCTURE_TYPE_MEMORY_BARRIER_2,
         .srcStageMask = VK_PIPELINE_STAGE_2_COPY_BIT,
         .srcAccessMask = VK_ACCESS_2_TRANSFER_WRITE_BIT,
         .dstStageMask = VK_PIPELINE_STAGE_2_HOST_BIT,
         .dstAccessMask = VK_ACCESS_2_HOST_READ_BIT,
      };
      const VkDependencyInfo dependency = {
         .sType = VK_STRUCTURE_TYPE_DEPENDENCY_INFO,
         .memoryBarrierCount = 1,
         .pMemoryBarriers = &host,
      };
      vkCmdPipelineBarrier2(c->cmd, &dependency);
   }
   image_barrier(c, image, layout, VK_IMAGE_LAYOUT_PRESENT_SRC_KHR, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT,
                 VK_ACCESS_2_MEMORY_WRITE_BIT, VK_PIPELINE_STAGE_2_ALL_COMMANDS_BIT, 0);
   vkEndCommandBuffer(c->cmd);

   const VkPipelineStageFlags wait_stage = VK_PIPELINE_STAGE_COLOR_ATTACHMENT_OUTPUT_BIT;
   const VkSubmitInfo submit = {
      .sType = VK_STRUCTURE_TYPE_SUBMIT_INFO,
      .waitSemaphoreCount = 1,
      .pWaitSemaphores = &c->acquired,
      .pWaitDstStageMask = &wait_stage,
      .commandBufferCount = 1,
      .pCommandBuffers = &c->cmd,
      .signalSemaphoreCount = 1,
      .pSignalSemaphores = &c->rendered,
   };
   vkResetFences(c->device, 1, &c->fence);
   result = vkQueueSubmit(c->queue, 1, &submit, c->fence);
   if (result != VK_SUCCESS) {
      report("frame: vkQueueSubmit rc=%d", result);
      return result;
   }
   const VkPresentInfoKHR present = {
      .sType = VK_STRUCTURE_TYPE_PRESENT_INFO_KHR,
      .waitSemaphoreCount = 1,
      .pWaitSemaphores = &c->rendered,
      .swapchainCount = 1,
      .pSwapchains = &c->swapchain,
      .pImageIndices = &index,
   };
   result = vkQueuePresentKHR(c->queue, &present);
   vk.last_present_rc = result;
   /* The one command buffer is recorded again next frame. */
   const VkResult waited = vkWaitForFences(c->device, 1, &c->fence, VK_TRUE, UINT64_C(5000000000));
   if (waited != VK_SUCCESS) {
      report("frame: vkWaitForFences rc=%d", waited);
      return waited;
   }
   return result;
}

static bool
channels_near(uint32_t bgra, unsigned b, unsigned g, unsigned r, unsigned tolerance)
{
   const unsigned pb = bgra & 0xff, pg = (bgra >> 8) & 0xff, pr = (bgra >> 16) & 0xff;
   return (unsigned)abs((int)pb - (int)b) <= tolerance && (unsigned)abs((int)pg - (int)g) <= tolerance &&
          (unsigned)abs((int)pr - (int)r) <= tolerance;
}

static bool
run_frames(struct context *c)
{
   set_stage("frames");
   audio_start();
   const uint64_t start = now_ns();
   uint64_t last = start;
   double window_min = 1e9, window_max = 0.0, window_sum = 0.0;
   unsigned window_count = 0;
   bool ok = true, readback_checked = false, options_seen = false;
   while (ok) {
      const double elapsed = (double)(now_ns() - start) / 1e9;
      if (elapsed >= RUN_SECONDS) {
         report("frames: %.0f s elapsed", RUN_SECONDS);
         break;
      }
      if (access(STOP_FILE, F_OK) == 0) {
         report("frames: stop file found");
         break;
      }
      if (pad.options_stop) {
         if (readback_checked && vk.frames_presented > WINDOW) {
            report("frames: stopped by OPTIONS");
            break;
         }
         if (!options_seen) {
            report("frames: OPTIONS pressed; stopping after the readback frame and one window");
            options_seen = true;
         }
      }
      /* The readback expects the triangle's own colours, so it waits for a
       * frame with no button held (a held button draws the triangle white). */
      const bool readback = !readback_checked && vk.frames_presented >= READBACK_FRAME && pad.held == 0;
      const VkResult result = frame(c, (float)elapsed, readback, pad.held ? 1.0f : 0.0f);
      if (result != VK_SUCCESS && result != VK_SUBOPTIMAL_KHR) {
         check(false, "frames: a frame failed");
         ok = false;
         break;
      }
      const uint64_t now = now_ns();
      const double ms = (double)(now - last) / 1e6;
      last = now;
      vk.frames_presented++;
      heartbeat++;
      poll_pad();
      if (audio.handle >= 0 && !audio.thread_started)
         audio_step(&audio_state); /* the no-thread fallback: one grain per frame */
      if (vk.frames_presented == 1) {
         stage_ms.first_present = since_ms(boot_ns);
         report("frames: first present %.1f ms after start", stage_ms.first_present);
         check(true, "frames: the first frame presented");
         persist();
         continue; /* The first interval includes the start-up; the window starts after it. */
      }
      if (ms < window_min)
         window_min = ms;
      if (ms > window_max)
         window_max = ms;
      window_sum += ms;
      window_count++;
      if (readback) {
         const uint32_t *pixels = c->readback.map;
         vk.readback_center = pixels[0];
         vk.readback_corner = pixels[1];
         /* The triangle's centroid is the screen centre, where the three vertex
          * colours (red, green, blue) interpolate to about 85 each; the corner
          * holds the clear colour (0.06, 0.06, 0.25) in B8G8R8A8: b=64 g=15 r=15. */
         vk.readback_ok = channels_near(vk.readback_center, 85, 85, 85, 16) &&
                          channels_near(vk.readback_corner, 64, 15, 15, 8);
         report("frames: readback centre 0x%08x corner 0x%08x", vk.readback_center, vk.readback_corner);
         check(vk.readback_ok, "frames: the presented frame's centre and corner pixels read back as drawn");
         readback_checked = true;
      }
      if (window_count == WINDOW) {
         vk.frame_min = window_min;
         vk.frame_avg = window_sum / window_count;
         vk.frame_max = window_max;
         report("frames: %u presented, last %u: min %.2f avg %.2f max %.2f ms", vk.frames_presented, WINDOW,
                vk.frame_min, vk.frame_avg, vk.frame_max);
         window_min = 1e9;
         window_max = 0.0;
         window_sum = 0.0;
         window_count = 0;
         persist();
      }
   }
   if (ok && !readback_checked)
      check(false, "frames: the readback frame was reached");
   if (ok)
      check(vk.frames_presented >= WINDOW, "frames: at least one full window of frames presented");
   if (pad.handle >= 0)
      check(pad.press_count > 0, "pad: at least one button press was read during the frames");
   if (audio.handle >= 0)
      check(atomic_load(&audio.tone_complete), "audio: the 1 s tone was written to the main port in full");
   cache_snapshot(&cache.exists_at_end, &cache.entries_at_end);
   report("shader cache: %s %s at the end, %u entries [%s]", SHADER_CACHE_DIR, cache.exists_at_end ? "exists" : "missing",
          cache.entries_at_end, cache.entries);
   check(cache.entries_at_end >= 1, "shader cache: RADV created entries under /download0");
   return ok;
}

/* ---------------------------------------------------------------- cleanup */

static void
destroy(struct context *c)
{
   set_stage("cleanup");
   if (c->device)
      vkDeviceWaitIdle(c->device);
   if (c->readback.buffer)
      vkDestroyBuffer(c->device, c->readback.buffer, NULL);
   if (c->readback.memory)
      vkFreeMemory(c->device, c->readback.memory, NULL);
   if (c->pipeline)
      vkDestroyPipeline(c->device, c->pipeline, NULL);
   if (c->layout)
      vkDestroyPipelineLayout(c->device, c->layout, NULL);
   if (c->vert)
      vkDestroyShaderModule(c->device, c->vert, NULL);
   if (c->frag)
      vkDestroyShaderModule(c->device, c->frag, NULL);
   for (uint32_t i = 0; i < c->image_count; i++) {
      if (c->views[i])
         vkDestroyImageView(c->device, c->views[i], NULL);
   }
   if (c->swapchain)
      vkDestroySwapchainKHR(c->device, c->swapchain, NULL);
   if (c->surface)
      vkDestroySurfaceKHR(c->instance, c->surface, NULL);
   if (c->device) {
      if (c->rendered)
         vkDestroySemaphore(c->device, c->rendered, NULL);
      if (c->acquired)
         vkDestroySemaphore(c->device, c->acquired, NULL);
      if (c->fence)
         vkDestroyFence(c->device, c->fence, NULL);
      if (c->pool)
         vkDestroyCommandPool(c->device, c->pool, NULL);
      vkDestroyDevice(c->device, NULL);
   }
   if (c->instance)
      vkDestroyInstance(c->instance, NULL);
   report("cleanup: every Vulkan object destroyed");
}

int
main(void)
{
   boot_ns = now_ns();
   const int captured = ps5_klog_capture_stderr("[za-vk:stderr] ");
   logs[0] = open_log(LIVE_LOG);
   logs[1] = open_log(KEEP_LOG);
   report("%s starts, pid %d, stderr to klog: %s", build_id, (int)getpid(), captured == 0 ? "captured" : "not captured");
   /* RADV's PS5 winsys points MESA_SHADER_CACHE_DIR at /app0 unless the title
    * set it first (radv_ps5_platform_once sets it without overwriting), and
    * /app0 is read-only to the title: r3 logged "Failed to create
    * /app0/radv-shader-cache for shader cache (Permission denied)". */
   cache.mkdir_rc = mkdir(SHADER_CACHE_DIR, 0755);
   cache.mkdir_errno = cache.mkdir_rc == 0 ? 0 : errno;
   cache.setenv_rc = setenv("MESA_SHADER_CACHE_DIR", SHADER_CACHE_DIR, 1);
   report("shader cache: mkdir %s rc=%d errno=%d; MESA_SHADER_CACHE_DIR set, rc=%d", SHADER_CACHE_DIR, cache.mkdir_rc,
          cache.mkdir_errno, cache.setenv_rc);
   const int asset = open("/app0/assets/banner.txt", O_RDONLY);
   if (asset >= 0) {
      char content[32];
      asset_ok = read(asset, content, sizeof(content)) > 0;
      close(asset);
   }
   check(asset_ok, "files: /app0/assets/banner.txt read");
   check(logs[0] != NULL, "files: the live log in /download0 opened");
   check(logs[1] != NULL, "files: the keep copy of the log in /download0 opened");
   persist();

   struct context c = {0};
   const char *failed_stage = NULL;
   if (!create_instance(&c))
      failed_stage = "instance";
   else if (!create_device(&c))
      failed_stage = "device";
   else if (!create_surface(&c))
      failed_stage = "surface";
   else if (!create_swapchain(&c))
      failed_stage = "swapchain";
   else if (!create_pipeline(&c))
      failed_stage = "pipeline";
   else {
      /* The pad and the port are set up after the GPU and torn down before it:
       * their failures are recorded, and the frames run either way. */
      setup_pad();
      setup_audio();
      if (!run_frames(&c))
         failed_stage = "frames";
   }
   persist();
   teardown_audio();
   teardown_pad();
   destroy(&c);

   static char reason[64];
   if (failed_stage) {
      snprintf(reason, sizeof(reason), "failed:%s", failed_stage);
      exit_reason = reason;
   } else {
      exit_reason = "completed";
   }
   set_stage("done");
   report("%s ends: %u passed, %u failed, exit %s", build_id, passed, failed, exit_reason);
   persist();
   for (int i = 0; i < 2; i++) {
      if (logs[i])
         fflush(logs[i]);
   }
   /* Let a collector read the live files before the sandbox goes away. */
   for (int i = 0; i < 10; i++) {
      sleep(1);
      heartbeat++;
      persist();
   }
   for (int i = 0; i < 2; i++) {
      if (logs[i])
         fclose(logs[i]);
   }
   return failed == 0 && passed > 0 ? 0 : 1;
}
