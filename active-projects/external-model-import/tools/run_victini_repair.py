"""One bounded, isolated PC verification of a staged Victini repair."""
import json,subprocess,sys
from pathlib import Path
from run_pc_gallery import QA,WORK,inspect_run
stage=int(sys.argv[1]);assert stage in (1,2,3,4)
name='pc-victini-repair-20261031-r%d'%stage
here=Path(__file__).parent;root=QA/'victini-repair-20261031-r1'
subprocess.run([sys.executable,str(here/'prepare_victini_repair.py'),str(stage)],check=True)
inputs='240:A:8,420:A:8,1200:X:8,1450:A:8,1800:A:8,1950:A:8,2100:DOWN:8,2250:A:8'
cmd=[sys.executable,str(here/'run_pc_nas.py'),name,'--seconds','300','--stop-after-shots','--save-src',str(root),'--cache-src',str(WORK/'warm-cache'),'--input',inputs,'--shot-at','900,1250,1650,2000,2403,2422,2440','--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
if stage==4:cmd.append('LARECOMP_TEX_DUMP=1')
if stage==1:cmd.extend(['--bundle',str(QA/'bundles/victini-repair-20261031-r1')])
else:cmd.extend(['--link-local-mods',str(WORK/'runs/pc-victini-repair-20261031-r1/mods')])
with (root/('driver-stage%d.log'%stage)).open('xb') as out:subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT,check=True)
spec=json.loads((root/'fixture.json').read_text(encoding='utf-8'))
report=inspect_run(name,spec['targets'],spec['body_frame_pairs'])
print(json.dumps(report,ensure_ascii=True),flush=True)
