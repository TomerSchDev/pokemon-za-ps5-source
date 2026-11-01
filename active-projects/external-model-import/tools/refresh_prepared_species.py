"""Version the unexecuted staged inputs after all previous tickets were withdrawn."""
import hashlib,json,py_compile,shutil
from pathlib import Path
LAB=Path(__file__).resolve().parents[3];TOOLS=Path(__file__).parent;SUITE=LAB/'pc-fifty-20261031-r1/prepared-suite-20261101-r1'
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def write(path,value):path.write_text(json.dumps(value,indent=1,ensure_ascii=False),encoding='utf-8')
def metadata(file):
 stat=file.stat();digest=sha(file);assert (stat.st_size,stat.st_mtime_ns)==(file.stat().st_size,file.stat().st_mtime_ns)
 return dict(path=str(file),bytes=stat.st_size,mtime_ns=stat.st_mtime_ns,sha256=digest)
def main():
 assert read(SUITE/'withdrawn-r1.json')['all_cancelled']
 proof=SUITE/'common/mapping-proof.json';assert proof.is_file()
 output=SUITE/'common/artifact-manifest-r2.json';assert not output.exists()
 old=read(SUITE/'common/artifact-manifest-r1.json');replacement=TOOLS/'prepare_species_suite.py';rows=[]
 for item in old['files']:
  file=Path(item['path']);now=metadata(file)
  if file.resolve()!=replacement.resolve():assert now==item,'Unexpected artifact drift: '+str(file)
  rows.append(now)
 compiled=SUITE/'common/python-compiled-r2';compiled.mkdir(exist_ok=False)
 additions=[proof,TOOLS/'prepared_species_dispatch.py',Path(__file__)]
 for file in (replacement,TOOLS/'prepared_species_dispatch.py',Path(__file__)):
  dest=compiled/(file.stem+'.pyc');py_compile.compile(str(file),cfile=str(dest),doraise=True);additions.append(dest)
 rows.extend(metadata(file) for file in additions)
 write(output,dict(version=2,files=rows,compiled_before_queue=True,game_launched=False,
  change='Only preparation recipe generator updated: Move1=X, Move2=A, bound to reviewed historical proof; runtime/game/models/settings/saves unchanged.',
  superseded_manifest=str(SUITE/'common/artifact-manifest-r1.json')))
 jobs=read(SUITE/'staged-jobs.json')['jobs']
 for job in jobs:
  path=Path(job['staged']);assert not (path.parent/'run.json').exists()
  assert sha(path)==job['staged_sha256']
  backup=path.with_name('staged-run-rev1.json');assert not backup.exists();shutil.copyfile(path,backup)
  record=read(path);record['prepared_contract'].update(artifact_manifest=str(output),artifact_manifest_sha256=sha(output),recipe_revision=2)
  write(path,record);job.update(staged_sha256=sha(path),recipe_revision=2)
  write(SUITE/job['case']/('staged-r2-'+job['variant']+'.json'),job)
 write(SUITE/'staged-jobs-r2.json',dict(version=2,jobs=jobs,all_inputs_updated_outside_queue=True,game_launched=False,queue_enrolled=False))
 print(json.dumps(dict(refreshed=len(jobs),files=len(rows),game_launched=False,queue_enrolled=False)),flush=True)
if __name__=='__main__':main()
