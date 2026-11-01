"""Prepare an isolated r19a tree; packaged source files are authoritative.
Existing trees and the immutable generated-game archive are never overwritten.
"""
import difflib, hashlib, json, shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
PORT=ROOT/'port/local-shader-r19'
BASE=Path('/home/tomer/ps5-za-native/capture-r17-20261028')
WORK=Path('/home/tomer/ps5-za-native/compiler-r19-20261028')

def main():
    assert not WORK.exists(), 'Use the prepared tree; do not overwrite a prior build.'
    WORK.mkdir()
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,
                        ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):
        shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'observer-r17/objects',WORK/'objects-r19')
    for name,target in [('title_entry-r19.c',WORK/'title_entry-r19.c'),
                        ('shaderc_cache.c',WORK/'port/shaderc-cache/shaderc_cache.c'),
                        ('shaders-r19.c',WORK/'source/runtime/nvn/vulkan/shaders.c')]:
        shutil.copy2(PORT/name,target)
    receipt={'base':str(BASE),'work':str(WORK),'base_eboot_sha256':'67284db32a427459a88f8ca0bb8f09d5e12992e8e48ae1e2ac33f29356a04139',
             'canonical_sources':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in PORT.glob('*.c')}}
    (WORK/'preparation-r19a.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))

if __name__=='__main__':main()
