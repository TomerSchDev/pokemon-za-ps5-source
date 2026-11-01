from pathlib import Path
import sys,shutil,json,hashlib,tarfile,os,threading,time
from compression import zstd
from storage_paths import data_root
ROOT=data_root();sys.path.insert(0,str(ROOT.parent/'pilot/tools'));import run_pilot
WORK=Path(__file__).resolve().parents[3]/'pc-model-tests'
run_pilot.PILOT=WORK;run_pilot.EXE=WORK/'runtime/lasrecomp.exe'
if "--game" in sys.argv:
 at=sys.argv.index("--game");run_pilot.GAME=Path(sys.argv[at+1]);del sys.argv[at:at+2]
elif (WORK/'runtime/temporary-game-cache.json').exists():
 cache=json.loads((WORK/'runtime/temporary-game-cache.json').read_text(encoding='utf-8'))
 source_stat=Path(cache['source']).stat()
 assert source_stat.st_size==cache['size'] and source_stat.st_mtime_ns==cache['mtime_ns']
 assert (WORK/'runtime/romfs.bin').stat().st_size==cache['size']
 run_pilot.GAME=WORK/'runtime'
name=sys.argv[1];assert '/' not in name and chr(92) not in name and name not in ('.','..')
prepare_only='--prepare-only' in sys.argv
if prepare_only:sys.argv.remove('--prepare-only')
capture_termination={'completed':False,'loader_stall':None}
model_watch=None
if '--watch-models' in sys.argv:
 at=sys.argv.index('--watch-models');watch_spec=Path(sys.argv[at+1]);del sys.argv[at:at+2]
 assert watch_spec.resolve().is_relative_to((ROOT/'qa/all-pokemon-20261030-r2').resolve())
 model_watch=json.loads(watch_spec.read_text(encoding='utf-8'))
 sys.path.insert(0,str(ROOT/'qa/python-lib'))
 from PIL import Image,ImageChops
 from pc_body_panel import load_empty_panels,pixels_from_empty,BODY_BOX
 empty_panels=load_empty_panels(ROOT/'qa/runs')
if '--stop-after-shots' in sys.argv:
 sys.argv.remove('--stop-after-shots')
 shot_list=sys.argv[sys.argv.index('--shot-at')+1]
 last_shot=WORK/'runs'/name/'build/frames'/('frame_%05d.png'%int(shot_list.split(',')[-1]))
 original_popen=run_pilot.subprocess.Popen
 def watched_popen(*args,**kwargs):
  proc=original_popen(*args,**kwargs)
  def watch():
   next_pair=0;previous_empty=False
   def complete_png(path):
    try:
     with path.open('rb') as f:f.seek(-12,2);return f.read()==bytes.fromhex('0000000049454e44ae426082')
    except (OSError,ValueError):return False
   while proc.poll() is None:
    complete=complete_png(last_shot)
    if complete:
     time.sleep(.5)
     if proc.poll() is None:
      capture_termination['completed']=True
      try:proc.terminate()
      except OSError:pass
     return
    if model_watch and next_pair<len(model_watch['body_frame_pairs']):
     pair=model_watch['body_frame_pairs'][next_pair]
     paths=[WORK/'runs'/name/'build/frames'/('frame_%05d.png'%n) for n in pair]
     if all(complete_png(p) for p in paths):
      try:
       with Image.open(paths[0]) as frame:body=frame.convert('RGB').crop((260,320,950,950))
       is_empty=pixels_from_empty(body,empty_panels)<500
       if is_empty and previous_empty:
        target=model_watch['targets'][next_pair]
        log=(WORK/'runs'/name/'stderr.log').read_text(encoding='utf-8',errors='replace')
        if ('ik_pokemon/data/'+target['model_path']) not in log:
         fault=next_pair-1
         capture_termination['loader_stall']={'index':fault,'key':model_watch['targets'][fault]['key']}
         try:proc.terminate()
         except OSError:pass
         return
       previous_empty=is_empty;next_pair+=1
      except OSError:pass
    time.sleep(.5)
  threading.Thread(target=watch,daemon=True).start()
  return proc
 run_pilot.subprocess.Popen=watched_popen
game_lib='LARECOMP_GAME_LIB='+str(WORK/'runtime/lasgame.dll')
if '--env' in sys.argv:
 at=sys.argv.index('--env')+1
 while at<len(sys.argv) and not sys.argv[at].startswith('--'):at+=1
 sys.argv.insert(at,game_lib)
else:sys.argv += ['--env',game_lib]
if '--bundle' in sys.argv:
 at=sys.argv.index('--bundle');bundle=Path(sys.argv[at+1]);del sys.argv[at:at+2]
 assert bundle.resolve().is_relative_to((ROOT/'qa/all-pokemon-20261030-r2/bundles').resolve())
 if '--wait-bundle-ready' in sys.argv:
  sys.argv.remove('--wait-bundle-ready');deadline=time.monotonic()+900
  while not (bundle/'bundle.json').exists():
   assert time.monotonic()<deadline,'NAS bundle build did not finish'
   print('Waiting for complete NAS bundle '+bundle.name,flush=True);time.sleep(20)
 prepared=WORK/'prepared'/name;assert not prepared.exists();prepared.mkdir(parents=True)
 hashes=json.loads((bundle/'mod-hashes.json').read_text(encoding='utf-8'))
 common=WORK/'common-mods';certificate=common/'verified-hashes.json'
 common_hashes=json.loads(certificate.read_text(encoding='utf-8')) if certificate.exists() else {}
 shared=set()
 with zstd.ZstdFile(bundle/'payload.tar.zst','rb') as stream,tarfile.open(fileobj=stream,mode='r|') as archive:
  for member in archive:
   assert (member.isfile() or member.isdir()) and not member.name.startswith('/') and ':' not in member.name and chr(92) not in member.name and '..' not in Path(member.name).parts
   if member.isfile() and member.name in common_hashes and hashes.get(member.name)==common_hashes[member.name]:
    target=prepared/member.name;target.parent.mkdir(parents=True,exist_ok=True)
    os.link(common/member.name,target);shared.add(member.name)
   else:archive.extract(member,prepared,filter='data')
 for rel,expected in hashes.items():
  if rel in shared:continue  # Immutable, already content-checked shared QA assets; runtime reads only.
  path=prepared/rel
  with path.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==expected,'Bundle content mismatch: '+rel
 # The Test save retains ambient Pokémon in its loaded zone. Keep their six
 # already-validated models available even when the box tests different species.
 for rel,expected in common_hashes.items():
  if rel in hashes:continue
  target=prepared/rel;target.parent.mkdir(parents=True,exist_ok=True)
  os.link(common/rel,target);hashes[rel]=expected
 fixes=WORK/'render-fixes'
 if (fixes/'verified-hashes.json').exists():
  for rel,expected in json.loads((fixes/'verified-hashes.json').read_text(encoding='utf-8')).items():
   assert rel not in hashes
   target=prepared/rel;target.parent.mkdir(parents=True,exist_ok=True);os.link(fixes/rel,target);hashes[rel]=expected
 run_pilot.MOD_HASH_MANIFEST=hashes
 original_copytree=run_pilot.shutil.copytree
 def staged_copy(src,dst,*args,**kwargs):
  if Path(src).resolve()==(prepared/'mods').resolve():
   assert Path(dst).resolve()==(WORK/'runs'/name/'mods').resolve() and not Path(dst).exists()
   os.rename(src,dst);return str(dst)
  return original_copytree(src,dst,*args,**kwargs)
 run_pilot.shutil.copytree=staged_copy
 sys.argv += ['--mods',str(prepared/'mods')]
 if prepare_only:
  (prepared/'verified-hashes.json').write_text(json.dumps(hashes),encoding='utf-8')
  print('Prepared verified local test assets: '+str(prepared/'mods'),flush=True)
  sys.exit(0)
elif '--link-local-mods' in sys.argv:
 at=sys.argv.index('--link-local-mods');local_mods=Path(sys.argv[at+1]);del sys.argv[at:at+2]
 assert local_mods.resolve().is_relative_to(WORK.resolve()) and local_mods.is_dir()
 original_copytree=run_pilot.shutil.copytree
 def linked_copy(src,dst,*args,**kwargs):
  is_mod_root=Path(src).resolve()==local_mods.resolve()
  if is_mod_root:kwargs['copy_function']=os.link
  result=original_copytree(src,dst,*args,**kwargs)
  fixes=WORK/'render-fixes';certificate=fixes/'verified-hashes.json'
  if is_mod_root and certificate.exists():
   assert Path(dst).resolve()==(WORK/'runs'/name/'mods').resolve()
   for rel,expected in json.loads(certificate.read_text(encoding='utf-8')).items():
    relative=Path(rel).relative_to('mods');assert '..' not in relative.parts
    target=Path(dst)/relative;target.parent.mkdir(parents=True,exist_ok=True)
    temp=target.with_name(target.name+'.qa-new');assert not temp.exists()
    os.link(fixes/rel,temp);os.replace(temp,target)
  return result
 run_pilot.shutil.copytree=linked_copy
 sys.argv += ['--mods',str(local_mods)]
run_pilot.main()
source=WORK/'runs'/name;dest=ROOT/'qa/runs'/name
assert not dest.exists();dest.mkdir(parents=True)
for f in source.rglob('*'):
 if not f.is_file() or any(part in ('cache','mods') for part in f.relative_to(source).parts):continue
 target=dest/f.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(f,target)
 with f.open('rb') as a,target.open('rb') as b:assert hashlib.file_digest(a,'sha256').digest()==hashlib.file_digest(b,'sha256').digest()
record=json.loads((dest/'run.json').read_text());record['temporary_local_profile']=str(source);record['canonical_model_and_game_data_on_NAS']=True;record['temporary_local_game_cache']=str(run_pilot.GAME) if run_pilot.GAME==WORK/'runtime' else None;record['terminated_after_requested_captures']=capture_termination['completed']
record['loader_stall_watch']=capture_termination['loader_stall']
if capture_termination['completed'] or capture_termination['loader_stall']:record['terminated_by_harness']=True
(dest/'run.json').write_text(json.dumps(record,indent=1))
print('Verified run artifacts on NAS: '+str(dest),flush=True)
