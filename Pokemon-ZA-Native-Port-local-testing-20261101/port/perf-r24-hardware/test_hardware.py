"""Actual r24 deployment/config helper tests using an in-memory console transport.

No hardware, network or production filesystem mutations. Test fixtures replace
only source binaries/remote transport; production identity/config/deploy checks run.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location('tested_r24_hardware',Path(__file__).with_name('hardware.py'))
h=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(h)

def sha(b):return hashlib.sha256(b).hexdigest()

class Source:
    def __init__(self,data):self.data=data
    def read_bytes(self):return self.data
    def __str__(self):return '<test-source>'

class Console:
    def __init__(self):
        self.app=h.t.APP
        self.files={self.app+'/eboot.bin':b'baseline',
          self.app+'/sce_sys/param.json':json.dumps({'titleId':'PPSA91762'}).encode(),
          '/user/app/PPSA91762/mount.lnk':self.app.encode(),
          self.app+'/slot-depth-options.txt':b'16\n',
          self.app+'/perf-r24-options.txt':b'old-options\n'}
        self.files.update({self.app+'/'+n:d for n,d in h.FIXED.items()})
        self.ftp=self;self.writes=[];self.renames=[];self.closed=False
        self.fail_stage_rename=False;self.corrupt_stage=False
    def read(self,path,limit=None):
        data=self.files.get(path)
        if data is not None and limit is not None:assert len(data)<=limit
        return data
    def sha256(self,path):return sha(self.files[path])
    def store(self,path,data):
        self.writes.append((path,data))
        self.files[path]=data+(b'corrupt' if self.corrupt_stage and 'stage-' in path else b'')
    def chmod(self,path,mode):assert path in self.files and mode=='755'
    def rename(self,src,dst):
        self.renames.append((src,dst))
        if self.fail_stage_rename and 'stage-' in src:
            self.fail_stage_rename=False;raise OSError('mock rename failure')
        self.files[dst]=self.files.pop(src)
    def close(self):self.closed=True

class HardwareTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='za-r24-helper-test-')
        self.addCleanup(self.tmp.cleanup)
        self.out=Path(self.tmp.name)
        self.c=Console();self.procs=[];self.counter=0
        self.old_options=h.t.options
        self.addCleanup(setattr,h.t,'options',self.old_options)
        self.patches=[patch.object(h,'E',self.out),
          patch.object(h,'CANDIDATE',sha(b'candidate')),
          patch.object(h.t,'SOURCE',Source(b'candidate')),
          patch.object(h.t,'BASE',Source(b'baseline')),
          patch.object(h.t,'BASE_SHA',sha(b'baseline')),
          patch.object(h.r,'Console',return_value=self.c),
          patch.object(h.r,'eboot_processes',side_effect=lambda:list(self.procs)),
          patch.object(h.r,'stamp',side_effect=self.stamp),
          patch.object(h.r,'http_text',return_value='mock launched')]
        for p in self.patches:p.start();self.addCleanup(p.stop)
    def stamp(self):self.counter+=1;return f'test-{self.counter:04}'
    def run_main(self,*args):
        with patch('sys.argv',['hardware.py',*args]):h.main()
    def unchanged(self):self.assertEqual(self.c.files[self.c.app+'/eboot.bin'],b'baseline')
    def test_active_process_cannot_modify_or_launch(self):
        self.procs=[{'pid':42,'titleId':'PPSA91762'}]
        for op in ('install24','install23','config','launch'):
            with self.assertRaises(RuntimeError):self.run_main(op)
        self.assertFalse(self.c.writes);self.assertFalse(self.c.renames);self.unchanged()
    def test_identity_and_mount_fail_closed(self):
        for target,bad in ((self.c.app+'/sce_sys/param.json',b'{"titleId":"OTHER"}'),
                           ('/user/app/PPSA91762/mount.lnk',b'/data/other')):
            old=self.c.files[target];self.c.files[target]=bad
            with self.assertRaises(AssertionError):self.run_main('install24')
            self.c.files[target]=old
        self.assertFalse(self.c.writes);self.unchanged()
    def test_unknown_binary_cannot_modify(self):
        self.c.files[self.c.app+'/eboot.bin']=b'unknown'
        for op in ('install24','install23','config','launch'):
            with self.assertRaises(AssertionError):self.run_main(op)
        self.assertFalse(self.c.writes)
    def test_corrupt_candidate_fails_before_remote_open(self):
        with patch.object(h.t,'SOURCE',Source(b'corrupt')):
            with self.assertRaises(AssertionError):self.run_main('install24')
        h.r.Console.assert_not_called();self.assertFalse(self.c.writes)
    def test_fixed_options_are_preserved_not_repaired_silently(self):
        for name in h.FIXED:
            key=self.c.app+'/'+name;old=self.c.files[key];self.c.files[key]=b'wrong'
            with self.assertRaises(AssertionError):self.run_main('config')
            self.c.files[key]=old
        self.assertFalse(self.c.writes)
    def test_config_exact_bytes_and_idempotency(self):
        fixed_before={n:self.c.files[self.c.app+'/'+n] for n in h.FIXED}
        self.run_main('config','--profile','1080')
        self.assertEqual(self.c.files[self.c.app+'/perf-r24-options.txt'],h.PROFILES['1080'])
        self.assertEqual(self.c.files[self.c.app+'/slot-depth-options.txt'],b'16\n')
        count=len(self.c.writes);self.run_main('config','--profile','1080')
        self.assertEqual(len(self.c.writes),count)
        self.assertEqual(fixed_before,{n:self.c.files[self.c.app+'/'+n] for n in h.FIXED})
        self.assertTrue(all('/data/homebrew/PPSA91762/' in p for p,_ in self.c.writes))
    def test_config_rename_failure_restores_previous_bytes(self):
        old=self.c.files[self.c.app+'/perf-r24-options.txt'];self.c.fail_stage_rename=True
        with self.assertRaises(OSError):self.run_main('config','--profile','cpu')
        self.assertEqual(self.c.files[self.c.app+'/perf-r24-options.txt'],old)
        self.unchanged()
    def test_corrupt_staged_binary_does_not_replace_installed(self):
        self.c.corrupt_stage=True
        with self.assertRaises(AssertionError):self.run_main('install24')
        self.unchanged();self.assertFalse(self.c.renames)
    def test_process_opened_during_upload_stops_before_replacement(self):
        original=self.c.store
        def store_then_busy(path,data):
            original(path,data);self.procs.append({'pid':99,'titleId':'PPSA91762'})
        with patch.object(self.c,'store',side_effect=store_then_busy):
            with self.assertRaises(RuntimeError):self.run_main('install24')
        self.unchanged();self.assertFalse(self.c.renames)
    def test_missing_new_config_is_created_without_touching_fixed(self):
        del self.c.files[self.c.app+'/perf-r24-options.txt']
        self.run_main('config')
        self.assertEqual(self.c.files[self.c.app+'/perf-r24-options.txt'],h.PROFILES['default'])
        self.assertEqual(self.c.files[self.c.app+'/performance-options.txt'],b'optimized\n')
        self.assertFalse(any('perf-r24-options.txt.before' in p for p in self.c.files))
    def test_shader_diagnostic_blocks_update(self):
        self.c.files[self.c.app+'/local-shader-test.txt']=b'test\n'
        with self.assertRaises(AssertionError):self.run_main('install24')
        self.assertFalse(self.c.writes);self.unchanged()
    def test_successful_install_then_restore_base_preserves_fixed(self):
        fixed_before={n:self.c.files[self.c.app+'/'+n] for n in h.FIXED}
        self.run_main('install24')
        self.assertEqual(self.c.files[self.c.app+'/eboot.bin'],b'candidate')
        self.assertEqual(self.c.files[self.c.app+'/perf-r24-options.txt'],h.PROFILES['default'])
        self.run_main('install23')
        self.unchanged()
        self.assertEqual(fixed_before,{n:self.c.files[self.c.app+'/'+n] for n in h.FIXED})
        self.assertEqual(self.c.files[self.c.app+'/slot-depth-options.txt'],b'16\n')
        self.assertTrue(any(data==b'candidate' and 'before-r20' in name for name,data in self.c.files.items()))
    def test_launch_requires_matching_version_and_options(self):
        with self.assertRaises(AssertionError):self.run_main('launch')
        self.run_main('launch','--version','r23c')
        self.assertFalse(self.c.writes);h.r.http_text.assert_called_once()
    def test_backup_is_read_only_and_double_verified(self):
        base='/mnt/sandbox/PPSA91762_000'
        self.c.files[base+'/app0/sce_sys/param.json']=b'{"titleId":"PPSA91762"}'
        root=base+'/download0/zarecomp/rando';run='rtest-123'
        self.c.files[root+'/active.json']=json.dumps({'id':run}).encode()
        self.c.files[root+'/'+run+'/report.json']=b'{"seed":1}'
        self.c.files[root+'/'+run+'/save/save_0/main']=b'mock-save'
        self.run_main('backup');self.assertFalse(self.c.writes);self.assertFalse(self.c.renames)
        result=json.loads(next(self.out.glob('backup-*/verification.json')).read_text())
        self.assertTrue(result['double_read_verified']);self.assertEqual(result['run'],run)
        self.assertEqual(len(result['files']),2)

if __name__=='__main__':unittest.main(verbosity=2)
