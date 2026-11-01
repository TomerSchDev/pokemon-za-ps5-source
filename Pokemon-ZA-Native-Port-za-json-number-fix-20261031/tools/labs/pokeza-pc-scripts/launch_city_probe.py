from pathlib import Path
import argparse,os,shutil,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('name');p.add_argument('save',type=Path)
p.add_argument('--fps',choices=['30','60'],default='30');p.add_argument('--baseline',action='store_true')
p.add_argument('--seconds',type=int,default=900)
p.add_argument('--stable',action='store_true',help='Use the delivered stable runtime; test input DLL only')
a=p.parse_args();root=Path(__file__).resolve().parent;workspace=root.parents[1]
if '/' in a.name or '\\' in a.name or '..' in a.name:p.error('Simple run name required')
run=root/'runs'/a.name;run.mkdir();(run/'save/save_0').mkdir(parents=True)
shutil.copy2(a.save,run/'save/save_0/main')
shutil.copytree(root/'runs/44-city-explore/cache',run/'cache')
env=os.environ.copy();env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
release=workspace/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/runtime' if a.stable else root/'city-runtime'
cmd=[sys.executable,str(root/'run_probe.py'),'play','--release',str(release),
    '--data-root',str(run),'--game',str(workspace/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/game'),
    '--seconds',str(a.seconds),'--capture-every','0','--fps',a.fps,
    '--input','240:A:8,420:A:8','--test-library',str(root/'lab-library/lasgame-lab.dll'),
    '--control',str(run/'control.txt')]
if not a.stable:
    cmd+=['--key-reuse','off' if a.baseline else 'on',
    '--empty-submit','off' if a.baseline else 'on','--submission-slots','8' if a.baseline else '16']
if a.fps=='60':cmd+=['--force-fps']
raise SystemExit(subprocess.call(cmd,env=env))
