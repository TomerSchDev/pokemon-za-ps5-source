"""Prepare an isolated observer-only r23b snapshot; never modify r23."""
from pathlib import Path
import hashlib,json,shutil
ROOT=Path(__file__).resolve().parents[2]
EVID=ROOT/'evidence/slot-depth-r23b'
BASE=Path('/home/tomer/ps5-za-native/slot-depth-r23-20261028')
WORK=Path('/home/tomer/ps5-za-native/slot-depth-r23b-20261028')

def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()

def main():
    ready=json.loads((ROOT/'evidence/slot-depth-r23/ready.json').read_text())
    pin=json.loads((ROOT/'evidence/slot-depth-r23/preparation.json').read_text())
    assert ready['eboot']['sha256']=='e89613683ab551fcbd4854bf08891db7defd5046ceb906b7438fcf517136104b'
    for rel,h in pin['candidate_runtime_sources'].items():assert sha(BASE/'source/runtime'/rel)==h,rel
    assert not WORK.exists() and not EVID.exists(),'Do not overwrite an earlier build'
    EVID.mkdir(parents=True)
    manifest={'base':str(BASE),'work':str(WORK),'base_eboot_sha256':ready['eboot']['sha256'],
        'runtime_sources':pin['candidate_runtime_sources'],
        'runtime_objects':{str(p.relative_to(BASE/'source/build/ps5/rt')):sha(p) for p in (BASE/'source/build/ps5/rt').rglob('*.o')},
        'extra_objects':{p.name:sha(p) for p in (BASE/'objects-r23').glob('*.o')}}
    (EVID/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r23',WORK/'objects-r23b')
    print('Prepared unchanged r23 runtime at',WORK)

if __name__=='__main__':main()
