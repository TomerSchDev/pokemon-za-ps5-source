"""Send a bounded command to this project's in-app test queue, and record it."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import time

p = argparse.ArgumentParser()
p.add_argument('run', type=Path)
p.add_argument('keys', help='Comma separated: A,B,X,Y,L,R,ZL,ZR,PLUS,MINUS,UP,DOWN,LEFT,RIGHT,CAMLEFT,CAMRIGHT, NONE')
p.add_argument('milliseconds', type=int)
p.add_argument('--shot', action='store_true')
a = p.parse_args()
names = 'A B X Y L R ZL ZR PLUS MINUS UP DOWN LEFT RIGHT CAMLEFT CAMRIGHT'.split()
if not 0 <= a.milliseconds <= 60000:
    p.error('duration must be 0..60000')
mask = 0
for name in a.keys.upper().split(','):
    if name == 'NONE': continue
    if name not in names: p.error('unknown key ' + name)
    mask |= 1 << names.index(name)
cmd = a.run / 'control.txt'
seq = int(cmd.read_text().split()[0]) + 1 if cmd.exists() else 1
tmp = cmd.with_suffix('.tmp')
tmp.write_text(f'{seq} {a.milliseconds} {mask} {int(a.shot)}\n')
replace_deadline = time.monotonic() + 2
while True:
    try:
        tmp.replace(cmd)
        break
    except PermissionError:
        # The Windows CRT reader briefly holds the control file without delete sharing.
        if time.monotonic() >= replace_deadline:
            raise
        time.sleep(0.02)
with (a.run / 'commands.jsonl').open('a') as f:
    f.write(json.dumps(dict(seq=seq, keys=a.keys, duration_ms=a.milliseconds,
        shot=a.shot, utc=datetime.now(timezone.utc).isoformat())) + '\n')
deadline = time.monotonic() + a.milliseconds / 1000 + 15
ack = a.run / 'lab-control.log'
while time.monotonic() < deadline:
    if ack.exists() and any(s.startswith(f'{seq} ') for s in ack.read_text().splitlines()):
        print(f'Command {seq} completed; screenshot request={a.shot}')
        break
    time.sleep(0.1)
else:
    raise SystemExit(f'Command {seq} not acknowledged; inspect the process before sending another')
