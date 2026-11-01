"""Offline tests for the actual observer client command and receipt paths."""
import io
import json
from pathlib import Path
import tempfile
import unittest
import client

SID = '000004c4dad1b643'

class FakeFTP:
    def __init__(self, ack): self.ack = ack
    def retrbinary(self, cmd, callback, blocksize):
        assert cmd.endswith('/ack_1.json'), cmd
        callback(json.dumps(self.ack).encode())

class ClientTests(unittest.TestCase):
    def test_commands(self):
        for name in client.PROFILES:
            self.assertEqual(client.text_command(SID, 1, 'submission', name),
                             f'{SID} 1 submission {name}\n'.encode())
        self.assertEqual(client.text_command(SID, 1, 'measure', 20),
                         f'{SID} 1 measure 20\n'.encode())
        self.assertEqual(client.text_command(SID, 1, 'input', 'A', 1),
                         f'{SID} 1 input A 1\n'.encode())
        for bad in ('batch', 'batch3', 'each extra', 'BATCH4', ''):
            with self.assertRaises(AssertionError): client.text_command(SID, 1, 'submission', bad)
        with self.assertRaises(AssertionError): client.text_command(SID, 1, 'submission', 'each', 1)

    def test_actual_collect_validates_applied_receipt(self):
        ack = dict(session=SID, seq=1, op='submission', result='applied', file='',
                   requested_profile='batch4', profile='batch4', max_lists=4, frame=123, cost_ns=100)
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            self.assertEqual(client.collect(FakeFTP(ack), SID, 1, out)['ack'], ack)
            self.assertTrue((out/'command_1.json').exists())
            for changes in ({'max_lists':2}, {'profile':'each'}, {'frame':0},
                            {'result':'queued'}, {'requested_profile':'batch'}):
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack, **changes}), SID, 1, out)
            for result in ('rejected_boundary','rejected_override','drain_failed'):
                rejected = {**ack, 'result':result, 'profile':'', 'max_lists':0}
                self.assertEqual(client.collect(FakeFTP(rejected), SID, 1, out)['ack']['result'], result)
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**rejected, 'profile':'batch4', 'max_lists':4}), SID, 1, out)

    def preparation_ack(self,profile='optimized'):
        flags=client.PREPARATION_PROFILES[profile]
        return dict(session=SID,seq=1,op='preparation',result='applied',file='',
                    requested_profile=profile,profile=profile,flags=flags,frame=456,
                    cost_ns=123456,runtime_result=flags+1)

    def test_preparation_commands_and_strict_names(self):
        for name in client.PREPARATION_PROFILES:
            self.assertEqual(client.text_command(SID,1,'preparation',name),
                             f'{SID} 1 preparation {name}\n'.encode())
        for bad in ('plan','lazy','OPTIMIZED','optimized extra','baseline\ninput A 10','',None,1,[]):
            with self.assertRaises(ValueError):client.text_command(SID,1,'preparation',bad)
        with self.assertRaises(ValueError):client.text_command(SID,1,'preparation','baseline',1)

    def test_preparation_collect_binds_expected_request(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'records'
            for name in client.PREPARATION_PROFILES:
                ack=self.preparation_ack(name)
                record=client.collect(FakeFTP(ack),SID,1,out,expected_preparation=name)
                self.assertEqual(record['ack'],ack)
                self.assertEqual(record['files'],[])
            ack=self.preparation_ack()
            with self.assertRaises(ValueError):client.collect(FakeFTP(ack),SID,1,out)
            with self.assertRaises(ValueError):client.collect(FakeFTP(ack),SID,1,out,expected_preparation='baseline')
            # Internally consistent forged echo must not replace our actual intent.
            with self.assertRaises(ValueError):
                client.collect(FakeFTP(self.preparation_ack('baseline')),SID,1,out,expected_preparation='optimized')
            for change in ({'op':'submission'},{'op':'snapshot'},{'op':'invalid'}):
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_preparation='optimized')

    def test_preparation_collect_rejects_malformed_applied_receipts_before_writes(self):
        ack=self.preparation_ack()
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'must-not-exist'
            changes=[{'flags':1},{'flags':True},{'flags':3.0},{'flags':4},{'profile':'baseline'},
                     {'profile':'unknown'},{'profile':[]},{'profile':''},{'requested_profile':'plan'},
                     {'requested_profile':'baseline'},{'frame':0},{'frame':True},{'frame':-1},{'frame':2**64},
                     {'cost_ns':-1},{'cost_ns':True},{'cost_ns':None},{'cost_ns':2**64},
                     {'runtime_result':0},{'runtime_result':3},{'runtime_result':True},{'runtime_result':2**32},
                     {'result':'queued'},{'file':'frame_1_1.png'},{'file':'../../save.bin'}]
            for change in changes:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_preparation='optimized')
                self.assertFalse(out.exists())
            for change in ({'session':'0000000000000000'},{'seq':2},{'seq':True}):
                with self.assertRaises(RuntimeError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_preparation='optimized')
                self.assertFalse(out.exists())

    def test_preparation_rejections_report_actual_state_without_claiming_applied(self):
        ack={**self.preparation_ack(),'profile':'baseline','flags':0}
        valid=[dict(result='rejected_boundary',frame=456,cost_ns=0,runtime_result=0),
               dict(result='rejected_boundary',frame=0,cost_ns=0,runtime_result=0),
               dict(result='rejected_in_menu',frame=0,cost_ns=0,runtime_result=0),
               dict(result='rejected_profile',runtime_result=-1),
               dict(result='drain_failed',runtime_result=-3),
               dict(result='receipt_mismatch',runtime_result=4),
               dict(result='receipt_mismatch',profile='',flags=-1,runtime_result=4)]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            for changes in valid:
                item={**ack,**changes}
                record=client.collect(FakeFTP(item),SID,1,out,expected_preparation='optimized')
                self.assertNotEqual(record['ack']['result'],'applied')
            bad=[dict(result='rejected_boundary',runtime_result=4,cost_ns=0),
                 dict(result='rejected_in_menu',frame=1,runtime_result=0,cost_ns=0),
                 dict(result='drain_failed',runtime_result=4),
                 dict(result='rejected_profile',runtime_result=-3),
                 dict(result='receipt_mismatch',profile='',flags=0),
                 dict(result='applied',profile='',flags=-1,runtime_result=4)]
            for changes in bad:
                with self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**changes}),SID,1,out,expected_preparation='optimized')

class RetirementTests(unittest.TestCase):
    target='0123456789abcdef:9000'
    def ack(self):
        return dict(session=SID,seq=1,op='retire_capture',result='retired',file='',cost_ns=123,
                    target_session='0123456789abcdef',target_seq=9000,
                    retired_file='frame_123_9000.png',removed=True,bytes=40000000,error_number=0)
    def test_command_scope(self):
        self.assertEqual(client.text_command(SID,1,'retire_capture',self.target),f'{SID} 1 retire_capture {self.target}\n'.encode())
        self.assertEqual(client.text_command(SID,3,'retire_capture',SID+':2'),f'{SID} 3 retire_capture {SID}:2\n'.encode())
        bad=[None,[],1,'../x:1','0123456789ABCDEF:1','0123456789abcdef:0','0123456789abcdef:01',
             '0123456789abcdef:18446744073709551616','0123456789abcdef:1 extra','0123456789abcdef:1/../../save',SID+':1']
        for target in bad:
            with self.subTest(target=target),self.assertRaises(ValueError):client.text_command(SID,1,'retire_capture',target)
        with self.assertRaises(ValueError):client.text_command(SID,1,'retire_capture',self.target,1)
    def test_collect_never_fetches_retired_file(self):
        with tempfile.TemporaryDirectory() as temp:
            result=client.collect(FakeFTP(self.ack()),SID,1,Path(temp),expected_retire_capture=self.target)
            self.assertEqual(result['files'],[])
            self.assertTrue(result['ack']['removed'])
    def test_receipt_matches_local_intent_before_writes(self):
        ack=self.ack()
        changes=[{'target_session':SID},{'target_seq':1},{'target_seq':True},{'op':'snapshot'},{'file':'frame_1_1.png'},
                 {'retired_file':'../../save/main'},{'retired_file':'frame_1_9001.png'},{'retired_file':'frame_01_9000.png'},
                 {'retired_file':'frame_18446744073709551616_9000.png'},{'removed':False},{'removed':1},
                 {'bytes':True},{'bytes':32},{'cost_ns':-1},{'error_number':1},{'result':'queued'}]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'must-not-exist'
            for change in changes:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_retire_capture=self.target)
                self.assertFalse(out.exists())
            with self.assertRaises(ValueError):client.collect(FakeFTP(ack),SID,1,out)
            with self.assertRaises(ValueError):client.collect(FakeFTP(ack),SID,1,out,expected_retire_capture='0123456789abcdef:9001')
            with self.assertRaises(RuntimeError):client.collect(FakeFTP({**ack,'seq':True}),SID,1,out,expected_retire_capture=self.target)
    def test_failure_receipts_do_not_claim_deletion(self):
        ack=self.ack()
        with tempfile.TemporaryDirectory() as temp:
            for result in ('already_absent','capture_stat_failed','invalid_capture_file','unlink_failed','session_changed','capture_changed'):
                item={**ack,'result':result,'removed':False,'bytes':0,'error_number':2}
                self.assertFalse(client.collect(FakeFTP(item),SID,1,Path(temp),expected_retire_capture=self.target)['ack']['removed'])

    def test_filesystem_diagnostics(self):
        ack={**self.ack(),'fs_step':'unlink','fs_result':0,'fs_mode':33188,
             'lstat_result':-1,'lstat_errno':13,'lstat_mode':0}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            self.assertTrue(client.collect(FakeFTP(ack),SID,1,out,expected_retire_capture=self.target)['ack']['removed'])
            for change in ({'fs_step':'unknown'},{'fs_result':-1},{'fs_mode':True},
                           {'lstat_mode':-1},{'lstat_result':2**31},{'lstat_errno':None}):
                with self.subTest(change=change),self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_retire_capture=self.target)
            for result in ('rejected_target','invalid_session_directory','missing_snapshot_ack','invalid_snapshot_ack'):
                item={**ack,'result':result,'removed':False,'retired_file':'','bytes':0,'error_number':0}
                self.assertFalse(client.collect(FakeFTP(item),SID,1,Path(temp),expected_retire_capture=self.target)['ack']['removed'])

if __name__ == '__main__': unittest.main()
