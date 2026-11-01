"""Add validated, absent SPIR-V keys. Never overwrite an existing console key."""
from pathlib import Path
import ftplib,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
root=Path(__file__).resolve().parents[2]
if r.eboot_processes(): raise RuntimeError('Close titles before the cache merge')
validation=json.loads((root/'evidence/title-r14-pc-shader-validation.json').read_text())
out=root/'evidence'/('title-r14-pc-shader-delivery-'+r.stamp()+'.json')
report={'uploaded':[],'existing_preserved':[],'utc':r.utc_now(),'complete':False}
c=r.Console()
try:
    remote='/data/homebrew/PPSA91761/cache/spirv'
    c.ftp.cwd(remote);existing={n for n,f in c.ftp.mlsd() if f.get('type')=='file'}
    for name in validation['keys']:
        if name in existing:report['existing_preserved'].append(name);continue
        p=root/'artifacts/title-r14-pc-shaders'/name;sha=hashlib.sha256(p.read_bytes()).hexdigest()
        tmp=remote+'/'+name+'.pc-new'
        with p.open('rb') as f:c.ftp.storbinary('STOR '+tmp,f,1<<20)
        if c.sha256(tmp)!=sha:raise RuntimeError('Readback failed: '+name)
        c.ftp.rename(tmp,remote+'/'+name);c.ftp.sendcmd('SITE CHMOD 644 '+remote+'/'+name)
        report['uploaded'].append({'name':name,'sha256':sha})
        if len(report['uploaded'])%50==0:r.log('Verified new PC shaders: '+str(len(report['uploaded'])));out.write_text(json.dumps(report,indent=2))
    report['complete']=True
    c.ftp.cwd(remote);report['total_shipped_spv']=sum(n.endswith('.spv') for n,f in c.ftp.mlsd() if f.get('type')=='file')
    out.write_text(json.dumps(report,indent=2))
    print(json.dumps({'uploaded':len(report['uploaded']),'preserved':len(report['existing_preserved']),'total':report['total_shipped_spv'],'evidence':str(out)}))
finally:c.close()
