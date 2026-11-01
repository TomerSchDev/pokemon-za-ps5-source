"""Merge independently audited exact source variants into the offline compile queue."""
from pathlib import Path
import hashlib,json
from forecast import ROOT
from translate_all import WORK,cache_hash


def main():
    ev=ROOT/'evidence/offline-shaders-20261028'
    extra=json.loads((ev/'audit-extra-sources.json').read_bytes())
    assert extra['complete']
    journal=WORK/'translation-journal.jsonl'
    known={}
    for line in journal.read_text().splitlines():
        item=json.loads(line)
        if item.get('key'): known[item['key']]=item['source_sha256']
    added=[];preserved=[]
    with journal.open('a',buffering=1) as stream:
        for item in extra['records']:
            data=Path(item['source_path']).read_bytes();key=item['key']
            assert hashlib.sha256(data).hexdigest()==item['source_sha256']
            assert cache_hash(data,item['stage'])==key
            if key in known:
                assert known[key]==item['source_sha256'];preserved.append(key);continue
            dest=WORK/'sources'/(key+'.'+item['ext'])
            if dest.exists():assert dest.read_bytes()==data
            else:dest.write_bytes(data)
            stream.write(json.dumps(item)+'\n');known[key]=item['source_sha256'];added.append(key)
    report=dict(complete=True,added=added,preserved=preserved,total_unique_sources=len(known),
                extra_translation_failures=len(extra['failures']))
    (ev/'audit-merge.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:len(v) if isinstance(v,list) else v for k,v in report.items()}))


if __name__=='__main__':main()
