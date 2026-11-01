"""Scoped storage migration input review and preparation; never console access."""
import argparse,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
SDK='/home/tomer/ps5-za-native/PS5_Vulkan/.deps/native/ps5-payload-sdk'
SOURCES=['port/main-install/relocate_side_mods.c','port/main-install/seed-side-data.c','port/hebrew-rtl/test/test_storage_migration.py','port/hebrew-rtl/storage-choice.py']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def linux(p):
    p=str(Path(p).resolve());return '/mnt/'+p[0].lower()+p[2:].replace('\\','/')
def wsl(*args):return subprocess.run(['wsl.exe','-d','Ubuntu','-u','tomer','--',*args],check=True,capture_output=True,text=True,encoding='utf-8')

ap=argparse.ArgumentParser();ap.add_argument('operation',choices=['review','build','test']);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--native-out',required=True);ap.add_argument('--review',type=Path);a=ap.parse_args();out=a.out.resolve()
if not a.native_out.startswith('/home/tomer/ps5-za-native/') or '/..' in a.native_out:raise ValueError('New isolated native output required')
if a.operation=='review':
    out.mkdir(parents=True,exist_ok=False)
    code=r'''
import hashlib,json,os,pathlib,subprocess,sys,sysconfig
sdk=pathlib.Path(sys.argv[1]);lock=json.loads(pathlib.Path(sys.argv[2]).read_text(encoding='utf-8-sig'))
def call(*args):return subprocess.check_output(args,text=True,stderr=subprocess.STDOUT).strip()
def digest(p):
 with open(p,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
paths=set();roots=[sdk/'bin',sdk/'target/include',sdk/'target/lib',sdk/'ldscripts',sdk/'toolchain',pathlib.Path('/usr/lib/llvm-21/lib/clang/21'),pathlib.Path('/usr/lib/gcc/x86_64-linux-gnu/15'),pathlib.Path('/usr/libexec/gcc/x86_64-linux-gnu/15'),pathlib.Path('/usr/include'),pathlib.Path(sysconfig.get_paths()['stdlib'])]
for root in roots:
 for base,dirs,files in os.walk(root):
  for name in files:
   p=pathlib.Path(base)/name
   if p.is_file():paths.add(p.resolve())
tools=['/usr/bin/clang-21','/usr/lib/llvm-21/bin/ld.lld','/usr/bin/llvm-config-21','/usr/bin/cc','/usr/bin/as','/usr/bin/ld','/usr/libexec/gcc/x86_64-linux-gnu/15/cc1','/usr/bin/python3','/bin/bash','/usr/bin/realpath','/usr/bin/readlink','/usr/bin/rev','/usr/bin/uname','/usr/bin/cut','/usr/bin/dirname','/usr/bin/basename']
for name in ('crt1.o','Scrt1.o','crti.o','crtn.o','libc.so','libc.so.6','libc_nonshared.a'):
 paths.add((pathlib.Path('/usr/lib/x86_64-linux-gnu')/name).resolve())
for name in tools:
 p=pathlib.Path(name).resolve();paths.add(p)
 try:
  for line in call('ldd',str(p)).splitlines():
   for word in line.split():
    if word.startswith('/') and pathlib.Path(word).is_file():paths.add(pathlib.Path(word).resolve())
 except subprocess.CalledProcessError:pass
rows=[{'path':str(p),'bytes':p.stat().st_size,'sha256':digest(p)} for p in sorted(paths)]
comparisons=[]
for name,expected in lock['files'].items():
 if '/ps5-payload-sdk/' in name or name=='/usr/bin/clang-21':
  p=pathlib.Path(name.replace('{native}','/home/tomer/ps5-za-native'))
  measured=digest(p);comparisons.append({'path':str(p),'expected':expected['sha256'],'measured':measured,'match':measured==expected['sha256']})
print(json.dumps({'sdk_revision':(sdk/'.ps5-sdk-revision').read_text().strip(),'compiler_version':call(str(sdk/'bin/prospero-clang'),'--version'),'host_cc':call('/usr/bin/cc','--version'),'python':call('/usr/bin/python3','--version'),'files':rows,'frozen_main_comparisons':comparisons}))
'''
    toolchain=json.loads(wsl('/usr/bin/python3','-c',code,SDK,linux(ROOT/'tools/za/releases/main-1.1.0.lock.json')).stdout)
    write(out/'toolchain.json',toolchain)
    if not all(r['match'] for r in toolchain['frozen_main_comparisons']):raise RuntimeError('Approved SDK/compiler pin mismatch; no build allowed')
    state=json.loads((ROOT.parent/'console-install-state/state.json').read_text(encoding='utf-8'))['payload']
    sources=[{'path':str(ROOT/p),'sha256':sha(ROOT/p)} for p in SOURCES]
    mapping=ROOT/'docs/testing/BUILD_DEPENDENCY_MAP.json';lock=ROOT/'tools/za/releases/main-1.1.0.lock.json'
    extension={'schema_version':1,'kind':'scoped_build_dependency_mapping','parent_map':{'path':str(mapping),'sha256':sha(mapping)},'nodes':[{'id':'hebrew-storage::'+p,'path':str(ROOT/p),'sha256':sha(ROOT/p),'role':'new canonical migration candidate source or recipe'} for p in SOURCES]+[{'id':'hebrew-storage::toolchain','path':str(out/'toolchain.json'),'sha256':sha(out/'toolchain.json'),'role':'approved frozen SDK/compiler comparison plus measured native and synthetic-host closure'}],'edges':[{'from':'hebrew-storage::port/main-install/relocate_side_mods.c','to':'hebrew-storage::port/main-install/seed-side-data.c','relationship':'includes_current_canonical_source'},{'from':'hebrew-storage::port/main-install/relocate_side_mods.c','to':'hebrew-storage::toolchain','relationship':'compiles_with'},{'from':'hebrew-storage::port/hebrew-rtl/test/test_storage_migration.py','to':'hebrew-storage::port/main-install/relocate_side_mods.c','relationship':'prepares_synthetic_host_controls'}]}
    write(out/'scoped-dependency-map.json',extension)
    record={'schema_version':1,'status':'READY_FOR_SCOPED_BUILD','allowed_to_start':True,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'project_id':'hebrew-choice-side-storage','operation':'compile only the migration helper and six synthetic fixtures; no game/mod/package generation','sources':sources,'mapping_snapshot':extension['parent_map'],'scoped_mapping':{'path':str(out/'scoped-dependency-map.json'),'sha256':sha(out/'scoped-dependency-map.json')},'toolchain':{'path':str(out/'toolchain.json'),'sha256':sha(out/'toolchain.json')},'native_output':a.native_out,'output':str(out),'flags':['-O2','-Wall','SDK fixed x86_64-sie-ps5 wrapper/default CRT/import flags','host fixture macros as source-pinned test matrix'],'environment_overrides':[],'current_authority':{'frozen_release_lock':str(lock),'lock_sha256':sha(lock),'sdk_selection':'SDK path declared by approved main-1.1.0; every available frozen SDK/compiler pin compared byte-for-byte','host_selection':'Measured installed Ubuntu GCC15 and Python3; only synthetic fixture controls, no game ABI input','new_sources':'Current canonical source, scoped migration candidate; no old worktree/evidence code used as build input'},'baseline_local_only':state['baselines']['PPSA91762'],'migration_candidate':{'baseline_control':'Existing side stays closed/intact until helper passes six synthetic safety cases; main36b3 and its JSON fix not rebuilt or changed','regressions':['verified byte comparison before unlink','newer save unchanged','modified original/target refusal before any unlink','main mount refusal','unknown files retained','symlink refusal','idempotent retry'],'final_candidate_validation':'NOT_RUN'},'scope':{'job_input_closure_complete':True,'no_game_assets_or_saves_consumed':True,'does_not_authorize_packaging_or_installation':True},'blocking_conditions':[]}
    write(out/'build-input-check.json',record);print(json.dumps({'status':record['status'],'files_measured':len(toolchain['files']),'frozen_pins_matched':len(toolchain['frozen_main_comparisons'])}))
elif a.operation=='build':
    if not a.review:raise ValueError('Explicit prebuild review required')
    review=json.loads(a.review.read_text(encoding='utf-8-sig'))
    if review['status']!='READY_FOR_SCOPED_BUILD' or not review['allowed_to_start'] or review['native_output']!=a.native_out:raise ValueError('Review scope differs')
    for r in review['sources']+[review['toolchain'],review['scoped_mapping']]:
        if sha(r['path'])!=r['sha256']:raise ValueError('Reviewed input changed: '+r['path'])
    if sha(ROOT/'docs/testing/BUILD_DEPENDENCY_MAP.json')!=review['mapping_snapshot']['sha256']:raise ValueError('Main mapping changed; refresh review')
    if sha(review['current_authority']['frozen_release_lock'])!=review['current_authority']['lock_sha256']:raise ValueError('Approved release lock changed')
    verify=r'''
import hashlib,json,pathlib,sys
records=json.loads(pathlib.Path(sys.argv[1]).read_text())['files']
for row in records:
 with open(row['path'],'rb') as f: actual=hashlib.file_digest(f,'sha256').hexdigest()
 if actual!=row['sha256']:raise SystemExit('Reviewed toolchain input changed: '+row['path'])
print('All measured toolchain inputs unchanged')
'''
    wsl('/usr/bin/python3','-c',verify,linux(review['toolchain']['path']))
    out.mkdir(parents=True,exist_ok=False);wsl('mkdir',a.native_out)
    native=wsl(SDK+'/bin/prospero-clang','-O2','-Wall',linux(ROOT/'port/main-install/relocate_side_mods.c'),'-o',a.native_out+'/relocate-side-mods.elf');(out/'native-build.log').write_text(native.stdout+native.stderr,encoding='utf-8')
    prep=wsl('/usr/bin/python3',linux(ROOT/'port/hebrew-rtl/test/test_storage_migration.py'),'prepare',a.native_out+'/host-fixtures');(out/'fixture-build.log').write_text(prep.stdout+prep.stderr,encoding='utf-8')
    shutil.copyfile(Path(r'\\wsl.localhost\Ubuntu')/a.native_out.lstrip('/').replace('/','\\')/'relocate-side-mods.elf',out/'relocate-side-mods.elf')
    write(out/'native-manifest.json',{'review':{'path':str(a.review.resolve()),'sha256':sha(a.review)},'payload':{'path':str(out/'relocate-side-mods.elf'),'sha256':sha(out/'relocate-side-mods.elf')},'native_output':a.native_out,'tests':'Prepared, not executed'});print('Native helper and all host fixtures prepared; no game/console accessed')
else:
    spec=__import__('importlib.util',fromlist=['util']);s=spec.spec_from_file_location('storage_pc_queue',ROOT/'tools/console-install-queue/console_queue.py');q=spec.module_from_spec(s);s.loader.exec_module(q)
    q.Board(resource='pc').check(os.environ['PC_TEST_AGENT'],os.environ['PC_TEST_TICKET'],os.environ['PC_TEST_TOKEN'])
    result=wsl('/usr/bin/python3',linux(ROOT/'port/hebrew-rtl/test/test_storage_migration.py'),'run',a.native_out+'/host-fixtures');out.mkdir(parents=True,exist_ok=False);(out/'host-tests.log').write_text(result.stdout+result.stderr,encoding='utf-8');print(result.stdout)
