from pathlib import Path
import sys,shutil,subprocess,json,os,hashlib
base,out=map(lambda s:Path(s).resolve(),sys.argv[1:]);assert not out.exists();shutil.copytree(base,out)
own=Path(__file__).resolve().parents[1];src=out/'frozen';src.mkdir()
for p in [own/'za_items.c',own/'za_items.h',own/'items.inc',own/'test/pc_command.c']:shutil.copy2(p,src/p.name)
p=out/'generated/main_339.c';s=p.read_text();s=s.replace('za_items_pump(c);','za_items_pump(c); extern void za_items_pc_batch(void*); za_items_pc_batch(c);');p.write_text(s)
record=json.loads((base/'build-result.json').read_text());env=dict(os.environ);env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
flags=record['flags']+['-I'+str(src)]
for name,p in [('main_339',p),('pc_command',src/'pc_command.c')]:
 with (out/(name+'.log')).open('wb') as f:subprocess.run(['C:/msys64/ucrt64/bin/clang.exe',*flags,'-c',str(p),'-o',str(out/'obj'/(name+'.o'))],env=env,stdout=f,stderr=f,check=True)
(out/'objects.rsp').write_text((base/'objects.rsp').read_text().replace(base.as_posix(),out.as_posix()))
with (out/'link.log').open('wb') as f:subprocess.run(['C:/msys64/ucrt64/bin/clang++.exe','-shared','-fuse-ld=lld','-static-libstdc++','-static-libgcc','-Wl,--stack,8388608','@'+str(out/'objects.rsp'),str(out/'lasrecomp.dll.a'),'-o',str(out/'lasgame.dll')],env=env,stdout=f,stderr=f,check=True)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
record.update(library_sha256=sha(out/'lasgame.dll'),diagnostic_only='Batch invokes the public ITEMS request API and production pump on the original bag callback; not included in PS5',source_hashes={p.name:sha(p) for p in src.iterdir()})
(out/'build-result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
