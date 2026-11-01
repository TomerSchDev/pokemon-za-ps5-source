"""Versioned source/evidence handoff; excludes game assets, binaries and SDKs."""
from pathlib import Path
import datetime, difflib, hashlib, json, sys, zipfile

root = Path(__file__).resolve().parents[2]
stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
dest = root/'deliverables'/('ZA-Native-Hardware-Update-'+stamp)
dest.mkdir()
report = Path(sys.argv[1]).resolve()
(dest/report.name).write_bytes(report.read_bytes())
entries = {}
def add(path, name):
    entries[name] = path.read_bytes()
for directory in ['port/title', 'port/sdl3-shim', 'port/vk-loader', 'port/ffmpeg-stubs', 'port/shaderc-cache',
                  'vk-probe/src', 'vk-probe/shaders']:
    for p in (root/directory).rglob('*'):
        if p.is_file() and p.suffix in {'.py','.ps1','.c','.h','.sh','.txt','.md','.mk','.S','.comp','.vert','.frag','.ttf'}:
            add(p, 'source/'+p.relative_to(root).as_posix())
for name in ['run_r3.py','vk-probe/build-vk-probe.sh','ENVIRONMENT.md']:
    p=root/name
    if p.exists(): add(p, 'source/'+name)

original = root.parent/'pokeza-recomp-ps5'
snapshot = Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\title-r1-20261027\source')
patch = []
for name in ['runtime/paths.c','runtime/platform/ps5.c','runtime/platform/ps5_compat.h',
             'runtime/kernel.c','runtime/loader.c','runtime/main.c','runtime/dispatch.c','runtime/services/time.c',
             'runtime/nvn/vulkan/device.c','tools/ps5/link-title.sh']:
    before=(original/name).read_text(encoding='utf-8').splitlines(keepends=True)
    after=(snapshot/name).read_text(encoding='utf-8').splitlines(keepends=True)
    patch.extend(difflib.unified_diff(before,after,fromfile='a/'+name,tofile='b/'+name))
entries['source/isolated-runtime-hardware.patch']=''.join(patch).encode()

for p in (root/'evidence').iterdir():
    if not p.is_file() or p.suffix not in {'.json','.txt','.log','.csv'}: continue
    if not (p.name.startswith(('title-r2','title-r3','title-r4','title-r5','title-r6','title-r7','title-r8','title-r9','title-r10','title-r11','title-r12','title-r13','title-r14',
                               'title-sdk','vk-title','vk-r6-visual','vk-r7-memdiag','vk-r8-fatvisual','vk-r9-staticpc',
                               'hardware-session'))): continue
    if 'build.log' in p.name: continue
    if 'klog' in p.name:
        # Keep our native diagnostics and crash records, omit unrelated system chatter.
        lines=p.read_text(encoding='utf-8',errors='replace').splitlines()
        selected=[s for s in lines if s.startswith(('[za-','[zarecomp]','[save-import]','[pipeline-cache]','[ps5]','#','copyin:'))]
        entries['evidence/'+p.name]='\n'.join(selected).encode()
    else: add(p,'evidence/'+p.name)
for p in sorted((root/'evidence').glob('title-r11-shaders-*/manifest.json')):
    # Hashes and validation records suffice for the handoff; generated game
    # shaders remain local and are not included in the source/evidence archive.
    add(p, 'evidence/'+p.parent.name+'/manifest.json')
for pattern in ['title-r12-save-transfer-*/*.json','title-r13-branding-update-*/manifest.json']:
    for p in sorted((root/'evidence').glob(pattern)):
        add(p,'evidence/'+p.relative_to(root/'evidence').as_posix())
for candidate in sorted((root/'artifacts').glob('title-r*-hardware')):
    for name in ['image-preservation.json','imports.txt']:
        p=candidate/'evidence'/name
        if p.exists(): add(p,'evidence/'+candidate.name+'/'+name)
entries['README.txt']=(
    'Native PS5 hardware handoff. Read the accompanying status report first.\n'
    'Probe success does not prove game playability. No game assets, generated game code,\n'
    'SDK binaries, keys or credentials are included. Runtime patch is relative to the\n'
    'existing local pokeza-recomp-ps5 checkout; port sources and build scripts are included.\n'
    'The installed full-title SHA and next debugging steps are in the report.\n'
).encode()
manifest={name: {'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()} for name,data in entries.items()}
entries['MANIFEST.json']=json.dumps(manifest,indent=2).encode()
archive=dest/'ZA-Native-Source-and-Hardware-Evidence.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name,data in entries.items(): z.writestr(name,data)
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    for name,record in manifest.items():
        assert hashlib.sha256(z.read(name)).hexdigest()==record['sha256']
print(json.dumps({'folder':str(dest),'files':len(entries),'archive_bytes':archive.stat().st_size},ensure_ascii=False))
