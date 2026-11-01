"""Remove only the obsolete ZA Native Probe A0, with verified off-console backup."""
import argparse
import ftplib
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT.parent / 'runtime')]
import run_r3 as r
import library_client as library

TITLE = 'PPSA91760'
NAME = 'ZA Native Probe A0'
APP = '/data/homebrew/' + TITLE
LAUNCHER = '/data/pldmgr/payloads/za_native_probe_launch'
ROOTS = (APP, LAUNCHER)
KEEP = ('PPSA91761', 'PPSA91762', 'PPSA91763')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def entries(c, path):
    c.ftp.cwd(path)
    try:
        rows = list(c.ftp.mlsd())
        listing = []
        c.ftp.retrlines('LIST', listing.append)
    finally:
        c.ftp.cwd('/')
    types = {}
    for line in listing:
        parts = line.split(None, 8)
        assert len(parts) == 9 and parts[0][0] in '-dl', 'Unknown LIST format'
        types[parts[8]] = parts[0][0]
    result = []
    for name, facts in rows:
        if name in ('.', '..'):
            continue
        assert name and not any(ch in name for ch in '/\\\r\n\x00'), 'Unsafe FTP name'
        assert facts.get('type') in ('file', 'dir'), 'Symlink or unknown type refused'
        assert types.get(name) == ('d' if facts['type'] == 'dir' else '-'), 'LIST type mismatch or symlink'
        result.append((name, facts))
    return sorted(result)


def bounded(path):
    p = PurePosixPath(path)
    assert p.is_absolute() and '..' not in p.parts and str(p) == path
    assert any(p == PurePosixPath(root) or PurePosixPath(root) in p.parents for root in ROOTS)


def tree(c, path):
    bounded(path)
    result = []
    for name, facts in entries(c, path):
        remote = path + '/' + name
        bounded(remote)
        if facts['type'] == 'dir':
            result.extend(tree(c, remote))
        else:
            result.append(dict(path=remote, bytes=int(facts['size'])))
    return result


def find_probe():
    games = library.api('games', timeout=15)['games']
    matching = [g for g in games if g['title_id'] == TITLE]
    assert len(matching) == 1
    probe = matching[0]
    assert probe['title_name'] == NAME and probe['path'] == APP and probe['runtime_path'] == APP
    assert probe['source_type'] == 'folder' and not probe['installed_pkg'] and not probe['mounted']
    assert probe['installed'] and probe['can_uninstall']
    assert all(any(g['title_id'] == t and g['installed'] for g in games) for t in KEEP)
    return probe


def guard(c):
    for root in ROOTS:
        parent = str(PurePosixPath(root).parent)
        name = PurePosixPath(root).name
        c.ftp.cwd(parent)
        lines = []
        try:
            c.ftp.retrlines('LIST', lines.append)
        finally:
            c.ftp.cwd('/')
        matches = [line.split(None, 8) for line in lines if len(line.split(None, 8)) == 9 and line.split(None, 8)[8] == name]
        assert len(matches) == 1 and matches[0][0][0] == 'd', 'Root is not an ordinary directory'
    assert not any(n.startswith(TITLE + '_') for n in c.listing('/mnt/sandbox')), 'Probe is running'
    assert c.read('/user/app/' + TITLE + '/mount.lnk', 4096).decode() == APP
    p = json.loads(c.read(APP + '/sce_sys/param.json', 65536))
    assert p['titleId'] == TITLE and p['localizedParameters']['en-US']['titleName'] == NAME
    find_probe()


def protected(c):
    result = {}
    for title in KEEP:
        for suffix in ('/sce_sys/param.json',):
            data = c.read('/data/homebrew/' + title + suffix, 65536)
            assert data is not None
            result[title + suffix] = digest(data)
        data = c.read('/user/app/' + title + '/mount.lnk', 4096)
        assert data is not None
        result[title + '/mount.lnk'] = digest(data)
    return result


def nas_copy(path, nas):
    nas.mkdir(parents=True, exist_ok=True)
    dest = nas / path.name
    if dest.exists():
        assert file_digest(dest) == file_digest(path), 'Different existing NAS version'
    else:
        with path.open('rb') as src, dest.open('xb') as dst:
            shutil.copyfileobj(src, dst)
    assert file_digest(dest) == file_digest(path)


def prepare(c, out, nas):
    assert not (out / 'backup.json').exists()
    guard(c)
    files = [f for root in ROOTS for f in tree(c, root)]
    assert 0 < sum(f['bytes'] for f in files) < 1 << 30
    keep = protected(c)
    running = r.eboot_processes()
    archive = out / 'ZA-Native-Probe-A0-recovery.zip'
    with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for f in files:
            data = c.read(f['path'], 512 << 20)
            assert data is not None and len(data) == f['bytes']
            f['sha256'] = digest(data)
            assert c.sha256(f['path']) == f['sha256'], 'Remote file changed during backup'
            z.writestr(f['path'].lstrip('/'), data)
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    record = dict(at=r.utc_now(), title=TITLE, name=NAME, roots=ROOTS, files=files,
                  bytes=sum(f['bytes'] for f in files), archive=archive.name,
                  archive_sha256=file_digest(archive), protected=keep, running=running,
                  nas=str(nas), backup_verified=True)
    write(out / 'backup.json', record)
    nas_copy(archive, nas)
    nas_copy(out / 'backup.json', nas)
    print(json.dumps(dict(stage='backup verified locally and on NAS', files=len(files), bytes=record['bytes'])), flush=True)


def remove_tree(c, path, allowed, removed):
    bounded(path)
    # This server's DELE rejects directories with EPERM. RMD rejects symlinks
    # and positively identifies a real non-empty directory before recursion.
    try:
        c.ftp.sendcmd('RMD ' + path)
        return
    except ftplib.error_perm as error:
        assert str(error).startswith('550') and 'Directory not empty' in str(error), str(error)
    for name, facts in entries(c, path):
        remote = path + '/' + name
        bounded(remote)
        if facts['type'] == 'dir':
            remove_tree(c, remote, allowed, removed)
        else:
            assert remote in allowed, 'Unexpected file appeared; refusing deletion'
            assert int(facts['size']) == allowed[remote]['bytes']
            assert c.sha256(remote) == allowed[remote]['sha256'], 'File changed since backup'
            c.ftp.sendcmd('DELE ' + remote)
            removed.append(remote)
    c.ftp.rmd(path)


def remove(c, out, nas):
    assert not (out / 'removal.json').exists()
    record = json.loads((out / 'backup.json').read_text(encoding='utf-8'))
    assert record['title'] == TITLE and record['roots'] == list(ROOTS) and record['backup_verified']
    archive = out / record['archive']
    assert file_digest(archive) == record['archive_sha256']
    assert file_digest(nas / archive.name) == record['archive_sha256']
    guard(c)
    assert protected(c) == record['protected']
    assert [f for root in ROOTS for f in tree(c, root)] == [dict(path=f['path'], bytes=f['bytes']) for f in record['files']]
    # Remove the verified unused source first: ShadowMount otherwise discovers
    # the remaining folder and re-registers the just-uninstalled test title.
    assert not r.eboot_processes(), 'Close the active game before cleanup'
    assert not any(n.startswith(TITLE + '_') for n in c.listing('/mnt/sandbox'))
    removed = []
    allowed = {f['path']: f for f in record['files']}
    try:
        for root in ROOTS:
            remove_tree(c, root, allowed, removed)
    finally:
        write(out / 'removed-paths.json', removed)
    assert TITLE not in c.listing('/data/homebrew')
    assert 'za_native_probe_launch' not in c.listing('/data/pldmgr/payloads')
    # This existing library operation unregisters only the exact backed-up ID.
    reply = library.api('shadow/games/uninstall', {'title_id': TITLE, 'confirm': True}, timeout=45)
    prior = out / 'uninstall-response.json'
    if prior.exists():
        history = out / 'uninstall-response-before-source-removal.json'
        assert not history.exists()
        prior.rename(history)
    write(prior, reply)
    assert reply.get('status') == 0 and reply.get('title_id') == TITLE
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        rows = library.api('games', timeout=10)['games']
        if not any(g['title_id'] == TITLE and g.get('installed') for g in rows):
            break
        time.sleep(1)
    else:
        raise RuntimeError('Source removed and backed up, but registration is still present')
    assert TITLE not in c.listing('/user/app'), 'Registration directory still present'
    assert protected(c) == record['protected']
    final_games = library.api('games', timeout=15)['games']
    assert not any(g['title_id'] == TITLE and g.get('installed') for g in final_games)
    assert all(any(g['title_id'] == t and g['installed'] for g in final_games) for t in KEEP)
    result = dict(at=r.utc_now(), title=TITLE, name=NAME, unregistered=True, files_removed=len(removed),
                  removed_bytes=record['bytes'], roots_removed=ROOTS, protected_titles=list(KEEP),
                  protected_registration_and_metadata_unchanged=True,
                  save_paths_touched=False, running_after=r.eboot_processes(),
                  backup_archive=archive.name, backup_sha256=record['archive_sha256'], nas=str(nas))
    write(out / 'removal.json', result)
    report = out / 'Results-HE.txt'
    report.write_text('הוסרה אפליקציית הבדיקה הישנה ZA Native Probe A0 (PPSA91760), כולל הרישום במסך הבית, קובצי הבדיקה והלאנצ׳ר שלה.\n'
                      + f"נמחקו {len(removed)} קבצים, בהיקף {record['bytes'] / 1024**2:.2f} MiB.\n"
                      + 'המשחק הרגיל, הרנדומייזר ופרויקט מריו נשארו מותקנים. לא בוצעה פעולה בנתיבי שמירות.\n'
                      + 'נשמר גיבוי שחזור מאומת של אפליקציית הבדיקה במחשב וב־NAS.\nNAS: ' + str(nas) + '\n', encoding='utf-8')
    for file in (out / 'uninstall-response.json', out / 'removed-paths.json', out / 'removal.json', report):
        nas_copy(file, nas)
    print(json.dumps(result), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('op', choices=('prepare', 'remove'))
    p.add_argument('--out', required=True, type=Path)
    a = p.parse_args()
    out = a.out.resolve()
    assert out.parent == ROOT / 'deliverables' and out.name.startswith('za-old-probe-cleanup-')
    out.mkdir(exist_ok=True)
    nas = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port') / out.name
    c = r.Console()
    try:
        (prepare if a.op == 'prepare' else remove)(c, out, nas)
    finally:
        c.close()


if __name__ == '__main__':
    main()
