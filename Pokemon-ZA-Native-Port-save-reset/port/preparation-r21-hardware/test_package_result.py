"""Offline smoke tests: all release/NAS paths are isolated local temporary paths."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
import package_result as package


class PackageSmoke(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='za-package-smoke-')
        self.base=Path(self.temp.name).resolve()
        assert self.base.parent==Path(tempfile.gettempdir()).resolve()
        assert self.base.name.startswith('za-package-smoke-')
        self.old_root,self.old_nas=package.ROOT,package.NAS_ROOT
        self.root=self.base/'project';self.nas=self.base/'mock-nas'
        self.root.mkdir();package.ROOT=self.root;package.NAS_ROOT=self.nas
        self.put('run_r3.py',b'# generic transport test fixture; never executed\n')
        self.put('port/preparation-r21/source.c',b'int old_source;\n')
        self.put('port/preparation-r21b/observer.c',b'int corrected_observer;\n')
        self.put('port/preparation-r21-hardware/tool.py',b'# test hardware-tool source\n')
        self.put('port/immutable-spans-r22/immutable-spans.inc',b'/* prepared, not installed */\n')
        self.put('port/immutable-spans-r22-integration/observer-r22.c',b'/* integrated controlled observer */\n')
        self.put('evidence/immutable-spans-r22-integration-review/review-he.txt',b'independent integration review\n')
        self.put('evidence/immutable-spans-r22-integration/runtime-r22.patch',b'controlled integration patch\n')
        self.put('port/slot-depth-r23/slot-runtime.inc',b'/* slot runtime */\n')
        self.put('port/slot-depth-r23-observer/observer-r23.c',b'/* slot observer */\n')
        self.put('evidence/slot-depth-r23/runtime-r23.patch',b'slot runtime patch\n')
        self.put('evidence/slot-depth-r23-observer/ready.json',b'{"observer_tests":"passed"}\n')
        self.put('evidence/slot-depth-r23-review/review-he.txt',b'slot review\n')
        self.put('port/slot-depth-r23b/prepare.py',b'# startup build\n')
        self.put('port/slot-depth-r23b-observer/slot-startup.inc',b'/* process-once startup */\n')
        self.put('evidence/slot-depth-r23b-review/review.json',b'{"review":"passed"}\n')
        self.put('evidence/slot-depth-r23b-observer/ready.json',b'{"tests":"passed"}\n')
        self.put('evidence/slot-depth-r23-driver-submit/results.json',b'{"windows":3}\n')
        self.put('research_notes/performance-r21-r23/report.txt',b'paired hardware findings\n')
        self.put('research_notes/ps5-resource-fit-r21/report.txt',b'resource fit review\n')
        self.put('evidence/preparation-r21b-review/review-he.txt','בדיקת r21b\n'.encode())
        self.put('evidence/preparation-r21b/receipt.json',b'{"build_passed":true}\n')
        self.put('evidence/preparation-r21-hardware/measure.csv',b'frame,dt\n1,40000000\n')
        self.put('evidence/preparation-r21-hardware/phase.json',b'{"completed":true}\n')
        self.put('evidence/preparation-r21-hardware/run.klog.log',b'unrelated private system row\n[za-r21] measured\n[vk] t=2 frame 50\n')
        self.put('evidence/preparation-r21-hardware/tests.log',b'host test passed\n')
        self.put('evidence/preparation-r21-hardware/secret-token.json',b'{"private":true}')
        self.put('evidence/preparation-r21-hardware/saves/savegame.txt',b'private game save')
        self.put('port/preparation-r21b/credentials.json',b'{"credential":"must not ship"}')
        self.put('port/preparation-r21b/api_keys.py',b'SECRET = "must not ship"')
        self.put('port/preparation-r21b/dependencies/library.c',b'not our source')
        self.put('port/preparation-r21b/build/compiler.a',b'not our dependency')
        self.put('port/preparation-r21b/romfs/game.zip',b'not our game archive')
        self.put('port/preparation-r21b/test-binary',b'host binary')
        self.put('port/preparation-r21b/artifact.bin',b'not a source file')
        artifact=self.put('selected/PPSA91762/eboot.bin',b'FAKE-SMOKE-TEST-EBOOT\0'*64)
        expected=package.digest(artifact)
        result=self.put('final-result.json',json.dumps({'title':'PPSA91762','selected_artifact_sha256':expected,'r22_installed':False}).encode())
        summary=self.put('summary.txt','סיכום בדיקה מקומית בלבד.\n'.encode())
        config=self.put('config/submission-options.txt',b'batch4\n')
        self.args=argparse.Namespace(artifact=artifact,expected_sha=expected,result=result,summary=summary,
            label='r21b-smoke',config=['submission-options.txt='+str(config)],source_file=[],evidence_file=[],png=[],publish=True)

    def tearDown(self):
        package.ROOT,package.NAS_ROOT=self.old_root,self.old_nas
        # Verify the final absolute cleanup target before TemporaryDirectory's
        # recursive removal; it must remain the explicitly created temp folder.
        assert self.base.parent==Path(tempfile.gettempdir()).resolve()
        assert self.base.name.startswith('za-package-smoke-') and self.base==Path(self.temp.name).resolve()
        self.temp.cleanup()

    def put(self,relative,data):
        p=self.root/relative;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);return p

    def test_scope_hashes_and_local_mock_nas_readback(self):
        plan=package.plan(self.args)
        self.assertFalse((self.root/'deliverables').exists());self.assertFalse(self.nas.exists())
        self.assertIn('run_r3.py',plan['sources'])
        self.assertIn('port/preparation-r21b/observer.c',plan['sources'])
        self.assertIn('evidence/preparation-r21b-review/review-he.txt',plan['sources'])
        self.assertIn('evidence/preparation-r21b/receipt.json',plan['evidence'])
        self.assertIn('evidence/preparation-r21b-review/review-he.txt',plan['evidence'])
        receipt=package.publish(self.args,plan)
        self.assertTrue(receipt['nas']['verified'])
        local=Path(receipt['local']);remote=Path(receipt['nas']['path'])
        self.assertTrue(local.is_relative_to(self.root/'deliverables'))
        self.assertTrue(remote.is_relative_to(self.nas))
        with zipfile.ZipFile(local/'Update.zip') as z:
            self.assertEqual(set(z.namelist()),{'PPSA91762/eboot.bin','PPSA91762/submission-options.txt','UPDATE-NOTE.txt'})
            self.assertEqual(hashlib.sha256(z.read('PPSA91762/eboot.bin')).hexdigest(),self.args.expected_sha)
            self.assertEqual(z.read('PPSA91762/submission-options.txt'),b'batch4\n')
        with zipfile.ZipFile(local/'Source.zip') as z:
            names=set(z.namelist())
            self.assertIn('run_r3.py',names);self.assertIn('port/preparation-r21b/observer.c',names)
            self.assertIn('R22-SOURCE-STATUS.txt',names)
            self.assertIn('NOT INSTALLED',z.read('R22-SOURCE-STATUS.txt').decode())
            self.assertIn('port/immutable-spans-r22-integration/observer-r22.c',names)
            self.assertIn('evidence/immutable-spans-r22-integration/runtime-r22.patch',names)
            for bad in ('credentials.json','api_keys.py','library.c','compiler.a','game.zip','test-binary','artifact.bin'):
                self.assertFalse(any(n.endswith('/'+bad) for n in names),bad)
        with zipfile.ZipFile(local/'Hardware-Evidence.zip') as z:
            names=set(z.namelist())
            self.assertIn('evidence/preparation-r21b/receipt.json',names)
            self.assertFalse(any(n.endswith('.png') for n in names))
            self.assertFalse(any('secret-token' in n or 'savegame' in n for n in names))
            filtered=z.read('evidence/preparation-r21-hardware/run.klog-selected.log')
            self.assertIn(b'[za-r21] measured',filtered)
            self.assertNotIn(b'unrelated private',filtered)
            self.assertNotIn('evidence/preparation-r21-hardware/run.klog.log',names)
        manifest=json.loads((local/'SHA256.json').read_text())
        self.assertEqual(set(manifest),{p.name for p in local.iterdir() if p.name!='SHA256.json'})
        for name,info in manifest.items():self.assertEqual(package.digest(local/name),info['sha256'])
        for path in local.iterdir():self.assertEqual(package.digest(path),package.digest(remote/path.name))
        self.assertEqual(package.digest(local/'SHA256.json'),receipt['sha_manifest_sha256'])
        self.assertTrue(package.copy_nas(local)['verified']) # identical copies are reusable
        # A different existing version on the simulated NAS must survive intact.
        conflict=remote/'Update.zip';conflict.write_bytes(b'EXISTING-DIFFERENT-VERSION')
        before=package.digest(conflict);failed=package.copy_nas(local)
        self.assertFalse(failed['verified']);self.assertIn('Existing different NAS file',failed['error'])
        self.assertEqual(package.digest(conflict),before)

    def test_hash_binding_and_forbidden_config_fail_before_delivery(self):
        expected=self.args.expected_sha
        self.args.expected_sha='0'*64
        with self.assertRaisesRegex(ValueError,'Selected eboot'):package.plan(self.args)
        self.args.expected_sha=expected
        self.args.result.write_text(json.dumps({'title':'PPSA91762','selected_artifact_sha256':'0'*64}))
        with self.assertRaisesRegex(ValueError,'disagrees'):package.plan(self.args)
        self.args.result.write_text(json.dumps({'title':'PPSA91762','selected_artifact_sha256':expected,'artifact':{'sha256':'0'*64}}))
        with self.assertRaisesRegex(ValueError,'disagrees'):package.plan(self.args)
        self.args.result.write_text(json.dumps({'title':'PPSA91762'}))
        with self.assertRaisesRegex(ValueError,'explicitly bind'):package.plan(self.args)
        self.args.result.write_text(json.dumps({'title':'PPSA91762','selected_artifact_sha256':expected}))
        self.args.config=['observer-command.txt='+str(self.args.summary)]
        with self.assertRaisesRegex(ValueError,'configuration'):package.plan(self.args)
        self.assertFalse((self.root/'deliverables').exists());self.assertFalse(self.nas.exists())

    def test_actual_native_png_size_is_optional_and_within_new_limit(self):
        # Sized test fixture, not a rendering-validity claim. Packaging checks
        # signature/size; actual game images have independent visual review.
        png=self.root/'evidence/preparation-r21-hardware/native-frame.png'
        with png.open('wb') as f:
            f.write(b'\x89PNG\r\n\x1a\n');f.seek(33188454-1);f.write(b'\0')
        plan=package.plan(self.args);self.assertFalse(plan['pngs'])
        self.args.png=[png];plan=package.plan(self.args)
        self.assertEqual(png.stat().st_size,33188454)
        self.assertEqual(len(plan['pngs']),1)
        receipt=package.publish(self.args,plan)
        with zipfile.ZipFile(Path(receipt['local'])/'Hardware-Evidence.zip') as z:
            self.assertEqual(z.getinfo('evidence/preparation-r21-hardware/native-frame.png').file_size,33188454)
        self.assertTrue(receipt['nas']['verified'])
        with png.open('r+b') as f:f.truncate(package.MAX_PNG+1)
        with self.assertRaisesRegex(ValueError,'PNG is too large'):package.plan(self.args)

    def test_changed_selected_binary_keeps_local_incomplete_and_never_copies(self):
        plan=package.plan(self.args)
        self.args.artifact.write_bytes(b'CHANGED-AFTER-SELECTION')
        with self.assertRaisesRegex(ValueError,'Archived binary differs'):package.publish(self.args,plan)
        self.assertFalse(self.nas.exists())
        folders=list((self.root/'deliverables').iterdir())
        self.assertEqual(len(folders),1);self.assertTrue((folders[0]/'INCOMPLETE.txt').exists())

    def test_installed_r22_labels_require_exact_integrated_ready_hash(self):
        value=json.loads(self.args.result.read_text());value['r22_installed']=True
        self.args.result.write_text(json.dumps(value))
        ready=self.put('evidence/immutable-spans-r22-integration/ready.json',json.dumps(
            {'title_id':'PPSA91762','eboot':{'sha256':'0'*64}}).encode())
        with self.assertRaisesRegex(ValueError,'ready-artifact hash'):package.plan(self.args)
        self.assertFalse(self.nas.exists());self.assertFalse((self.root/'deliverables').exists())
        ready.write_text(json.dumps({'title_id':'PPSA91762','eboot':{'sha256':self.args.expected_sha}}))
        value['r22_installed']='true';self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'explicit boolean'):package.plan(self.args)
        value['r22_installed']=True;self.args.result.write_text(json.dumps(value))
        plan=package.plan(self.args);receipt=package.publish(self.args,plan)
        local=Path(receipt['local']);self.assertTrue(receipt['nas']['verified'])
        meta=json.loads((local/'Packaging.json').read_text())
        self.assertTrue(meta['r22_installed_as_recorded'])
        self.assertIn('Integrated r22 runtime selected',meta['r22_status'])
        with zipfile.ZipFile(local/'Source.zip') as z:
            note=z.read('R22-SOURCE-STATUS.txt').decode()
            self.assertIn('original standalone TB1 candidate-only source',note)
            self.assertIn('Integrated r22 runtime selected',note)
            self.assertNotIn('NOT INSTALLED',note)
        with zipfile.ZipFile(local/'Update.zip') as z:
            self.assertNotIn('NOT INSTALLED',z.read('UPDATE-NOTE.txt').decode())

    def test_r23_selection_and_inherited_r22_labels_are_hash_bound(self):
        value=json.loads(self.args.result.read_text());value.update(r22_installed=True,r23_installed=True)
        self.args.result.write_text(json.dumps(value))
        ready=self.put('evidence/slot-depth-r23/ready.json',json.dumps({'title_id':'PPSA91762','eboot':{'sha256':'0'*64}}).encode())
        with self.assertRaisesRegex(ValueError,'r23 ready-artifact hash'):package.plan(self.args)
        ready.write_text(json.dumps({'title_id':'PPSA91762','eboot':{'sha256':self.args.expected_sha}}))
        value['selected_runtime']='r22';self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'selected_runtime differs'):package.plan(self.args)
        value['selected_runtime']='r23';value['r23_installed']='true';self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'explicit boolean'):package.plan(self.args)
        value['r23_installed']=True;self.args.result.write_text(json.dumps(value))
        collision=self.put('evidence/immutable-spans-r22-integration/ready.json',ready.read_bytes())
        with self.assertRaisesRegex(ValueError,'Ambiguous'):package.plan(self.args)
        collision.unlink()
        plan=package.plan(self.args);self.assertEqual(plan['selection']['runtime'],'r23')
        self.assertIn('port/slot-depth-r23/slot-runtime.inc',plan['sources'])
        self.assertIn('port/slot-depth-r23-observer/observer-r23.c',plan['sources'])
        self.assertIn('evidence/slot-depth-r23/runtime-r23.patch',plan['sources'])
        self.assertIn('evidence/slot-depth-r23-observer/ready.json',plan['evidence'])
        self.assertIn('evidence/slot-depth-r23-review/review-he.txt',plan['sources'])
        receipt=package.publish(self.args,plan);self.assertTrue(receipt['nas']['verified'])
        local=Path(receipt['local']);meta=json.loads((local/'Packaging.json').read_text())
        self.assertEqual(meta['selected_runtime'],'r23');self.assertTrue(meta['r23_installed_as_recorded'])
        self.assertIn('inherited by the selected r23 binary',meta['r22_status'])
        self.assertEqual(meta['runtime_ready_binding']['sha256'],package.digest(ready))
        with zipfile.ZipFile(local/'Source.zip') as z:
            self.assertIn('inherited by the selected r23 binary',z.read('R22-SOURCE-STATUS.txt').decode())
            self.assertIn('Integrated r23 slot-depth runtime selected',z.read('R23-SOURCE-STATUS.txt').decode())
        with zipfile.ZipFile(local/'Update.zip') as z:
            self.assertIn('Selected runtime binding: r23',z.read('UPDATE-NOTE.txt').decode())
            self.assertNotIn('NOT INSTALLED',z.read('UPDATE-NOTE.txt').decode())

    def test_r23b_startup_variant_requires_ready_and_strict_config(self):
        value=json.loads(self.args.result.read_text())
        value.update(selected_runtime='r23b',r22_installed=True,r23_installed=True,r23b_installed=True)
        self.args.result.write_text(json.dumps(value))
        config=self.put('config/slot-depth-options.txt',b'16\n')
        self.args.config.append('slot-depth-options.txt='+str(config))
        with self.assertRaisesRegex(ValueError,'selected_runtime differs'):package.plan(self.args)
        ready=self.put('evidence/slot-depth-r23b/ready.json',json.dumps({'title_id':'PPSA91762','eboot':{'sha256':self.args.expected_sha}}).encode())
        for bad in (b'',b' 16',b'16 ',b'16\r\n',b'16\nX',b'016',b'\xef\xbb\xbf16'):
            config.write_bytes(bad)
            with self.assertRaisesRegex(ValueError,'exactly 8 or 16'):package.plan(self.args)
        for good in (b'8',b'8\n',b'16',b'16\n'):
            config.write_bytes(good);plan=package.plan(self.args)
            self.assertEqual(plan['selection']['runtime'],'r23b')
        value['r23b_installed']='true';self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'explicit boolean'):package.plan(self.args)
        value['r23b_installed']=True;self.args.result.write_text(json.dumps(value));plan=package.plan(self.args)
        for path in ('port/slot-depth-r23b/prepare.py','port/slot-depth-r23b-observer/slot-startup.inc','research_notes/performance-r21-r23/report.txt','evidence/slot-depth-r23b-review/review.json'):
            self.assertIn(path,plan['sources'])
        for path in ('evidence/slot-depth-r23-driver-submit/results.json','evidence/slot-depth-r23b-observer/ready.json'):
            self.assertIn(path,plan['evidence'])
        receipt=package.publish(self.args,plan);self.assertTrue(receipt['nas']['verified'])
        local=Path(receipt['local']);meta=json.loads((local/'Packaging.json').read_text())
        self.assertEqual(meta['selected_runtime'],'r23b');self.assertTrue(meta['r23b_installed_as_recorded'])
        self.assertEqual(meta['runtime_ready_binding']['sha256'],package.digest(ready))
        with zipfile.ZipFile(local/'Update.zip') as z:
            self.assertEqual(z.read('PPSA91762/slot-depth-options.txt'),b'16\n')
            self.assertIn('process-once startup preference',z.read('UPDATE-NOTE.txt').decode())
        with zipfile.ZipFile(local/'Source.zip') as z:
            self.assertIn('inherited by the selected r23b binary',z.read('R22-SOURCE-STATUS.txt').decode())
            self.assertIn('original standalone TB1 candidate-only source',z.read('R22-SOURCE-STATUS.txt').decode())
        # Neither a matching plain-r23 artifact nor an absent r23b receipt may
        # claim support for the startup configuration.
        ready.unlink();self.put('evidence/slot-depth-r23/ready.json',json.dumps({'title_id':'PPSA91762','eboot':{'sha256':self.args.expected_sha}}).encode())
        value.update(selected_runtime='r23',r23b_installed=False);self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'slot-depth-options.txt requires'):package.plan(self.args)

    def test_r23c_ready_binding_and_historical_r23b_failure(self):
        self.put('port/slot-depth-r23c/prepare.py',b'# POSIX startup variant\n')
        self.put('port/slot-depth-r23c-observer/slot-startup.inc',b'/* bounded POSIX */\n')
        self.put('evidence/slot-depth-r23c-observer/ready.json',b'{"tests":"passed"}\n')
        self.put('evidence/slot-depth-r23c-review/review.json',b'{"review":"passed"}\n')
        value=json.loads(self.args.result.read_text())
        value.update(selected_runtime='r23c',r22_installed=True,r23_installed=True,r23c_installed=True,r23b_installed=False)
        self.args.result.write_text(json.dumps(value))
        config=self.put('config/slot-depth-options.txt',b'16\n')
        self.args.config.append('slot-depth-options.txt='+str(config))
        with self.assertRaisesRegex(ValueError,'selected_runtime differs'):package.plan(self.args)
        ready=self.put('evidence/slot-depth-r23c/ready.json',json.dumps({'title_id':'PPSA91762','eboot':{'sha256':self.args.expected_sha}}).encode())
        plan=package.plan(self.args);self.assertEqual(plan['selection']['runtime'],'r23c')
        self.assertIn('port/slot-depth-r23c/prepare.py',plan['sources'])
        self.assertIn('port/slot-depth-r23c-observer/slot-startup.inc',plan['sources'])
        self.assertIn('evidence/slot-depth-r23c-review/review.json',plan['sources'])
        self.assertIn('evidence/slot-depth-r23c-observer/ready.json',plan['evidence'])
        value['r23b_installed']=True;self.args.result.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError,'Installed r23b label'):package.plan(self.args)
        value['r23b_installed']=False;self.args.result.write_text(json.dumps(value));plan=package.plan(self.args)
        receipt=package.publish(self.args,plan);self.assertTrue(receipt['nas']['verified'])
        local=Path(receipt['local']);meta=json.loads((local/'Packaging.json').read_text())
        self.assertEqual(meta['selected_runtime'],'r23c');self.assertTrue(meta['r23c_installed_as_recorded']);self.assertFalse(meta['r23b_installed_as_recorded'])
        self.assertEqual(meta['runtime_ready_binding']['sha256'],package.digest(ready))
        with zipfile.ZipFile(local/'Update.zip') as z:
            self.assertEqual(z.read('PPSA91762/slot-depth-options.txt'),b'16\n')
            self.assertIn('bounded POSIX reader',z.read('UPDATE-NOTE.txt').decode())
            self.assertIn('r23b startup configuration failed safely on hardware',z.read('UPDATE-NOTE.txt').decode())
        with zipfile.ZipFile(local/'Source.zip') as z:
            self.assertIn('inherited by the selected r23c binary',z.read('R22-SOURCE-STATUS.txt').decode())


if __name__=='__main__':unittest.main()
