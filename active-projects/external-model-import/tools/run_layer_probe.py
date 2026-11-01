"""Run the bounded layer-channel probe once the native GPU slot is released."""
from pathlib import Path
import json,subprocess,sys,time
from run_pc_gallery import QA,WORK,inspect_run

def main():
    while len(json.loads((QA/'wide/progress-native-r1.json').read_text(encoding='utf-8'))['batches'])<8:
        time.sleep(10)
    spec=QA/'wide/layer-registry-probe-r39.json'
    data=json.loads(spec.read_text(encoding='utf-8'))
    name='pc-layer-registry-probe-r39'
    cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,
         '--link-local-mods',str(WORK/'layer-registry-probe/mods'),
         '--seconds','230','--stop-after-shots','--watch-models',str(spec),
         '--save-src',str(QA/'wide/layer-registry-probe-r39'),
         '--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
         '--input',','.join(data['inputs']),
         '--shot-at','900,1250,1650,2000,'+','.join(str(n) for pair in data['body_frame_pairs'] for n in pair),
         '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
    print('Starting isolated bone-channel probe in the released PC slot',flush=True)
    with (QA/'wide/layer-registry-probe-r39-driver.log').open('xb') as out:
        subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
    result=inspect_run(name,data['targets'],data['body_frame_pairs'])
    print(json.dumps([{k:t.get(k) for k in ('key','render_status','animation_status','body_pixels_changed_gt10')} for t in result['targets']]),flush=True)

if __name__=='__main__':main()
