"""Versioned asset update for PPSA91762 only, while no title is running."""
from pathlib import Path
import hashlib,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
revision=sys.argv[1];assert re.fullmatch(r'r[0-9]+',revision)
assert not r.eboot_processes(),'Close active game before asset update'
app=r.ROOT/'artifacts'/('randomizer-'+revision)/'PPSA91762/randomizer-assets'
remote='/data/homebrew/PPSA91762/randomizer-assets/'
manifest=json.loads((app/'asset-manifest.json').read_text());c=r.Console();records=[]
try:
    for name in ['research-rewards.bin','research-rewards.json','progression-wild.bin','progression.json','asset-manifest.json']:
        data=(app/name).read_bytes();sha=hashlib.sha256(data).hexdigest()
        if name!='asset-manifest.json':assert sha==manifest[name]['sha256']
        previous=c.read(remote+name)
        if previous==data:records.append({'name':name,'sha256':sha,'unchanged':True});continue
        backup=None
        if previous is not None:
            backup=remote+name+'.before-'+revision+'-'+hashlib.sha256(previous).hexdigest()[:16]
            old=c.read(backup)
            if old is None:c.store(backup,previous)
            else:assert old==previous
            assert c.sha256(backup)==hashlib.sha256(previous).hexdigest()
        c.store(remote+name+'.new',data);assert c.sha256(remote+name+'.new')==sha
        c.ftp.rename(remote+name+'.new',remote+name)
        assert c.sha256(remote+name)==sha
        records.append({'name':name,'sha256':sha,'backup':backup})
finally:c.close()
report={'utc':r.utc_now(),'title':'PPSA91762','revision':revision,'verified':True,'records':records}
(r.EVIDENCE/('randomizer-'+revision+'-assets-updated.json')).write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
