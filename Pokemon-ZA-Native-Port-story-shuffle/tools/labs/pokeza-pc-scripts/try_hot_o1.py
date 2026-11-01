"""Compile only two sampled O0 units at O1, preserving all baseline outputs."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import shutil
import sys
from build_game import GENFLAGS

root=Path(__file__).resolve().parent
rel=root/'release-v0.1.3/ZA Recomp'; work=root/'aot-v1.0.0'
out=root/'hot-o1-library'
out.mkdir(exist_ok=False)
flags=[('-mcpu=x86_64_v3' if x=='-march=x86-64-v3' else x) for x in GENFLAGS.split() if x!='-Iruntime']
flags+=['-g0','-I'+str(rel/'gamelib-src'),'-DGAMELIB_ID="7b03da558e0b6144"']
env=os.environ.copy()
env['ZIG_GLOBAL_CACHE_DIR']=env['ZIG_LOCAL_CACHE_DIR']=str(work/'zig-cache')
def compile_unit(name):
    src=work/'main'/(name+'.c')
    assert (work/'obj'/(name+'.opt')).read_text().strip()=='O0'
    with (out/(name+'.log')).open('wb') as log:
        subprocess.run([str(rel/'zig/zig.exe'),'cc',*flags,'-c',str(src),'-o',str(out/(name+'.o'))],
            env=env,stdout=log,stderr=log,check=True,timeout=600)
    print('Compiled '+name+' at O1',flush=True)
names=['main_013','main_038']
with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(compile_unit,names))
lines=(work/'objects.rsp').read_text().splitlines()
for n in names:
    old='"'+(work/'obj'/(n+'.o')).as_posix()+'"'
    assert lines.count(old)==1
    lines[lines.index(old)]='"'+(out/(n+'.o')).as_posix()+'"'
(out/'objects.rsp').write_text('\n'.join(lines))
rt=rel/'zig/rt'; dll=out/'lasgame.dll'
with (out/'link.log').open('wb') as log:
    subprocess.run([str(rel/'zig/zig.exe'),'lld-link','@'+str(rt/'link.rsp'),
        '-LIBPATH:'+str(rt),'-OUT:'+str(dll),'@'+str(out/'objects.rsp'),str(rel/'lasrecomp.dll.a')],
        env=env,cwd=work,stdout=log,stderr=log,check=True,timeout=300)
dll.with_suffix('.dll.id').write_text('7b03da558e0b6144\n')
with dll.open('rb') as f: sha=hashlib.file_digest(f,'sha256').hexdigest()
(out/'manifest.json').write_text(json.dumps(dict(utc=datetime.now(timezone.utc).isoformat(),sha256=sha,
    changes={'f_7000056b10':'O0 to O1','f_70000f42e0':'O0 to O1'},
    game_source_edits=False,baseline_unchanged=True,battle_regression_tested=False),indent=2))
run=root/'runs/11-hot-o1'; run.mkdir()
shutil.copytree(root/'saves/post-battle-20261024/save_0',run/'save/save_0')
shutil.copytree(root/'runs/07-battle/cache',run/'cache')
package=root.parents[1]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'
cmd=[sys.executable,str(root/'run_probe.py'),'play','--release',str(package/'runtime'),
     '--game',str(package/'game'),'--data-root',str(run),'--save',str(run/'save'),
     '--seconds','150','--capture-every','0','--fps','60','--force-fps',
     '--input','240:A:8,420:A:8','--shot-at','900','--test-library',str(dll)]
subprocess.run(cmd,check=True,stdout=subprocess.DEVNULL)
subprocess.run([sys.executable,str(root/'summarize_benchmark.py'),str(run),'--start','60','--end','120'],check=True)
