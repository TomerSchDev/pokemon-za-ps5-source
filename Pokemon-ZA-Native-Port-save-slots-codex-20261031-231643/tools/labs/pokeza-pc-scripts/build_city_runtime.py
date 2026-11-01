from pathlib import Path
import os,subprocess,shutil,hashlib,json
root=Path(__file__).resolve().parent
opt=root/'runtime-opt-r1'; source=opt/'source'; out=root/'city-runtime'
out.mkdir(exist_ok=True)
device=source/'runtime/nvn/vulkan/device.c'
original=device.read_bytes();s=original.decode()
s=s.replace('VkG g_vk;','''VkG g_vk;
// Test-only screenshot mailbox: the main-thread request is consumed by present.
static atomic_uint pokelab_capture_seq;
void pokelab_request_shot(unsigned seq) { atomic_store_explicit(&pokelab_capture_seq, seq, memory_order_release); }
''',1)
anchor='    static long shot_every = -1;'
assert s.count(anchor)==1
s=s.replace(anchor,'''    unsigned lab_seq = atomic_exchange_explicit(&pokelab_capture_seq, 0, memory_order_acquire);
    if (lab_seq) {
        char lab_path[256];
        snprintf(lab_path, sizeof lab_path, "build/live-%06u.png", lab_seq);
        renderer_save_texture_tex(b, lab_path);
    }
'''+anchor,1)
device.write_text(s,encoding='utf-8',newline='\n')
(out/'device-diagnostic.c').write_text(s,encoding='utf-8')
try:
    env=os.environ.copy();env.update(MSYSTEM='UCRT64',CHERE_INVOKING='1')
    subprocess.run(['C:/msys64/usr/bin/bash.exe','-lc',
        'export PATH="/ucrt64/bin:/usr/bin:$PATH"; make -j8 GAMELIB_ID=7b03da558e0b6144 DEPS=../SDL3-3.4.18/x86_64-w64-mingw32 build/lasrecomp.exe'],cwd=source,env=env,check=True)
    shutil.copy2(source/'build/lasrecomp.exe',out/'lasrecomp.exe')
    shutil.copy2(opt/'runtime/SDL3.dll',out/'SDL3.dll')
finally:device.write_bytes(original)
with (out/'lasrecomp.exe').open('rb') as f:h=hashlib.file_digest(f,'sha256').hexdigest()
(out/'provenance.json').write_text(json.dumps(dict(sha256=h,base='runtime optimization r1',change='atomic on-demand render-texture capture; production files untouched'),indent=2))
print(h)
