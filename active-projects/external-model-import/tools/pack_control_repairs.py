"""Small verified transfer pack of controller-only QA repairs, built on the NAS."""
from pathlib import Path
import hashlib,json,sys,tarfile

def main(source):
    files=sorted((source/'romfs').rglob('*'));hashes={}
    with tarfile.open(source/'controls.tar.gz','w:gz') as archive:
        for path in files:
            if not path.is_file():continue
            assert not path.is_symlink()
            relative='mods/00-native-control-fixes/romfs/'+path.relative_to(source/'romfs').as_posix()
            hashes[relative]=hashlib.sha256(path.read_bytes()).hexdigest()
            archive.add(path,arcname=relative,recursive=False)
    (source/'control-hashes.json').write_text(json.dumps(hashes),encoding='utf-8')
    print(json.dumps({'controller_files':len(hashes),'compressed_bytes':(source/'controls.tar.gz').stat().st_size}))

if __name__=='__main__':main(Path(sys.argv[1]))
