"""Isolated fake-workspace/fake-NAS tests; never accesses actual NAS or console."""
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

SPEC=importlib.util.spec_from_file_location('r24_publisher_tested',Path(__file__).with_name('publish_review.py'))
m=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(m)


class ReviewPublisherTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='za-review-publisher-test-')
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/'project';self.root.mkdir()
        self.nas=Path(self.tmp.name)/'fake-nas';self.nas.mkdir()
        for name,value in (('ROOT',self.root),('NAS_ROOT',self.nas)):
            p=patch.object(m,name,value);p.start();self.addCleanup(p.stop)
        for d in m.REVIEW_ROOTS:(self.root/d).mkdir(parents=True)
        self.write('port/perf-r24-hardware/tool.py','print("review")\n')
        self.write('port/perf-r24-hardware/__pycache__/tool.pyc','private')
        for ref in m.REFERENCES:self.write(ref,'reference\n')
        self.write('port/perf-r24/patches/change.patch','diff review\n')
        self.native=self.root/'evidence/perf-r24-analysis-review/native-review-20261029-060100Z'
        self.write(self.native/'summary.json','{"phases":1}\n')
        self.write(self.native/'results/phase.json','{"valid":true}\n')
        self.write(self.native/'originals/private.json','{"save":"secret"}')
        self.write(self.native/'originals/all.klog.log','private raw log')
        self.write(self.native/'originals/image.png','private image')
        self.write('evidence/perf-r24-analysis-review/native-review-20261029-055600Z/summary.json','{}')
        self.write('evidence/perf-r24-analysis-review/native-review-20261029-055600Z/results/old.json','{}')
        self.write('evidence/perf-r24-review/test.c','int x;\n')
        self.write('evidence/perf-r24-review/test','binary-not-for-publish')
        self.write('evidence/perf-r24-review/tests.log','passed\n')
        self.write('evidence/perf-r24-config-review/__pycache__/hidden.py','private cache')
        self.report=self.write('evidence/perf-r24-config-review/final-report.txt',
            'סקירה עצמאית\nההרצות בחומרה בוצעו במשימה אחרת\nתוצאות.\n')
        self.meta=self.write('evidence/perf-r24-config-review/final-report.json',json.dumps({
            'review_role':'independent_review','hardware_executor':'other_thread',
            'installed_by_this_thread':False,'hardware_tests_run_by_this_thread':False,'status':'partial'}))
        self.stamp='20261029-061000Z'
    def write(self,name,text):
        path=Path(name);path=path if path.is_absolute() else self.root/path
        path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text,encoding='utf-8');return path
    def prepare(self):return m.prepare(self.report,self.meta,self.native,self.stamp)
    def test_validation_is_read_only_and_excludes_private_intermediates(self):
        leaf,files,count=self.prepare()
        self.assertFalse((self.root/'deliverables').exists());self.assertFalse(list(self.nas.iterdir()))
        self.assertEqual(set(files),m.FINAL_NAMES);self.assertGreater(count,5)
        with zipfile.ZipFile(io.BytesIO(files['Review-Tools.zip'])) as z:
            names=z.namelist()
            self.assertTrue(any(n.endswith('/tests.log') for n in names))
            for n in names:
                self.assertNotIn('/originals/',n);self.assertNotIn('__pycache__',n)
                self.assertNotIn('055600Z',n);self.assertFalse(n.endswith('/test'))
        self.assertEqual(leaf,'ZA-r24-Independent-Review-'+self.stamp)
    def test_scope_requires_explicit_false_and_other_thread(self):
        original=json.loads(self.meta.read_text())
        for key,value in [('installed_by_this_thread',True),('installed_by_this_thread',0),
                          ('hardware_executor','this_thread'),('status','installed')]:
            obj=dict(original);obj[key]=value;self.meta.write_text(json.dumps(obj))
            with self.assertRaises(ValueError):self.prepare()
        self.meta.write_text(json.dumps(original));self.report.write_text('ordinary report')
        with self.assertRaises(ValueError):self.prepare()
    def test_older_snapshot_and_invalid_stamp_rejected(self):
        old=self.native.with_name('native-review-20261029-055600Z')
        with self.assertRaises(ValueError):m.prepare(self.report,self.meta,old,self.stamp)
        for stamp in ('../escape','20261329-061000Z','20261029-256000Z'):
            with self.assertRaises(ValueError):m.prepare(self.report,self.meta,self.native,stamp)
    def test_exact_publication_and_identical_reuse(self):
        leaf,files,_=self.prepare();result=m.publish(leaf,files)
        self.assertTrue(result['nas_completed'])
        first={(self.nas/leaf/n).stat().st_mtime_ns for n in files}
        again=m.publish(leaf,files);self.assertTrue(again['nas_completed'])
        self.assertEqual(first,{(self.nas/leaf/n).stat().st_mtime_ns for n in files})
        for name,data in files.items():
            self.assertEqual((self.root/'deliverables'/leaf/name).read_bytes(),data)
            self.assertEqual((self.nas/leaf/name).read_bytes(),data)
        manifest=json.loads(files['SHA256.json'])
        for n,pin in manifest.items():self.assertEqual(pin['sha256'],m.digest(files[n]))
    def test_different_existing_local_file_is_never_overwritten(self):
        leaf,files,_=self.prepare();dest=self.root/'deliverables'/leaf;dest.mkdir(parents=True)
        (dest/'Review-HE.txt').write_bytes(b'other version')
        with self.assertRaises(ValueError):m.publish(leaf,files)
        self.assertEqual((dest/'Review-HE.txt').read_bytes(),b'other version')
        self.assertFalse(list(self.nas.iterdir()))
    def test_nas_unavailable_or_different_preserves_local_and_reports_failure(self):
        leaf,files,_=self.prepare()
        with patch.object(m,'NAS_ROOT',self.nas/'missing'):
            result=m.publish(leaf,files)
        self.assertFalse(result['nas_completed']);self.assertIn('nas_error',result)
        self.assertTrue((self.root/'deliverables'/leaf/'Review.json').exists())
        target=self.nas/leaf;target.mkdir();(target/'Review.json').write_bytes(b'old')
        result=m.publish(leaf,files);self.assertFalse(result['nas_completed'])
        self.assertEqual((target/'Review.json').read_bytes(),b'old')
    def test_deterministic_zip_and_report_snapshot(self):
        first=self.prepare();second=self.prepare();self.assertEqual(first,second)
        self.write('evidence/perf-r24-review/test.c','int changed;\n')
        self.assertNotEqual(first[1]['Review-Tools.zip'],self.prepare()[1]['Review-Tools.zip'])
    def test_source_path_outside_workspace_rejected(self):
        outside=Path(self.tmp.name)/'outside.txt';outside.write_text('private')
        with self.assertRaises(ValueError):m.read_small(outside)
    def test_partial_native_result_json_is_not_packaged(self):
        self.write(self.native/'results/phase.json','{"valid":')
        with self.assertRaises(ValueError):self.prepare()


if __name__=='__main__':unittest.main(verbosity=2)
