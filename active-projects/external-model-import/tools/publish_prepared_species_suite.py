"""Publish the prepared suite's source/metadata, excluding saves and game assets."""
import hashlib,json,shutil,zipfile
from datetime import datetime,timezone
from pathlib import Path
LAB=Path(__file__).resolve().parents[3];WORK=LAB/'pc-fifty-20261031-r1';SUITE=WORK/'prepared-suite-20261101-r1'
def sha(path):
 with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def clean(value):
 if isinstance(value,dict):return {k:clean(v) for k,v in value.items() if k not in ('footer','OriginalTrainerName','ID32') and 'token' not in k.lower()}
 if isinstance(value,list):return [clean(v) for v in value]
 return value
def main():
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=WORK/'evidence'/('prepared-species-suite-'+stamp);out.mkdir(exist_ok=False)
 case_dirs=[p for p in SUITE.iterdir() if p.is_dir() and p.name!='common']
 assert len(case_dirs)==9
 # Explicit extensions and depths only: never recurse into fixtures, bins or mods.
 for case in case_dirs:
  dest=out/'cases'/case.name;dest.mkdir(parents=True)
  for file in case.iterdir():
   if file.is_file() and file.suffix in ('.json','.py','.ps1','.cs'):
    if file.suffix=='.json':(dest/file.name).write_text(json.dumps(clean(json.loads(file.read_text(encoding='utf-8-sig'))),indent=1,ensure_ascii=False),encoding='utf-8')
    else:shutil.copyfile(file,dest/file.name)
 for name in ('staged-jobs-r2.json','readiness-all-r3.json','enrolled-jobs-r3.json','withdrawn-r1.json','withdrawn-r2.json','exact-command-verification-r3.json'):
  file=SUITE/name
  if file.exists():shutil.copyfile(file,out/name)
 for name in ('models-r1.json','artifact-manifest-r4.json','mapping-proof.json'):
  shutil.copyfile(SUITE/'common'/name,out/name)
 source=out/'source';source.mkdir()
 paths=[Path(__file__),Path(__file__).with_name('prepare_species_suite.py'),Path(__file__).with_name('prepared_species_dispatch.py'),
  Path(__file__).with_name('dispatch_prepared_species_r3.py'),Path(__file__).with_name('refresh_prepared_species_r4.py'),Path(__file__).with_name('refresh_prepared_species.py'),Path(__file__).with_name('Compile-PreparedSpeciesTools.ps1'),Path(__file__).with_name('Inspect-PreparedSpeciesFixture.ps1'),
  Path(__file__).with_name('test_prepared_staging.py'),Path(__file__).with_name('pc_fifty_control.py'),
  LAB/'hebrew-lab/tools/run_poc.py',LAB/'Pokemon-ZA-Native-Port/AGENTS.md']
 for file in paths:shutil.copyfile(file,source/file.name)
 compiled=out/'compiled-tools';compiled.mkdir()
 for file in (SUITE/'common/compiled-r1/InspectFiftySave.cs',SUITE/'common/compiled-r1/InspectFiftySave.dll'):
  shutil.copyfile(file,compiled/file.name)
 manifest=dict(utc=datetime.now(timezone.utc).isoformat(),cases=9,prepared_battle_legs=20,current_recipe_revision=3,current_artifact_revision=4,
  superseded_revision='R1 tickets90–109 and R2 tickets111–130 all withdrawn before ownership/gameplay due input mapping / literal pin mismatches. Only R3 recipes/enrollments are current.',
  includes_game_payloads_saves_keys_or_dependencies=False,gameplay_pass_inferred=False,
  source_unit_checks='9/9 staging/router contract tests passed; not game tests',
  source_rule='One agent per route case; complete compilation/artifacts/private fixture/config/actions/assertions/cleanup before each canonical enrollment.',
  files={p.relative_to(out).as_posix():dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.rglob('*') if p.is_file()})
 (out/'manifest.json').write_text(json.dumps(manifest,indent=1),encoding='utf-8')
 archive=out.with_suffix('.zip')
 with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
  for file in sorted(out.rglob('*')):
   if file.is_file():z.write(file,file.relative_to(out).as_posix())
 with zipfile.ZipFile(archive) as z:assert z.testzip() is None
 nas=Path(r'\\TheOnePiece\Software\Pokemon-ZA-All-Models\PC-QA-50-20261031-r1\Prepared-Suites')/archive.name
 nas.parent.mkdir(parents=True,exist_ok=True)
 if nas.exists():assert sha(nas)==sha(archive)
 else:shutil.copyfile(archive,nas)
 assert sha(nas)==sha(archive)
 receipt=dict(local=str(archive),nas=str(nas),sha256=sha(archive),sha256_verified=True,cases=9,battle_legs=20)
 (out/'nas-receipt.json').write_text(json.dumps(receipt,indent=1),encoding='utf-8')
 print(json.dumps(receipt),flush=True)
if __name__=='__main__':main()
