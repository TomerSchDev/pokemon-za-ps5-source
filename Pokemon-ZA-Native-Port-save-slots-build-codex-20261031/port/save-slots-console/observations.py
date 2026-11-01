"""Read-only observations for PPSA91781. Draft: no console orchestration here.

All transport calls are supplied by the canonical guarded Console/Lease.
Raw save bytes belong only in local private evidence, never exported journals.
"""
import hashlib
import json
import re

TITLE = 'PPSA91781'
APP = '/data/homebrew/' + TITLE
SANDBOX = '/mnt/sandbox/' + TITLE + '_000'
RUN_ROOT = SANDBOX + '/download0/zarecomp/rando'
RUN_ID = re.compile(r'[a-z0-9][a-z0-9-]{0,79}')
EBOOT_SHA = '81e264c8991f5ba86870a7fd89fe13765a07eb0ae9f240047ccea656baaf25fe'
PARAM_SHA = 'ef08948495c2f469b3f9c4edc3a023743ac608eccdd46aaeaf617274c7928c6a'


def digest(value):
    return hashlib.sha256(value).hexdigest()


def run_id(value):
    if not isinstance(value, str) or not RUN_ID.fullmatch(value):
        raise ValueError('Invalid confined run ID')
    return value


def decode(raw, label):
    if raw is None:
        raise ValueError('Required file missing: ' + label)
    obj = json.loads(raw.decode('utf-8-sig', errors='strict'))
    if not isinstance(obj, dict):
        raise ValueError('Object required: ' + label)
    return obj


def own(c, identity, m, check):
    """Recheck every identity edge before reads and especially own-close.

    The ledger must come from this driver's fresh launch, not caller PID input.
    Hashing the installed eboot happens when the session identity is acquired;
    the canonical registered baseline must remain exactly pinned throughout.
    """
    check()
    if (identity.get('title') != TITLE or identity.get('eboot_sha256') != EBOOT_SHA
            or identity.get('param_sha256') != PARAM_SHA
            or not re.fullmatch(r'[0-9a-f]{16}', identity.get('session', ''))):
        raise RuntimeError('Identity ledger is not this candidate/title/session')
    procs = m.api.eboot_processes()
    check()
    if len(procs) != 1 or m.api.process_pid(procs[0]) != identity['pid']:
        raise RuntimeError('Own PID changed; never control an unknown process')
    raw = c.read(SANDBOX + '/app0/sce_sys/param.json', 65536)
    if raw is None or digest(raw) != PARAM_SHA or decode(raw, 'mounted param').get('titleId') != TITLE:
        raise RuntimeError('Actual mounted title/param changed')
    if m.observer.TITLE != TITLE or m.observer.BASE != SANDBOX + '/download0/zarecomp/observer':
        raise RuntimeError('Host observer selector is not isolated')
    status = m.observer.status(c.ftp)
    if status['session'] != identity['session']:
        raise RuntimeError('Fresh observer session changed')
    check()
    names = c.listing('/mnt/sandbox')
    mounted = [n for n in names if re.fullmatch(r'(?:PPSA|CUSA|FAKE).+_[0-9]{3}', n)]
    if mounted != [TITLE + '_000']:
        raise RuntimeError('Another/unknown mounted title; refuse process control')
    check()
    return status


def run_snapshot(c, name, parser, check):
    """Two consistent reads of main/slot plus immutable metadata/table hashes.

    A moving save during an in-game commit is INCOMPLETE, never a false CRC bug.
    This method never writes the console or decrypts a game save.
    """
    name = run_id(name)
    root = RUN_ROOT + '/' + name
    check()
    report_raw = c.read(root + '/report.json', 1 << 20)
    report = decode(report_raw, 'report')
    if report.get('native_complete') is not True or report.get('native_run_id') != name:
        raise ValueError('Incomplete or foreign run report')
    if not isinstance(report.get('seed'), str):
        raise ValueError('Missing canonical seed string')
    main = c.read(root + '/save/save_0/main', 32 << 20)
    check()
    slot = c.read(root + '/slot.zrs', 48 << 20)
    if main is None or slot is None:
        raise ValueError('New run lacks source save or slot container')
    parsed = parser(slot, expected_run_id=name, expected_seed=report['seed'])
    if parsed.pop('save_bytes') != main:
        raise ValueError('Container SAVE differs from source main')
    if parsed['summary']['run_id'] != name or parsed['summary']['seed'] != report['seed']:
        raise ValueError('Container run/seed differs from report')
    tables = report.get('native_tables')
    extras = report.get('native_extra_tables', [])
    if not isinstance(tables, list) or len(tables) not in (3, 4) or not isinstance(extras, list):
        raise ValueError('Missing immutable randomized table manifest')
    manifest = {}
    for row in tables + extras:
        rel = row.get('path')
        if (not isinstance(rel, str) or not rel or rel.startswith('/') or '\\' in rel
                or any(part in ('', '.', '..') for part in rel.split('/'))):
            raise ValueError('Unconfined native table path')
        if rel in manifest:
            raise ValueError('Duplicate immutable table path')
        check()
        value = c.sha256(root + '/romfs/' + rel)
        if value != row.get('sha256'):
            raise ValueError('Immutable table changed: ' + rel)
        manifest[rel] = value
    check()
    if c.read(root + '/save/save_0/main', 32 << 20) != main or c.read(root + '/slot.zrs', 48 << 20) != slot:
        raise RuntimeError('Save/container changed during observation; retry after save finishes')
    if c.read(root + '/report.json', 1 << 20) != report_raw:
        raise RuntimeError('Immutable report changed during observation')
    check()
    return {'run_id': name, 'report_sha256': digest(report_raw),
            'main_sha256': digest(main), 'main_bytes': len(main), 'slot': parsed,
            'tables': manifest}, {'main': main, 'slot.zrs': slot}


def run_inventory(c, m, check):
    check()
    rows = m.listing(c, RUN_ROOT)
    if len(rows) > 32:
        raise ValueError('Fresh private two-run test root unexpectedly large')
    runs = []
    for name, facts in rows:
        if facts['type'] == 'dir':
            runs.append(run_id(name))
        elif name != 'active.json':
            raise ValueError('Unexpected file in fresh private test root: ' + name)
    raw = c.read(RUN_ROOT + '/active.json', 4096)
    active = None if raw is None else decode(raw, 'active')['id']
    if active is not None and run_id(active) not in runs:
        raise ValueError('Active run not present in observed run list')
    check()
    return {'runs': sorted(runs), 'active': active}


def transition(before, after, *, created=None, deleted=None, active=None):
    """Exact one-run creation/deletion/list/switch assertions, no writes."""
    old, new = set(before['runs']), set(after['runs'])
    if len(old) != len(before['runs']) or len(new) != len(after['runs']):
        raise ValueError('Duplicate run inventory')
    if created is not None and deleted is not None:
        raise ValueError('One transition per assertion')
    if created is not None:
        run_id(created)
        if created in old or new != old | {created}:
            raise ValueError('New-run operation did not create exactly the one expected own run')
    elif deleted is not None:
        run_id(deleted)
        if deleted not in old or new != old - {deleted}:
            raise ValueError('Delete operation changed an unexpected run set')
    elif new != old:
        raise ValueError('List/continue changed the run set')
    if active is not None and (run_id(active) not in new or after['active'] != active):
        raise ValueError('Selected active run differs')
    return {'result': 'PASS', 'before': before, 'after': after,
            'created': created, 'deleted': deleted, 'expected_active': active}


def writer_roundtrip(before, after, log_delta):
    """Actual writer assertions, deliberately separate from initial creation."""
    old, new = before['slot'], after['slot']
    if before['run_id'] != after['run_id']:
        raise ValueError('Writer snapshots belong to different runs')
    if before['main_sha256'] == after['main_sha256']:
        raise ValueError('No source-save byte change after actual in-game Save')
    if old['container_sha256'] == new['container_sha256']:
        raise ValueError('Container did not change with the committed save')
    if not re.search(r'\[slot\] commit [1-9][0-9]*: [^\r\n]* rewritten \([1-9][0-9]* bytes\): save ', log_delta):
        raise ValueError('No fresh actual writer commit/rewritten log')
    if not new['summary']['flags'] & 8 or new['summary']['save_sha256'] != after['main_sha256']:
        raise ValueError('Fresh summary does not prove the source-save SHA')
    for field in ('run_id', 'seed', 'created_time'):
        if old['summary'][field] != new['summary'][field]:
            raise ValueError('Writer changed immutable summary identity: ' + field)
    for field in ('RAND', 'SETT'):
        if old['section_sha256'][field] != new['section_sha256'][field]:
            raise ValueError('Writer changed immutable section: ' + field)
    if before['report_sha256'] != after['report_sha256'] or before['tables'] != after['tables']:
        raise ValueError('Writer changed immutable run metadata/tables')
    return {'result': 'PASS', 'assertion': 'actual_in_game_writer_roundtrip',
            'run_id': after['run_id'], 'before_main_sha256': before['main_sha256'],
            'after_main_sha256': after['main_sha256'], 'after_container_sha256': new['container_sha256']}
