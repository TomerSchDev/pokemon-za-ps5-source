from pathlib import Path
import json,hashlib,shutil,subprocess,os
own=Path(__file__).resolve().parents[1];build=own/'work/pc-build-05'
dest=build/'frozen';dest.mkdir(exist_ok=False)
files=['za_items.c','za_items.h','items.inc','prepare-items-hooks.py','research/source-pins.json']
for n in files:
 target=dest/n;target.parent.mkdir(exist_ok=True,parents=True);shutil.copy2(own/n,target)
record=json.loads((build/'build-result.json').read_text());env=dict(os.environ);env['PATH']='C:/msys64/ucrt64/bin;'+env['PATH']
subprocess.run(['C:/msys64/ucrt64/bin/clang.exe',*record['flags'],'-c',str(dest/'za_items.c'),'-o',str(dest/'control-za_items.o')],env=env,check=True)
assert (dest/'control-za_items.o').read_bytes()==(build/'obj/za_items.o').read_bytes(),'Core helper does not reproduce PC proof object'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
record.update(source_hashes={n:sha(dest/n) for n in files},item_helper_object_reproduced=True,diagnostic_only='PC mailbox and catalog batch calls use the production public request/pump API; no diagnostic controller in PS5')
(build/'build-result.json').write_text(json.dumps(record,indent=2));print('PC helper reproduced byte-for-byte from frozen source')
