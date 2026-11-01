"""Use the released second PC lane for a bounded material and motion regression probe."""
from pathlib import Path
import json,subprocess,sys,time
from run_pc_gallery import ROOT,QA,WORK,inspect_run
from run_pc_wide import plan
from run_pc_final_retests import PWSH,LINUX_QA

def main():
    while True:
        try:
            completed=json.loads((QA/'wide/progress-import-r2.json').read_text(encoding='utf-8'))['batches']
            if any(b['name']=='pc-wide-import-010-r2' for b in completed):break
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(10)
    exe=str(WORK/'runtime/lasrecomp.exe').replace("'","''")
    query="@(Get-Process lasrecomp -ErrorAction SilentlyContinue | Where-Object Path -eq '"+exe+"').Count"
    active=int(subprocess.run([PWSH,'-NoProfile','-NonInteractive','-Command',query],capture_output=True,text=True,check=True).stdout.strip())
    assert active<=1,'Do not start a third game process.'
    keys=['0044-00-1','0205-00-0','0442-00-0','0790-00-0','0397-00-0','0397-00-1','0821-00-0']
    inventory=json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']
    targets=[next(t for t in inventory if t['key']==key) for key in keys]
    inputs,pairs=plan(len(targets));shots=[(a,a+19,b) for a,b in pairs]
    directory=QA/'retests';directory.mkdir(exist_ok=True);name='pc-quality-retest-000-r1'
    spec=directory/(name+'.json');assert not spec.exists()
    spec.write_text(json.dumps({'mode':'box','targets':targets,'body_frame_pairs':shots,'include_sibling_asset_folders':True},indent=1),encoding='utf-8')
    save=directory/name
    fixture=[PWSH,'-NoProfile','-NonInteractive','-File',str(ROOT/'tools/bulkfixture/Run-MultiFixture.ps1'),
             '-SourceSave',str(ROOT/'qa/saves/multi-six/save_0/main'),'-Manifest',str(spec),'-OutputSave',str(save/'save_0/main')]
    subprocess.run(fixture,check=True,capture_output=True)
    bundle='material-pilot-r1'
    ssh=['ssh','-i',r'C:\Users\Tomer\.ssh\theonepiece_codex_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes',
         '-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes','TomerSch@192.168.1.234','python3',
         LINUX_QA+'/build_qa_bundle.py',LINUX_QA+'/retests/'+name+'.json',bundle]
    with (directory/'material-pilot-r1-bundle.log').open('xb') as out:subprocess.run(ssh,stdout=out,stderr=subprocess.STDOUT,check=True)
    cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,'--bundle',str(QA/'bundles'/bundle),
         '--seconds','300','--stop-after-shots','--watch-models',str(spec),'--save-src',str(save),
         '--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),'--input',','.join(inputs),
         '--shot-at','900,1250,1650,2000,'+','.join(str(n) for triple in shots for n in triple),
         '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
    print('Starting material/motion pilot on the released PC lane; seven identities',flush=True)
    with (directory/'material-pilot-r1-driver.log').open('xb') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
    report=inspect_run(name,targets,shots)
    (directory/'material-pilot-r1-results.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    print(json.dumps([{k:t.get(k) for k in ('key','render_status','animation_status','body_pixels_changed_gt10')} for t in report['targets']]),flush=True)

if __name__=='__main__':main()
