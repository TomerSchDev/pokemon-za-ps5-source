"""Package only reviewed source, city templates, UI and validation evidence."""
from pathlib import Path
import hashlib,json,shutil,zipfile
root=Path(__file__).resolve().parent; workspace=root.parents[1]
out=workspace/'deliverables/Pokemon-ZA-Quick-Start-0.1.0-20261025'
out.mkdir(exist_ok=True)
def copy(src,rel):
    dst=out/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
manifest=json.loads((root/'quickstart/templates.json').read_text())
for name,entry in manifest['starters'].items():
    assert entry['game_reload_verified'],name
    src=root/'quickstart/templates'/name/'main'
    assert hashlib.sha256(src.read_bytes()).hexdigest()==entry['sha256'],name
    copy(src,Path('templates')/name/'main')
copy(root/'quickstart/templates.json','templates.json')
copy(root/'quickstart-build/dist/ZA-Quick-Start.exe','ZA-Quick-Start.exe')
for file in ('quickstart.py','quickcore.py','test_quickcore.py'):
    copy(root/'quickstart'/file,Path('source/quickstart')/file)
copy(root/'save-lab/Program.cs','source/save-lab/Program.cs')
cs=(root/'save-lab/SaveLab.csproj').read_text().replace('../../pkhex/','../pkhex/')
(out/'source/save-lab/SaveLab.csproj').write_text(cs)
copy(workspace/'research/pkhex/LICENSE','source/save-lab/PKHeX-LICENSE.txt')
for file in ('README-HE.txt','BUILD-SOURCE.txt','CITY-FPS-HE.txt','VALIDATION.json'):
    copy(root/'quickstart'/file,file)
for src in (root/'quickstart/evidence').glob('*'):
    if src.is_file():copy(src,Path('evidence')/src.name)
records=[]
for p in sorted(out.rglob('*')):
    if not p.is_file() or p.name=='SHA256.json':continue
    records.append(dict(path=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
(out/'SHA256.json').write_text(json.dumps(records,indent=2))
archive=out.with_name(out.name+'.zip')
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as z:
    for p in sorted(out.rglob('*')):
        if p.is_file():z.write(p,str(Path(out.name)/p.relative_to(out)))
print(json.dumps(dict(folder=str(out),zip=str(archive),bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest())))
