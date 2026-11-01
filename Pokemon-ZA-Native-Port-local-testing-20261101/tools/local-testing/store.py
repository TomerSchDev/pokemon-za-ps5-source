"""Small transactional journal. Production state lives outside source checkouts."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from contextlib import contextmanager
from contracts import canonical, STATUSES


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
        f.flush()
        os.fsync(f.fileno())
    os.replace(temp, path)


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / 'jobs.sqlite3'
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS jobs (sequence INTEGER PRIMARY KEY AUTOINCREMENT, '
                       'id TEXT UNIQUE NOT NULL, manifest TEXT NOT NULL, manifest_sha256 TEXT NOT NULL, '
                       'submitted REAL NOT NULL, phase TEXT NOT NULL, verdict TEXT, cancel INTEGER DEFAULT 0, '
                       'execution_id TEXT, detail TEXT NOT NULL DEFAULT "{}", result TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, '
                       'job_id TEXT NOT NULL, at REAL NOT NULL, phase TEXT NOT NULL, detail TEXT NOT NULL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    def submit(self, manifest, sha):
        job = 'job-' + uuid.uuid4().hex
        with self.connect() as db:
            db.execute('INSERT INTO jobs(id,manifest,manifest_sha256,submitted,phase) VALUES (?,?,?,?,?)',
                       (job, canonical(manifest), sha, time.time(), 'QUEUED'))
            db.execute('INSERT INTO events(job_id,at,phase,detail) VALUES (?,?,?,?)',
                       (job, time.time(), 'QUEUED', '{}'))
        return self.get(job)

    @staticmethod
    def decode(row):
        out = dict(row)
        for k in ('manifest', 'detail', 'result'):
            out[k] = json.loads(out[k]) if out[k] else None
        return out

    def get(self, job):
        with self.connect() as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
            if not row:
                raise ValueError('unknown job: ' + job)
            out = self.decode(row)
            out['queue_position'] = (db.execute("SELECT count(*) FROM jobs WHERE phase='QUEUED' AND sequence<=?",
                                               (row['sequence'],)).fetchone()[0] if row['phase'] == 'QUEUED' else None)
            return out

    def list(self):
        with self.connect() as db:
            return [self.decode(r) for r in db.execute('SELECT * FROM jobs ORDER BY sequence')]

    def update(self, job, phase=None, **detail):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT phase,detail FROM jobs WHERE id=?', (job,)).fetchone()
            merged = {**json.loads(row['detail']), **detail}
            phase = phase or row['phase']
            db.execute('UPDATE jobs SET phase=?,detail=? WHERE id=?', (phase, canonical(merged), job))
            db.execute('INSERT INTO events(job_id,at,phase,detail) VALUES (?,?,?,?)',
                       (job, time.time(), phase, canonical(detail)))

    def claim(self, worker_identity):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM jobs WHERE phase NOT IN ('FINISHED','QUEUED')").fetchone():
                raise RuntimeError('unfinished execution requires recovery')
            row = db.execute("SELECT * FROM jobs WHERE phase='QUEUED' ORDER BY sequence LIMIT 1").fetchone()
            if row is None:
                return None
            execution = 'exec-' + uuid.uuid4().hex
            detail = {'worker': worker_identity, 'claimed_at': time.time(), 'containment_armed': False}
            db.execute('UPDATE jobs SET phase=?,execution_id=?,detail=? WHERE id=?',
                       ('WAITING_RESOURCE', execution, canonical(detail), row['id']))
        return self.get(row['id'])

    def cancel(self, job):
        with self.connect() as db:
            changed = db.execute("UPDATE jobs SET cancel=1 WHERE id=? AND phase!='FINISHED'", (job,)).rowcount
        if not changed:
            self.get(job)
        return self.get(job)

    def finish(self, job, result):
        if result.get('status') not in STATUSES:
            raise ValueError('a terminal result requires an explicit supported status')
        if result['status'] == 'PASS' and (not result.get('checks') or
                any(c.get('passed') is not True for c in result['checks']) or not result.get('reproducibility')):
            raise ValueError('PASS requires explicit true assertions and reproducibility evidence')
        with self.connect() as db:
            db.execute('UPDATE jobs SET phase=?,verdict=?,result=? WHERE id=?',
                       ('FINISHED', result['status'], canonical(result), job))
            db.execute('INSERT INTO events(job_id,at,phase,detail) VALUES (?,?,?,?)',
                       (job, time.time(), 'FINISHED', canonical({'status': result['status']})))


@contextmanager
def worker_lock(root):
    path = Path(root) / 'worker.lock'
    with path.open('a+b') as f:
        f.seek(0)
        if f.read(1) == b'':
            f.write(b'0')
            f.flush()
        f.seek(0)
        if os.name == 'nt':
            import msvcrt
            try:
                msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise RuntimeError('another local test worker holds the OS lock') from exc
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            f.seek(0)
            if os.name == 'nt':
                msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(f, fcntl.LOCK_UN)
