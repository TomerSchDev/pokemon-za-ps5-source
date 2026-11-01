"""Stage the exact reviewed archive while leaving the running launcher and save intact."""
from pathlib import Path
import hashlib,json,sys,time,zipfile,shutil,ftplib
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT.parents[1]/'Pokemon-ZA-Native-Port'))
import run_r3 as api
OUT=ROOT/'console-install-20261030'
APP='/data/homebrew/PPSA91762'
SHA='c65d58dd131f882895c00d1cdde94b8de994936613df6e0a9c5406abe095bd3c'
REMOTE=APP+'/models995-package-r1.zip'

def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    local=ROOT/'deliveries/Pokemon-ZA-995-Species-Experimental-20261030-r1.zip'
    assert sha(local)==SHA
    backup=OUT/'Console-before-models995-20261030.zip'
    if not backup.exists():
        with zipfile.ZipFile(backup,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
            for name in ('active-before.json','report-before.json','save-before.main'):
                z.write(OUT/name,name)
            for p in (OUT/'native-tables-before').rglob('*'):
                if p.is_file():z.write(p,p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(backup) as z:assert z.testzip() is None
    nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\20261030-v1\Console-Install-20261030')
    nas.mkdir(parents=True,exist_ok=True);dest=nas/backup.name
    if not dest.exists():shutil.copyfile(backup,dest)
    assert sha(backup)==sha(dest)
    print('Current console save/tables backup verified on NAS',flush=True)
    c=api.Console()
    try:
        assert c.sha256(APP+'/eboot.bin')=='65f6745f29d46d77da95cf56362874b71460cc0e70fca36c5e23825b60344568'
        assert c.sha256(APP+'/game/exefs/main')=='2308530d73b7fea60bb845ad57d9b1f10d3ff213f89c01f73627dc8224f43ef9'
        manifest=OUT/'models995.manifest.bin'
        target=APP+'/models995.manifest.bin'
        if c.sha256(target)!=sha(manifest):
            with manifest.open('rb') as f:c.ftp.storbinary('STOR '+target+'.part',f,1<<20)
            assert c.sha256(target+'.part')==sha(manifest)
            c.ftp.rename(target+'.part',target)
        try:size=c.ftp.size(REMOTE)
        except ftplib.error_perm as e:
            if not str(e).startswith('550'):raise
            size=None
        if size is not None:
            assert size==local.stat().st_size and c.sha256(REMOTE)==SHA
        else:
            done=0;last=0;start=time.monotonic()
            def progress(chunk):
                nonlocal done,last
                done+=len(chunk)
                if done-last>=64<<20:
                    print('UPLOAD',done,'/',local.stat().st_size,'bytes',round(done/(time.monotonic()-start)/2**20,1),'MiB/s',flush=True);last=done
            with local.open('rb') as f:c.ftp.storbinary('STOR '+REMOTE+'.part',f,1<<20,callback=progress)
            print('Checking console archive SHA-256 readback...',flush=True)
            assert c.sha256(REMOTE+'.part')==SHA
            c.ftp.rename(REMOTE+'.part',REMOTE)
        result=dict(archive=REMOTE,sha256=SHA,bytes=local.stat().st_size,readback_verified=True,
                    backup=str(backup),backup_sha256=sha(backup),backup_NAS=str(dest),installed=False)
        (OUT/'stage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)
    finally:c.close()

if __name__=='__main__':main()
