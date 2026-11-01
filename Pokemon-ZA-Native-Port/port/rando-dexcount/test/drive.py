"""Send one command to the diagnostic controller of a running PC proof (test/pc_control.c) and wait for it.

usage: drive.py RUN_DIR STEP [STEP ...]
STEP = <ms>:<KEY+KEY...>[:shot]   e.g. 3000:UP:shot  200:A  800:ZL+ZR  1500::shot (wait, then a screenshot)
KEYS: A B X Y L R ZL ZR PLUS MINUS (buttons), UP DOWN LEFT RIGHT (left stick), CUP CDOWN CLEFT CRIGHT (camera),
      DL DU DR DD (d-pad), LS RS (stick clicks)
Writes RUN_DIR/control.txt atomically, waits for 'done seq=N' in RUN_DIR/control.log, prints the new screenshots.
"""
from pathlib import Path
import os, re, sys, time

BITS = dict(A=0, B=1, X=2, Y=3, L=4, R=5, ZL=6, ZR=7, PLUS=8, MINUS=9, UP=10, DOWN=11, LEFT=12, RIGHT=13,
            CUP=14, CDOWN=15, CLEFT=16, CRIGHT=17, DL=18, DU=19, DR=20, DD=21, LS=22, RS=23)


def main():
    run = Path(sys.argv[1])
    steps = []
    for s in sys.argv[2:]:
        parts = s.split(':')
        ms = int(parts[0])
        mask = 0
        for k in filter(None, (parts[1] if len(parts) > 1 else '').split('+')):
            mask |= 1 << BITS[k]
        steps.append('%d %d %d' % (ms, mask, 1 if len(parts) > 2 and parts[2] == 'shot' else 0))
    log = run / 'control.log'
    text = log.read_text() if log.exists() else ''
    seqs = [int(x) for x in re.findall(r'done seq=(\d+)', text)]
    seq = (max(seqs) if seqs else 0) + 1
    before = set(p.name for p in (run / 'build').glob('c*.png'))
    tmp = run / 'control.tmp'
    tmp.write_text('%d\n%s\n' % (seq, '\n'.join(steps)))
    os.replace(tmp, run / 'control.txt')
    budget = sum(int(s.split()[0]) for s in steps) / 1000 + 3 + 0.5 * len(steps)
    t0 = time.monotonic()
    while time.monotonic() - t0 < budget + 20:
        if log.exists() and ('done seq=%d ' % seq) in log.read_text():
            break
        time.sleep(0.2)
    else:
        print('TIMEOUT waiting for seq', seq)
        return 1
    done_at = time.time()
    # periodic window shots (run-pc.py --every): the first one written after the command finished
    latest = None
    while time.time() - done_at < 6:
        frames = sorted((run / 'build').glob('frame_*.png'), key=lambda q: q.stat().st_mtime)
        fresh = [q for q in frames if q.stat().st_mtime > done_at + 0.3 and q.stat().st_size > 0]
        if fresh:
            time.sleep(0.4)
            latest = fresh[0]
            break
        time.sleep(0.2)
    frames = sorted((run / 'build').glob('frame_*.png'), key=lambda q: q.stat().st_mtime)
    for q in frames[:-8]:
        if latest is None or q != latest:
            q.unlink()  # (own run folder only; evidence frames are copied to build/keep first)
    print('seq', seq, 'done', latest if latest else '(no new frame)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
