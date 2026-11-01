"""Stage and, separately, publish NEW PPSA91762. Never replaces PPSA91761."""
from pathlib import Path
import argparse,ftplib,hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r
ROOT=Path(__file__).resolve().parents[2]
STAGE='/data/.za-native-randomizer-r1/PPSA91762'
FINAL='/data/homebrew/PPSA91762'

def main():
    p=argparse.ArgumentParser();p.add_argument('revision');p.add_argument('--publish',action='store_true');a=p.parse_args()
    if not a.revision.startswith('r') or not a.revision[1:].isdigit():raise ValueError('Invalid revision')
    app=ROOT/'artifacts'/('randomizer-'+a.revision)/'PPSA91762'
    record=ROOT/'evidence'/('randomizer-'+a.revision+'-stage.json')
    meta=json.loads((app/'sce_sys/param.json').read_text())
    assert meta['titleId']=='PPSA91762'
    c=r.Console()
    try:
        if 'PPSA91762' in c.listing('/data/homebrew'):raise RuntimeError('Title already exists; refusing to replace it')
        if c.read('/user/app/PPSA91762/mount.lnk') is not None:raise RuntimeError('Title ID already registered')
        if a.publish:
            if r.eboot_processes():raise RuntimeError('Close running game before publishing and launch')
            report=json.loads(record.read_text());assert report['complete'] and not report['published']
            copylog=c.read('/data/za-randomizer-copy.log') or b''
            if b'COMPLETE all six files verified' not in copylog:raise RuntimeError('Game data copy not complete')
            (ROOT/'evidence/randomizer-game-copy-verified.log').write_bytes(copylog)
            eboot=next(x for x in report['files'] if x['path']=='eboot.bin')
            assert c.sha256(STAGE+'/eboot.bin')==eboot['sha256']
            c.ftp.rename(STAGE,FINAL)
            assert json.loads(c.read(FINAL+'/sce_sys/param.json'))['titleId']=='PPSA91762'
            report['published']=True;report['published_utc']=r.utc_now();record.write_text(json.dumps(report,indent=2))
            r.log('Published separate title PPSA91762');return
        c.ftp.cwd(STAGE)
        report={'title':'PPSA91762','revision':a.revision,'utc':r.utc_now(),'complete':False,'published':False,'files':[]}
        made={''}
        files=sorted(x for x in app.rglob('*') if x.is_file())
        for index,src in enumerate(files,1):
            rel=src.relative_to(app).as_posix()
            for i in range(1,len(rel.split('/'))):
                folder='/'.join(rel.split('/')[:i])
                if folder not in made:
                    try:c.ftp.mkd(STAGE+'/'+folder)
                    except ftplib.error_perm:c.ftp.cwd(STAGE+'/'+folder)
                    c.chmod(STAGE+'/'+folder,'755');made.add(folder)
            remote=STAGE+'/'+rel
            with src.open('rb') as f:sha=hashlib.file_digest(f,'sha256').hexdigest()
            existing=c.sha256(remote)
            if existing and existing!=sha:raise RuntimeError('Different staging file preserved: '+rel)
            if not existing:
                with src.open('rb') as f:c.ftp.storbinary('STOR '+remote+'.new',f,1<<20)
                if c.sha256(remote+'.new')!=sha:raise RuntimeError('Readback mismatch: '+rel)
                c.ftp.rename(remote+'.new',remote)
                c.chmod(remote,'755' if rel=='eboot.bin' or src.suffix=='.prx' else '644')
            report['files'].append({'path':rel,'bytes':src.stat().st_size,'sha256':sha})
            if index%100==0 or rel=='eboot.bin':
                record.write_text(json.dumps(report,indent=2));r.log(f'Verified {index}/{len(files)} overlay files: '+rel)
        report['complete']=True;record.write_text(json.dumps(report,indent=2));r.log('Overlay completely staged and verified')
    finally:c.close()

if __name__=='__main__':main()
