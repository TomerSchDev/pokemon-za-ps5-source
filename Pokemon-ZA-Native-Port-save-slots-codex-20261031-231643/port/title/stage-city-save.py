"""Stage the pinned 2.0.2 city Tepig save; the title imports it before guest boot."""
from pathlib import Path
import ftplib
import hashlib
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import run_r3 as r

SOURCE = Path('C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/runs/03-save-write/save/save_0/main')
EXPECTED = 'f5c64116c3fa0c39b407272b0646212c7bb27fdbb5bfbbf3601e232ecebd3c27'
REMOTE = '/data/homebrew/PPSA91761/save-import/city-tepig-f5c64116.main'
ROOT = Path(__file__).resolve().parents[2]

def main():
    data = SOURCE.read_bytes()
    if len(data) != 3186611 or hashlib.sha256(data).hexdigest() != EXPECTED:
        raise RuntimeError('Prepared save differs from verified PC checkpoint')
    out = ROOT/'evidence'/('title-r12-save-transfer-'+r.stamp())
    out.mkdir()
    (out/'prepared-city-tepig.main').write_bytes(data)
    record = dict(utc=r.utc_now(), source=str(SOURCE), bytes=len(data), source_sha256=EXPECTED,
                  game_version='2.0.2', checkpoint='City, Mission 03, Tepig', staged_path=REMOTE)
    c = r.Console()
    try:
        folder = REMOTE.rsplit('/', 1)[0]
        try: c.ftp.mkd(folder)
        except ftplib.error_perm: c.ftp.cwd(folder)
        existing = c.sha256(REMOTE)
        if existing is not None and existing != EXPECTED:
            raise RuntimeError('Different existing staged save; refusing overwrite')
        if existing is None:
            c.store(REMOTE+'.new', data)
            if c.sha256(REMOTE+'.new') != EXPECTED: raise RuntimeError('Upload readback mismatch')
            c.ftp.rename(REMOTE+'.new', REMOTE)
            c.chmod(REMOTE, '644')
        record['staged_readback_sha256'] = c.sha256(REMOTE)
        if record['staged_readback_sha256'] != EXPECTED: raise RuntimeError('Final stage mismatch')
        # Best-effort pre-close snapshot. The authoritative backup is made by
        # the native importer, before the next guest startup.
        old = c.read('/mnt/sandbox/PPSA91761_000/download0/zarecomp/save/save_0/main')
        if old:
            (out/'pre-close-observed.main').write_bytes(old)
            record['pre_close_observed_sha256'] = hashlib.sha256(old).hexdigest()
    finally:
        c.close()
    (out/'manifest.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))
    print('Evidence:', out)

if __name__ == '__main__': main()
