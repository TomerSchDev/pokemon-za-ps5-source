"""Version-one local test contracts. No execution, environment expansion or shell commands."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import re

STATUSES = ('PASS', 'FAIL', 'ERROR', 'TIMEOUT', 'UNSUPPORTED', 'CANCELLED')
PHASES = ('QUEUED', 'WAITING_RESOURCE', 'PREPARING', 'RUNNING', 'FINALIZING', 'FINISHED')
IDENT = re.compile(r'[A-Za-z0-9_.-]{1,100}\Z')
HASH = re.compile(r'[0-9a-f]{64}\Z')
BUTTON = re.compile(r'(?:A|B|X|Y|LSTICK|RSTICK|L|R|ZL|ZR|PLUS|MINUS|UP|DOWN|LEFT|RIGHT|R?STICK_(?:UP|DOWN|LEFT|RIGHT)|STICK_[0-9]{1,3})\Z')


class ContractError(ValueError):
    pass


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def read_json(path):
    def unique(pairs):
        out = {}
        for k, v in pairs:
            if k in out:
                raise ContractError('duplicate JSON key: ' + k)
            out[k] = v
        return out
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique,
                      parse_constant=lambda s: (_ for _ in ()).throw(ContractError('nonfinite number: ' + s)))


def keys(obj, required, optional=()):
    if not isinstance(obj, dict):
        raise ContractError('expected JSON object')
    missing, extra = set(required) - obj.keys(), obj.keys() - set(required) - set(optional)
    if missing or extra:
        raise ContractError(f'keys missing={sorted(missing)} unknown={sorted(extra)}')


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ContractError(f'expected integer {low}..{high}: {value!r}')


def string(value, limit=1000):
    if not isinstance(value, str) or not value or len(value) > limit or '\x00' in value:
        raise ContractError('expected nonempty bounded string')


def path_ref(ref, base):
    keys(ref, ('path', 'sha256'))
    string(ref['path'])
    if not isinstance(ref['sha256'], str) or not HASH.fullmatch(ref['sha256']):
        raise ContractError('sha256 must be lowercase hexadecimal')
    ref['path'] = str((base / ref['path']).resolve())


def validate(raw, base):
    m = copy.deepcopy(raw)
    keys(m, ('schema_version', 'test_id', 'type', 'agent_id', 'build_id', 'runtime',
             'timeout_seconds', 'queue_timeout_seconds', 'input', 'execution', 'graphics',
             'screenshots', 'assertions', 'resources', 'artifacts', 'result_directory'), ('logic_level',))
    integer(m['schema_version'], 1, 1)
    for k in ('test_id', 'agent_id', 'build_id', 'result_directory'):
        if not isinstance(m[k], str) or not IDENT.fullmatch(m[k]) or m[k] in ('.', '..'):
            raise ContractError('invalid identifier: ' + k)
    if m['type'] not in ('logic', 'render', 'full'):
        raise ContractError('type must be logic, render or full')
    if 'logic_level' in m and (m['type'] != 'logic' or m['logic_level'] not in ('L1', 'L2', 'L3')):
        raise ContractError('logic_level is L1/L2/L3, for logic only')
    integer(m['timeout_seconds'], 1, 900)
    integer(m['queue_timeout_seconds'], 1, 86400)
    rt = m['runtime']
    keys(rt, ('executable', 'game_module', 'game_directory'))
    path_ref(rt['executable'], base)
    path_ref(rt['game_module'], base)
    string(rt['game_directory'])
    rt['game_directory'] = str((base / rt['game_directory']).resolve())
    keys(m['execution'], ('seconds',), ('stop_after_frame',))
    integer(m['execution']['seconds'], 1, 600)
    if 'stop_after_frame' in m['execution']:
        integer(m['execution']['stop_after_frame'], 1, 1000000)
    keys(m['input'], ('script', 'checkpoint'))
    script = m['input']['script']
    if not isinstance(script, str) or len(script.encode('ascii', errors='replace')) >= 16384:
        raise ContractError('input script must fit the legacy 16384-byte buffer')
    for token in script.split(',') if script else ():
        fields = token.split(':')
        if len(fields) not in (2, 3) or not fields[0].isdigit() or not BUTTON.fullmatch(fields[1]):
            raise ContractError('invalid input action: ' + token)
        integer(int(fields[0]), 1, 1000000)
        if len(fields) == 3:
            if not fields[2].isdigit():
                raise ContractError('invalid input length')
            integer(int(fields[2]), 1, 1000000)
        if fields[1].startswith('STICK_') and fields[1][6:].isdigit():
            integer(int(fields[1][6:]), 0, 359)
    cp = m['input']['checkpoint']
    if not isinstance(cp, dict) or cp.get('kind') not in ('new_game', 'copied_save'):
        raise ContractError('checkpoint kind must be new_game or copied_save')
    if cp['kind'] == 'new_game':
        keys(cp, ('kind',))
    else:
        keys(cp, ('kind', 'path', 'files'))
        string(cp['path'])
        cp['path'] = str((base / cp['path']).resolve())
        if not isinstance(cp['files'], dict) or not cp['files'] or 'save_0/main' not in cp['files']:
            raise ContractError('copied_save needs pinned files including save_0/main')
        for name, sha in cp['files'].items():
            p = Path(name)
            if p.is_absolute() or '..' in p.parts or '\\' in name or ':' in name or not name.startswith('save_0/') or not HASH.fullmatch(str(sha)):
                raise ContractError('invalid checkpoint file identity')
    g = m['graphics']
    keys(g, ('width', 'height', 'hidden', 'fps', 'pace_trace'))
    integer(g['width'], 64, 7680)
    integer(g['height'], 64, 4320)
    integer(g['fps'], 30, 60)
    if g['fps'] not in (30, 60) or type(g['hidden']) is not bool or type(g['pace_trace']) is not bool:
        raise ContractError('invalid graphics settings')
    shots = m['screenshots']
    keys(shots, ('frames', 'every', 'mode'), ('baseline',))
    if not isinstance(shots['frames'], list):
        raise ContractError('screenshot frames must be an array')
    for f in shots['frames']:
        integer(f, 1, 1000000)
    if shots['frames'] != sorted(set(shots['frames'])) or len(shots['frames']) > 100:
        raise ContractError('screenshot frames must be sorted, unique; at most 100')
    integer(shots['every'], 0, 1000000)
    if shots['mode'] not in ('capture_only', 'reference'):
        raise ContractError('invalid screenshot mode')
    if m['type'] == 'render' and not shots['frames']:
        raise ContractError('render requires explicit frames (warm-up is before the first frame)')
    stop = m['execution'].get('stop_after_frame')
    if stop is not None and (stop not in shots['frames'] or any(f > stop for f in shots['frames'])):
        raise ContractError('stop_after_frame must be the final requested screenshot')
    if shots['mode'] == 'reference':
        b = shots.get('baseline')
        keys(b, ('path', 'sha256', 'frame', 'rmse_max', 'changed_fraction_max', 'pixel_threshold'))
        ref = {k: b[k] for k in ('path', 'sha256')}
        path_ref(ref, base)
        b.update(ref)
        if b['frame'] not in shots['frames']:
            raise ContractError('baseline frame must be requested')
        for k in ('rmse_max', 'changed_fraction_max'):
            if type(b[k]) not in (int, float) or not 0 <= b[k] <= 1:
                raise ContractError('baseline tolerances must be 0..1')
        integer(b['pixel_threshold'], 0, 255)
    elif 'baseline' in shots:
        raise ContractError('capture_only must not supply baseline')
    if not isinstance(m['assertions'], list) or not m['assertions']:
        raise ContractError('at least one explicit assertion is required')
    for a in m['assertions']:
        if not isinstance(a, dict):
            raise ContractError('assertion must be an object')
        kind = a.get('kind')
        if kind == 'log_contains':
            keys(a, ('kind', 'text'))
            string(a['text'], 500)
        elif kind in ('min_presented_frame', 'screenshot_exists'):
            keys(a, ('kind', 'frame'))
            integer(a['frame'], 1, 1000000)
            if kind == 'screenshot_exists' and a['frame'] not in shots['frames']:
                raise ContractError('screenshot assertion frame must be requested')
        elif kind == 'fps_at_least':
            keys(a, ('kind', 'value'))
            if type(a['value']) not in (int, float) or not 0 < a['value'] <= 1000:
                raise ContractError('invalid FPS threshold')
        else:
            raise ContractError('unsupported assertion kind: ' + str(kind))
    keys(m['resources'], ('game_instances', 'gpu'))
    for k in m['resources']:
        integer(m['resources'][k], 1, 1)
    keys(m['artifacts'], ('logs', 'screenshots', 'metrics'))
    for k in m['artifacts']:
        if type(m['artifacts'][k]) is not bool:
            raise ContractError('artifact requirements must be boolean')
    if not m['artifacts']['logs'] or not m['artifacts']['metrics']:
        raise ContractError('logs and metrics are mandatory')
    if bool(shots['frames'] or shots['every']) and not m['artifacts']['screenshots']:
        raise ContractError('requested screenshots must be retained')
    return m


def fixture_files(root):
    root = Path(root)
    files = {}
    for p in sorted((root / 'save_0').rglob('*')):
        if p.is_symlink() or p.is_junction():
            raise ContractError('fixture links/junctions are not allowed')
        if p.is_file():
            files[p.relative_to(root).as_posix()] = digest(p)
    if 'save_0/main' not in files:
        raise ContractError('fixture needs save_0/main')
    return files
