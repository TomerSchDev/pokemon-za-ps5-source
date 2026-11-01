#!/usr/bin/env python3
"""zw — the Z-A workbench: one front door to the project's existing tools.

zw never reimplements a tool; it forwards to the script that owns the job, so each tool keeps
its own checks. Console-touching verbs refuse unless --console-ok (or ZW_CONSOLE_OK=1) is given.
Run `zw` for the verb list and `zw card <name>` for the one-page guide an agent needs.
"""
from __future__ import annotations

import ftplib
import importlib.util
import os
from pathlib import Path
import re
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LAB = REPO.parent                                   # PS5-13.60
CARDS = HERE / 'cards'
STATE = Path(os.environ.get('ZW_STATE', LAB / 'zw-state'))
HOST = '192.168.1.135'
PY = [sys.executable, '-I']
OBSERVER = REPO / 'port' / 'perf-r24' / 'observer'
# The handoff's Codex\...\update-2.0.2-20261025\game folder no longer exists; this is the local read-only copy.
PC_GAME = Path(os.environ.get('ZA_PC_GAME_ROOT', LAB / 'hebrew-lab' / 'qa-game-reference-20261030'))
PC_RUNS = LAB / 'hebrew-lab' / 'runs'
FPS_LINE = re.compile(r'\[vk\] t=\S+ frame (\d+) ([\d.]+) fps max ([\d.]+)ms')

# verb -> (target, console?, one-line help). Targets are argv prefixes; {repo}/{lab} expand.
FORWARD = {
    'atlas':  (PY + ['{repo}/tools/za-atlas/P6/za_atlas.py'], False, 'code atlas: find|str|fn|who-calls|callees|path|class|annotate|stats'),
    'crash':  (PY + ['{repo}/tools/za-atlas/P4/crash.py'], False, 'symbolize a klog crash: LOG --elf llvm-pie.elf'),
    'za':     (['cmd', '/c', '{repo}/tools/za/za.cmd'], False, 'builds: profiles|doctor|verify|reproduce|check-proof|build r29-ui'),
    'queue':  (PY + ['{repo}/tools/console-install-queue/console_queue.py'], False, 'shared console install queue (local only)'),
    'obs':    (PY + ['{repo}/port/perf-r24/observer/client.py'], True, 'raw observer client: status|snapshot|measure|fps|input|collect|...'),
    'fifty-ui': ([sys.executable, '{lab}/species-lab/import-all-20261030/tools/console_fifty_ui.py'], True, 'guarded fifty-species QA input sequence and verified screenshots'),
    'hebrew': (PY + ['{lab}/hebrew-lab/tools/{script}.py'], False, 'run a hebrew-lab tool: zw hebrew <script> [args]'),
    'species': (PY + ['{lab}/species-lab/pilot/tools/{script}.py'], False, 'run a species pilot tool: zw species <script> [args]'),
    'species-all': ([sys.executable, '{lab}/species-lab/import-all-20261030/tools/{script}.py'], False, 'existing imported-species lab preparation and PC evidence tools'),
    'fifty-fixture': ([os.environ.get('ZA_FIXTURE_PWSH', 'pwsh'), '-NoProfile', '-File', '{lab}/species-lab/import-all-20261030/tools/Run-ConsoleFiftyFixture.ps1'], False, 'prepare isolated fifty-species test save; no console access'),
    'species-save': (['pwsh', '-NoProfile', '-File', '{lab}/species-lab/import-all-20261030/tools/{script}.ps1'], False, 'local copied-save inspection and fixture tools'),
    'unity': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity/Tools/{script}.py'], False, 'existing local Unity tools: zw unity <script> [args]'),
    'unity-visuals': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity/Tools/visuals/{script}.py'], False, 'existing Unity visual exporters/audits: zw unity-visuals <script> [args]'),
    'unity-content': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity/Tools/content/{script}.py'], False, 'existing Unity catalog tools: zw unity-content <script> [args]'),
    'unity-build': (['pwsh', '-NoProfile', '-File', 'C:/Users/Tomer/Documents/ChatGPT/Pokemon-ZA-Unity/Tools/Build.ps1'], False, 'Windows Unity prototype build into an explicitly new output folder'),
    'shader-link': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity-Work/CodeAudit/ShaderResearch/link_capture.py'], False, 'read-only capture/BNSH/NSO metadata correlation; existing Unity Work environment, Work outputs only'),
    'surface-full': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity-Work/WorldAudit/CharacterMaterials-v013-20261031/full_surface_profiles.py'], False, 'full native character material data; Work outputs only'),
    'geometry-verify': (['{lab}/../Pokemon-ZA-Unity-Work/venv/Scripts/python.exe', '{lab}/../Pokemon-ZA-Unity-Work/GeometryAudit/verify_staged_export.py'], False, 'existing Work geometry verifier; verify-only inputs/outputs'),
}
# Task kits: the smallest set of cards an agent needs for one kind of job (rules always first).
KITS = {
    'hebrew':    ['mods', 'hebrew', 'pc-run'],
    'species':   ['main', 'mods', 'species', 'pc-run', 'atlas'],
    'fps':       ['fps', 'console-observe', 'pc-run', 'build', 'atlas'],
    'cheat':     ['main', 'randomizer', 'atlas', 'build', 'pc-run'],
    'randomizer': ['main', 'randomizer', 'atlas', 'build', 'pc-run'],
    'build':     ['main', 'build', 'console-install'],
    'merge':     ['main', 'build', 'console-install'],
    'install':   ['console-install', 'console-observe', 'crash'],
    'crash':     ['crash', 'atlas', 'console-observe'],
    'console-qa': ['console-observe', 'fps', 'crash'],
}
COMPOSITE = {
    'brief':  'paste-ready agent brief: rules + the cards one task needs (zw brief <task>; no task = list)',
    'card':   'print a task card: zw card <name>   (no name = list)',
    'doctor': 'check that tools, data and paths exist (add --console-ok to probe console ports)',
    'pc':     'PC build: zw pc run NAME --seconds N [--fps 30|60] [--shot-at F,..] [--input ..] [--mods DIR] | pc fps RUN | pc shots RUN',
    'shot':   'console screenshot: zw shot --out DIR --console-ok',
    'fps':    'zw fps measure SECONDS --out DIR | fps set 0|1 (all --console-ok) | fps analyze CSV',
    'input':  'console button press: zw input BUTTON FRAMES --console-ok (A B X Y L R ZL ZR PLUS MINUS UP DOWN ...)',
    'klog':   'capture console klog: zw klog --out FILE [--seconds N] --console-ok',
}


class ZwError(Exception):
    pass


def expand(part, script=''):
    return part.replace('{repo}', str(REPO)).replace('{lab}', str(LAB)).replace('{script}', script)


def take_flag(args, flag):
    if flag in args:
        args.remove(flag)
        return True
    return False


def take_opt(args, name, default=None):
    if name in args:
        i = args.index(name)
        if i + 1 >= len(args):
            raise ZwError(name + ' needs a value')
        value = args[i + 1]
        del args[i:i + 2]
        return value
    return default


def require_console(args):
    if not (take_flag(args, '--console-ok') or os.environ.get('ZW_CONSOLE_OK') == '1'):
        raise ZwError('This verb contacts the console. Only in a session Tomer coordinated, game state known; '
                      're-run with --console-ok. See workbench/cards/rules.md.')


def usage():
    print(__doc__.strip().splitlines()[0] + '\n')
    print('Forwarding verbs:')
    for verb, (_, console, text) in FORWARD.items():
        print(f'  {verb:8} {"[console] " if console else ""}{text}')
    print('Workbench verbs:')
    for verb, text in COMPOSITE.items():
        print(f'  {verb:8} {text}')
    print('\nCards: ' + ', '.join(sorted(p.stem for p in CARDS.glob('*.md'))))
    return 0


def forward(verb, args):
    target, console, _ = FORWARD[verb]
    if console:
        require_console(args)
    script = ''
    if '{script}' in ''.join(target):
        if not args or not re.fullmatch(r'[A-Za-z0-9_\-]+', args[0]):
            raise ZwError(f'usage: zw {verb} <script> [args]')
        script = args.pop(0)
    argv = [expand(p, script) for p in target] + args
    cwd = None
    if verb in ('hebrew', 'species'):
        if not Path(argv[2]).is_file():
            raise ZwError('No such tool: ' + argv[2])
        cwd = Path(argv[2]).parent.parent       # these tools resolve paths from their lab folder
    elif verb in ('unity', 'unity-visuals', 'unity-content', 'unity-build'):
        cwd = LAB.parent / 'Pokemon-ZA-Unity'
    return subprocess.call(argv, cwd=cwd)


def card(args):
    if not args:
        for p in sorted(CARDS.glob('*.md')):
            print(f'{p.stem:16} {p.read_text(encoding="utf-8").splitlines()[0].lstrip("# ")}')
        return 0
    path = CARDS / (args[0] + '.md')
    if not path.is_file():
        raise ZwError('No card ' + args[0] + '; run `zw card` for the list')
    sys.stdout.write(path.read_text(encoding='utf-8'))
    return 0


def brief(args):
    if not args or args[0] not in KITS:
        for task, cards in KITS.items():
            print(f'{task:11} rules + {" + ".join(cards)}')
        return 0 if not args else 2
    print('You work on the Pokémon Legends: Z-A native PS5 project. Tools: run `zw <verb>` from the repo root '
          f'({REPO}); `zw` lists verbs, `zw card <name>` prints any other card. Read only what you need.\n')
    for name in ['rules'] + KITS[args[0]]:
        path = CARDS / (name + '.md')
        if path.is_file():
            print(path.read_text(encoding='utf-8').rstrip() + '\n\n---\n')
    return 0


def doctor(args):
    probe = take_flag(args, '--console-ok') or os.environ.get('ZW_CONSOLE_OK') == '1'
    checks = [
        ('atlas db', LAB / 'za-atlas-data' / 'atlas.sqlite'),
        ('za tool', REPO / 'tools' / 'za' / 'za.py'),
        ('install queue state', LAB / 'console-install-state'),
        ('observer client', OBSERVER / 'client.py'),
        ('hebrew-lab tools', LAB / 'hebrew-lab' / 'tools'),
        ('PC runtime exe', LAB / 'hebrew-lab' / 'runtime' / 'lasrecomp.exe'),
        ('PC game (read-only)', PC_GAME),
        ('species pilot', LAB / 'species-lab' / 'pilot' / 'tools'),
    ]
    bad = 0
    for name, path in checks:
        ok = path.exists()
        bad += not ok
        print(f'  {"ok " if ok else "MISSING"}  {name:22} {path}')
    wsl = subprocess.run(['wsl', '-d', 'Ubuntu', '--', 'test', '-d', '/home/tomer/ps5-za-native'],
                         capture_output=True).returncode == 0
    bad += not wsl
    print(f'  {"ok " if wsl else "MISSING"}  {"WSL build root":22} /home/tomer/ps5-za-native')
    try:
        import PIL  # noqa: F401  (observer screenshots are verified with Pillow)
        print('  ok   Pillow')
    except ImportError:
        print('  warn  Pillow not installed: zw shot downloads but cannot verify PNGs (py -3 -m pip install pillow)')
    if probe:
        import socket
        for name, port in (('FTP', 2121), ('Payload Manager', 8084), ('klog', 3232)):
            try:
                socket.create_connection((HOST, port), timeout=1.5).close()
                print(f'  ok   console {name} :{port}')
            except OSError as exc:
                print(f'  down console {name} :{port} ({exc})')
    else:
        print('  (console not probed; add --console-ok)')
    return 1 if bad else 0


# ---------------------------------------------------------------- observer composites

def observer_client():
    sys.path.insert(0, str(OBSERVER))           # client.py imports its sibling analyze.py
    spec = importlib.util.spec_from_file_location('za_observer_client', OBSERVER / 'client.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def next_seq(client, ftp, session):
    """Seq must increase per session. Take the larger of the console's acks and our own record."""
    STATE.mkdir(parents=True, exist_ok=True)
    record = STATE / f'observer-{session}.seq'
    used = int(record.read_text()) if record.is_file() else 0
    try:
        for name in ftp.nlst(f'{client.BASE}/session_{session}'):
            m = re.search(r'ack_(\d+)\.json$', name)
            if m:
                used = max(used, int(m[1]))
    except ftplib.error_perm:
        pass                                    # no session directory yet
    seq = used + 1
    record.write_text(str(seq))
    return seq


def observe(op, value, out, wait, frames=None):
    client = observer_client()
    with ftplib.FTP() as ftp:
        ftp.connect(HOST, 2121, timeout=10)
        ftp.login()
        session = client.status(ftp)['session']
        seq = next_seq(client, ftp, session)
        client.issue(ftp, session, seq, op, value, frames)
        print(f'queued {op} session={session} seq={seq}', flush=True)
        if op == 'measure':                     # no FTP traffic while measuring
            ftp.quit()
    time.sleep(wait)
    deadline = time.monotonic() + 30
    while True:
        with ftplib.FTP() as ftp:
            ftp.connect(HOST, 2121, timeout=10)
            ftp.login()
            try:
                record = client.collect(ftp, session, seq, Path(out))
            except ftplib.error_perm:
                record = None                   # acknowledgement not written yet
        if record and record.get('result') != 'settling':
            break
        if time.monotonic() > deadline:
            raise ZwError(f'No acknowledgement for seq {seq}; collect later with '
                          f'zw obs collect --session {session} --seq {seq} --out {out} --console-ok')
        time.sleep(1)
    for f in record.get('files', []):
        print('saved', Path(out) / f['name'], f['sha256'][:12])
    print('result', record['ack'].get('result'))
    return 0


def shot(args):
    require_console(args)
    out = take_opt(args, '--out') or raise_(ZwError('zw shot needs --out DIR'))
    return observe('snapshot', None, out, 1)


def fps(args):
    if args[:1] == ['analyze'] and len(args) == 2:
        return subprocess.call(PY + [str(OBSERVER / 'analyze.py'), args[1]])
    if args[:1] == ['measure']:
        require_console(args)
        out = take_opt(args, '--out') or raise_(ZwError('zw fps measure needs --out DIR'))
        seconds = int(args[1]) if len(args) > 1 else 20
        if not 1 <= seconds <= 120:
            raise ZwError('measure is 1..120 seconds')
        return observe('measure', seconds, out, seconds + 3)
    if args[:1] == ['set']:
        require_console(args)
        if args[1:] not in (['0'], ['1']):
            raise ZwError('zw fps set 1 (request 60, auto-fallback) | 0 (30)')
        return observe('fps', int(args[1]), take_opt(args, '--out', STATE / 'receipts'), 1)
    raise ZwError(COMPOSITE['fps'])


def press(args):
    require_console(args)
    out = take_opt(args, '--out', STATE / 'receipts')
    if len(args) != 2 or not args[1].isdigit():
        raise ZwError(COMPOSITE['input'])
    return observe('input', args[0], out, 1, int(args[1]))


def klog(args):
    require_console(args)
    out = Path(take_opt(args, '--out') or raise_(ZwError('zw klog needs --out FILE')))
    seconds = float(take_opt(args, '--seconds', '60'))
    sys.path.insert(0, str(REPO))
    from run_r3 import KlogCapture
    out.parent.mkdir(parents=True, exist_ok=True)
    cap = KlogCapture(out)
    cap.start()
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    cap.stop()
    if cap.error:
        print('klog:', cap.error)
    print(f'{cap.lines} lines -> {out} ({cap.backlog_lines} replayed backlog lines skipped)')
    return 0 if cap.connected else 1


# ---------------------------------------------------------------- PC build

def pc_run_dir(name):
    path = Path(name)
    return path if path.is_dir() else PC_RUNS / name


def pc(args):
    sub = args.pop(0) if args else ''
    if sub == 'run':
        # hebrew-lab/tools/run_poc.py is the generic bounded runner: own data root, copied save,
        # scripted input, captures, child-only termination. Runs land in hebrew-lab/runs/<NAME>.
        fps = take_opt(args, '--fps')
        if '--game' not in args:
            args += ['--game', str(PC_GAME)]
        env = []
        if fps:
            if fps not in ('30', '60'):
                raise ZwError('--fps is 30 or 60 (60 = forced, no fallback; measurement only)')
            env.append('LARECOMP_FPS=' + fps)
        if env:
            if '--env' in args:
                args[args.index('--env') + 1:args.index('--env') + 1] = env
            else:
                args += ['--env'] + env
        return forward('hebrew', ['run_poc'] + args)
    if sub == 'fps' and len(args) == 1:
        log = pc_run_dir(args[0]) / 'stderr.log'
        rows = [(int(m[1]), float(m[2]), float(m[3]))
                for m in FPS_LINE.finditer(log.read_text(encoding='utf-8', errors='replace'))]
        if not rows:
            raise ZwError('No [vk] fps lines in ' + str(log))
        values = sorted(r[1] for r in rows)
        print(f'{len(rows)} intervals (LARECOMP_FPS_INTERVAL, default 2 s): '
              f'min {values[0]:.1f}  median {values[len(values) // 2]:.1f}  max {values[-1]:.1f} fps; '
              f'worst frame {max(r[2] for r in rows):.1f} ms')
        print('interval averages, not per-frame percentiles')
        return 0
    if sub == 'shots' and len(args) == 1:
        build = pc_run_dir(args[0]) / 'build'
        for png in sorted(build.glob('frames/*.png')) + sorted(build.glob('*.png')):
            print(png)
        return 0
    raise ZwError(COMPOSITE['pc'])


def raise_(exc):
    raise exc


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        return usage()
    verb, args = argv[0], list(argv[1:])
    if verb in FORWARD:
        return forward(verb, args)
    handlers = {'pc': pc, 'brief': brief, 'card': card, 'doctor': doctor, 'shot': shot, 'fps': fps, 'input': press, 'klog': klog}
    if verb in handlers:
        return handlers[verb](args)
    raise ZwError(f'Unknown verb {verb!r}; run zw for the list')


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        sys.exit(main(sys.argv[1:]))
    except ZwError as exc:
        print('zw:', exc, file=sys.stderr)
        sys.exit(2)
