"""Sequential, bounded runs of the same saved scene; never overlapping games."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

root = Path(__file__).resolve().parent
package = root.parents[1] / 'deliverables/Pokemon-ZA-PC-v0.1.4-20261024'
save = root / 'saves/post-battle-20261024'
if not (save/'save_0/main').is_file():
    raise SystemExit('Verified post-battle snapshot required')
for name, fps, seconds, extra in [
    ('08-bench30', '30', 150, []),
    ('09-bench60', '60', 150, ['--force-fps']),
    ('10-profile', '60', 85, ['--force-fps', '--profile', '55,10',
                           '--test-library', str(root/'profile-library/lasgame.dll')]),
]:
    run = root/'runs'/name
    if run.exists(): raise SystemExit('Refusing to reuse run: '+str(run))
    run.mkdir()
    shutil.copytree(save/'save_0', run/'save/save_0')
    shutil.copytree(root/'runs/07-battle/cache', run/'cache')
    (run/'method.json').write_text(json.dumps(dict(
        scene='Post-first-battle save, stationary avatar after reload',
        cache_seed='07-battle/cache', measured_range_seconds=[60,120],
        input_note='Two initial confirm presses; no movement during timing',
        sampling_only=name=='10-profile'), indent=2))
    cmd=[sys.executable, str(root/'run_probe.py'), 'play', '--release', str(package/'runtime'),
         '--data-root', str(run), '--game', str(package/'game'), '--save', str(run/'save'),
         '--seconds', str(seconds), '--capture-every', '0', '--fps', fps,
         '--input', '240:A:8,420:A:8', '--shot-at', '900', *extra]
    proc=subprocess.Popen(cmd, stdout=subprocess.DEVNULL)
    record=run/'probe-play.json'
    for _ in range(100):
        if record.exists(): break
        if proc.poll() is not None: raise SystemExit('Probe failed before launch')
        time.sleep(.1)
    pid=json.loads(record.read_text())['pid']
    print(json.dumps(dict(run=name,pid=pid)), flush=True)
    telemetry=subprocess.Popen(['powershell.exe','-NoProfile','-File',str(root/'telemetry.ps1'),
        '-GamePid',str(pid),'-OutputPath',str(run/'telemetry.jsonl'),'-Samples','65'],
        stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    if proc.wait()!=0: raise SystemExit('Probe failed: '+name)
    telemetry.wait(timeout=15)
    if name!='10-profile':
        subprocess.run([sys.executable,str(root/'summarize_benchmark.py'),str(run),
                        '--start','60','--end','120'],check=True)
    else:
        subprocess.run([sys.executable,str(root/'profile_summary.py'),str(run),
            '--map',str(root/'profile-library/lasgame.map'),'--exe',str(package/'runtime/lasrecomp.exe')],check=True)
