"""Validate a ZA r15 shader pack; --install adds absent files over local PS5 FTP.

Only /data/homebrew/PPSA91762/cache/spirv is writable by this tool. Existing keys,
the live cache, executable, game data and saves are never replaced.
"""
import argparse, concurrent.futures, ftplib, hashlib, io, json, re, threading, time, uuid, zipfile
from datetime import datetime, timezone
from pathlib import Path

TITLE = 'PPSA91762'
EBOOT_SHA256 = '5e02bcf386b07cd1c96e0ee2f2bd3f32bd900849aeacdc4668023a71372150c0'
REMOTE = '/data/homebrew/'+TITLE+'/cache/spirv'


def digest(data): return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with open(path,'rb') as stream: return hashlib.file_digest(stream,'sha256').hexdigest()


def validate_pack(path):
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('schema') != 1 or manifest.get('title') != TITLE or manifest.get('eboot_sha256') != EBOOT_SHA256:
            raise ValueError('Pack does not target the installed ZA Randomizer r15 build')
        if manifest.get('raw_shaderc_results') is not True:
            raise ValueError('Wrong cache format')
        rows = manifest['files']
        if not 1 <= len(rows) <= 100000:
            raise ValueError('Invalid file count')
        expected = {'manifest.json'}
        for row in rows:
            key = row['key']
            if not re.fullmatch('[0-9a-f]{16}', key): raise ValueError('Invalid cache key')
            name = 'cache/spirv/'+key+'.spv'
            if name in expected: raise ValueError('Duplicate cache key')
            expected.add(name)
            info = archive.getinfo(name)
            if not 20 < info.file_size <= 16 << 20 or info.file_size % 4 or info.file_size != row['bytes']:
                raise ValueError('Invalid SPIR-V size: '+key)
            data = archive.read(name)
            if data[:4] != b'\x03\x02\x23\x07' or digest(data) != row['spv_sha256']:
                raise ValueError('Corrupt SPIR-V: '+key)
            if not row.get('validated'): raise ValueError('Unvalidated module: '+key)
        if len(archive.namelist()) != len(expected) or set(archive.namelist()) != expected:
            raise ValueError('Unexpected or duplicate archive entries')
    return manifest


def connect(host):
    import importlib.util
    spec = importlib.util.spec_from_file_location('cache_install_guard', Path(__file__).resolve().parents[2] / 'tools/console-install-queue/install_guard.py')
    guard = importlib.util.module_from_spec(spec); spec.loader.exec_module(guard)
    board, agent, ticket, token = guard.owner()
    board.authorize_install(agent, ticket, token)
    ftp = ftplib.FTP()
    try:
        ftp.connect(host,2121,timeout=30); ftp.login(); ftp.sendcmd('SELF')
    except (OSError, EOFError, ftplib.error_temp) as error:
        ftp.close(); guard.observe_connection('offline', str(error)); raise
    guard.observe_connection('online', 'FTP handshake succeeded')
    return guard.GuardedFTP(ftp)


def remote_sha(ftp, path):
    sha = hashlib.sha256(); ftp.retrbinary('RETR '+path,sha.update,1<<20)
    return sha.hexdigest()


def listing(ftp):
    ftp.cwd(REMOTE)
    try: return {name for name, facts in ftp.mlsd() if facts.get('type') == 'file'}
    finally: ftp.cwd('/')


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('archive',type=Path); ap.add_argument('--install',action='store_true')
    ap.add_argument('--host',default='192.168.1.135'); ap.add_argument('--workers',type=int,choices=range(1,5),default=4)
    ap.add_argument('--receipt',type=Path)
    args = ap.parse_args()
    print('Validating every local module...',flush=True)
    manifest = validate_pack(args.archive)
    print(f"Validated {len(manifest['files'])} local modules",flush=True)
    if not args.install: return
    receipt = args.receipt or args.archive.with_name('INSTALL-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.json')
    if receipt.exists(): raise FileExistsError(receipt)
    report = dict(complete=False,title=TITLE,utc=datetime.now(timezone.utc).isoformat(),
                  archive_sha256=file_digest(args.archive),uploaded=[],existing_preserved=[],errors=[])
    def save():
        tmp = receipt.with_suffix('.new'); tmp.write_text(json.dumps(report,indent=2)); tmp.replace(receipt)
    first = connect(args.host)
    try:
        actual = remote_sha(first,'/data/homebrew/'+TITLE+'/eboot.bin')
        if actual != EBOOT_SHA256: raise RuntimeError('Console executable changed; no files were uploaded')
        report['verified_eboot_sha256'] = actual
        existing = listing(first)
        report['before_spv_count'] = sum(n.endswith('.spv') for n in existing)
    finally: first.close()
    needed = []
    for row in manifest['files']:
        if row['key']+'.spv' in existing:
            report['existing_preserved'].append(row['key'])
        else: needed.append(row)
    save()
    connections=[]; archives=[]; lock=threading.Lock(); local=threading.local(); token=uuid.uuid4().hex[:12]
    def upload(row):
        ftp=getattr(local,'ftp',None)
        if ftp is None:
            ftp=connect(args.host); local.ftp=ftp
            with lock: connections.append(ftp)
        name=row['key']+'.spv'; final=REMOTE+'/'+name; temp=final+'.offline-'+token
        try:
            # Recheck immediately before upload; another helper may have added this key.
            ftp.voidcmd('TYPE I')
            try:
                ftp.size(final)
                return dict(key=row['key'],preserved=True)
            except ftplib.error_perm as error:
                if not str(error).startswith('550'): raise
            archive=getattr(local,'archive',None)
            if archive is None:
                archive=zipfile.ZipFile(args.archive); local.archive=archive
                with lock: archives.append(archive)
            data=archive.read('cache/spirv/'+name)
            if digest(data) != row['spv_sha256']: raise ValueError('Archive changed during transfer')
            ftp.storbinary('STOR '+temp,io.BytesIO(data),1<<20)
            if remote_sha(ftp,temp) != row['spv_sha256']: raise ValueError('Remote readback mismatch')
            ftp.sendcmd('SITE CHMOD 644 '+temp)
            # Same protection again after the transfer; preserve any competing result.
            try:
                ftp.size(final)
            except ftplib.error_perm as error:
                if not str(error).startswith('550'): raise
            else:
                ftp.delete(temp)
                return dict(key=row['key'],preserved=True)
            ftp.rename(temp,final)
            return dict(key=row['key'],sha256=row['spv_sha256'],bytes=row['bytes'],readback_verified=True)
        except Exception:
            try: ftp.delete(temp)
            except Exception: pass
            ftp.close(); local.ftp=None
            raise
    start=time.monotonic(); last=start
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            pending={}; queue=iter(needed)
            while True:
                while len(pending) < args.workers*2:
                    row=next(queue,None)
                    if row is None: break
                    pending[pool.submit(upload,row)] = row
                if not pending: break
                ready,_=concurrent.futures.wait(pending,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED)
                for future in ready:
                    row=pending.pop(future)
                    try:
                        item=future.result()
                        if item.get('preserved'): report['existing_preserved'].append(item['key'])
                        else: report['uploaded'].append(item)
                    except Exception as error:
                        report['errors'].append(dict(key=row['key'],error=str(error)))
                if report['errors']:
                    # Stop scheduling new files on transport failure. Completed entries remain usable.
                    for future,row in pending.items():
                        try:
                            item=future.result()
                            if item.get('preserved'): report['existing_preserved'].append(item['key'])
                            else: report['uploaded'].append(item)
                        except Exception as error: report['errors'].append(dict(key=row['key'],error=str(error)))
                    save(); raise RuntimeError('Upload stopped; see receipt. Rerun safely to add remaining keys.')
                if time.monotonic()-last > 15:
                    report['elapsed_seconds']=round(time.monotonic()-start,1); save()
                    print(f"Verified new files: {len(report['uploaded'])}/{len(needed)}",flush=True);last=time.monotonic()
        final=connect(args.host)
        try:
            names=listing(final)
            assert all(row['key']+'.spv' in names for row in manifest['files']), 'Final listing missing a key'
            report['after_spv_count']=sum(n.endswith('.spv') for n in names)
        finally: final.close()
        report['complete']=True;report['elapsed_seconds']=round(time.monotonic()-start,1);save()
        print(json.dumps(dict(uploaded=len(report['uploaded']),preserved=len(report['existing_preserved']),
            total=report['after_spv_count'],receipt=str(receipt))),flush=True)
    finally:
        for ftp in connections: ftp.close()
        for archive in archives: archive.close()
        save()


if __name__ == '__main__': main()
