from pathlib import Path,PurePosixPath
import sys,json,os,shutil,subprocess,hashlib,tarfile,re,time
ROOT=Path('/volume1/Software/Pokemon-ZA-All-Models/Workstation-Data-20261030-v1/PS5-13.60/species-lab/import-all-20261030')
QA=ROOT/'qa/all-pokemon-20261030-r2';SRC=ROOT/'build/all-species-r1/all-models/romfs'
spec=Path(sys.argv[1]);assert spec.resolve().is_relative_to(QA)
manifest=json.loads(spec.read_text());name=sys.argv[2];assert re.fullmatch('[a-z0-9-]+',name)
base=QA/'base-mods';started=time.monotonic()
def clone(a,b):
 b.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['cp','-a','--reflink=always','--',str(a),str(b)],check=True)
if not (base/'complete.json').exists():
 assert not base.exists();base.mkdir()
 for parent,dirs,files in os.walk(SRC):
  rel=Path(parent).relative_to(SRC)
  if rel==Path('ik_pokemon') and 'data' in dirs:dirs.remove('data')
  for filename in files:
   source=Path(parent)/filename;relative=source.relative_to(SRC)
   if relative.as_posix().startswith('world/ik_data/field/pokemon/encount_data/'):continue
   assert not source.is_symlink()
   clone(source,base/'mods/all-models/romfs'/relative)
 (base/'complete.json').write_text(json.dumps({'base_files':sum(1 for x in (base/'mods').rglob('*') if x.is_file())}))
bundle=QA/'bundles'/name;assert not bundle.exists();bundle.mkdir(parents=True)
clone(base/'mods',bundle/'mods')
folders=set()
for target in manifest['targets']:
 folder=PurePosixPath(target['model_path']).parent;assert not folder.is_absolute() and '..' not in folder.parts
 folders.add(folder)
 if manifest.get('include_sibling_asset_folders') and target.get('imported'):
  parent=SRC/'ik_pokemon/data'/folder.parent
  if parent.is_dir():
   for sibling in parent.iterdir():
    assert not sibling.is_symlink()
    if sibling.is_dir():folders.add(folder.parent/sibling.name)
for folder in sorted(folders):
 source=SRC/'ik_pokemon/data'/folder;dest=bundle/'mods/all-models/romfs/ik_pokemon/data'/folder
 if source.is_dir() and not dest.exists():clone(source,dest)
 for overlay_name in ('motion-overlay','rate-overlay'):
  overlay=QA/overlay_name/'romfs/ik_pokemon/data'/folder
  if overlay.is_dir():
   for patch in overlay.iterdir():
    assert patch.is_file() and not patch.is_symlink();dest.mkdir(parents=True,exist_ok=True)
    temp=dest/(patch.name+'.new');shutil.copyfile(patch,temp);os.replace(temp,dest/patch.name)
hashes={}
for f in sorted((bundle/'mods').rglob('*')):
 if not f.is_file():continue
 assert not f.is_symlink()
 with f.open('rb') as s:hashes[f.relative_to(bundle).as_posix()]=hashlib.file_digest(s,'sha256').hexdigest()
(bundle/'mod-hashes.json').write_text(json.dumps(hashes))
output=bundle/'payload.tar.zst'
with output.open('xb') as dest:
 proc=subprocess.Popen(['zstd','-T2','-1','-c'],stdin=subprocess.PIPE,stdout=dest)
 with tarfile.open(fileobj=proc.stdin,mode='w|',dereference=True) as tar:tar.add(bundle/'mods',arcname='mods')
 proc.stdin.close();assert proc.wait()==0
(bundle/'bundle.json').write_text(json.dumps({'models':len(manifest['targets']),'variant_asset_folders':len(folders),'files':len(hashes),'bytes':output.stat().st_size,'model_data_storage':'NAS','source_build_unchanged':True,'motion_overlay':'QA r2 experimental','seconds':time.monotonic()-started}))
print((bundle/'bundle.json').read_text(),flush=True)
