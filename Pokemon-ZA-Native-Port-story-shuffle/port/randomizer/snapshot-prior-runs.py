"""Read-only integrity check and save backup for the two pre-r8 test runs."""
from pathlib import Path
import hashlib,json,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r

base='/mnt/sandbox/PPSA91762_000/download0/zarecomp/rando/'
out=r.EVIDENCE/('randomizer-prior-runs-'+r.stamp());out.mkdir()
origins=['randomizer-run-20261027-204242Z','randomizer-run-20261027-205658Z']
records=[];c=r.Console()
try:
    for origin in origins:
        expected_raw=(r.EVIDENCE/origin/'report.json').read_bytes()
        expected=json.loads(expected_raw);run=expected['native_run_id']
        assert re.fullmatch(r'r[0-9a-f]{16}-[0-9a-f]{8}',run)
        raw=c.read(base+run+'/report.json',1<<20)
        assert raw==expected_raw,'Prior run report changed or missing: '+run
        dest=out/run;dest.mkdir();(dest/'report.json').write_bytes(raw)
        for row in expected['native_tables']:
            rel=row['path'];assert '..' not in rel and not rel.startswith('/') and '\\' not in rel
            assert c.sha256(base+run+'/romfs/'+rel)==row['sha256'],rel
        save_path=base+run+'/save/save_0/main'
        data=c.read(save_path,16<<20);assert data,'Save missing: '+run
        digest=hashlib.sha256(data).hexdigest()
        readback=c.sha256(save_path)
        assert readback is not None,'Sandbox became unavailable during backup: '+run
        assert readback==digest,'Save changed during backup: '+run
        (dest/'main').write_bytes(data)
        records.append({'run':run,'seed':expected['seed'],'report_unchanged':True,
                        'tables_verified':len(expected['native_tables']),
                        'save_bytes':len(data),'save_sha256':digest,'double_read_verified':True})
finally:c.close()
receipt={'utc':r.utc_now(),'title':'PPSA91762','runs':records}
(out/'verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
print(json.dumps(receipt,indent=2));print(out)
