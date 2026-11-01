"""Patch a private copy of the validated r16 build. Never edit shared runtime."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parents[2]
base = Path('/home/tomer/ps5-za-native/perf-r16-20261028')
work = Path('/home/tomer/ps5-za-native/capture-r17-20261028')
assert work.is_dir() and work != base
assert hashlib.sha256((base/'source/runtime/nvn/vulkan/exec.c').read_bytes()).hexdigest() == 'c946497e728a57389d5d2bed8b7904548aafe74dabb9b92b38b37109752dcee4'
manifest = {}

def patch(src, dest, changes):
    data = src.read_text()
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    for old, new in changes:
        assert data.count(old) == 1, (src, old[:100], data.count(old))
        data = data.replace(old, new, 1)
    dest.write_text(data)
    manifest[str(dest.relative_to(work))] = {'source': str(src), 'before': before, 'after':hashlib.sha256(dest.read_bytes()).hexdigest()}

patch(base/'source/runtime/nvn/vulkan/device.c', work/'source/runtime/nvn/vulkan/device.c', [
    ('typedef struct { uint32_t w, h; bool bgr;', '#include "observer.h"\nstatic VkResult za_observer_present_result = VK_NOT_READY;\nstatic bool za_observer_representing;\ntypedef struct { uint32_t w, h; bool bgr;'),
    ('VkResult r = vkQueuePresentKHR(g_vk.queue, &pi);', 'VkResult r = vkQueuePresentKHR(g_vk.queue, &pi);\n    za_observer_present_result = r;'),
    ('void backend_represent(void) {\n    if (g_last_presented)', 'void backend_represent(void) {\n    za_observer_representing = true;\n    if (g_last_presented)'),
    ('else SDL_Delay(16);\n}', 'else SDL_Delay(16);\n    za_observer_representing = false;\n}'),
    ('void backend_present(NvnTexture *t) {', 'static void za_observer_save(void *texture, const char *path) { renderer_save_texture_tex((TexBackend *)texture, path); }\nvoid backend_present(NvnTexture *t) {\n    za_observer_present_result = VK_NOT_READY;'),
    ('    g_frame_counter++;', '    g_frame_counter++;\n    extern uint64_t za_renderer_build_activity(void);\n    za_observer_frame(total_frames, have && (za_observer_present_result == VK_SUCCESS || za_observer_present_result == VK_SUBOPTIMAL_KHR),\n        za_observer_representing, za_renderer_build_activity(), b, za_observer_save);'),
])
patch(base/'source/runtime/hle/input.c', work/'source/runtime/hle/input.c', [
    ('    if (!spec) return;', '    extern bool za_observer_enabled(void);\n    if (!spec && !za_observer_enabled()) return;\n    if (!spec) spec = "";'),
    ('    script_buttons = b;', '    extern void za_observer_input(uint64_t, uint64_t *, int32_t *, int32_t *, int32_t *, int32_t *);\n    za_observer_input(frame, &b, &lx, &ly, &rx, &ry);\n    script_buttons = b;'),
])
patch(base/'title_entry-r16.c', work/'title_entry-r17.c', [
    ('    za_performance_init();', '    za_performance_init();\n    extern void za_observer_init(void);\n    za_observer_init();'),
])
patch(root/'port/randomizer/native_menu.cpp', work/'native_menu-r17.cpp', [
    ('namespace za::native {', '#include "observer.h"\nnamespace za::native {'),
    ('    while(selected.empty()) {', '    while(selected.empty()) {\n        if (page==Main && za_observer_menu(active.c_str())) {\n            if (selectRun(Root,active,error)) { selected=active; break; }\n            page=Error; dirty=true;\n        }'),
])
manifest['capture_source']={'sha256': hashlib.sha256((root/'port/observer-r17/title_png.c').read_bytes()).hexdigest(),
    'copied_from':'SMO-Native-Port/port/title/title_png.c, unchanged'}
(root/'evidence/observer-r17/patch-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
obj=work/'observer-r17/objects'
obj.mkdir(parents=True,exist_ok=True)
for src in (base/'randomizer-r16/objects').glob('*.o'): shutil.copy2(src,obj/src.name)
shutil.copy2(base/'randomizer-r16/objects/assets_hashes.h',obj/'assets_hashes.h')
print(json.dumps({'patched_files':len(manifest)-1,'work':str(work)}))
