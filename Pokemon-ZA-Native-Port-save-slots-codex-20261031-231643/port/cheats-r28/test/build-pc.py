"""Recompile only audited hook units and relink an isolated diagnostic PC game DLL.
All existing generated sources, objects, game data, and runtime files are read-only.
MSYS2 clang substitutes for the cleaned-up Zig toolchain; ABI is the same Win64 C.
"""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, subprocess, sys, time
p=argparse.ArgumentParser();p.add_argument('--aot',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
a=p.parse_args();out=a.out.resolve();aot=a.aot.resolve();own=Path(__file__).resolve().parents[1]
out.mkdir(parents=True,exist_ok=True); (out/'obj').mkdir(exist_ok=True)
env=dict(os.environ);env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
cc='C:/msys64/ucrt64/bin/clang.exe';cxx='C:/msys64/ucrt64/bin/clang++.exe'
def run(args,name):
    with (out/(name+'.log')).open('wb') as f: subprocess.run(args,cwd=out,env=env,stdout=f,stderr=f,check=True)
subprocess.run([sys.executable,str(own/'prepare-items-hooks.py'),str(aot/'main'),str(aot.parent/'game/exefs/main'),str(out/'generated')],check=True)
for name in ('main_097.c','main_220.c','main_339.c'):
    target=out/'generated'/name
    text=target.read_text().replace('za_items_pump(c);','za_items_pump(c); extern void za_items_pc_batch(void*); za_items_pc_batch(c);')
    target.write_text(text)
entry=(aot/'source/tools/gamelib_entry.c').read_text()
needle='    static const GameLibTables t'
assert entry.count(needle)==1
entry=entry.replace(needle,'    extern void za_money_pc_start(void); za_money_pc_start();\n'+needle)
(out/'gamelib_entry.c').write_text(entry)
(out/'lasrecomp.def').write_text('LIBRARY lasrecomp.exe\nEXPORTS\nfnprof_hit\ng_fnprof DATA\nrt_brk\nrt_dispatch\nrt_setjmp_site\nrt_svc\nrt_ticks\nrt_udf\n')
run(['C:/msys64/ucrt64/bin/dlltool.exe','-d','lasrecomp.def','-l','lasrecomp.dll.a','-m','i386:x86-64'],'import-library')
flags=['-O1','-DGUEST_VOLATILE','-fno-strict-aliasing','-Wno-return-type','-Wno-unused-label','-fvisibility=hidden','-D_FILE_OFFSET_BITS=64','-march=x86-64-v3','-g0','-I'+str(aot/'source/runtime'),'-I'+str(own),'-I'+str(own.parent/'cheats-r27'),'-DZA_ITEMS_TRACE=1','-DGAMELIB_ID="7b03da558e0b6144"']
sources=[out/'generated'/n for n in ('main_097.c','main_333.c','main_339.c','main_220.c','main_303.c','main_315.c','main_384.c','main_1035.c')]+[out/'gamelib_entry.c',own/'test/pc_command.c',own/'test/pc_compat.c',own.parent/'cheats-r27/za_money.cpp',own/'za_items.c']
def compile(src):
    args=[cxx if src.suffix=='.cpp' else cc,*flags]
    if src.suffix=='.cpp':args+=['-std=c++20','-fno-exceptions','-fno-rtti','-DZA_MONEY_TRACE=1']
    run([*args,'-c',str(src),'-o',str(out/'obj'/(src.stem+'.o'))],src.stem)
with concurrent.futures.ThreadPoolExecutor(3) as pool:list(pool.map(compile,sources))
replacements={s.stem for s in sources};lines=[]
for line in (aot/'objects.rsp').read_text().splitlines():
    stem=Path(line.strip('"')).stem
    lines.append('"'+(out/'obj'/(stem+'.o')).as_posix()+'"' if stem in replacements else line)
for stem in ('pc_command','pc_compat','za_money','za_items'):lines.append('"'+(out/'obj'/(stem+'.o')).as_posix()+'"')
(out/'objects.rsp').write_text('\n'.join(lines)+'\n')
run([cxx,'-shared','-fuse-ld=lld','-static-libstdc++','-static-libgcc','-Wl,--stack,8388608','@'+str(out/'objects.rsp'),str(out/'lasrecomp.dll.a'),'-o',str(out/'lasgame.dll')],'link')
(out/'lasgame.dll.id').write_text('7b03da558e0b6144\n')
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
record=dict(compiler=subprocess.check_output([cc,'--version'],env=env).decode().splitlines()[0],
  note='Existing reference AOT objects retained except five audited money units and diagnostic entry/controller; MSYS2 Clang/LLD relink.',
  library_sha256=sha(out/'lasgame.dll'),flags=flags,original_sources_unchanged=True,pc_execution_verified=False)
(out/'build-result.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
