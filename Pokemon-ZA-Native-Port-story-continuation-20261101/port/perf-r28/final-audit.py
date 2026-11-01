from pathlib import Path
import hashlib,json,subprocess,re
root=Path(__file__).resolve().parents[2]
base=Path('/home/tomer/ps5-za-native/r27b-play-20261029')
out=Path('/home/tomer/ps5-za-native/r28-play-20261030/r28')
latest=root.parent/'hebrew-lab/trial/build-r5'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
expected={p.name:p for p in (base/'objects-r27').glob('*.o')}
for n in ['cheats.o','hebrew_trial.o','hebrew_install.o']:expected[n]=latest/'objects'/n
actual={p.name:p for p in (out/'objects').glob('*.o')}
assert set(actual)==set(expected)|{'za_items.o'}
changed=sorted(n for n in expected if sha(expected[n])!=sha(actual[n]))
assert changed==['cheats.o','title_entry.o'],changed
runtime=(out/'evidence/runtime-inputs.txt').read_text().splitlines()
for n in runtime:assert sha(base/'source'/n)==sha(out.parent/'source'/n),n
proof=json.loads((out/'evidence/pc-proof.json').read_text())
for n in ['za_items.c','za_items.h','items.inc']:assert sha(out/'src'/n)==proof['source_hashes'][n],n
nm='/usr/lib/llvm-21/bin/llvm-objdump'
dump=subprocess.check_output([nm,'-d','--no-show-raw-insn','--disassemble-symbols=_ZN2za6native8bootMenuEv',str(out/'llvm-pie.elf')],text=True)
assert re.search(r'\bcallq?\s+[^\n]*<__wrap_za_observer_menu>',dump),'Observer-aware boot menu call lost'
result=dict(custom_objects_changed=changed,custom_objects_added=['za_items.o'],custom_objects_unchanged=len(expected)-2,
 runtime_objects_unchanged=len(runtime),hebrew_objects_byte_identical=True,pc_ps5_item_helper_sources_identical=True,
 observer_aware_launcher_call_preserved=True,eboot_sha256=sha(out/'eboot.bin'))
(out/'evidence/final-audit.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
