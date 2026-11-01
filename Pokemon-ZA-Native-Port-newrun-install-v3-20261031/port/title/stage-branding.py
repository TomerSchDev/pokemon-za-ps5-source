"""Back up and update only this title's known metadata and optional FPS profile."""
from pathlib import Path
import hashlib, io, json, sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r

ROOT=Path(__file__).resolve().parents[2]
if r.eboot_processes(): raise RuntimeError('Close running title before updating')
src=ROOT/'port/title/assets/branding-r13'
out=ROOT/'evidence'/('title-r13-branding-update-'+r.stamp());out.mkdir()
record={'title':'PPSA91761','files':[],'database_name_refresh_pending':True}
c=r.Console()
try:
    folders=['/data/homebrew/PPSA91761/sce_sys','/user/appmeta/PPSA91761','/user/app/PPSA91761/sce_sys']
    plan=[(folder+'/'+name,src/name) for folder in folders for name in ['icon0.png','pic0.dds','pic1.dds','param.json']]
    plan += [('/system_data/priv/appmeta/PPSA91761/param.json',src/'param.json'),('/user/app/PPSA91761/icon0.png',src/'icon0.png')]
    # Inspect and save all old files before the first replacement.
    old={}
    for remote,local in plan:
        data=c.read(remote,32<<20)
        if data is None: raise RuntimeError('Expected metadata missing: '+remote)
        if remote.endswith('param.json') and json.loads(data)['titleId']!='PPSA91761':
            raise RuntimeError('Unexpected title identity')
        old[remote]=data
        (out/remote.strip('/').replace('/','__')).write_bytes(data)
    for remote,local in plan:
        data=local.read_bytes(); sha=hashlib.sha256(data).hexdigest()
        if data!=old[remote]:
            c.ftp.storbinary('STOR '+remote+'.za-r13-new',io.BytesIO(data),1<<20)
            if c.sha256(remote+'.za-r13-new')!=sha: raise RuntimeError('Temp readback mismatch')
            c.ftp.rename(remote+'.za-r13-new',remote)
            c.ftp.sendcmd('SITE CHMOD 644 '+remote)
        if c.sha256(remote)!=sha: raise RuntimeError('Readback mismatch')
        record['files'].append({'remote':remote,'before_sha256':hashlib.sha256(old[remote]).hexdigest(),'sha256':sha})
        (out/'manifest.json').write_text(json.dumps(record,indent=2))
    profile='/data/homebrew/PPSA91761/performance-profile.txt'
    previous=c.read(profile,1024)
    if previous: (out/'performance-profile.before.txt').write_bytes(previous)
    c.ftp.storbinary('STOR '+profile+'.new',io.BytesIO(b'60-auto\n'))
    if c.read(profile+'.new')!=b'60-auto\n': raise RuntimeError('Profile verification failed')
    c.ftp.rename(profile+'.new',profile);c.ftp.sendcmd('SITE CHMOD 644 '+profile)
    record['profile']='60-auto';record['verified']=c.read(profile)==b'60-auto\n'
    (out/'manifest.json').write_text(json.dumps(record,indent=2))
    print(json.dumps({'evidence':str(out),'verified_files':len(record['files']),'profile':record['profile']}))
finally:c.close()
