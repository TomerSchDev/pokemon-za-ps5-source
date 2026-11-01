"""Package only the binary update, requested-use guide, verification and explicit source changes."""
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'evidence/r26p1-fps-menu-20261029'
DEST=ROOT/'deliverables/ZA-r26p1-FPSMenu-20261029'
NAS=Path(r'\\TheOnePiece\Software\PS5-13.60')/OUT.name
SHA='c382275b90704d50e50e57875116bd69341e6c6b9c9c4e4d43223b367e19f7fa'

def digest(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def nas_copy(path,relative):
    expected=digest(path);target=NAS/relative;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists() and digest(target)!=expected:target=target.with_name(target.stem+'-'+expected[:12]+target.suffix)
    if not target.exists():shutil.copyfile(path,target)
    assert digest(target)==expected
    return dict(local=str(path),nas=str(target),bytes=path.stat().st_size,sha256=expected,verified=True)

def archive(path,items):
    if path.exists():raise FileExistsError(path)
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        for source,name in items:z.write(source,name)
    with zipfile.ZipFile(path) as z:assert z.testzip() is None

if __name__=='__main__':
    report_path=OUT/'installation-confirmed.json'
    if not report_path.exists():report_path=OUT/'installation.json'
    report=json.loads(report_path.read_text(encoding='utf-8'))
    assert report['installed'] and report['installed_sha256']==SHA and report['hardware_trial_api_verified']
    binary=ROOT/'artifacts/randomizer-r26p1-play/PPSA91762/eboot.bin';assert digest(binary)==SHA
    DEST.mkdir(parents=True,exist_ok=True)
    guide=DEST/'README-HE.md';shutil.copyfile(ROOT/'port/perf-r26/FIX-FPS-TRIAL-HE.md',guide)
    final_text=OUT/'INSTALLATION-FINAL-HE.txt'
    verification=DEST/'INSTALLATION-HE.txt';shutil.copyfile(final_text if final_text.exists() else OUT/'INSTALLATION-HE.txt',verification)
    sums=DEST/'SHA256SUMS.txt';sums.write_text(SHA+'  PPSA91762/eboot.bin\n',encoding='ascii')
    update=DEST/'ZA-r26p1-FPS-Menu-20261029.zip'
    archive(update,[(binary,'PPSA91762/eboot.bin'),(guide,guide.name),(verification,verification.name),(sums,sums.name)])
    source=DEST/'ZA-r26p1-FPS-Menu-Source-20261029.zip'
    names=('cheats-r26.cpp','build-perf-r26p1.sh','install_r26p1.py','install_r26p.py','package_r26p1.py',
           'FIX-FPS-TRIAL-HE.md','README-HE.md','INSTALL-r26p-play-HE.md','test/test_cheats_r26.cpp','test/test-r26p.sh')
    items=[(ROOT/'port/perf-r26'/n,'port/perf-r26/'+n) for n in names]
    for n in ('tests.log','objects-vs-r26p.txt','runtime-objects-vs-r26p.txt','registration.json','imports-diff.txt','package-vs-r26p.txt','SHA256SUMS.txt','menu-callers.s'):
        items.append((ROOT/'evidence/perf-r26p1'/n,'evidence/perf-r26p1/'+n))
    items.append((report_path,'installation-confirmed.json'))
    archive(source,items)
    receipts=[nas_copy(p,Path('packages')/p.name) for p in (update,source,guide,verification,sums)]
    manifest=DEST/'delivery.json';manifest.write_text(json.dumps(dict(at=report['at'],files=receipts),ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    nas_copy(manifest,Path('packages')/manifest.name)
    print(json.dumps(dict(stage='update/source ZIPs CRC checked; NAS SHA256 copies verified',files=receipts),ensure_ascii=False),flush=True)
