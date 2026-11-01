#!/usr/bin/env python3
"""Reproduce the latest JSON-fix candidate, then replace only its RTL object.

No installation or release promotion. All original link inputs remain read-only.
Run through `zw hebrew-choice-build` with a new native output directory.
"""
import argparse,hashlib,json,os,shutil,subprocess
from pathlib import Path

def sha(p):
    with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--base-sha256',required=True);p.add_argument('--tested-source-sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    native=Path('/home/tomer/ps5-za-native');base=a.base.resolve();out=a.out.resolve()
    if native not in out.parents or out.exists() or base==out or base in out.parents:raise ValueError('New isolated native output directory required')
    here=Path(__file__).resolve().parent;source=here/'src/rtl_engine.c'
    if sha(source)!=a.tested_source_sha256:raise ValueError('Source differs from the PC-tested pin')
    expected=a.base_sha256.lower();base_program=base/'program'
    if sha(base_program/'eboot.bin')!=expected:raise ValueError('Base is not the recorded console baseline')
    commands=json.loads((base/'evidence/commands.json').read_text())
    link=[c for c in commands if Path(c[0]).name=='prospero-lld']
    if len(link)!=1:raise ValueError('Expected one audited link command')
    link=link[0];rtl=[s for s in link if s.endswith('rtl_engine.o')]
    if len(rtl)!=1:raise ValueError('Expected exactly one existing RTL object')
    conversion=[c for c in commands if Path(c[0]).name=='llvm-strip' or (Path(c[0]).name=='ps5-native-tool' and (c[1]=='link' or (c[1]=='self' and '--sign' in c)))]
    if len(conversion)!=3:raise ValueError('Expected strip, conversion, and SELF signing')
    # Pin every existing file argument. Only the selected object will be replaced.
    inputs={s:sha(s) for c in [link,*conversion] for s in c[1:] if Path(s).is_file()}
    fb=native/'hebrew-rtl-ps5-20261031-r1/fribidi/fribidi-1.0.16/lib'
    runtime=here.parents[1].parent/'pokeza-recomp-ps5/runtime'
    inputs.update({str(f):sha(f) for folder in (runtime,fb) for f in folder.glob('*.h')})
    inputs[str(base/'evidence/commands.json')]=sha(base/'evidence/commands.json')
    out.mkdir();(out/'evidence').mkdir();(out/'source').mkdir()
    shutil.copy2(source,out/'source/rtl_engine.c');shutil.copy2(__file__,out/'source'/Path(__file__).name)
    history=[]
    with (out/'evidence/build.log').open('x') as log:
        def run(argv,capture=False):
            argv=list(map(str,argv));history.append(argv);print('RUN',Path(argv[0]).name,flush=True)
            r=subprocess.run(argv,stdout=subprocess.PIPE if capture else log,stderr=log,check=True)
            return r.stdout if capture else None
        def image(folder,replacement=None):
            folder.mkdir();argv=list(link);argv[argv.index('-o')+1]=str(folder/'llvm-pie.elf')
            if replacement:argv[argv.index(rtl[0])]=str(replacement)
            run(argv)
            files={str(base_program/name):str(folder/name) for name in ('llvm-pie.elf','title-stripped.elf','eboot.elf','eboot.bin')}
            for cmd in conversion:run([files.get(s,s) for s in cmd])
        image(out/'control')
        if sha(out/'control/eboot.bin')!=expected:raise ValueError('Unchanged control did not reproduce the installed baseline byte-for-byte')
        vulkan=native/'PS5_Vulkan';sdk=vulkan/'.deps/native/ps5-payload-sdk'
        obj=out/'rtl_engine.o'
        run(['/usr/bin/clang-21','-target','x86_64-sie-ps5','-fvisibility-nodllstorageclass=default','-isysroot',sdk,'-isystem',sdk/'target/include/c++/v1','-isystem',sdk/'target/include','-fno-stack-protector','-fno-plt','-femulated-tls','-fdenormal-fp-math=ieee','-DGUEST_VOLATILE','-fno-strict-aliasing','-fvisibility=hidden','-I'+str(runtime),'-march=x86-64-v3','-DZA_PS5','-O2','-std=gnu11','-include','string.h','-I'+str(fb),'-c',out/'source/rtl_engine.c','-o',obj])
        image(out/'candidate',obj)
        nm='/usr/lib/llvm-21/bin/llvm-nm'
        def symbols(path):
            data=run([nm,'--defined-only',path],True)
            return {line.split()[-1].decode() for line in data.splitlines() if line.split()}
        before=symbols(out/'control/llvm-pie.elf');after=symbols(out/'candidate/llvm-pie.elf')
        lost=sorted(before-after)
        if lost or not {'f_700264efe4','original_700264efe4','rtl_transform','fribidi_log2vis','__wrap_strtod','__wrap_localeconv'}<=after:raise ValueError('Lost base symbols or required features')
        registration=run(['python3',here.parent/'local-shader-r19/verify-registration.py',out/'control/llvm-pie.elf',out/'candidate/llvm-pie.elf'],True)
        (out/'evidence/registration.json').write_bytes(registration)
        for path,digest in inputs.items():
            if sha(path)!=digest:raise ValueError('Base input changed during build: '+path)
        if sha(source)!=a.tested_source_sha256:raise ValueError('Source changed during build')
        result=dict(base_sha256=expected,control_sha256=sha(out/'control/eboot.bin'),candidate_sha256=sha(out/'candidate/eboot.bin'),source_sha256=a.tested_source_sha256,replaced_object=rtl[0],old_object_sha256=inputs[rtl[0]],new_object_sha256=sha(obj),lost_symbols=lost,added_symbols=sorted(after-before),inputs_unchanged=True,console_access=False,hardware_tested=False)
        (out/'evidence/result.json').write_text(json.dumps(result,indent=2));(out/'evidence/inputs.json').write_text(json.dumps(inputs,indent=2));(out/'evidence/commands.json').write_text(json.dumps(history,indent=2))
        print(json.dumps(result),flush=True)
if __name__=='__main__':main()
