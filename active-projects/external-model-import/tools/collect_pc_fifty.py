"""Publish only actual PC screenshots and run metadata, with content verification."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,re,shutil,sys

def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def main():
    name=sys.argv[1]
    assert re.fullmatch(r'pc-fifty-[a-z0-9-]+',name)
    lab=Path(__file__).resolve().parents[3]
    source=lab/'hebrew-lab/runs'/name
    record=json.loads((source/'run.json').read_text())
    assert 'finished_utc' in record,'Wait until the bounded run finishes.'
    dest=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1')/name
    captures=[];rejected=[]
    for rel in record['captured_files']:
        candidate=source/rel
        if candidate.is_file() and candidate.stat().st_size>12 and candidate.read_bytes()[-8:]==b'IEND\xaeB`\x82':captures.append(rel)
        else:rejected.append({'path':rel,'reason':'PNG incomplete or absent; not accepted as evidence'})
    files=['run.json','stderr.log']+captures
    files += [name for name in ('controlled-stop.json','live-controls.jsonl','live-paused.json','queue-handoff.json','queue-handoff-result.json','reads.log') if (source/name).is_file()]
    files += [str(p.relative_to(source)) for p in sorted((source/'build').glob('profile-*.json'))]
    evidence=[]
    for rel in files:
        relative=Path(rel)
        assert not relative.is_absolute() and '..' not in relative.parts
        src=source/relative
        expected=sha(src)
        target=dest/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists() and sha(target)!=expected:
            target=target.with_name(target.stem+'-'+expected[:12]+target.suffix)
        if not target.exists():shutil.copyfile(src,target)
        assert sha(target)==expected
        evidence.append({'source':str(src),'nas':str(target),'bytes':src.stat().st_size,'sha256':expected})
    manifest={'PC_only':True,'run':name,'copied_utc':datetime.now(timezone.utc).isoformat(),
              'screenshots':len(captures),'rejected_captures':rejected,'sha256_verified':True,'files':evidence,
              'combat_pass_inferred_from_inputs':False,'review_required':True}
    receipt=source/'nas-copy.json'
    receipt.write_text(json.dumps(manifest,indent=1),encoding='utf-8')
    target=dest/'nas-copy.json'
    if target.exists() and sha(target)!=sha(receipt):target=dest/('nas-copy-'+sha(receipt)[:12]+'.json')
    if not target.exists():shutil.copyfile(receipt,target)
    assert sha(target)==sha(receipt)
    print(json.dumps({'run':name,'images':manifest['screenshots'],'nas':str(dest),'sha256_verified':True}),flush=True)

if __name__=='__main__':main()
