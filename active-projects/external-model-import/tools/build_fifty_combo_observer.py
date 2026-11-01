"""WSL-only isolated observer input extension on the exact FD-fixed candidate."""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def run(args, **kw):
    subprocess.run(list(map(str,args)),check=True,**kw)
def main():
    project=Path(sys.argv[1]).resolve()
    base=Path('/home/tomer/ps5-za-native/r28b-dlc-dex-fd-20261031-r1')
    work=Path('/home/tomer/ps5-za-native/r28b-fd-qa-input-20261031-r2')
    assert not work.exists();work.mkdir()
    obs=work/'observer';shutil.copytree(project/'port/perf-r24/observer',obs)
    src=obs/'observer-r24.c';original=src.read_text()
    names=['ZL_ZR','ZL_A','ZL_B','ZL_X','ZL_Y','ZL_L','ZL_R','L_R_PLUS','L_A','L_B','L_X','L_Y']
    masks=[(1<<8)|(1<<9),257,258,260,264,320,384,(1<<6)|(1<<7)|(1<<10),65,66,68,72]
    text=original.replace('"RSTICK_RIGHT","RELEASE"};','"RSTICK_RIGHT","RELEASE",'+','.join(json.dumps(n) for n in names)+'};')
    assert text!=original
    cases='\n'.join('    case %d:*buttons |= UINT64_C(%d);break;'%(25+i,m) for i,m in enumerate(masks))
    text=text.replace('    default:break;\n    }\n    pthread_mutex_unlock(&input_lock);',cases+'\n    default:break;\n    }\n    pthread_mutex_unlock(&input_lock);')
    assert all(('case %d:'%(25+i)) in text for i in range(len(names)))
    src.write_text(text)
    test=obs/'test-observer.c';t=test.read_text()
    extra='''
    const char*combo_names[]={NAMES};
    const uint64_t combo_masks[]={MASKS};
    for(unsigned k=0;k<sizeof combo_masks/sizeof combo_masks[0];k++){
      char cmd[80];snprintf(cmd,sizeof cmd,"input %s 3",combo_names[k]);send(serial++,cmd);frame(i,0);
      for(unsigned n=0;n<5;n++){uint64_t b=UINT64_C(1)<<30;int32_t x=1,y=2,r=3,s=4;
        za_observer_input(i+n,&b,&x,&y,&r,&s);
        assert(b==((UINT64_C(1)<<30)|((n>=1&&n<=3)?combo_masks[k]:0)));
        assert(x==1&&y==2&&r==3&&s==4);
      }i+=6;
    }
    puts("12 combined inputs: exact masks, physical button preservation, axes unchanged, bounded expiration passed");
'''.replace('NAMES',','.join(json.dumps(n) for n in names)).replace('MASKS',','.join(str(m) for m in masks))
    mark='    test_slot_depth(&serial,&i);';assert t.count(mark)==1
    test.write_text(t.replace(mark,mark+extra))
    store=work/'test-store';store.mkdir();enable=work/'enable.txt'
    with (work/'host-tests.log').open('w') as log:
        run(['clang-21','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-pthread',
             '-I'+str(obs),'-DZA_OBSERVER_HOST_TEST=1','-DZA_OBSERVER_ROOT="'+str(store)+'"',
             '-DZA_OBSERVER_ENABLE="'+str(enable)+'"','-DZA_SLOT_STARTUP_PATH="'+str(work/'missing-options')+'"',
             test,'-o',work/'test-observer'],stdout=log,stderr=subprocess.STDOUT)
        run([work/'test-observer'],stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'ASAN_OPTIONS':'detect_leaks=1'})
    print('Observer legacy and combo ASan/UBSan tests passed',flush=True)
    sdk=Path('/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk')
    obj=work/'observer.o'
    run(['sh','/home/tomer/ps5-za-native/PS5_Vulkan/tooling/prospero-clang18','-std=c11','-O2','-Wall','-Wextra','-Werror','-ffunction-sections','-fdata-sections','-I'+str(obs),'-I'+str(project/'port/observer-r17'),'-c',src,'-o',obj],env={**os.environ,'PS5_PAYLOAD_SDK':str(sdk),'PS5_CLANG':'/usr/bin/clang-21'})
    extra_inputs=(base/'r28b/evidence/control-link-inputs.txt').read_text().strip()
    old=str(base/'r28b/inputs/009/observer.o');assert extra_inputs.count(old)==1
    extra_inputs=extra_inputs.replace(old,str(obj))
    runtime=[base/'source'/p for p in (base/'r28b/evidence/runtime-inputs.txt').read_text().split()]
    all_inputs=runtime+[Path(p) for p in extra_inputs.split() if p.startswith('/')]+[base/'r28b/base/liblasgame-base.a']
    pins=[{'path':str(p),'sha256':sha(p)} for p in all_inputs]
    out=work/'candidate';out.mkdir()
    env={**os.environ,'PS5_VULKAN':'/home/tomer/ps5-za-native/PS5_Vulkan','PS5_PAYLOAD_SDK':str(sdk),'PS5_CLANG':'/usr/bin/clang-21','ZA_PS5_EXTRA_INPUTS':extra_inputs}
    with (work/'link.log').open('w') as log:
        run(['bash','tools/ps5/link-title.sh',out/'llvm-pie.elf',*runtime,base/'r28b/base/liblasgame-base.a'],cwd=base/'source',env=env,stdout=log,stderr=subprocess.STDOUT)
    assert all(sha(p['path'])==p['sha256'] for p in pins)
    run(['python3',project/'port/local-shader-r19/verify-registration.py',base/'candidate/llvm-pie.elf',out/'llvm-pie.elf'])
    tool=Path('/home/tomer/ps5-za-native/PS5_Vulkan/build/host/ps5-native-tool')
    run([sdk/'bin/llvm-strip','--strip-debug','-o',out/'title-stripped.elf',out/'llvm-pie.elf'])
    with (work/'conversion.log').open('w') as log:
        run([tool,'link','--in',out/'title-stripped.elf','--out',out/'eboot.elf','--stub-dir',sdk/'target/lib','--stub',out/'ps5-link/stubs/libSceAgc.so','--stub',out/'ps5-link/stubs/libSceAgcDriver.so','--module-sdk','0x02000009','--companion-sdk','0x08050001','--file-name','eboot.elf'],stdout=log,stderr=subprocess.STDOUT)
        run([tool,'self','--sign','--in',out/'eboot.elf','--out',out/'eboot.bin','--magic','0x1D3D154F'],stdout=log,stderr=subprocess.STDOUT)
    result={'base_eboot_sha256':'4b4d1b502e217a578b687c2e5016d718b0c95c246f69c6b78d4187f9f25c10b4','eboot_sha256':sha(out/'eboot.bin'),'pie_sha256':sha(out/'llvm-pie.elf'),'observer_source_sha256':sha(src),'original_observer_source_sha256':hashlib.sha256(original.encode()).hexdigest(),'changed_link_input':'observer.o only; all FD-fixed runtime objects preserved','input_pins':pins,'host_tests':'legacy observer suite and 12 combo masks passed ASan/UBSan','combo_names':names,'combo_masks':masks,'console_installed':False}
    (work/'BUILD-INFO.json').write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k!='input_pins'}),flush=True)
if __name__=='__main__':main()
