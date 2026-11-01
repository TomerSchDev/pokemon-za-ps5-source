"""Prepare an immutable local PC mod snapshot from the already verified cohort archive."""
from pathlib import Path
import hashlib,json,shutil,zipfile
from storage_paths import data_root

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    lab=Path(__file__).resolve().parents[3]
    source=data_root()/'qa/all-pokemon-20261030-r2/console-fifty-20261031-r1'
    work=lab/'pc-fifty-20261031-r1'
    assert not work.exists(),'Use a new version instead of replacing a PC test root.'
    package=json.loads((source/'model-package.json').read_text())
    archive=source/'console-fifty-models-20261031-r1.zip'
    assert sha(archive)==package['zip_sha256']
    work.mkdir()
    with zipfile.ZipFile(archive) as z:
        entries=z.infolist()
        for item in entries:
            rel=Path(item.filename)
            assert not rel.is_absolute() and '..' not in rel.parts and ':' not in item.filename and '\\' not in item.filename
            assert rel.parts[:2]==('mods','all-models')
        z.extractall(work)
    hashes={str(p.relative_to(work)).replace('\\','/'):sha(p) for p in (work/'mods').rglob('*') if p.is_file()}
    shutil.copyfile(source/'selection.json',work/'selection.json')
    record={'PC_only':True,'console_access':False,'source_archive':str(archive),'source_archive_sha256':package['zip_sha256'],
            'files':len(hashes),'uncompressed_bytes':sum(i.file_size for i in entries),'mod_hashes':hashes}
    (work/'prepared.json').write_text(json.dumps(record,indent=1),encoding='utf-8')
    print(json.dumps({'prepared':str(work),'files':len(hashes),'bytes':record['uncompressed_bytes'],'console_access':False}),flush=True)

if __name__=='__main__':main()
