"""Refresh outside all test queues; pin guarded router scopes, not unrelated verbs."""
import hashlib,importlib.util,json,py_compile,shutil
from pathlib import Path
LAB=Path(__file__).resolve().parents[3];TOOLS=Path(__file__).parent;SUITE=LAB/'pc-fifty-20261031-r1/prepared-suite-20261101-r1'
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):path.write_text(json.dumps(value,indent=1,ensure_ascii=False),encoding='utf-8')
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def row(file):
 stat=file.stat();digest=sha(file);assert (stat.st_size,stat.st_mtime_ns)==(file.stat().st_size,file.stat().st_mtime_ns)
 return dict(path=str(file),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=digest)
def main():
 spec=importlib.util.spec_from_file_location('r4_run_poc',LAB/'hebrew-lab/tools/run_poc.py');runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
 output=SUITE/'common/artifact-manifest-r4.json';assert not output.exists()
 router=LAB/'Pokemon-ZA-Native-Port/workbench/zw.py';runtime=LAB/'hebrew-lab/tools/run_poc.py'
 rows=[]
 for item in read(SUITE/'common/artifact-manifest-r3.json')['files']:
  file=Path(item['path'])
  if file.resolve()==router.resolve():
   rows.append(dict(kind='canonical_router',path=str(router),scope_sha256=runner.canonical_router_scope(router),
    source_sha256_at_preparation=sha(router),scope='pc/require_turn/forward/argument helpers, runtime constants and relevant tool entries; unrelated FORWARD entries excluded'))
  else:
   fresh=row(file)
   if file.resolve()!=runtime.resolve():assert fresh==item,'Unexpected candidate drift: '+str(file)
   rows.append(fresh)
 compiled=SUITE/'common/python-compiled-r4';compiled.mkdir(exist_ok=False)
 for file in (runtime,TOOLS/'dispatch_prepared_species_r3.py',Path(__file__),TOOLS/'test_prepared_staging.py'):
  dest=compiled/(file.stem+'.pyc');py_compile.compile(str(file),cfile=str(dest),doraise=True);rows.append(row(dest))
 rows.extend(row(file) for file in (TOOLS/'dispatch_prepared_species_r3.py',Path(__file__),TOOLS/'test_prepared_staging.py'))
 write(output,dict(version=4,files=rows,compiled_before_queue=True,game_launched=False,
  change='Canonical guarded routes are pinned semantically, allowing unrelated agents to add independent forward entries. Runtime/module/game/mod/private fixture hashes remain exact. Staged command argv generated from one current SHA.',
  source_unit_checks='9 staging/lease/router regressions pass'))
 jobs=read(SUITE/'staged-jobs-r2.json')['jobs']
 for job in jobs:
  path=Path(job['staged']);assert not (path.parent/'run.json').exists()
  backup=path.with_name('staged-run-rev3.json');assert not backup.exists();shutil.copyfile(path,backup)
  record=read(path);record['prepared_contract'].update(artifact_manifest=str(output),artifact_manifest_sha256=sha(output),artifact_revision=4)
  write(path,record);pin=sha(path);job.update(staged_sha256=pin,artifact_revision=4)
  common=['.\\zw','pc','run',path.parent.name,'--seconds','225']
  job['launch']=[*common,'--from-staged','--staged-sha256',pin]
  job['verify']=[*common,'--verify-staged','--staged-sha256',pin]
  recipe_path=SUITE/job['case']/('recipe-r3-'+job['variant']+'.json');recipe=read(recipe_path)
  recipe.update(job=job,launch=job['launch'],artifact_revision=4)
  write(recipe_path,recipe)
 write(SUITE/'staged-jobs-r2.json',dict(version=2,artifact_revision=4,recipe_revision=3,jobs=jobs,queue_enrolled=False,game_launched=False))
 print(json.dumps(dict(refreshed=len(jobs),files=len(rows),game_launched=False,queue_enrolled=False)),flush=True)
if __name__=='__main__':main()
