"""Install an immutable, content-checked controller pack in the temporary PC cache."""
import hashlib,io,json,os,tarfile
from pathlib import Path
from run_pc_gallery import QA,WORK

def main():
    source=QA/'native-control-repairs-r3'
    report=json.loads((source/'controls-report.json').read_text(encoding='utf-8'))
    assert report['staged']==833 and not report['failures']
    hashes=json.loads((source/'control-hashes.json').read_text(encoding='utf-8'))
    dest=WORK/'render-fixes';seen=set()
    with tarfile.open(fileobj=io.BytesIO((source/'controls.tar.gz').read_bytes()),mode='r:gz') as archive:
        for member in archive:
            assert member.isfile() and member.name in hashes
            relative=Path(member.name)
            assert not relative.is_absolute() and '..' not in relative.parts and ':' not in member.name and chr(92) not in member.name
            payload=archive.extractfile(member).read()
            assert hashlib.sha256(payload).hexdigest()==hashes[member.name]
            target=dest/relative;target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():assert target.read_bytes()==payload
            else:
                temp=target.with_name(target.name+'.qa-new');temp.write_bytes(payload);os.replace(temp,target)
            seen.add(member.name)
    assert seen==set(hashes)
    certificate=dest/'verified-hashes.json';current=json.loads(certificate.read_text(encoding='utf-8'))
    current.update(hashes);temp=certificate.with_suffix('.qa-new')
    temp.write_text(json.dumps(current),encoding='utf-8');os.replace(temp,certificate)
    print('Installed %d content-checked controller-only QA files; original game/build untouched.'%len(hashes),flush=True)

if __name__=='__main__':main()
