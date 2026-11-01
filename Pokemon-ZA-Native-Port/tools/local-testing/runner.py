#!/usr/bin/env python3
"""Local, exclusive game-test queue. Invoked through zw test; no network service."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True  # imported canonical tools must not update a source checkout's caches
sys.path.insert(0, str(Path(__file__).resolve().parent))
from contracts import canonical, digest, fixture_files, keys, read_json, validate
from store import Store, atomic_json, worker_lock
from worker import recover, run_one, safe_roots, under
import windows

REPO = Path(__file__).resolve().parents[2]
CANONICAL = REPO.parent / 'Pokemon-ZA-Native-Port'


def config(path):
    c = read_json(path)
    keys(c, ('schema_version', 'canonical_checkout', 'state_root', 'results_root', 'max_game_instances'))
    if type(c['schema_version']) is not int or c['schema_version'] != 1 or type(c['max_game_instances']) is not int or c['max_game_instances'] != 1:
        raise ValueError('only schema 1 with max_game_instances=1 is supported')
    base = Path(path).resolve().parent
    for k in ('canonical_checkout', 'state_root', 'results_root'):
        c[k] = str((base / c[k]).resolve())
        if str(c[k]).startswith('\\\\'):
            raise ValueError('execution config must use local filesystem paths')
    if not (Path(c['canonical_checkout']) / 'workbench/zw.py').is_file():
        raise ValueError('canonical zw.py is missing')
    for target in ('state_root', 'results_root'):
        if under(c[target], c['canonical_checkout']) or under(c['canonical_checkout'], c[target]):
            raise ValueError('state/results must be outside canonical source tree')
    if under(c['state_root'], c['results_root']) or under(c['results_root'], c['state_root']):
        raise ValueError('state_root and results_root must be separate')
    return c


def prepare(args, cfg):
    lab = Path(cfg['canonical_checkout']).parent / 'hebrew-lab'
    exe = (args.exe or lab / 'runtime/lasrecomp.exe').resolve()
    game = (args.game or lab / 'qa-game-reference-20261030').resolve()
    module = (args.dll or game / 'lasgame.dll').resolve()
    frames = [int(s) for s in args.frames.split(',')] if args.frames else []
    cp = {'kind': 'new_game'}
    if args.save_src:
        cp = {'kind': 'copied_save', 'path': str(args.save_src.resolve()), 'files': fixture_files(args.save_src)}
    m = {'schema_version': 1, 'test_id': args.test_id, 'type': args.type, 'agent_id': args.agent,
         'build_id': args.build, 'timeout_seconds': args.timeout, 'queue_timeout_seconds': args.queue_timeout,
         'runtime': {'executable': {'path': str(exe), 'sha256': digest(exe)},
                     'game_module': {'path': str(module), 'sha256': digest(module)}, 'game_directory': str(game)},
         'input': {'script': args.input, 'checkpoint': cp},
         'execution': {'seconds': args.seconds},
         'graphics': {'width': args.width, 'height': args.height, 'hidden': args.hidden, 'fps': 30, 'pace_trace': args.pace_trace},
         'screenshots': {'frames': frames, 'every': args.every, 'mode': 'capture_only'},
         'assertions': [{'kind': 'log_contains', 'text': '[gamelib]'}] +
                       [{'kind': 'screenshot_exists', 'frame': f} for f in frames],
         'resources': {'game_instances': 1, 'gpu': 1},
         'artifacts': {'logs': True, 'screenshots': bool(frames or args.every), 'metrics': True},
         'result_directory': args.test_id}
    if args.stop_after_frame:
        m['execution']['stop_after_frame'] = args.stop_after_frame
    m = validate(m, Path.cwd())
    safe_roots(cfg, m)
    if args.out.exists():
        raise ValueError('manifest output already exists; use a new filename')
    atomic_json(args.out, m)
    return {'manifest': str(args.out.resolve()), 'manifest_sha256': hashlib.sha256(canonical(m).encode()).hexdigest(),
            'note': 'prepared only; no game launched or test passed'}


def public(row):
    return {k: row.get(k) for k in ('id', 'sequence', 'execution_id', 'phase', 'verdict', 'cancel',
                                   'queue_position', 'submitted', 'detail')}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=Path(os.environ.get('ZA_TEST_CONFIG', CANONICAL.parent / 'local-test-config.json')))
    sub = p.add_subparsers(dest='command', required=True)
    init = sub.add_parser('init', help='write shared local configuration, never a private PC resource queue')
    init.add_argument('--canonical', type=Path, default=CANONICAL)
    init.add_argument('--state-root', type=Path)
    init.add_argument('--results-root', type=Path)
    prep = sub.add_parser('prepare', help='pin a real build and write a manifest without launching it')
    prep.add_argument('--test-id', required=True)
    prep.add_argument('--agent', required=True)
    prep.add_argument('--build', required=True)
    prep.add_argument('--type', choices=('logic', 'render', 'full'), default='full')
    prep.add_argument('--exe', type=Path)
    prep.add_argument('--dll', type=Path)
    prep.add_argument('--game', type=Path)
    prep.add_argument('--save-src', type=Path)
    prep.add_argument('--input', default='')
    prep.add_argument('--frames', default='120')
    prep.add_argument('--every', type=int, default=0)
    prep.add_argument('--seconds', type=int, default=45)
    prep.add_argument('--timeout', type=int, default=60)
    prep.add_argument('--queue-timeout', type=int, default=3600)
    prep.add_argument('--stop-after-frame', type=int)
    prep.add_argument('--hidden', action='store_true')
    prep.add_argument('--pace-trace', action='store_true')
    prep.add_argument('--width', type=int, default=1280)
    prep.add_argument('--height', type=int, default=720)
    prep.add_argument('--out', type=Path, required=True)
    submit = sub.add_parser('submit')
    submit.add_argument('manifest', type=Path)
    for name in ('status', 'results', 'cancel'):
        item = sub.add_parser(name)
        item.add_argument('job_id')
    sub.add_parser('list')
    work = sub.add_parser('work', help='run a foreground worker; use Start-Process -WindowStyle Hidden for background')
    work.add_argument('--once', action='store_true', help='execute one job then exit')
    work.add_argument('--idle-exit-seconds', type=int, default=30)
    sub.add_parser('recover')
    sub.add_parser('capacity', help='read existing disk/commit limits without claiming a turn or launching a game')
    checks = sub.add_parser('selftest', help='small synthetic infrastructure checks, never a game verdict')
    checks.add_argument('--existing-queues', action='store_true', help='also run canonical queue regression tests on synthetic temp state')
    a = p.parse_args(argv)
    if a.command == 'selftest':
        code = subprocess.call([sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-s', str(Path(__file__).parent), '-p', 'test_*.py', '-v'])
        if code == 0 and a.existing_queues:
            cfg = config(a.config)
            folder = str(Path(cfg['canonical_checkout']) / 'tools/console-install-queue')
            code = subprocess.call([sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-s', folder, '-p', 'test_*.py'])
            if code == 0:
                code = subprocess.call([sys.executable, '-I', '-B', '-m', 'unittest', 'discover', '-s',
                                        str(Path(cfg['canonical_checkout']) / 'workbench'), '-p', 'test_zw.py'])
        return code
    if a.command == 'init':
        if a.config.exists():
            raise ValueError('config exists; edit it deliberately or choose a new configuration file')
        root = a.canonical.resolve()
        c = {'schema_version': 1, 'canonical_checkout': str(root),
             'state_root': str((a.state_root or root.parent / 'local-test-state').resolve()),
             'results_root': str((a.results_root or root.parent / 'local-test-results').resolve()), 'max_game_instances': 1}
        atomic_json(a.config, c)
        try:
            config(a.config)
        except Exception:
            a.config.unlink()
            raise
        print(json.dumps({'config': str(a.config.resolve()), **c}, ensure_ascii=False))
        return 0
    cfg = config(a.config)
    if a.command == 'capacity':
        from worker import load_module
        legacy = load_module('za_capacity_readonly', Path(cfg['canonical_checkout']).parent / 'hebrew-lab/tools/run_poc.py')
        values = legacy.resource_status()
        ready = os.name == 'nt' and values['disk_free_bytes'] >= 2 * 1024**3 and values.get('free_commit_bytes', 0) >= legacy.MINIMUM_FREE_COMMIT
        print(json.dumps({'ready': ready, 'measured': values, 'minimum_free_commit_bytes': legacy.MINIMUM_FREE_COMMIT,
                          'minimum_free_disk_bytes': 2 * 1024**3, 'game_launched': False}, ensure_ascii=False))
        return 0 if ready else 1
    if a.command == 'prepare':
        print(json.dumps(prepare(a, cfg), ensure_ascii=False))
        return 0
    store = Store(cfg['state_root'])
    if a.command == 'submit':
        m = validate(read_json(a.manifest), a.manifest.resolve().parent)
        safe_roots(cfg, m)
        row = store.submit(m, hashlib.sha256(canonical(m).encode()).hexdigest())
        print(json.dumps(public(row), ensure_ascii=False))
    elif a.command == 'list':
        print(json.dumps([public(store.get(j['id'])) for j in store.list()], ensure_ascii=False, indent=2))
    elif a.command == 'status':
        row = public(store.get(a.job_id))
        if row['detail'].get('ticket'):
            from worker import CanonicalPC
            board = CanonicalPC(cfg).board
            state = board.load()
            waiting = [r['ticket'] for r in state['jobs'] if r['state'] == 'queued']
            row['canonical_pc_queue_position'] = waiting.index(row['detail']['ticket']) + 1 if row['detail']['ticket'] in waiting else None
            active = state.get('active')
            row['canonical_pc_owner'] = {k: active[k] for k in ('ticket', 'agent')} if active else None
        print(json.dumps(row, ensure_ascii=False, indent=2))
    elif a.command == 'cancel':
        print(json.dumps(public(store.cancel(a.job_id)), ensure_ascii=False))
    elif a.command == 'results':
        row = store.get(a.job_id)
        print(json.dumps(row['result'] or {'job_id': a.job_id, 'phase': row['phase'], 'status': None,
                                         'reason': 'no completed verdict yet'}, ensure_ascii=False, indent=2))
        return 0 if row['verdict'] == 'PASS' else (1 if row['verdict'] else 3)
    elif a.command in ('work', 'recover'):
        if os.name != 'nt':
            raise ValueError('Windows worker required; manifest/store selftests are portable')
        with worker_lock(store.root):
            recovered = recover(cfg, store)
            for result in recovered:
                print(json.dumps({'recovered': result['job_id'], 'status': result['status']}, ensure_ascii=False), flush=True)
            if a.command == 'recover':
                return 0
            idle_since = time.monotonic()
            while True:
                job = store.claim(windows.identity())
                if job is None:
                    if a.once or time.monotonic() - idle_since >= a.idle_exit_seconds:
                        break
                    time.sleep(0.5)
                    continue
                result = run_one(cfg, store, job)
                print(json.dumps({k: result[k] for k in ('job_id', 'execution_id', 'status', 'reason', 'result_directory')}, ensure_ascii=False), flush=True)
                if store.get(job['id'])['phase'] != 'FINISHED':
                    raise RuntimeError('cleanup/recovery required; worker stops without claiming another job')
                if a.once:
                    return 0 if result['status'] == 'PASS' else 1
                idle_since = time.monotonic()
    return 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(json.dumps({'status': 'CANCELLED', 'reason': 'CLI interrupted'}), file=sys.stderr)
        sys.exit(130)
    except Exception as exc:
        print(json.dumps({'status': 'ERROR', 'error_type': type(exc).__name__, 'reason': str(exc)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
