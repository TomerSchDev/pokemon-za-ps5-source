"""NAS-only model package for the random console QA cohort. No executable or user save."""
from pathlib import Path
import hashlib,json,os,struct,subprocess,sys,tarfile,zipfile
from storage_paths import data_root
ROOT=data_root();QA=ROOT/'qa/all-pokemon-20261030-r2';OUT=QA/'console-fifty-20261031-r1'

def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def main():
 selected=json.loads((OUT/'selection.json').read_text())['targets']
 all_targets={}
 for s in selected:
  for model in (s['model'],s['evolution']['model']):all_targets[model['key']]=model
 inventory=json.loads((QA/'inventory-v4.json').read_text())['targets']
 for n in (10,44,46,201,722,928):
  m=next(m for m in inventory if m['national']==n and m['form']==0 and m['gender']==0);all_targets[m['key']]=m
 spec=OUT/'assets.json';spec.write_text(json.dumps({'targets':list(all_targets.values())},indent=1))
 bundle=QA/'bundles/console-fifty-20261031-r1'
 if not (bundle/'bundle.json').exists():subprocess.run([sys.executable,str(QA/'build_qa_bundle.py'),str(spec),bundle.name],check=True)
 romfs=bundle/'mods/all-models/romfs'
 folders={str(Path(m['model_path']).parent) for m in all_targets.values()}
 # Apply the same controller, form, material and texture repairs validated on PC.
 controllers=QA/'native-control-repairs-r3'
 count=0
 with tarfile.open(controllers/'controls.tar.gz','r:gz') as z:
  for member in z:
   relative=Path(member.name).relative_to('mods/00-native-control-fixes/romfs')
   if str(relative.parent).removeprefix('ik_pokemon/data/') not in folders:continue
   assert member.isfile() and '..' not in relative.parts
   target=romfs/relative;target.parent.mkdir(parents=True,exist_ok=True)
   raw=z.extractfile(member).read();temp=target.with_suffix(target.suffix+'.new');temp.write_bytes(raw);temp.replace(target);count+=1
 repair_counts={}
 for kind in ('variant-texture-repairs-r1','material-name-repairs-r1','transparency-repairs-r1'):
  repairs=QA/kind/'romfs/ik_pokemon/data';n=0
  for folder in folders:
   source=repairs/folder
   if not source.is_dir():continue
   for p in source.rglob('*'):
    if not p.is_file():continue
    relative=p.relative_to(repairs);target=romfs/'ik_pokemon/data'/relative;target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_suffix(target.suffix+'.new');temp.write_bytes(p.read_bytes());temp.replace(target);n+=1
  repair_counts[kind]=n
 cat=Path('ik_pokemon/catalog/catalog/poke_resource_table.trpmcatalog')
 target=romfs/cat;temp=target.with_suffix('.new');temp.write_bytes((QA/'form-bindings-r1/romfs'/cat).read_bytes());temp.replace(target)
 files=sorted(p for p in romfs.rglob('*') if p.is_file())
 archive=OUT/'console-fifty-models-20261031-r1.zip';manifest=OUT/'console-fifty-models-20261031-r1.manifest.bin'
 assert not archive.exists() and not manifest.exists()
 entries=[(p.relative_to(romfs).as_posix(),p.stat().st_size,sha(p)) for p in files]
 total=sum(n for _,n,_ in entries)
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
  for p in files:z.write(p,'mods/all-models/romfs/'+p.relative_to(romfs).as_posix())
 with manifest.open('xb') as out:
  out.write(b'ZAM99501'+struct.pack('<IQ',len(entries),total))
  for name,size,digest in entries:
   raw=name.encode('ascii');out.write(struct.pack('<HQ',len(raw),size)+bytes.fromhex(digest)+raw)
 report={'selected_species':50,'asset_models_including_evolutions_and_ambient_guards':len(all_targets),'controller_repairs':count,'additional_repairs':repair_counts,'files':len(files),'uncompressed_bytes':total,'zip_bytes':archive.stat().st_size,'zip_sha256':sha(archive),'manifest_sha256':sha(manifest),'source_build_modified':False,'console_installed':False,'includes_executable':False,'includes_user_save':False}
 (OUT/'model-package.json').write_text(json.dumps(report,indent=1))
 print(json.dumps(report),flush=True)

if __name__=='__main__':main()
