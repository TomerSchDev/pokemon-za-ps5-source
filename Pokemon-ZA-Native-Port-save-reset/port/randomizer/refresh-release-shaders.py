"""Add this title's verified helper outputs to a local release, never to the console."""
from pathlib import Path
import hashlib, json, re, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r

revision=sys.argv[1]
if not re.fullmatch(r'r[0-9]+',revision): raise ValueError('Invalid revision')
target=r.ROOT/'artifacts'/('randomizer-'+revision)/'PPSA91762/cache/spirv'
assert target.is_dir()
records={};c=r.Console()
try:
    for manifest in sorted(r.EVIDENCE.glob('randomizer-shaders-*/manifest.json')):
        for row in json.loads(manifest.read_text()):
            assert re.fullmatch(r'[0-9a-f]{16}\.(vert|frag|comp)',row['source']),row['source']
            name=row['source'].split('.')[0]+'.spv'
            candidates=list(manifest.parent.rglob(name))
            assert len(candidates)==1,(name,candidates)
            data=candidates[0].read_bytes();sha=hashlib.sha256(data).hexdigest()
            assert sha==row['spv_sha256']
            remote='/data/homebrew/PPSA91762/cache/spirv/'+name
            assert c.sha256(remote)==sha,remote
            dest=target/name
            if dest.exists():assert dest.read_bytes()==data,name
            else:dest.write_bytes(data)
            records[name]={'sha256':sha,'bytes':len(data),'console_verified':True}
finally:c.close()
receipt={'revision':revision,'utc':r.utc_now(),'entries':len(list(target.glob('*.spv'))),'helper_outputs':records}
(r.EVIDENCE/('randomizer-'+revision+'-release-shaders.json')).write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps({'entries':receipt['entries'],'verified_helper_outputs':len(records)}))
