"""Persist PS5 pipeline caches during play; leave the upstream checkout alone."""
from pathlib import Path
import sys,shutil
root=Path(__file__).resolve().parents[2]
source=Path(sys.argv[1]);p=source/'runtime/nvn/vulkan/device.c'
s=p.read_text()
if '#include "za_pipeline_cache.h"' not in s:
    s=s.replace('VkG g_vk;','VkG g_vk;\n#ifdef ZA_PS5\n#include "za_pipeline_cache.h"\n#endif',1)
    begin=s.index('    // pipeline cache: cache/vk_pipelines.bin')
    end=s.index('\n}\n\nvoid vk_pipeline_cache_save',begin)
    old=s[begin:end]
    s=s[:begin]+'#ifdef ZA_PS5\n    za_pipeline_cache_init();\n    za_pipeline_cache_start();\n#else\n'+old+'\n#endif'+s[end:]
    begin=s.index('void vk_pipeline_cache_save(void) {')+len('void vk_pipeline_cache_save(void) {')
    end=s.index('\n}\n\n// ================================================================== swapchain',begin)
    old=s[begin:end]
    s=s[:begin]+'\n#ifdef ZA_PS5\n    za_pipeline_cache_checkpoint();\n#else'+old+'\n#endif'+s[end:]
    s=s.replace('    if (g_vk.dev) {\n        vkDeviceWaitIdle(g_vk.dev);',
                '    if (g_vk.dev) {\n#ifdef ZA_PS5\n        za_pipeline_cache_shutdown();\n#endif\n        vkDeviceWaitIdle(g_vk.dev);',1)
    p.write_text(s)
header=root/'port/title/pipeline_cache.h'
target=source/'runtime/nvn/vulkan/za_pipeline_cache.h'
if not target.exists() or target.read_bytes()!=header.read_bytes():
    shutil.copyfile(header,target)
    # Upstream Makefile does not list Vulkan-local headers as dependencies.
    p.touch()
print('PS5 periodic cache checkpoint installed in isolated device.c')
