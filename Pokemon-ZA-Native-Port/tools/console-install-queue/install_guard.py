"""Shared install write guard and observed connectivity reporting (no connection at import)."""
import ftplib
import hashlib
import importlib.util
import os
from pathlib import Path
import time
import uuid

spec = importlib.util.spec_from_file_location('guarded_queue', Path(__file__).with_name('console_queue.py'))
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)


def owner():
    agent, ticket, token = (os.environ.get('CONSOLE_INSTALL_' + name, '') for name in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        raise q.QueueError('Installation requires a console queue owner and deployment proof; use zw install-bundle')
    return q.Board(os.environ.get('CONSOLE_INSTALL_STATE')), agent, ticket, token


def observe_connection(state, detail):
    """Record a real transport error or successful FTP handshake; keep ownership on failure."""
    try:
        board, agent, ticket, token = owner()
        active, _ = board.authenticate(board.load(), agent, ticket, token, allow_stale=True, cleanup=True)
        if state == 'online' and not active.get('offline'):
            return
        path = board.root / 'observations' / ('connection-' + uuid.uuid4().hex + '.json')
        path.parent.mkdir(parents=True, exist_ok=True)
        q.atomic_write(path, q.canonical({'console': q.CONSOLE, 'ticket': ticket,
            'lease_id': active['lease_id'], 'state': state, 'observed_at': time.time(), 'detail': str(detail)}))
        board.connection(agent, ticket, token, state, path)
    except (q.QueueError, OSError):
        # Reporting failure must not release a reservation or mask the transport failure.
        return


class GuardedFTP:
    """All project installer writes must match the active, proved application bundle."""
    def __init__(self, ftp):
        self.raw = ftp
        self._validated_side_job = None

    def validate_policy(self, job, base):
        # A side job's immutable declaration establishes confinement once per
        # connection. Every upload still hashes the actual stream below, and
        # the canonical installer verifies all final bytes before handoff.
        # Rehashing a multi-GB image on every mkdir/chmod would prevent a bundle
        # from fitting a turn. Main test evidence is always revalidated.
        if job.get('deployment', {}).get('mode') == 'side_app':
            key = hashlib.sha256(q.canonical(job)).hexdigest()
            if key == self._validated_side_job:
                return
            q.install_policy(job, base)
            self._validated_side_job = key
        else:
            q.install_policy(job, base)

    def __getattr__(self, name):
        attribute = getattr(self.raw, name)
        if not callable(attribute):
            return attribute
        def call(*args, **kwargs):
            try:
                return attribute(*args, **kwargs)
            except (OSError, EOFError, ftplib.error_temp) as exc:
                observe_connection('offline', type(exc).__name__ + ': ' + str(exc))
                raise
        return call

    def authorization(self, path, directory=False):
        path = q.remote_path(path)
        board, agent, ticket, token = owner()
        state = board.load()
        active, row = board.authenticate(state, agent, ticket, token)
        if active.get('offline'):
            raise q.Busy('Console offline; reservation is paused')
        self.validate_policy(row['job'], board.root)
        artifacts = row['job']['artifacts']
        # Explicit artifact and staging siblings only. No writes to another title or user saves.
        matches = [r for r in artifacts if path == r['remote_path'] or path.startswith(r['remote_path'] + '.new-')]
        if directory and (path == '/data/homebrew' or any(r['remote_path'].startswith(path.rstrip('/') + '/') for r in artifacts)):
            return None
        if not matches:
            raise q.QueueError('Write is outside the declared tested bundle: ' + path)
        return matches[0]

    def storbinary(self, command, source, *args, **kwargs):
        if not command.startswith('STOR '):
            raise q.QueueError('Only an explicit STOR destination is supported')
        path = command[5:]
        # Runtime observer mailbox is not an application installation.
        if path == '/data/homebrew/PPSA91762/observer-command.txt':
            board, agent, ticket, token = owner()
            board.check(agent, ticket, token)
        else:
            artifact = self.authorization(path)
            position = source.tell()
            digest = hashlib.sha256()
            for block in iter(lambda: source.read(1024 * 1024), b''):
                digest.update(block)
            source.seek(position)
            if digest.hexdigest() != artifact['sha256']:
                raise q.QueueError('Upload bytes differ from the proved candidate')
        return self.__getattr__('storbinary')(command, source, *args, **kwargs)

    def rename(self, old, new):
        board, agent, ticket, token = owner()
        active, row = board.authenticate(board.load(), agent, ticket, token, cleanup=True)
        if active.get('offline'):
            raise q.Busy('Console offline; keep the installation turn')
        self.validate_policy(row['job'], board.root)
        old, new = q.remote_path(old), q.remote_path(new)
        for artifact in row['job']['artifacts']:
            final = artifact['remote_path']
            if (old.startswith(final + '.new-') and new == final
                    or old == final and new.startswith(final + '.before-')
                    or old.startswith(final + '.before-') and new == final):
                return self.__getattr__('rename')(old, new)
        raise q.QueueError('Rename is outside the declared installation transaction')

    def mkd(self, path):
        self.authorization(path, directory=True)
        return self.__getattr__('mkd')(path)

    def delete(self, path):
        self.authorization(path)
        if '.new-' not in path:
            raise q.QueueError('Automatic deletion is restricted to this installation staging file')
        return self.__getattr__('delete')(path)

    def rmd(self, path):
        raise q.QueueError('Directory deletion is not part of a guarded install')

    def sendcmd(self, command):
        if command.startswith('SITE CHMOD '):
            self.authorization(command.split(' ', 3)[3], directory=True)
        elif command not in ('SELF', 'NOOP', 'PWD', 'SYST', 'FEAT', 'TYPE I', 'TYPE A'):
            raise q.QueueError('Raw mutating FTP commands are disabled in the installer')
        return self.__getattr__('sendcmd')(command)

    def voidcmd(self, command):
        if command not in ('NOOP', 'TYPE I', 'TYPE A'):
            raise q.QueueError('Raw mutating FTP commands are disabled in the installer')
        return self.__getattr__('voidcmd')(command)

    def storlines(self, *args, **kwargs):
        raise q.QueueError('Use the guarded binary upload path')

    def transfercmd(self, *args, **kwargs):
        raise q.QueueError('Raw data transfers are disabled in the installer')
