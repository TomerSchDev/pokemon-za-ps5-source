"""Small staging contract regressions. Synthetic files only; never a game verdict."""
import contextlib,hashlib,importlib.util,io,json,os,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch

LAB=Path(__file__).resolve().parents[3]
spec=importlib.util.spec_from_file_location('prepared_run_poc',LAB/'hebrew-lab/tools/run_poc.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class StagingTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  self.game=self.root/'game';self.game.mkdir();self.fixture=self.root/'fixture/save_0';self.fixture.mkdir(parents=True)
  self.exe=self.root/'runtime.exe';self.exe.write_bytes(b'synthetic-not-executable')
  for name in ('lasgame.dll','romfs.bin'):(self.game/name).write_bytes(b'synthetic-'+name.encode())
  (self.fixture/'main').write_bytes(b'synthetic-save')
  files=[self.exe,self.game/'lasgame.dll',self.game/'romfs.bin',Path(runner.__file__)]
  self.manifest=self.root/'artifacts.json'
  self.manifest.write_text(json.dumps(dict(files=[dict(path=str(f),bytes=f.stat().st_size,mtime_ns=f.stat().st_mtime_ns,sha256=runner.sha256(f)) for f in files])))
  self.patches=[patch.object(runner,'LAB',self.root),patch.object(runner,'EXE',self.exe),
    patch.object(runner,'resource_status',return_value=dict(disk_free_bytes=100*1024**3,free_commit_bytes=100*1024**3)),
    patch.dict(os.environ,{},clear=True)]
  for item in self.patches:item.start()
 def tearDown(self):
  for item in reversed(self.patches):item.stop()
  self.temp.cleanup()
 def stage(self):
  args=['run_poc.py','pc-fifty-synthetic','--seconds','225','--game',str(self.game),'--save-src',str(self.fixture.parent),'--stage-only','--artifact-manifest',str(self.manifest)]
  with patch.object(sys,'argv',args),patch.object(runner.subprocess,'Popen',side_effect=AssertionError('Preparation must never launch')),contextlib.redirect_stdout(io.StringIO()):runner.main()
  return self.root/'runs/pc-fifty-synthetic'
 def options(self,root,verify=False):
  from argparse import Namespace
  return Namespace(name=root.name,seconds=225,game=self.game,staged_sha256=runner.sha256(root/'staged-run.json'),mods=None,save_src=None,input='',cache_src=None,env=[],shot_at='',capture_every=0,font=None,verify_staged=verify)
 def test_preparation_never_launches_and_is_single_use(self):
  root=self.stage();self.assertFalse((root/'run.json').exists());self.assertEqual((root/'save/save_0/main').read_bytes(),b'synthetic-save')
  with self.assertRaises(SystemExit),contextlib.redirect_stderr(io.StringIO()):self.stage()
 def test_full_verification_does_not_launch(self):
  root=self.stage()
  with patch.object(runner,'execute_run',side_effect=AssertionError('Verification launched')),contextlib.redirect_stdout(io.StringIO()):runner.launch_staged(self.options(root,True),__import__('argparse').ArgumentParser(),None,None,None)
 def test_manifest_drift_is_rejected(self):
  root=self.stage();self.manifest.write_text('{}')
  with self.assertRaises(ValueError):runner.launch_staged(self.options(root),__import__('argparse').ArgumentParser(),lambda:None,None,None)
 def test_private_save_drift_is_rejected(self):
  root=self.stage();(root/'save/save_0/main').write_bytes(b'tampered')
  with self.assertRaises(SystemExit),contextlib.redirect_stderr(io.StringIO()):runner.launch_staged(self.options(root),__import__('argparse').ArgumentParser(),lambda:None,None,None)
 def test_sealed_recipe_and_no_copy_at_launch(self):
  root=self.stage()
  with patch.object(runner.shutil,'copytree',side_effect=AssertionError('Launch copied inputs')),patch.object(runner,'execute_run') as execute:
   runner.launch_staged(self.options(root),__import__('argparse').ArgumentParser(),lambda:None,None,None)
   self.assertEqual(execute.call_count,1);self.assertEqual(execute.call_args.args[2]['budget_seconds'],225)
 def test_launch_requires_lease(self):
  root=self.stage()
  with self.assertRaises(SystemExit),contextlib.redirect_stderr(io.StringIO()):runner.launch_staged(self.options(root),__import__('argparse').ArgumentParser(),None,None,None)
 def test_artifact_content_tamper_is_rejected(self):
  (self.game/'romfs.bin').write_bytes(b'changed-size')
  with self.assertRaises(ValueError):runner.verify_artifact_manifest(self.manifest,full=True)

class CanonicalPreparationGate(unittest.TestCase):
 def test_unrelated_forward_does_not_invalidate_guarded_router_scope(self):
  original=LAB/'Pokemon-ZA-Native-Port/workbench/zw.py'
  with tempfile.TemporaryDirectory() as folder:
   copy=Path(folder)/'zw.py';source=original.read_text(encoding='utf-8')
   copy.write_text(source.replace('FORWARD = {',"FORWARD = {\n    'synthetic-unrelated': ([], False, 'unused'),",1),encoding='utf-8')
   self.assertEqual(runner.canonical_router_scope(original),runner.canonical_router_scope(copy))
   copy.write_text(source.replace('def pc(args):',"def pc(args):\n    raise RuntimeError('changed guarded route')",1),encoding='utf-8')
   self.assertNotEqual(runner.canonical_router_scope(original),runner.canonical_router_scope(copy))
 def test_only_preparation_is_exempt_from_the_pc_lease(self):
  spec=importlib.util.spec_from_file_location('staged_zw_gate',LAB/'Pokemon-ZA-Native-Port/workbench/zw.py')
  zw=importlib.util.module_from_spec(spec);spec.loader.exec_module(zw)
  with patch.dict(os.environ,{},clear=True),patch.object(zw,'forward',return_value=0) as forward:
   for flag in ('--stage-only','--verify-staged','--preflight-only'):
    self.assertEqual(zw.pc(['run','pc-fifty-synthetic','--seconds','225',flag]),0)
   self.assertEqual(forward.call_count,3)
   for flags in ([],['--from-staged']):
    with self.assertRaises(zw.ZwError):zw.pc(['run','pc-fifty-synthetic','--seconds','225',*flags])

if __name__=='__main__':unittest.main(verbosity=1)
