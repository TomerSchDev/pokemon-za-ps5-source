"""Create an independent r22 clone from finalized r21c; never modify its inputs."""
from pathlib import Path
import difflib
import hashlib
import importlib.util
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/immutable-spans-r22-integration'
BASE=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028')
WORK=Path('/home/tomer/ps5-za-native/immutable-spans-r22-20261028')
TB1=ROOT/'port/immutable-spans-r22'

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected exactly one anchor: '+old[:100])
    return text.replace(old,new,1)

def write(p,text):p.write_text(text,encoding='utf-8',newline='\n')

def observer_files():
    source=ROOT/'port/preparation-r21c'
    for name in ('analyze.py','observer.h','preparation-observer-api.h','retire-capture.inc','test-retire.inc'):
        shutil.copy2(source/name,HERE/name)
    text=(source/'observer-r21c.c').read_text()
    text=once(text,'#include "preparation-observer-api.h"','#include "preparation-observer-api.h"\n#include "immutable-control.h"')
    text=once(text,'static bool decimal(', '#include "immutable-observer.inc"\n\nstatic bool decimal(')
    text=once(text,'    if (!strcmp(op,"preparation") && count == 4 && preparation_flags(arg) >= 0) valid = true;',
        '    if (!strcmp(op,"preparation") && count == 4 && preparation_flags(arg) >= 0) valid = true;\n    if (!strcmp(op,"immutable_spans") && count == 4 && immutable_mode(arg) >= 0) valid = true;')
    text=once(text,'    if (!strcmp(c.op,"preparation")) { ack_preparation(&c,"rejected_in_menu",0,0,0); return false; }',
        '    if (!strcmp(c.op,"preparation")) { ack_preparation(&c,"rejected_in_menu",0,0,0); return false; }\n    if (!strcmp(c.op,"immutable_spans")) { ack_immutable(&c,"rejected_in_menu",0,0,0); return false; }')
    text=once(text,'    } else if(!strcmp(c.op,"fps")) {','''    } else if(!strcmp(c.op,"immutable_spans")) {
        if (!frame || !submitted || represented) { ack_immutable(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before = plat_now_ns();
        int applied = za_immutable_spans_switch(c.arg,frame);
        const char *result = applied > 0 ? "applied" : applied == -1 ? "rejected_mode" : applied == -3 ? "drain_failed" : "receipt_mismatch";
        ack_immutable(&c,result,applied,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"fps")) {''')
    write(HERE/'observer-r22.c',text)
    client=(source/'client.py').read_text()
    client=once(client,"PREPARATION_PROFILES={'baseline':0,'plan-only':1,'lazy-only':2,'optimized':3}",
        "PREPARATION_PROFILES={'baseline':0,'plan-only':1,'lazy-only':2,'optimized':3}\nIMMUTABLE_MODES={'off':0,'on':1}")
    client=once(client,"    elif op=='retire_capture':",'''    elif op=='immutable_spans':
        if not isinstance(arg,str) or arg not in IMMUTABLE_MODES or frames is not None:
            raise ValueError('Invalid immutable spans mode or argument count')
    elif op=='retire_capture':''')
    a=client.index('def validate_preparation_ack(');b=client.index('def validate_retire_capture_ack(',a)
    validation=client[a:b].replace('validate_preparation_ack','validate_immutable_ack').replace('PREPARATION_PROFILES','IMMUTABLE_MODES').replace('expected_profile','expected_mode').replace('requested_profile','requested_mode').replace("'profile'","'mode'").replace("'preparation'","'immutable_spans'").replace('rejected_profile','rejected_mode').replace('Preparation','Immutable spans').replace('preparation','immutable spans').replace('profile','mode')
    client=client[:b]+validation+client[b:]
    client=once(client,'def collect(ftp,session,seq,out,expected_preparation=None,expected_retire_capture=None):',
        'def collect(ftp,session,seq,out,expected_preparation=None,expected_retire_capture=None,expected_immutable_spans=None):')
    client=once(client,'    validate_submission_ack(ack)','''    if ack.get('op')=='immutable_spans' or expected_immutable_spans is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_immutable_ack(ack,expected_immutable_spans)
    validate_submission_ack(ack)''')
    client=once(client,"'preparation','retire_capture','collect'","'preparation','immutable_spans','retire_capture','collect'")
    client=once(client,"        if op=='preparation':s.add_argument('value',choices=tuple(PREPARATION_PROFILES))",
        "        if op=='preparation':s.add_argument('value',choices=tuple(PREPARATION_PROFILES))\n        if op=='immutable_spans':s.add_argument('value',choices=tuple(IMMUTABLE_MODES))")
    client=once(client,"            s.add_argument('--retire-capture',help=", "            s.add_argument('--immutable-spans',choices=tuple(IMMUTABLE_MODES),help='Expected actual immutable-spans mode; required for its receipt')\n            s.add_argument('--retire-capture',help=")
    client=once(client,'args.out,args.preparation,args.retire_capture)','args.out,args.preparation,args.retire_capture,args.immutable_spans)')
    write(HERE/'client.py',client)
    tests=(source/'test-observer.c').read_text().replace('#include "observer-r21c.c"','#include "observer-r22.c"')
    tests=once(tests,'static void receipt_has(', '#include "test-immutable-observer-stubs.inc"\n\nstatic void receipt_has(')
    tests=once(tests,'#include "test-retire.inc"','#include "test-retire.inc"\n#include "test-immutable-observer.inc"')
    tests=once(tests,'    test_retirement(&serial,&i);','    test_retirement(&serial,&i);\n    test_immutable_observer(&serial,&i);')
    write(HERE/'test-observer.c',tests)
    tests=(source/'test-client.py').read_text()
    tests=once(tests,"if __name__ == '__main__': unittest.main()",(HERE/'test-immutable-client.inc').read_text()+"\nif __name__ == '__main__': unittest.main()\n")
    write(HERE/'test-client.py',tests)

def main():
    ready=json.loads((ROOT/'evidence/preparation-r21c/ready.json').read_text())
    pin=json.loads((ROOT/'evidence/preparation-r21c/preparation.json').read_text())
    for rel,h in pin['runtime_sources'].items():assert sha(BASE/'source/runtime'/rel)==h,rel
    for name,h in ready['files'].items():assert sha(ROOT/'port/preparation-r21c'/name)==h,name
    assert not WORK.exists(),'Refuse to overwrite any prior snapshot'
    assert not (EVID/'preparation.json').exists(),'Refuse to overwrite a prior manifest'
    EVID.mkdir(parents=True,exist_ok=True)
    baseline_sources={str(p.relative_to(BASE/'source/runtime')):sha(p) for p in (BASE/'source/runtime').rglob('*') if p.is_file()}
    manifest={'base':str(BASE),'work':str(WORK),'base_eboot_sha256':ready['eboot']['sha256'],
        'runtime_sources':baseline_sources,
        'runtime_objects':{str(p.relative_to(BASE/'source/build/ps5/rt')):sha(p) for p in (BASE/'source/build/ps5/rt').rglob('*.o')},
        'extra_objects':{p.name:sha(p) for p in (BASE/'objects-r21c').glob('*.o')},
        'observer_base_files':ready['files']}
    generated=EVID/'tb1-generated'
    subprocess.run([sys.executable,str(TB1/'generate.py'),'--source',str(BASE/'source'),'--out',str(generated)],check=True)
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r21c',WORK/'objects-r22')
    target=WORK/'source/runtime/nvn/vulkan'
    for name in ('exec.c','za_immutable_spans_r22.inc','za_immutable_spans_r22.h'):
        shutil.copy2(generated/'runtime/nvn/vulkan'/name,target/name)
    text=(target/'exec.c').read_text()
    text=once(text,'#include "za_preparation_boundary_r21.inc"','#include "za_preparation_boundary_r21.inc"\n#include "za_immutable_boundary_r22.inc"')
    write(target/'exec.c',text)
    for a,b in [('immutable-control.h','za_immutable_control_r22.h'),('immutable-boundary.inc','za_immutable_boundary_r22.inc')]:shutil.copy2(HERE/a,target/b)
    objects=WORK/'source/runtime/nvn/objects.c'
    text=objects.read_text()
    text=once(text,'#include "nvn.h"','#include "nvn.h"\n#include "vulkan/za_immutable_control_r22.h"')
    text=once(text,'NVN(nvnQueueSubmitCommands) {',(HERE/'immutable-wrapper.inc').read_text()+'\nNVN(nvnQueueSubmitCommands) {')
    write(objects,text)
    observer_files()
    patch=[]
    for rel in ('nvn/vulkan/exec.c','nvn/objects.c'):
        a=(BASE/'source/runtime'/rel).read_text();b=(WORK/'source/runtime'/rel).read_text()
        patch.extend(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='a/runtime/'+rel,tofile='b/runtime/'+rel))
    for name in ('za_immutable_spans_r22.inc','za_immutable_spans_r22.h','za_immutable_control_r22.h','za_immutable_boundary_r22.inc'):
        patch.extend(difflib.unified_diff([],(target/name).read_text().splitlines(True),fromfile='/dev/null',tofile='b/runtime/nvn/vulkan/'+name))
    write(EVID/'runtime-r22.patch',''.join(patch))
    manifest['candidate_runtime_sources']={str(p.relative_to(WORK/'source/runtime')):sha(p) for p in (WORK/'source/runtime').rglob('*') if p.is_file()}
    write(EVID/'preparation.json',json.dumps(manifest,indent=2)+'\n')
    print('Prepared separate r22 snapshot:',WORK)

if __name__=='__main__':main()
