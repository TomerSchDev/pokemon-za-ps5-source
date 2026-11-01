"""Stage two pinned reward assets for the owned title while no game is running."""
from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
assert not r.eboot_processes(),'A game is running'
app=r.ROOT/'artifacts/randomizer-r8/PPSA91762/randomizer-assets'
remote='/data/homebrew/PPSA91762/randomizer-assets/'
manifest=json.loads((app/'asset-manifest.json').read_text());records=[];c=r.Console()
try:
    for name in ['research-rewards.bin','research-rewards.json']:
        data=(app/name).read_bytes();sha=hashlib.sha256(data).hexdigest();assert sha==manifest[name]['sha256']
        previous=c.read(remote+name)
        if previous is not None:assert previous==data,'Different reward assets already exist'
        else:c.store(remote+name,data)
        assert c.sha256(remote+name)==sha
        records.append({'path':remote+name,'bytes':len(data),'sha256':sha})
    previous=c.read(remote+'asset-manifest.json')
    if previous:
        backup=remote+'asset-manifest-before-r8-'+hashlib.sha256(previous).hexdigest()[:16]+'.json'
        existing=c.read(backup)
        if existing is None:c.store(backup,previous)
        else:assert existing==previous
    data=(app/'asset-manifest.json').read_bytes();c.store(remote+'asset-manifest.json.new',data)
    assert c.sha256(remote+'asset-manifest.json.new')==hashlib.sha256(data).hexdigest()
    c.ftp.rename(remote+'asset-manifest.json.new',remote+'asset-manifest.json')
    assert c.sha256(remote+'asset-manifest.json')==hashlib.sha256(data).hexdigest()
finally:c.close()
receipt={'utc':r.utc_now(),'title':'PPSA91762','files':records,'verified':True}
(r.EVIDENCE/'randomizer-reward-assets-staged.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8');print(receipt)
