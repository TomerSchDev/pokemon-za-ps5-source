"""Reuse the second GPU slot after the native queue, never start a third game."""
from pathlib import Path
import json,subprocess,sys,time
from run_pc_gallery import QA

def main():
    pwsh=r'C:\Users\Tomer\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe'
    progress=QA/'wide/progress-native-r1.json'
    while True:
        state=json.loads(progress.read_text(encoding='utf-8'))
        if len(state['batches'])==8:
            assert all(x['driver_exit']==0 for x in state['batches'])
            break
        time.sleep(20)
    while not (QA.parent/'runs/pc-native-identity-probe-r41/gallery-results.json').exists():
        time.sleep(10)
    for start,end in ((1,2),(8,10)):
        print('Second PC lane: imported batches %d..%d, revision 2'%(start,end),flush=True)
        cmd=[sys.executable,str(Path(__file__).with_name('run_pc_wide.py')),'--kind','import',
             '--start',str(start),'--end',str(end),'--revision','2','--pwsh',pwsh]
        result=subprocess.run(cmd)
        if result.returncode:raise RuntimeError('Second lane stopped; evidence retained for diagnosis')
    print('Second PC lane complete',flush=True)

if __name__=='__main__':main()
