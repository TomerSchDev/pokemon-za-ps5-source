#!/usr/bin/env python3
"""Save reproducible source bundle and evidence for the completed offline build."""
import datetime
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import zipfile

root, work, dest = map(pathlib.Path, sys.argv[1:4])
app = dest / 'PPSA91761'
assert (app / 'eboot.bin').is_file()
assert (dest / 'evidence/game-manifest.json').is_file()
source = work / 'source'
evidence = dest / 'evidence'
for f in work.joinpath('evidence').glob('source-*.txt'):
    shutil.copyfile(f, evidence / f.name)
for f in root.joinpath('evidence').glob('title-r1-*'):
    if f.is_file():
        shutil.copyfile(f, evidence / f.name)
for name in ('README.txt',):
    shutil.copyfile(root / 'port/title' / name, dest / name)
shutil.copyfile(source / 'LICENSE', dest / 'LICENSE')
archive = dest / 'ZA-native-source-snapshot-r1.zip'
allowed_dirs = ('runtime', 'tools', 'third_party', 'fonts', 'docs')
with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
    files = [f for d in allowed_dirs for f in (source/d).rglob('*') if f.is_file()]
    files += [source / n for n in ('Makefile','LICENSE','ENVIRONMENT.md','.gitignore')]
    for f in sorted(files):
        if f.suffix.lower() in ('.pem', '.pfx', '.p12', '.keys') or f.name == '.env':
            raise SystemExit(f'Unexpected private credential-shaped file: {f}')
        z.write(f, 'pokeza-recomp-ps5/' + f.relative_to(source).as_posix())
    for folder in ('sdl3-shim','vk-loader','ffmpeg-stubs','shaderc-cache'):
        for f in sorted((work/'port'/folder).rglob('*')):
            if f.is_file(): z.write(f, 'port/' + f.relative_to(work/'port').as_posix())
    for f in sorted((root/'port/title').rglob('*')):
        if f.is_file(): z.write(f, 'port/title/' + f.relative_to(root/'port/title').as_posix())

def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()

objects = list((source/'build/ps5/gen').rglob('*.o'))
image = json.loads((evidence/'image-preservation.json').read_text())
info = {
    'build_id': 'za-native-title-r1-20261027', 'title_id': 'PPSA91761',
    'built_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'offline_link_convert_sign': 'passed', 'hardware_tested': False,
    'hardware_pending': ['r5', 'r5fat', 'native title first boot and gameplay'],
    'source_head': (work/'evidence/source-head.txt').read_text().strip(),
    'source_dirty_snapshot': True,
    'generated_objects': len(objects),
    'generated_object_bytes': sum(p.stat().st_size for p in objects),
    'gamelib_abi_id': (source/'build/ps5/liblasgame.a.id').read_text().strip(),
    'eboot_bytes': (app/'eboot.bin').stat().st_size,
    'eboot_sha256': sha(app/'eboot.bin'),
    'portable_shaders': len(list((app/'cache/spirv').glob('*.spv'))),
    'game_tables': image['game_tables'],
    'limitations': ['No desktop menus or text entry', 'No video decoding',
                   'Shader cache misses need offline compilation', 'Hardware memory/thread support unverified'],
}
vulkan = pathlib.Path('/home/tomer/ps5-za-native/PS5_Vulkan')
sdk = vulkan/'.deps/native/ps5-payload-sdk'
info['sdk_revision'] = (sdk/'.ps5-sdk-revision').read_text().strip()
info['clang'] = subprocess.check_output(['/usr/bin/clang-21', '--version'], text=True).splitlines()[0]
info['radv_archive_sha256'] = sha(vulkan/'.deps/native/radv-release/lib/libvulkan_radeon.ps5.a')
info['libps5platform_sha256'] = sha(sdk/'target/lib/libps5platform.a')
shutil.copyfile(vulkan/'.deps/native/radv-release/PROVENANCE.txt', evidence/'RADV-PROVENANCE.txt')
(dest/'BUILD-INFO.json').write_text(json.dumps(info, indent=2))
print(json.dumps(info, indent=2))
