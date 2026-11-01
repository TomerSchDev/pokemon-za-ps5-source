#!/usr/bin/env python3
"""gen_vk_loader.py - writes vk_loader.c, the static Vulkan "loader" of the PS5 port of Pokemon Legends Z-A Recomp.

The RADV archive (libvulkan_radeon.ps5.a) exports only the ICD entry points (vk_icdGetInstanceProcAddr and friends),
while the runtime, VMA's glue and ImGui's Vulkan backend call vk* commands as plain symbols. vk_loader.c defines one
trampoline per command that jumps through a function-pointer table:
  - global commands  (vkCreateInstance, vkEnumerateInstance*)      from vk_icdGetInstanceProcAddr(NULL, name), lazily;
  - instance-level   (VkInstance / VkPhysicalDevice first argument) from vk_icdGetInstanceProcAddr(instance, name)
                      at vkCreateInstance, together with a first resolution of every device-level command (Mesa hands
                      out trampolines that dispatch through the device's table);
  - device-level     (VkDevice / VkQueue / VkCommandBuffer first argument) from vkGetDeviceProcAddr(device, name)
                      at vkCreateDevice; when that gives NULL the instance-level pointer stays (the fallback).
  - vkGetInstanceProcAddr forwards to the ICD (with the loader's own vkCreate*/vkDestroy* wrappers for those names).

Inputs:  <vulkan include dir>/vulkan/vulkan_core.h - the PS5_Mesa headers, the version the ICD was built with
         (VK_HEADER_VERSION 354 = Vulkan 1.4.354); the prototypes and their parameter names come from there, the
         section guards (#define VK_VERSION_1_x 1 / #define VK_KHR_xxx 1) say which command belongs to what.
         required-symbols.txt - the vk* names the runtime's objects import (from the compile audit's undefined.tsv);
         every one of them must be covered, or the generator fails.
Usage:   python3 -I gen_vk_loader.py --vulkan-include /path/to/PS5_Mesa/include \
             --required required-symbols.txt --out vk_loader.c [--sections VK_VERSION_1_0,VK_KHR_surface,...] [--list]
The output is deterministic (no timestamps; the header's sha256 is recorded): build-check.sh regenerates it into a
work directory and compares it with the committed file.

SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse
import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
from typing import List, Tuple

# The sections (core versions and extensions) whose commands get a trampoline. Everything the runtime calls directly
# is in core 1.0 / 1.1 or VK_KHR_surface / VK_KHR_swapchain; the rest is what it and the port's SDL3 shim reach
# through vkGetInstanceProcAddr / vkGetDeviceProcAddr (device.c VK_DEVICE_COMMANDS_12/13, exec.c external memory
# host, device fault, NV checkpoints, debug utils) and VK_KHR_display, which the shim's surface creation uses.
DEFAULT_SECTIONS = [
    "VK_VERSION_1_0", "VK_VERSION_1_1", "VK_VERSION_1_2", "VK_VERSION_1_3",
    "VK_KHR_surface", "VK_KHR_swapchain", "VK_KHR_display", "VK_KHR_display_swapchain",
    "VK_KHR_get_physical_device_properties2", "VK_KHR_get_surface_capabilities2",
    "VK_KHR_dynamic_rendering", "VK_KHR_synchronization2", "VK_KHR_timeline_semaphore",
    "VK_EXT_debug_utils", "VK_EXT_external_memory_host",
    "VK_EXT_extended_dynamic_state", "VK_EXT_extended_dynamic_state2",
    "VK_EXT_device_fault", "VK_NV_device_diagnostic_checkpoints",
]

GLOBAL_COMMANDS = {"vkCreateInstance", "vkEnumerateInstanceVersion", "vkEnumerateInstanceExtensionProperties",
                   "vkEnumerateInstanceLayerProperties", "vkGetInstanceProcAddr"}
# commands with a body of their own in the template below (table bookkeeping, layer handling, lazy global loading)
SPECIAL = {"vkGetInstanceProcAddr", "vkGetDeviceProcAddr", "vkCreateInstance", "vkDestroyInstance",
           "vkCreateDevice", "vkDestroyDevice", "vkEnumerateInstanceVersion",
           "vkEnumerateInstanceExtensionProperties", "vkEnumerateInstanceLayerProperties"}
INSTANCE_HANDLES = {"VkInstance", "VkPhysicalDevice"}
DEVICE_HANDLES = {"VkDevice", "VkQueue", "VkCommandBuffer"}

GUARD_RE = re.compile(r"^#define (VK_(?:VERSION_\d+_\d+|[A-Z0-9]+_[a-z][A-Za-z0-9_]*)) 1\s*$", re.M)
PROTO_RE = re.compile(r"VKAPI_ATTR\s+([\w\s\*]+?)\s+VKAPI_CALL\s+(vk\w+)\s*\(([^)]*)\)\s*;")
PARAM_RE = re.compile(r"^(.*?)\s*\b(\w+)\s*(\[[^\]]*\])?$", re.S)
HEADER_VERSION_RE = re.compile(r"^#define VK_HEADER_VERSION (\d+)\s*$", re.M)
TOKEN_RE = re.compile(r"\{(call|p\d+)\}")  # the placeholders of SPECIAL_BODIES (the C braces stay as they are)


@dataclass
class Proto:
    name: str
    ret: str
    params: List[Tuple[str, str, str]]  # (type, name, array suffix)
    section: str
    level: str = ""
    required: bool = False

    def decl(self) -> str:
        if not self.params:
            return f"VKAPI_ATTR {self.ret} VKAPI_CALL {self.name}(void)"
        args = ", ".join(f"{t} {n}{a}" for t, n, a in self.params)
        return f"VKAPI_ATTR {self.ret} VKAPI_CALL {self.name}({args})"

    def call(self) -> str:
        return ", ".join(n for _, n, _ in self.params)


def parse_params(text: str) -> List[Tuple[str, str, str]]:
    text = " ".join(text.split())
    if text in ("", "void"):
        return []
    out = []
    for p in text.split(","):
        m = PARAM_RE.match(p.strip())
        if not m:
            sys.exit(f"cannot parse parameter '{p}'")
        out.append((m.group(1).strip(), m.group(2), m.group(3) or ""))
    return out


def parse_header(text: str) -> List[Proto]:
    guards = [(m.start(), m.group(1)) for m in GUARD_RE.finditer(text)]
    protos = []
    for m in PROTO_RE.finditer(text):
        section = ""
        for pos, name in guards:
            if pos < m.start():
                section = name
            else:
                break
        protos.append(Proto(m.group(2), " ".join(m.group(1).split()), parse_params(m.group(3)), section))
    return protos


def level_of(p: Proto) -> str:
    if p.name in GLOBAL_COMMANDS:
        return "global"
    if p.name == "vkGetDeviceProcAddr":
        return "instance"  # obtained from the instance, as the Vulkan loader and the vk-probe do
    first = p.params[0][0].replace("const", "").strip() if p.params else ""
    if first in INSTANCE_HANDLES:
        return "instance"
    if first in DEVICE_HANDLES:
        return "device"
    sys.exit(f"{p.name}: first parameter '{first}' is no dispatchable handle and the command is not a known global one")


def read_required(path: str) -> List[str]:
    names = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.split("#", 1)[0].strip()
            if line:
                names.append(line)
    return names


PRELUDE = r"""
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <vulkan/vulkan.h>
#include <vulkan/vk_icd.h> /* vk_icdGetInstanceProcAddr, vk_icdNegotiateLoaderICDInterfaceVersion: what the RADV archive exports */

#define VKL_LOG(...) (fprintf(stderr, "[vk-loader] " __VA_ARGS__), fflush(stderr))
/* The loader/ICD interface version this file speaks: the ICD places VK_LOADER_DATA first in every dispatchable
 * object itself (v1), creates and destroys surfaces itself (v3: the port's VK_KHR_display surface), and is Vulkan
 * 1.1+ (v5). Nothing here depends on the answer; it is negotiated because v2+ ICDs expect that call first. */
#define VKL_LOADER_INTERFACE_VERSION 5u

enum vkl_level { VKL_GLOBAL = 0, VKL_INSTANCE = 1, VKL_DEVICE = 2 };
"""

STATE = r"""
static PFN_vkVoidFunction vkl_fn[VKL_COUNT]; /* the pointer each trampoline jumps through (NULL: not provided) */
static unsigned char vkl_src[VKL_COUNT];    /* 0 nothing, 1 vk_icdGetInstanceProcAddr(NULL), 2 (instance), 3 vkGetDeviceProcAddr */
static VkInstance vkl_instance;             /* the one instance created through this loader (the runtime makes one) */
static VkDevice vkl_device;                 /* the one device (idem) */
static bool vkl_global_done;

static bool vkl_trace(void)
{
    static int on = -1;
    if (on < 0) {
        const char *e = getenv("ZA_VK_LOADER_TRACE");
        on = e && *e && strcmp(e, "0") != 0;
    }
    return on > 0;
}

static const char *vkl_level_name(int level)
{
    return level == VKL_GLOBAL ? "global" : level == VKL_INSTANCE ? "instance" : "device";
}

__attribute__((noreturn)) static void vkl_missing(int id)
{
    VKL_LOG("%s was called, but the driver gave no pointer for it (%s-level; instance %p, device %p%s) - aborting\n",
            vkl_names[id].name, vkl_level_name(vkl_names[id].level), (void *)vkl_instance, (void *)vkl_device,
            vkl_instance ? "" : "; was vkCreateInstance called through this loader?");
    abort();
}

/* the global commands, from the ICD without an instance: once, on the first global call */
static void vkl_load_global(void)
{
    if (vkl_global_done) return;
    uint32_t version = VKL_LOADER_INTERFACE_VERSION;
    VkResult negotiated = vk_icdNegotiateLoaderICDInterfaceVersion(&version);
    int found = 0;
    for (int i = 0; i < VKL_COUNT; i++) {
        if (vkl_names[i].level != VKL_GLOBAL) continue;
        vkl_fn[i] = vk_icdGetInstanceProcAddr(VK_NULL_HANDLE, vkl_names[i].name);
        vkl_src[i] = vkl_fn[i] ? 1 : 0;
        if (vkl_fn[i]) found++;
        else if (vkl_trace()) VKL_LOG("global %s: not provided by the ICD\n", vkl_names[i].name);
    }
    vkl_global_done = true;
    if (vkl_trace())
        VKL_LOG("ICD interface version %u (negotiation %d); %d global entry points\n", version, (int)negotiated, found);
}

/* every instance- and device-level command from the ICD's vkGetInstanceProcAddr: the device-level ones come back
 * as Mesa's trampolines (dispatch through the device's table), replaced at vkCreateDevice where possible */
static void vkl_load_instance(VkInstance instance)
{
    int found = 0, missing = 0;
    vkl_instance = instance;
    for (int i = 0; i < VKL_COUNT; i++) {
        if (vkl_names[i].level == VKL_GLOBAL) continue;
        vkl_fn[i] = vk_icdGetInstanceProcAddr(instance, vkl_names[i].name);
        vkl_src[i] = vkl_fn[i] ? 2 : 0;
        if (vkl_fn[i]) found++;
        else {
            missing++;
            if (vkl_names[i].required || vkl_trace())
                VKL_LOG("instance %p: %s not provided (%s-level%s)\n", (void *)instance, vkl_names[i].name,
                        vkl_level_name(vkl_names[i].level), vkl_names[i].required ? "; the runtime calls it" : "");
        }
    }
    VKL_LOG("instance %p: %d of %d instance- and device-level entry points resolved, %d not provided\n",
            (void *)instance, found, found + missing, missing);
}

static void vkl_load_device(VkDevice device)
{
    PFN_vkGetDeviceProcAddr gdpa = (PFN_vkGetDeviceProcAddr)vkl_fn[VKL_vkGetDeviceProcAddr];
    int direct = 0, fallback = 0, none = 0;
    vkl_device = device;
    for (int i = 0; i < VKL_COUNT; i++) {
        if (vkl_names[i].level != VKL_DEVICE) continue;
        PFN_vkVoidFunction p = gdpa ? gdpa(device, vkl_names[i].name) : NULL;
        if (p) {
            vkl_fn[i] = p;
            vkl_src[i] = 3;
            direct++;
        } else if (vkl_fn[i]) {
            fallback++;
            if (vkl_names[i].required || vkl_trace())
                VKL_LOG("device %p: %s through the instance-level trampoline (vkGetDeviceProcAddr gave NULL%s)\n",
                        (void *)device, vkl_names[i].name, vkl_names[i].required ? "; the runtime calls it" : "");
        } else {
            none++;
            if (vkl_names[i].required || vkl_trace())
                VKL_LOG("device %p: %s not provided%s\n", (void *)device, vkl_names[i].name,
                        vkl_names[i].required ? " - the runtime calls it" : "");
        }
    }
    VKL_LOG("device %p: %d device-level entry points direct, %d through instance-level trampolines, %d not provided\n",
            (void *)device, direct, fallback, none);
}

static void vkl_forget_device(void)
{
    for (int i = 0; i < VKL_COUNT; i++) {
        if (vkl_names[i].level != VKL_DEVICE) continue;
        vkl_fn[i] = vkl_instance ? vk_icdGetInstanceProcAddr(vkl_instance, vkl_names[i].name) : NULL;
        vkl_src[i] = vkl_fn[i] ? 2 : 0;
    }
    vkl_device = VK_NULL_HANDLE;
}

static void vkl_forget_instance(void)
{
    for (int i = 0; i < VKL_COUNT; i++) {
        if (vkl_names[i].level == VKL_GLOBAL) continue;
        vkl_fn[i] = NULL;
        vkl_src[i] = 0;
    }
    vkl_instance = VK_NULL_HANDLE;
    vkl_device = VK_NULL_HANDLE;
}

/* For the port's diagnostics (not a Vulkan name): where every entry point currently points. */
void za_vk_loader_report(void)
{
    static const char *const src[] = {"not provided", "ICD global", "ICD instance / trampoline", "ICD device"};
    int count[4] = {0, 0, 0, 0};
    for (int i = 0; i < VKL_COUNT; i++) count[vkl_src[i] & 3]++;
    VKL_LOG("report: instance %p, device %p; %d entry points: %d direct from the device, %d from the instance, "
            "%d global, %d not provided\n", (void *)vkl_instance, (void *)vkl_device, (int)VKL_COUNT, count[3],
            count[2], count[1], count[0]);
    for (int i = 0; i < VKL_COUNT; i++)
        if (!vkl_fn[i] || vkl_trace())
            VKL_LOG("  %-48s %-8s %s%s\n", vkl_names[i].name, vkl_level_name(vkl_names[i].level),
                    src[vkl_src[i] & 3], vkl_names[i].required ? "  (the runtime calls it)" : "");
}

/* the loader's own wrappers that vkGetInstanceProcAddr / vkGetDeviceProcAddr hand out for their names, so that an
 * instance or device created through a pointer obtained that way is still seen by the table bookkeeping */
static PFN_vkVoidFunction vkl_own(const char *name, bool device_scope)
{
    if (!name) return NULL;
    if (!strcmp(name, "vkDestroyDevice")) return (PFN_vkVoidFunction)vkDestroyDevice;
    if (!strcmp(name, "vkGetDeviceProcAddr")) return (PFN_vkVoidFunction)vkGetDeviceProcAddr;
    if (device_scope) return NULL;
    if (!strcmp(name, "vkGetInstanceProcAddr")) return (PFN_vkVoidFunction)vkGetInstanceProcAddr;
    if (!strcmp(name, "vkCreateInstance")) return (PFN_vkVoidFunction)vkCreateInstance;
    if (!strcmp(name, "vkDestroyInstance")) return (PFN_vkVoidFunction)vkDestroyInstance;
    if (!strcmp(name, "vkCreateDevice")) return (PFN_vkVoidFunction)vkCreateDevice;
    if (!strcmp(name, "vkEnumerateInstanceVersion")) return (PFN_vkVoidFunction)vkEnumerateInstanceVersion;
    if (!strcmp(name, "vkEnumerateInstanceExtensionProperties")) return (PFN_vkVoidFunction)vkEnumerateInstanceExtensionProperties;
    if (!strcmp(name, "vkEnumerateInstanceLayerProperties")) return (PFN_vkVoidFunction)vkEnumerateInstanceLayerProperties;
    return NULL;
}
"""

# bodies of the special commands; {call} / {p0}.. are substituted with the header's parameter names (TOKEN_RE)
SPECIAL_BODIES = {
    "vkGetInstanceProcAddr": """{
    /* straight to the ICD, as the vk-probe and the SDL3 shim do; the loader's own wrappers for its own names */
    PFN_vkVoidFunction own = vkl_own({p1}, false);
    return own ? own : vk_icdGetInstanceProcAddr({p0}, {p1});
}""",
    "vkGetDeviceProcAddr": """{
    PFN_vkVoidFunction own = vkl_own({p1}, true);
    if (own) return own;
    PFN_vkGetDeviceProcAddr f = (PFN_vkGetDeviceProcAddr)vkl_fn[VKL_vkGetDeviceProcAddr];
    if (!f) {
        if (vkl_trace()) VKL_LOG("vkGetDeviceProcAddr(%p, %s) before an instance exists: NULL\\n", (void *){p0}, {p1} ? {p1} : "(null)");
        return NULL;
    }
    return f({call});
}""",
    "vkEnumerateInstanceVersion": """{
    vkl_load_global();
    PFN_vkEnumerateInstanceVersion f = (PFN_vkEnumerateInstanceVersion)vkl_fn[VKL_vkEnumerateInstanceVersion];
    if (f) return f({call});
    *{p0} = VK_API_VERSION_1_0; /* the loader's rule: a driver without the command is Vulkan 1.0 */
    return VK_SUCCESS;
}""",
    "vkEnumerateInstanceExtensionProperties": """{
    vkl_load_global();
    PFN_vkEnumerateInstanceExtensionProperties f = (PFN_vkEnumerateInstanceExtensionProperties)vkl_fn[VKL_vkEnumerateInstanceExtensionProperties];
    if (f) return f({call});
    if ({p0}) return VK_ERROR_LAYER_NOT_PRESENT; /* there are no layers here */
    *{p1} = 0;
    return VK_SUCCESS;
}""",
    "vkEnumerateInstanceLayerProperties": """{
    vkl_load_global();
    PFN_vkEnumerateInstanceLayerProperties f = (PFN_vkEnumerateInstanceLayerProperties)vkl_fn[VKL_vkEnumerateInstanceLayerProperties];
    if (f) return f({call});
    *{p0} = 0; /* no layers */
    return VK_SUCCESS;
}""",
    "vkCreateInstance": """{
    vkl_load_global();
    PFN_vkCreateInstance f = (PFN_vkCreateInstance)vkl_fn[VKL_vkCreateInstance];
    if (!f) {
        VKL_LOG("vkCreateInstance: the ICD has no vkCreateInstance\\n");
        return VK_ERROR_INCOMPATIBLE_DRIVER;
    }
    if ({p0} && {p0}->enabledLayerCount) {
        /* what the Vulkan loader answers when a requested layer is missing; the runtime then retries without
         * (device.c: "validation layer unavailable; continuing without") */
        VKL_LOG("vkCreateInstance: %u layer(s) requested (%s...), but there are no layers on the console\\n",
                {p0}->enabledLayerCount, {p0}->ppEnabledLayerNames && {p0}->ppEnabledLayerNames[0] ? {p0}->ppEnabledLayerNames[0] : "?");
        return VK_ERROR_LAYER_NOT_PRESENT;
    }
    VkResult r = f({call});
    if (r == VK_SUCCESS) vkl_load_instance(*{p2});
    else VKL_LOG("vkCreateInstance: %d\\n", (int)r);
    return r;
}""",
    "vkDestroyInstance": """{
    if ({p0} == VK_NULL_HANDLE) return;
    PFN_vkDestroyInstance f = (PFN_vkDestroyInstance)vkl_fn[VKL_vkDestroyInstance];
    if (!f) vkl_missing(VKL_vkDestroyInstance);
    f({call});
    if ({p0} == vkl_instance) vkl_forget_instance();
}""",
    "vkCreateDevice": """{
    PFN_vkCreateDevice f = (PFN_vkCreateDevice)vkl_fn[VKL_vkCreateDevice];
    if (!f) vkl_missing(VKL_vkCreateDevice);
    VkResult r = f({call});
    if (r == VK_SUCCESS) vkl_load_device(*{p3});
    else VKL_LOG("vkCreateDevice: %d\\n", (int)r);
    return r;
}""",
    "vkDestroyDevice": """{
    if ({p0} == VK_NULL_HANDLE) return;
    PFN_vkDestroyDevice f = (PFN_vkDestroyDevice)vkl_fn[VKL_vkDestroyDevice];
    if (!f) vkl_missing(VKL_vkDestroyDevice);
    f({call});
    if ({p0} == vkl_device) vkl_forget_device();
}""",
}


def generate(protos: List[Proto], header_path: str, header_version: str, header_sha: str, sections: List[str],
             required_path: str) -> str:
    out = []
    w = out.append
    w("/*\n * vk_loader.c - a static Vulkan loader for the PS5 port of Pokemon Legends Z-A Recomp: every vk* command the\n"
      " * title calls as a symbol, as a trampoline through a table filled from the RADV ICD (vk_icdGetInstanceProcAddr,\n"
      " * vkGetDeviceProcAddr). GENERATED by gen_vk_loader.py - do not edit; regenerate (README.md).\n"
      f" *   header:   vulkan/vulkan_core.h VK_HEADER_VERSION {header_version} (sha256 {header_sha})\n"
      f" *   sections: {', '.join(sections)}\n"
      f" *   required: {sum(p.required for p in protos)} names the runtime's objects import ({os.path.basename(required_path)})\n"
      f" *   commands: {len(protos)} ({sum(p.level == 'global' for p in protos)} global, "
      f"{sum(p.level == 'instance' for p in protos)} instance-level, {sum(p.level == 'device' for p in protos)} device-level)\n"
      " * SPDX-License-Identifier: GPL-3.0-or-later\n */")
    w(PRELUDE.rstrip("\n"))
    w("\nenum vkl_id {")
    table = [p for p in protos if p.name != "vkGetInstanceProcAddr"]  # (forwards to the ICD: no table slot)
    section = None
    for p in table:
        if p.section != section:
            section = p.section
            w(f"    /* {section} */")
        w(f"    VKL_{p.name},")
    w("    VKL_COUNT\n};\n")
    w("static const struct vkl_entry {\n    const char *name;\n    unsigned char level;    /* enum vkl_level */\n"
      "    unsigned char required; /* the runtime's objects import it (required-symbols.txt) */\n} vkl_names[VKL_COUNT] = {")
    for p in table:
        w(f'    [VKL_{p.name}] = {{"{p.name}", VKL_{p.level.upper()}, {1 if p.required else 0}}},')
    w("};")
    w(STATE.rstrip("\n"))
    w("\n/* ================================================================== the entry points */")
    section = None
    for p in protos:
        if p.section != section:
            section = p.section
            w(f"\n/* ---- {section} */")
        names = {f"p{i}": n for i, (_, n, _) in enumerate(p.params)}
        names["call"] = p.call()
        if p.name in SPECIAL_BODIES:
            body = TOKEN_RE.sub(lambda m: names[m.group(1)], SPECIAL_BODIES[p.name])
            w(f"\n{p.decl()}\n{body}")
            continue
        ret = "" if p.ret == "void" else "return "
        w(f"\n{p.decl()}\n{{\n    PFN_{p.name} f = (PFN_{p.name})vkl_fn[VKL_{p.name}];\n"
          f"    if (!f) vkl_missing(VKL_{p.name});\n    {ret}f({p.call()});\n}}")
    w("")
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vulkan-include", required=True, help="directory holding vulkan/vulkan_core.h (PS5_Mesa/include)")
    ap.add_argument("--required", required=True, help="required-symbols.txt")
    ap.add_argument("--out", required=True, help="the vk_loader.c to write")
    ap.add_argument("--sections", default=",".join(DEFAULT_SECTIONS), help="comma-separated header sections to cover")
    ap.add_argument("--list", action="store_true", help="print every generated command with its level")
    args = ap.parse_args()

    header_path = f"{args.vulkan_include}/vulkan/vulkan_core.h"
    with open(header_path, "rb") as f:
        raw = f.read()
    text = raw.decode("utf-8")
    m = HEADER_VERSION_RE.search(text)
    if not m:
        sys.exit(f"{header_path}: no VK_HEADER_VERSION")
    header_version = m.group(1)
    header_sha = hashlib.sha256(raw).hexdigest()
    sections = [s for s in args.sections.split(",") if s]

    protos = parse_header(text)
    by_name = {p.name: p for p in protos}
    if len(by_name) != len(protos):
        sys.exit("duplicate prototypes in the header")
    known_sections = {p.section for p in protos}
    for s in sections:
        if s not in known_sections:
            sys.exit(f"section {s} has no commands in {header_path}")
    chosen = [p for p in protos if p.section in sections]
    required = read_required(args.required)
    missing = [n for n in required if n not in by_name]
    if missing:
        sys.exit(f"required names that are no command of {header_path}: {' '.join(missing)}")
    uncovered = [n for n in required if by_name[n].section not in sections]
    if uncovered:
        sys.exit("required names outside the chosen sections (add their section with --sections): "
                 + " ".join(f"{n} ({by_name[n].section})" for n in uncovered))
    for p in chosen:
        p.level = level_of(p)
        p.required = p.name in required
    for name in SPECIAL:
        if name not in {p.name for p in chosen}:
            sys.exit(f"{name} must be among the chosen sections' commands")

    code = generate(chosen, header_path, header_version, header_sha, sections, args.required)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(code)
    if args.list:
        for p in chosen:
            print(f"{p.level:8s} {p.section:40s} {p.name}{'  (required)' if p.required else ''}")
    print(f"{args.out}: {len(chosen)} commands ({sum(p.level == 'global' for p in chosen)} global, "
          f"{sum(p.level == 'instance' for p in chosen)} instance, {sum(p.level == 'device' for p in chosen)} device), "
          f"{len(required)} required, header {header_version}", file=sys.stderr)


if __name__ == "__main__":
    main()
