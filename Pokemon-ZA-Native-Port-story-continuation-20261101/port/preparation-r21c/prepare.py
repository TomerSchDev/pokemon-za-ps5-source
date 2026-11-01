"""Copy the ready r21 snapshot; runtime sources and objects stay byte identical."""
from pathlib import Path
import hashlib,json,shutil,difflib
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
EVID=ROOT/'evidence/preparation-r21c'
BASE=Path('/home/tomer/ps5-za-native/preparation-r21b-20261028')
WORK=Path('/home/tomer/ps5-za-native/preparation-r21c-20261028')
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()
def main():
    ready=json.loads((ROOT/'evidence/preparation-r21b/ready.json').read_text())
    base_manifest=json.loads((ROOT/'evidence/preparation-r21b/preparation.json').read_text())
    for r,h in base_manifest['runtime_sources'].items():assert sha(BASE/'source/runtime'/r)==h,r
    assert not WORK.exists(),'Do not overwrite another build'
    WORK.mkdir()
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r21b',WORK/'objects-r21c')
    EVID.mkdir(exist_ok=True)
    manifest={'base':str(BASE),'work':str(WORK),'base_eboot_sha256':ready['eboot']['sha256'],
       'runtime_sources':base_manifest['runtime_sources'],
       'runtime_objects':{str(p.relative_to(BASE/'source/build/ps5/rt')):sha(p) for p in (BASE/'source/build/ps5/rt').rglob('*.o')},
       'extra_objects':{p.name:sha(p) for p in (BASE/'objects-r21b').glob('*.o')}}
    (EVID/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n')
    patch=[]
    for old,new in [('observer-r21b.c','observer-r21c.c'),('client.py','client.py'),('retire-capture.inc','retire-capture.inc')]:
        a=(ROOT/'port/preparation-r21b'/old).read_text();b=(HERE/new).read_text()
        patch.extend(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='r21b/'+old,tofile='r21c/'+new))
    (EVID/'observer-r21c.patch').write_text(''.join(patch))
    print('Prepared unchanged r21 runtime at',WORK)
if __name__=='__main__':main()
