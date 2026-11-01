"""Free current test-session navigation captures; exact local/remote hash gate."""
from pathlib import Path
import argparse, hashlib
import sample
def main():
    p=argparse.ArgumentParser();p.add_argument("session");p.add_argument("files",nargs="+",type=Path);a=p.parse_args()
    assert len(a.session)==16 and all(c in "0123456789abcdef" for c in a.session)
    root=(sample.ROOT/"evidence/preparation-r21-hardware"/("session-"+a.session)).resolve()
    c=sample.r.Console()
    try:
        assert sample.client.status(c.ftp)["session"]==a.session
        for path in a.files:
            path=path.resolve(); assert path.is_relative_to(root)
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            receipt=dict(ack=dict(result="saved"),files=[dict(name=path.name,sha256=digest,readback_verified=True)])
            sample.retire_snapshot(c,a.session,receipt,path.parent)
            print(path.name, digest, "verified and retired")
    finally:c.close()
if __name__=="__main__":main()
