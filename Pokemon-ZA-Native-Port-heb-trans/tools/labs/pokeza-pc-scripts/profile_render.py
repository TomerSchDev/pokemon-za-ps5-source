"""Capture renderer evidence from one isolated, copied game state."""
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
PACKAGE = ROOT.parents[1] / 'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'

def main():
    p = argparse.ArgumentParser()
    p.add_argument('name')
    p.add_argument('--resolution', choices=['1x','1.5x','2x'], default='1x')
    a = p.parse_args()
    if Path(a.name).name != a.name or a.name in ('.','..'):
        p.error('name must be one directory component')
    run = ROOT / 'runs' / a.name
    run.mkdir(exist_ok=False)
    save = ROOT / 'saves/post-battle-20261024/save_0/main'
    lib = ROOT / 'hot-o1-library/lasgame.dll'
    shutil.copytree(save.parent, run / 'save/save_0')
    shutil.copytree(ROOT / 'runs/07-battle/cache', run / 'cache')
    def digest(path):
        with path.open('rb') as f:
            return hashlib.file_digest(f, 'sha256').hexdigest()
    (run / 'method.json').write_text(json.dumps(dict(
        library_sha256=digest(lib), source_save_sha256=digest(save),
        scene='post-first-battle night alley', instrumented=True,
        gpu_timestamp_frames=[1800,2100,2400], timing_window_seconds=[60,100],
        resolution=a.resolution, game_execution_verified=False,
        limits='Nested CPU categories; GPU timestamps include gaps between commands; not a pure GPU utilization measure.'
    ), indent=2))
    subprocess.run([sys.executable, str(ROOT / 'run_probe.py'), 'play',
        '--release', str(PACKAGE / 'runtime'), '--game', str(PACKAGE / 'game'),
        '--data-root', str(run), '--save', str(run / 'save'), '--seconds','110',
        '--capture-every','0','--fps','60','--force-fps','--resolution',a.resolution,
        '--input','240:A:8,420:A:8','--shot-at','900',
        '--test-library',str(lib),'--vk-profile','--gpu-profile-at','1800,2100,2400'], check=True)

if __name__ == '__main__':
    main()
