"""Build a private, user-specific location catalogue from retained save snapshots."""
from pathlib import Path
import hashlib, json, shutil, subprocess

ROOT=Path(__file__).resolve().parent
PROJECT=ROOT.parent
DOTNET=ROOT/'deps/dotnet10/dotnet.exe'
APP=ROOT/'src/bin/Release/net10.0-windows/ZA Save Workbench.dll'
def call(*args):
    p=subprocess.run([str(DOTNET),str(APP),*map(str,args)],capture_output=True,text=True,encoding='utf-8')
    if p.returncode: raise RuntimeError(p.stdout+p.stderr)
    return json.loads(p.stdout)
def write(path, obj): path.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')

backup=PROJECT/'evidence/observer-r17-hardware/save-backup-20261028-075340Z'
current=backup/'save/save_0/main'
city=PROJECT/'evidence/randomizer-run-20261028-041247Z/main'
assets=ROOT/'assets'
(assets/'checkpoints/current').mkdir(parents=True,exist_ok=True)
shutil.copy2(current,assets/'checkpoints/current/main')
run=json.loads((backup/'active.json').read_bytes())['id']
report=json.loads((backup/'report.json').read_bytes())
bookmarks=[]; contexts={}
for path,label in [(current,'המיקום בגיבוי האחרון · מפה פנימית'),(city,'העיר בתחילת הריצה · ליד מרכז הפוקימונים')]:
    mark=call('bookmark',path,label)
    mark['Validation']='Read from an existing snapshot of this run. Transplanting this destination into the current save has not been console-tested.'
    bookmarks.append(mark)
    contexts[mark['SourceSha256']]={'RunId':run,'Seed':report['seed'],'SourceSnapshot':path.parent.name,'ExternalRandomization':'Keep existing run ROMFS and report unchanged'}
write(assets/'bookmarks.json',bookmarks)
write(assets/'source-contexts.json',contexts)
write(assets/'run-context.json',{'RunId':run,'Seed':report['seed'],'BackupUtc':'2026-10-28T07:53:40Z','SourceSaveSha256':hashlib.sha256(current.read_bytes()).hexdigest(),'Scope':'Private current-run save included; not a live console save reader.'})
print(json.dumps({'bookmarks':len(bookmarks),'run':run,'maps':[b['Position']['Map'] for b in bookmarks]}))
