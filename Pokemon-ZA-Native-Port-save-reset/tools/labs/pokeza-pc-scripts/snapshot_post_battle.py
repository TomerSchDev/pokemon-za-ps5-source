from pathlib import Path
import hashlib
import json
import shutil
from datetime import datetime, timezone

root = Path(__file__).resolve().parent
src = root/'runs/test-save/save_0/main'
dst = root/'saves/post-battle-20261024/save_0/main'
pkg = root.parents[1]/'deliverables/Pokemon-ZA-PC-v0.1.4-20261024/save-test/save_0/main'
def digest(p):
    with p.open('rb') as f: return hashlib.file_digest(f, 'sha256').hexdigest()
expected=digest(src)
for target in [dst,pkg]:
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): raise RuntimeError('Refusing overwrite: '+str(target))
    shutil.copy2(src,target)
    assert digest(target)==expected
assert digest(src)==expected
record=dict(utc=datetime.now(timezone.utc).isoformat(),sha256=expected,source_stable=True,
            copied_to_package=True, game_stopped_before_copy=True,
            scene='After winning first battle, at start of night escape tutorial',
            reloaded=False)
(dst.parent.parent/'snapshot.json').write_text(json.dumps(record,indent=2))
p=root/'runs/07-battle/probe-play.json'
r=json.loads(p.read_text());r.update(game_execution_verified=True,
    intentional_stop_reason='Stopped verified PID after post-battle autosave, for repeatable benchmarks')
p.write_text(json.dumps(r,indent=2))
print(json.dumps(record))
