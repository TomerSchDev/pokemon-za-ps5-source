"""Focused offline tests for external evidence path and CPU bound checks."""
import tempfile
from pathlib import Path
import unittest
import analyze_external_run as e


class ExternalReviewTest(unittest.TestCase):
    def assessment(self,total):
        rows=[dict(frame=i,dt_ns=36000000) for i in range(1,57)]
        boot=dict(windows=[dict(start=1,frame=56,frames=56,line=10,
            perf=dict(threads=42,thread_cpu_ns=total,top_rows=[dict(id=i,ns=1000000000) for i in range(6)]))])
        return e.cpu_assessment(boot,rows,13)
    def test_impossible_thread_total_rejected(self):
        r=self.assessment(55000000000)
        self.assertEqual(r['status'],'unreliable_rejected')
        self.assertEqual(r['violating_windows'],1)
        self.assertEqual(r['windows'][0]['identical_top_deltas'],[dict(ns=1000000000,count=6)])
    def test_bound_is_not_semantics_proof(self):
        self.assertEqual(self.assessment(10000000000)['status'],'not_disproved_by_bound')
    def test_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):e.under(Path(d),'../escape')
    def test_snapshot_preserves_hash_and_prefix(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';dst=root/'dst';src.mkdir();dst.mkdir()
            (src/'log').write_bytes(b'complete\npartial')
            s=e.Snapshot(src,dst);p=s.copy('log',True)
            self.assertEqual(p.read_bytes(),b'complete\n')
            self.assertEqual((src/'log').read_bytes(),b'complete\npartial')
            self.assertNotEqual(s.manifest[0]['source_sha256_at_read'],s.manifest[0]['copy_sha256'])
    def test_png_reuse_keeps_verified_reference(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);src=root/'src';dst=root/'dst';old=root/'old';src.mkdir();dst.mkdir();(old/'originals').mkdir(parents=True)
            (src/'image.png').write_bytes(b'png fixture');(old/'originals/image.png').write_bytes(b'png fixture')
            s=e.Snapshot(src,dst,old);p=s.copy('image.png')
            self.assertEqual(p,old/'originals/image.png')
            self.assertFalse((dst/'originals/image.png').exists())
            self.assertEqual(s.manifest[0]['reused_snapshot_sha256'],s.manifest[0]['source_sha256_at_read'])
    def profile_text(self):
        return '\n'.join(['[gpuprof] frame 120: 3 marks, 3.00 ms first to last',
                          '[gpuprof] 1.000 ms 33.3% pass: first',
                          '[gpuprof] 2.000 ms 66.7% (submission start; includes GPU idle before it)',
                          '[gpuprof] frame 240: 2 marks, 1.00 ms first to last',
                          '[gpuprof] 1.000 ms 100.0% pass: later'])
    def test_pass_profile_selection_and_idle_separation(self):
        r=e.pass_profiles(self.profile_text(),100,200)
        self.assertEqual(r['selected_profile_frames'],[120])
        self.assertEqual(r['top_pass_labels'][0]['mean_ms_per_profiled_frame'],1)
        self.assertEqual(len(r['profiles'][0]['rows']),2)
    def test_incomplete_pass_profile_rejected(self):
        r=e.pass_profiles(self.profile_text().replace('3 marks','4 marks'),100,200)
        self.assertEqual(r['selected_profile_frames'],[]);self.assertEqual(len(r['rejected_profiles']),1)
    def test_inconsistent_pass_total_rejected(self):
        r=e.pass_profiles(self.profile_text().replace('3.00 ms first','4.00 ms first'),100,200)
        self.assertEqual(r['selected_profile_frames'],[]);self.assertEqual(len(r['rejected_profiles']),1)


if __name__=='__main__':unittest.main()
