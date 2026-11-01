"""Stage a NEW PPSA91761 title, stream SHA-256 verification, publish last.

The r2 overlay supplies code/metadata; unchanged game assets come from r1.
Never writes an existing final title, save directory, or other application.
"""
import datetime
import ftplib
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'deliverables/ZA-Native-Title-r1-20261027/PPSA91761'
OVERLAY = ROOT / 'artifacts/title-r2-hardware/PPSA91761'
HOST = '192.168.1.135'
FINAL = '/data/homebrew/PPSA91761'
STAMP = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%SZ')
STAGE = '/data/.za-native-title-r2-' + STAMP

def digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()

def main():
    meta = json.loads((OVERLAY / 'sce_sys/param.json').read_text())
    assert meta['titleId'] == 'PPSA91761'
    assert (OVERLAY / 'eboot.bin').stat().st_size > 300_000_000
    with urllib.request.urlopen(f'http://{HOST}:8084/processes_list', timeout=8) as response:
        if any(p.get('name') == 'eboot.bin' for p in json.load(response)['processes']):
            raise RuntimeError('An application is running; no deployment performed')
    files = {p.relative_to(BASE).as_posix(): p for p in BASE.rglob('*') if p.is_file()}
    files.update({p.relative_to(OVERLAY).as_posix(): p for p in OVERLAY.rglob('*') if p.is_file()})
    ftp = ftplib.FTP()
    ftp.connect(HOST, 2121, timeout=60)
    ftp.login()
    ftp.sendcmd('SELF')
    report = dict(title='PPSA91761', host=HOST, stage=STAGE, final=FINAL, files=[], published=False)
    output = ROOT / 'evidence' / ('title-r2-deploy-' + STAMP + '.json')
    try:
        ftp.cwd('/data/homebrew')
        names = [n for n, _ in ftp.mlsd()]
        if any(n == 'PPSA91761' or n.startswith('PPSA91761.') for n in names):
            raise RuntimeError('PPSA91761 already exists; refusing to replace it')
        ftp.mkd(STAGE)
        ftp.sendcmd('SITE CHMOD 755 ' + STAGE)
        folders = sorted({str(Path(rel).parent).replace('\\', '/') for rel in files if '/' in rel},
                         key=lambda p: (p.count('/'), p))
        made = {''}
        for folder in folders:
            parts = folder.split('/')
            for i in range(1, len(parts)+1):
                sub = '/'.join(parts[:i])
                if sub not in made:
                    ftp.mkd(STAGE + '/' + sub)
                    ftp.sendcmd('SITE CHMOD 755 ' + STAGE + '/' + sub)
                    made.add(sub)
        print(f'Staging {len(files)} files, {sum(p.stat().st_size for p in files.values()):,} bytes')
        for index, (rel, path) in enumerate(sorted(files.items()), 1):
            remote = STAGE + '/' + rel
            size = path.stat().st_size
            expected = digest(path)
            progress = [0, time.monotonic()]
            def transferred(chunk):
                progress[0] += len(chunk)
                if time.monotonic() - progress[1] >= 15:
                    print(f'{rel}: uploaded {progress[0]:,}/{size:,}')
                    progress[1] = time.monotonic()
            with path.open('rb') as source:
                ftp.storbinary('STOR ' + remote, source, 1 << 20, transferred)
            ftp.sendcmd('SITE CHMOD ' + ('755' if rel == 'eboot.bin' or path.suffix == '.prx' else '644') + ' ' + remote)
            received = hashlib.sha256()
            progress[:] = [0, time.monotonic()]
            def readback(chunk):
                received.update(chunk)
                progress[0] += len(chunk)
                if time.monotonic() - progress[1] >= 15:
                    print(f'{rel}: verifying {progress[0]:,}/{size:,}')
                    progress[1] = time.monotonic()
            ftp.retrbinary('RETR ' + remote, readback, 1 << 20)
            if received.hexdigest() != expected:
                raise RuntimeError('Readback mismatch: ' + rel)
            report['files'].append(dict(path=rel, bytes=size, sha256=expected))
            output.write_text(json.dumps(report, indent=2), encoding='utf-8')
            if index % 30 == 0 or size > 1 << 20 or index == len(files):
                print(f'Verified {index}/{len(files)}: {rel}')
        ftp.rename(STAGE, FINAL)
        report['published'] = True
        report['published_utc'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Published ' + FINAL)
        print(output)
    finally:
        ftp.close()

if __name__ == '__main__':
    main()
