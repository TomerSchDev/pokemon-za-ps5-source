"""Guard the controlled start6 fixture; no save reading or writing here.

This does not grant natural progression or chapter completion. The original party,
trainers and chapter5/6 state must remain intact. A deliberately unsafe operation
must fail before an output file is created.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import tempfile

BASE_OPS_SHA256 = 'c39bebd39fb24eef06ffba6b2b04e4077ede3f428d5e5b92aae4eed8ac84e522'


def validate(operations):
    for op in operations:
        kind, rest = op.split(':', 1)
        name, value = rest.split('=', 1)
        if kind not in ('flag', 'sysflag', 'work', 'quest'):
            raise ValueError('forbidden fixture mutation kind: ' + kind)
        if re.search(r'(?:Ev_m|MAINQUEST_|WORK_M)0?[5-9](?:_|$)', name) or \
           re.search(r'(?:Ev_m|MAINQUEST_|WORK_M)10(?:_|$)', name):
            raise ValueError('future chapter mutation blocked: ' + name)
        if kind == 'work' and name == 'SYS_WORK_PHASE' and value != '51000':
            raise ValueError('not the controlled start6 phase')
    if operations.count('work:SYS_WORK_PHASE=51000') != 1:
        raise ValueError('exactly one controlled phase assignment required')


def write_new(operations, out):
    validate(operations)  # before any filesystem mutation
    if any((p / '.git').exists() for p in (out.resolve(), *out.resolve().parents)):
        raise ValueError('fixture operations must stay outside Git')
    with out.open('x', encoding='utf-8') as stream: stream.write(' '.join(operations) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--base-ops', type=Path)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    if args.selftest:
        bad = ('quest:SYS_WORK_MAINQUEST_05_01=255', 'quest:SYS_WORK_MAINQUEST_06_01=255',
               'flag:flag_Ev_m06_1010=1', 'work:SYS_WORK_M6_MegaMate_Break=27', 'level:all=50')
        with tempfile.TemporaryDirectory() as temp:
            for i, mutation in enumerate(bad):
                target = Path(temp) / (str(i) + '.txt')
                try: write_new(['work:SYS_WORK_PHASE=51000', mutation], target)
                except ValueError: pass
                else: raise AssertionError('unsafe fixture accepted: ' + mutation)
                if target.exists(): raise AssertionError('unsafe output created')
        validate(['flag:flag_Ev_m04_5050=1', 'quest:SYS_WORK_MAINQUEST_04_05=255', 'work:SYS_WORK_PHASE=51000'])
        print(json.dumps({'negative_controls_rejected_before_write': len(bad), 'valid_control_passed': True}))
        return
    if not args.base_ops or not args.out: ap.error('--base-ops and --out required')
    raw = args.base_ops.read_bytes()
    if hashlib.sha256(raw).hexdigest() != BASE_OPS_SHA256: raise ValueError('unreviewed prerequisite operation source')
    operations = [op for op in raw.decode('utf-8-sig').split() if not op.startswith('work:SYS_WORK_PHASE=')]
    operations += ['flag:flag_Ev_m04_5050=1', 'flag:flag_Ev_m04_5060=1', 'work:SYS_WORK_PHASE=51000']
    write_new(operations, args.out)
    print(json.dumps({'operations': len(operations), 'controlled_starting_state': True,
                      'natural_progression': False, 'no_future_chapter_mutations': True}))


if __name__ == '__main__': main()
