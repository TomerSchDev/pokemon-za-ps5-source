"""Idle-only r23b deployment with explicit gated startup16 configuration.

Only the verified target title is edited. Rollback to exact r23 sets startup8;
the previous config is retained in local evidence and a versioned remote name.
"""
import hashlib
import deploy

t = deploy.t
t.SOURCE = deploy.ROOT / 'artifacts/randomizer-r23b-slot-depth/PPSA91762/eboot.bin'
t.BASE = deploy.ROOT / 'artifacts/randomizer-r23-slot-depth/PPSA91762/eboot.bin'
t.BASE_SHA = 'e89613683ab551fcbd4854bf08891db7defd5046ceb906b7438fcf517136104b'
t.E = deploy.ROOT / 'evidence/preparation-r21-hardware/deployment-r23b'


def configure_startup(c, ignored, out):
    batch = deploy.preserve_options(c, ignored, out)
    installed = c.sha256(t.APP + '/eboot.bin')
    candidate = hashlib.sha256(t.SOURCE.read_bytes()).hexdigest()
    assert installed in (candidate, t.BASE_SHA)
    data = b'16\n' if installed == candidate else b'8\n'
    name = 'slot-depth-options.txt'
    remote = t.APP + '/' + name
    previous = c.read(remote, 1024)
    if previous is not None:
        (out / ('previous-' + name)).write_bytes(previous)
    (out / name).write_bytes(data)
    if previous != data:
        stage = remote + '.staged-' + t.r.stamp()
        backup = remote + '.before-' + t.r.stamp()
        c.store(stage, data)
        assert c.read(stage, 1024) == data
        t.idle(); t.identity(c)
        assert c.read(remote, 1024) == previous
        if previous is not None:
            c.ftp.rename(remote, backup)
        try:
            c.ftp.rename(stage, remote)
        except Exception:
            if previous is not None:
                c.ftp.rename(backup, remote)
            raise
    assert c.read(remote, 1024) == data
    return dict(**batch, slot_depth_startup=int(data), startup_readback=True,
                startup_previous=previous.decode(errors='replace') if previous else None,
                startup_sha256=hashlib.sha256(data).hexdigest())


t.options = configure_startup
if __name__ == '__main__':
    t.main()
