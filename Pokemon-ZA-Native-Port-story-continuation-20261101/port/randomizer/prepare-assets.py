from pathlib import Path
import hashlib,json,sys
source=Path(sys.argv[1]);destination=Path(sys.argv[2]);destination.mkdir(parents=True,exist_ok=True)
manifest={}
for p in sorted(source.iterdir()):
    if not p.is_file() or p.suffix not in {'.json','.bin'}:continue
    data=p.read_bytes();digest=hashlib.sha256(data).hexdigest();q=destination/p.name
    if q.exists():assert hashlib.sha256(q.read_bytes()).hexdigest()==digest,p.name
    else:q.write_bytes(data)
    manifest[p.name]={'bytes':len(data),'sha256':digest}
for p in sorted((Path(__file__).parent/'reward-assets').iterdir()):
    if not p.is_file() or p.suffix not in {'.json','.bin'}:continue
    data=p.read_bytes();digest=hashlib.sha256(data).hexdigest();q=destination/p.name
    if q.exists():assert hashlib.sha256(q.read_bytes()).hexdigest()==digest,p.name
    else:q.write_bytes(data)
    manifest[p.name]={'bytes':len(data),'sha256':digest}
header=Path(sys.argv[3])
header.write_text('#define ZA_TABLES_SHA256 "'+manifest['tables.json']['sha256']+'"\n#define ZA_STARTERS_SHA256 "'+manifest['starter-deltas.json']['sha256']+'"\n#define ZA_REWARDS_SHA256 "'+manifest['research-rewards.json']['sha256']+'"\n')
with header.open('a') as f:f.write('#define ZA_PROGRESSION_SHA256 "'+manifest['progression.json']['sha256']+'"\n')
(destination/'asset-manifest.json').write_text(json.dumps(manifest,indent=2))
print('Prepared',len(manifest),'immutable input assets')
