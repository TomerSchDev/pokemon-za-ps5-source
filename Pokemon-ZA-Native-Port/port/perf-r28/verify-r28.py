from pathlib import Path
import hashlib,importlib.util,json,subprocess,sys,re
def sha(p):
 with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
 if not ok:raise RuntimeError(msg)
def load_module(project):
 spec=importlib.util.spec_from_file_location('old',project/'port/perf-r27/verify-r27-build.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);return old
mode=sys.argv[1]
if mode=='gate':
 proof,own=map(Path,sys.argv[2:]);p=json.loads(proof.read_text())
 require(p['items_verified'] and p['save_verified'] and p['reload_verified'] and p['cap_verified'],'Actual source-matched PC integration proof required')
 require(not p['alpha']['enabled'],'Unproven alpha must stay disabled')
 for n,h in p['source_hashes'].items():require(sha(own/n)==h,'PC proof source mismatch: '+n)
 print('PC ITEMS gate passed; alpha disabled explicitly')
elif mode=='archive':
 base,candidate,out,project=map(Path,sys.argv[2:]);old=load_module(project)
 a,b=old.archive_members(base),old.archive_members(candidate)
 require(a.keys()==b.keys(),'Archive members changed')
 changed=sorted(n for n in a if a[n]!=b[n])
 require(changed==sorted(['main_097.o','main_220.o','main_333.o','main_339.o','main_384.o','main_1035.o']),'Unexpected archive changes '+str(changed))
 out.write_text(json.dumps(dict(changed=changed,unchanged=len(a)-len(changed),before_sha256=sha(base),after_sha256=sha(candidate)),indent=2))
elif mode=='image':
 base,candidate,out,project=map(Path,sys.argv[2:]);old=load_module(project)
 nm='/usr/lib/llvm-21/bin/llvm-nm';objdump='/usr/lib/llvm-21/bin/llvm-objdump'
 def imports(p):return sorted(line.split()[-1] for line in subprocess.check_output([nm,'-D','--undefined-only',str(p)],text=True).splitlines() if line.split())
 a,b=imports(base),imports(candidate);require(a==b,'Imports differ from installed Hebrew trial baseline')
 (out/'imports.json').write_text(json.dumps(dict(unchanged=True,imports=b),indent=2))
 symbols=subprocess.check_output([nm,'--defined-only','--extern-only',str(candidate)],text=True)
 names=[l.split()[-1] for l in symbols.splitlines() if l.split()]
 require(len(names)==len(set(names)),'Duplicate global definitions')
 pairs=old.TIMING_CALLS+old.MONEY_CALLS+old.MENU_CALLS+[
 ('f_70002bc8ec','za_items_pump'),('f_7000bba2cc','za_items_pump'),('f_7000b49360','za_items_reset'),
 ('za_items_pump','f_700048963c'),('menu_handle_event','za_items_request'),('menu_handle_event','za_hebrew_trial_request')]
 reports=[]
 for caller,callee in pairs:
  dump=subprocess.run([objdump,'-d','--no-show-raw-insn','--disassemble-symbols='+caller,str(candidate)],capture_output=True,text=True,check=True).stdout
  require(re.search(r'\b(?:callq?|jmpq?)\s+[^\n]*<'+re.escape(callee)+r'>',dump),f'Missing call {caller} -> {callee}')
  reports.append([caller,callee])
 (out/'linked-calls.json').write_text(json.dumps(reports,indent=2))
 print('Imports, unique globals and retained/new linked calls verified')
else:raise ValueError(mode)
