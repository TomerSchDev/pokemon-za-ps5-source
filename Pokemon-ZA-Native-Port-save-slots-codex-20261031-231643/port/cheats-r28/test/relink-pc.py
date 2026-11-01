from pathlib import Path
import sys,shutil,subprocess,os,json,hashlib
base,out=map(lambda s:Path(s).resolve(),sys.argv[1:])
own=Path(__file__).resolve().parents[1]
assert not out.exists()
shutil.copytree(base,out)
src=out/'frozen';src.mkdir()
for p in (own/'za_items.c',own/'za_items.h',own/'items.inc',own/'test/pc_command.c'):
    shutil.copy2(p,src/p.name)
record=json.loads((base/'build-result.json').read_text())
env=dict(os.environ);env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
flags=[f for f in record['flags'] if not f.startswith('-I'+str(own))]+['-I'+str(src),'-I'+str(own.parent/'cheats-r27')]
for name in ['za_items','pc_command']:
    with (out/(name+'.log')).open('wb') as f:
        subprocess.run(['C:/msys64/ucrt64/bin/clang.exe',*flags,'-c',str(src/(name+'.c')),'-o',str(out/'obj'/(name+'.o'))],env=env,stdout=f,stderr=f,check=True)
(out/'objects.rsp').write_text((base/'objects.rsp').read_text().replace(base.as_posix(),out.as_posix()))
with (out/'link.log').open('wb') as f:
    subprocess.run(['C:/msys64/ucrt64/bin/clang++.exe','-shared','-fuse-ld=lld','-static-libstdc++','-static-libgcc','-Wl,--stack,8388608','@'+str(out/'objects.rsp'),str(out/'lasrecomp.dll.a'),'-o',str(out/'lasgame.dll')],env=env,stdout=f,stderr=f,check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
record.update(library_sha256=sha(out/'lasgame.dll'),source_hashes={p.name:sha(p) for p in src.iterdir()},note='Seven audited hook units retained; item helper/controller rebuilt from frozen source')
(out/'build-result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
