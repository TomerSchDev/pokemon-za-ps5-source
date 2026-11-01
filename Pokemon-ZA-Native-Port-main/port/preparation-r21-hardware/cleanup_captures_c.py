"""Retire only locally preserved, exact-hash-matching observer PNG captures."""
import argparse, hashlib, json, re, sys, time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT)); import run_r3 as r
sys.path.insert(0,str(ROOT/'port/preparation-r21c')); import client
import console as ownership

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--session',required=True);p.add_argument('--pid',type=int,required=True)
    p.add_argument('--seq',type=int,required=True);p.add_argument('--limit',type=int,default=12,choices=range(1,21))
    a=p.parse_args(); c=r.Console(); receipts=[]; total=0; seq=a.seq
    out=ROOT/'evidence/preparation-r21-hardware'/('capture-cleanup-'+r.stamp())
    out.mkdir(parents=True,exist_ok=False)
    try:
        run=ownership.check(c,client,a.session,a.pid)
        owner=json.loads((ownership.H/('session-'+a.session)/'identity.json').read_text())
        assert owner['run']==run and owner['pid']==a.pid and owner['backup_verified']
        candidates=[]
        for folder in ('submission-r20b-hardware','preparation-r21-hardware'):
            for path in sorted((ROOT/'evidence'/folder).glob('session-*/*/frame_*_*.png')):
                sid=re.fullmatch(r'session-([a-f0-9]{16})',path.parent.parent.name)
                name=re.fullmatch(r'frame_([0-9]+)_([0-9]+)\.png',path.name)
                if sid and name and path.stat().st_size>1000000:
                    candidates.append((path,sid[1],int(name[2])))
        for path,sid,targetseq in candidates:
            if len(receipts)>=a.limit:break
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            remote=client.BASE+'/session_'+sid+'/'+path.name
            remote_hash=c.sha256(remote)
            if remote_hash is None:continue
            assert remote_hash==digest, ('Capture differs; keep it',remote)
            token=f'{sid}:{targetseq}'
            client.issue(c.ftp,a.session,seq,'retire_capture',token)
            deadline=time.monotonic()+15
            while True:
                try:
                    record=client.collect(c.ftp,a.session,seq,out,expected_retire_capture=token)
                    break
                except r.ftplib.error_perm as e:
                    if not str(e).startswith('550') or time.monotonic()>deadline:raise
                    time.sleep(.3)
            assert record['ack']['result']=='retired',record
            assert c.sha256(remote) is None
            record.update(local=str(path),sha256=digest,bytes=path.stat().st_size,remote=remote)
            receipts.append(record);total+=path.stat().st_size;seq+=1
            (out/'receipt.json').write_text(json.dumps(dict(session=a.session,run=run,bytes_freed=total,next_seq=seq,files=receipts),indent=2)+'\n')
            print(json.dumps(dict(retired=path.name,bytes_freed=total,next_seq=seq)),flush=True)
        ownership.check(c,client,a.session,a.pid)
        print(out)
    finally:c.close()
if __name__=='__main__':main()
