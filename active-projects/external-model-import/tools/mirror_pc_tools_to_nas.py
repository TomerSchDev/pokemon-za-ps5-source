"""Preserve prior NAS helper versions and copy the current small project sources."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
from storage_paths import data_root
source=Path(__file__).resolve().parent;target=data_root()/'tools'
history=target/('pcqa-source-history-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
changed=[];unchanged=0
for path in sorted([*source.glob('*.py'),*source.glob('*.ps1')]):
    payload=path.read_bytes();destination=target/path.name
    if destination.exists() and destination.read_bytes()==payload:unchanged+=1;continue
    if destination.exists():
        history.mkdir(exist_ok=True);(history/path.name).write_bytes(destination.read_bytes())
    temp=destination.with_name(destination.name+'.pcqa-new');temp.write_bytes(payload);temp.replace(destination)
    assert hashlib.sha256(destination.read_bytes()).digest()==hashlib.sha256(payload).digest()
    changed.append(path.name)
print(json.dumps({'verified_changed':changed,'unchanged':unchanged,'history':str(history)}))
