"""A-B-B-A diagnostic of a pre-existing optimization; not a new speedup claim."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib
import json
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parent
PACKAGE=ROOT.parents[1]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'

def main():
    for name,mode in [('24-state-on-a-retry1','on'),('25-state-off-a','off'),
                      ('26-state-off-b','off'),('27-state-on-b','on')]:
        run=ROOT/'runs'/name
        run.mkdir(exist_ok=False)
        save=ROOT/'saves/post-battle-20261024/save_0/main'
        lib=ROOT/'readable-build-v2/lasgame-candidate.dll'
        shutil.copytree(save.parent,run/'save/save_0')
        shutil.copytree(ROOT/'runs/07-battle/cache',run/'cache')
        def digest(p):
            with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
        (run/'method.json').write_text(json.dumps(dict(
            library_sha256=digest(lib),source_save_sha256=digest(save),
            scene='post-first-battle night alley',state_filter=mode,
            timing_window_seconds=[50,80],game_execution_verified=False,
            scope='Benefit of existing upstream filter, not an added optimization'),indent=2))
        print(json.dumps(dict(starting=name,utc=datetime.now(timezone.utc).isoformat())),flush=True)
        subprocess.run([sys.executable,str(ROOT/'run_probe.py'),'play',
            '--release',str(PACKAGE/'runtime'),'--game',str(PACKAGE/'game'),
            '--data-root',str(run),'--save',str(run/'save'),'--seconds','90',
            '--capture-every','0','--fps','60','--force-fps','--resolution','1x',
            '--input','240:A:8,420:A:8','--shot-at','900','--test-library',str(lib),
            '--state-filter',mode],check=True,stdout=subprocess.DEVNULL)
        subprocess.run([sys.executable,str(ROOT/'summarize_benchmark.py'),str(run),
                        '--start','50','--end','80'],check=True)

if __name__=='__main__': main()
