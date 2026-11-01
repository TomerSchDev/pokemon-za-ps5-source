"""Retest late-box native identities independently of unsupported form entries."""
from pathlib import Path
import json,subprocess,sys
from run_pc_gallery import ROOT,QA,WORK,inspect_run
from run_pc_wide import plan

def main():
    wanted=['0957-00-0','0958-00-0','0959-00-0','0978-00-0']
    inventory=json.loads((QA/'inventory-v3.json').read_text(encoding='utf-8'))['targets']
    targets=[next(t for t in inventory if t['key']==key) for key in wanted]
    inputs,shots=plan(len(targets));spec=QA/'wide/native-identity-probe-r41.json'
    assert not spec.exists()
    spec.write_text(json.dumps({'mode':'box','targets':targets,'body_frame_pairs':shots},indent=1),encoding='utf-8')
    save=QA/'wide/native-identity-probe-r41'
    pwsh=r'C:\Users\Tomer\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
    fixture=[pwsh,'-NoProfile','-NonInteractive','-File',str(ROOT/'tools/bulkfixture/Run-MultiFixture.ps1'),
             '-SourceSave',str(ROOT/'qa/saves/multi-six/save_0/main'),'-Manifest',str(spec),'-OutputSave',str(save/'save_0/main')]
    subprocess.run(fixture,check=True,capture_output=True)
    name='pc-native-identity-probe-r41'
    cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,
         '--link-local-mods',str(WORK/'common-mods/mods'),'--seconds','230','--stop-after-shots','--watch-models',str(spec),
         '--save-src',str(save),'--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
         '--input',','.join(inputs),'--shot-at','900,1250,1650,2000,'+','.join(str(n) for pair in shots for n in pair),
         '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
    print('Starting independent native identity control probe',flush=True)
    with (QA/'wide/native-identity-probe-r41-driver.log').open('xb') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
    report=inspect_run(name,targets,shots)
    print(json.dumps([{k:t.get(k) for k in ('key','render_status','animation_status')} for t in report['targets']]),flush=True)

if __name__=='__main__':main()
