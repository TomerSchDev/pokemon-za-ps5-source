"""Package the private app and redistributable source; verify NAS copies."""
from pathlib import Path
from datetime import datetime
import hashlib,json,shutil,zipfile

ROOT=Path(__file__).resolve().parent
stamp=datetime.now().strftime('%Y%m%d-%H%M%S')
out=ROOT.parent/'deliverables'/f'ZA-Save-Workbench-0.1.0-{stamp}'
out.mkdir(parents=True,exist_ok=False)
publish=ROOT/'publish';pkhex=ROOT/'deps/PKHeX'
nuget=Path.home()/'.nuget/packages'
copies={
    'LICENSE':pkhex/'LICENSE',
    'DOTNET-LICENSE.txt':nuget/'microsoft.netcore.app.runtime.win-x64/10.0.14/LICENSE.TXT',
    'DOTNET-THIRD-PARTY.txt':nuget/'microsoft.netcore.app.runtime.win-x64/10.0.14/THIRD-PARTY-NOTICES.TXT',
    'WINDOWSDESKTOP-LICENSE.txt':nuget/'microsoft.windowsdesktop.app.runtime.win-x64/10.0.14/LICENSE',
    'README-HE.txt':ROOT/'README-HE.txt',
    'THIRD-PARTY.txt':ROOT/'THIRD-PARTY.txt',
}
for name,path in copies.items():shutil.copy2(path,publish/name)
audit=publish/'verification';audit.mkdir(exist_ok=True)
for name in ('integration-tests.json','story-research.json'):
    shutil.copy2(ROOT/'evidence'/name,audit/name)

def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

appzip=out/'ZA-Save-Workbench-0.1.0-Windows-x64-Private.zip'
with zipfile.ZipFile(appzip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in sorted(publish.rglob('*')):
        if p.is_file():z.write(p,Path('ZA Save Workbench')/p.relative_to(publish))
sourcezip=out/'ZA-Save-Workbench-0.1.0-Source.zip'
with zipfile.ZipFile(sourcezip,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for name in ('README-HE.txt','THIRD-PARTY.txt','build.ps1','test-save-workbench.py'):
        z.write(ROOT/name,name)
    z.write(pkhex/'LICENSE','LICENSE')
    for p in sorted((ROOT/'src').glob('*')):
        if p.is_file():z.write(p,Path('src')/p.name)
    z.write(ROOT/'assets/key-names.json','assets/key-names.json')
    for name in ('Directory.Build.props','.editorconfig','icon.png','LICENSE','README.md'):
        z.write(pkhex/name,Path('vendor/PKHeX')/name)
    for p in sorted((pkhex/'PKHeX.Core').rglob('*')):
        rel=p.relative_to(pkhex)
        if p.is_file() and not {'bin','obj'}.intersection(rel.parts):z.write(p,Path('vendor/PKHeX')/rel)
    z.writestr('BUILD.txt','Install .NET SDK 10, then run build.ps1 -Publish. Private save/bookmark/run metadata and console tools are intentionally not included. Use your own decrypted main save. Source commit 8e3eb3d47bb496746c3eaa9d160329d295a5e2e5.\n')
shutil.copy2(ROOT/'README-HE.txt',out/'README-HE.txt')
shutil.copy2(ROOT/'evidence/story-research.json',out/'STORY-RESEARCH.json')
shutil.copy2(ROOT/'evidence/integration-tests.json',out/'VERIFICATION.json')
files={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in out.iterdir() if p.is_file()}
(out/'SHA256SUMS.txt').write_text(''.join(f'{v["sha256"]}  {k}\n' for k,v in files.items()),encoding='utf-8')
nas=Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')/out.name
try:
    nas.mkdir(parents=True,exist_ok=False)
    for p in out.iterdir():
        if not p.is_file():continue
        target=nas/p.name
        if target.exists():
            if sha(p)!=sha(target):raise RuntimeError('Existing NAS file differs: '+str(target))
        else:shutil.copy2(p,target)
        if sha(p)!=sha(target):raise RuntimeError('NAS copy hash mismatch: '+p.name)
    result={'local':str(out),'nas':str(nas),'nas_verified':True,'files':files}
except Exception as e:
    result={'local':str(out),'nas':str(nas),'nas_verified':False,'error':str(e),'files':files}
(ROOT/'evidence/delivery.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
