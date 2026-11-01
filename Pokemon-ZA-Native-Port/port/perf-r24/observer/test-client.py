"""Offline tests for the actual observer client command and receipt paths."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import client

SID = '000004c4dad1b643'

class FakeFTP:
    def __init__(self, ack): self.ack = ack
    def retrbinary(self, cmd, callback, blocksize):
        assert cmd.endswith('/ack_1.json'), cmd
        callback(json.dumps(self.ack).encode())

class ClientTests(unittest.TestCase):
    def test_side_status_binds_mounted_param_to_target(self):
        side='/mnt/sandbox/PPSA91990_000/download0/zarecomp/observer'
        files={side+'/session.json':json.dumps({'title':'PPSA91762','protocol':17,'session':SID}).encode(),
               '/mnt/sandbox/PPSA91990_000/app0/sce_sys/param.json':b'{"titleId":"PPSA91990"}'}
        class FTP:
            def retrbinary(self,command,callback,blocksize):callback(files[command[5:]])
        with patch.object(client,'TITLE','PPSA91990'), patch.object(client,'BASE',side):
            self.assertEqual(client.status(FTP())['session'],SID)
            files['/mnt/sandbox/PPSA91990_000/app0/sce_sys/param.json']=b'{"titleId":"PPSA91762"}'
            with self.assertRaises(ValueError):client.status(FTP())
            files[side+'/session.json']=json.dumps({'title':'OTHER','protocol':17,'session':SID}).encode()
            with self.assertRaises(ValueError):client.status(FTP())

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

class ImmutableSpansTests(unittest.TestCase):
    def ack(self,mode='on'):
        flags=client.IMMUTABLE_MODES[mode]
        return dict(session=SID,seq=1,op='immutable_spans',result='applied',file='',
            requested_mode=mode,mode=mode,flags=flags,frame=900,cost_ns=123,runtime_result=flags+1)
    def test_immutable_command_strict_names(self):
        for mode in client.IMMUTABLE_MODES:
            self.assertEqual(client.text_command(SID,1,'immutable_spans',mode),f'{SID} 1 immutable_spans {mode}\n'.encode())
        for mode in ('ON','enabled','true','on extra','on\ninput A 10','',[],None,1):
            with self.subTest(mode=mode),self.assertRaises(ValueError):client.text_command(SID,1,'immutable_spans',mode)
        with self.assertRaises(ValueError):client.text_command(SID,1,'immutable_spans','on',1)
    def test_immutable_collect_binds_actual_to_local_request(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'records'
            for mode in client.IMMUTABLE_MODES:
                ack=self.ack(mode)
                self.assertEqual(client.collect(FakeFTP(ack),SID,1,out,expected_immutable_spans=mode)['ack'],ack)
            with self.assertRaises(ValueError):client.collect(FakeFTP(self.ack()),SID,1,out)
            with self.assertRaises(ValueError):client.collect(FakeFTP(self.ack('off')),SID,1,out,expected_immutable_spans='on')
            with self.assertRaises(ValueError):client.collect(FakeFTP(self.ack()),SID,1,out,expected_preparation='optimized',expected_immutable_spans='on')
    def test_immutable_untrusted_ack_rejected_before_write(self):
        ack=self.ack()
        changes=[{'op':'preparation'},{'op':'snapshot'},{'requested_mode':'off'},{'mode':'off'},{'mode':[]},
            {'flags':0},{'flags':True},{'flags':1.0},{'flags':2},{'flags':-1},{'mode':''},
            {'frame':0},{'frame':True},{'frame':-1},{'frame':2**64},{'cost_ns':-1},{'cost_ns':True},
            {'runtime_result':1},{'runtime_result':0},{'runtime_result':True},{'runtime_result':2**31},
            {'result':'queued'},{'file':'frame_900_1.png'},{'file':'../../save.bin'}]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'must-not-exist'
            for change in changes:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_immutable_spans='on')
                self.assertFalse(out.exists())
            for change in ({'session':'0000000000000000'},{'seq':True},{'seq':2}):
                with self.assertRaises(RuntimeError):client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_immutable_spans='on')
                self.assertFalse(out.exists())
    def test_immutable_failures_never_claim_application(self):
        ack={**self.ack(),'mode':'off','flags':0}
        cases=[dict(result='rejected_boundary',runtime_result=0,cost_ns=0),
            dict(result='rejected_boundary',runtime_result=0,cost_ns=0,frame=0),
            dict(result='rejected_in_menu',runtime_result=0,cost_ns=0,frame=0),
            dict(result='rejected_mode',runtime_result=-1),dict(result='drain_failed',runtime_result=-3),
            dict(result='receipt_mismatch',runtime_result=2),dict(result='receipt_mismatch',mode='',flags=-1)]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            for change in cases:
                record=client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_immutable_spans='on')
                self.assertNotEqual(record['ack']['result'],'applied')
            for change in (dict(result='drain_failed',runtime_result=2),dict(result='rejected_mode',runtime_result=-3),
                dict(result='rejected_boundary',runtime_result=0,cost_ns=1),dict(result='receipt_mismatch',mode='',flags=0)):
                with self.assertRaises(ValueError):client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_immutable_spans='on')


class SlotDepthTests(unittest.TestCase):
    def ack(self,target=16):
        return dict(session=SID,seq=1,op='slot_depth',result='applied',file='',frame=900,cost_ns=123,runtime_result=target,
            requested_slots=target,status_valid=True,status_abi_version=1,active_slots=target,capacity_slots=64,
            status_requested_slots=target,previous_slots=8,budget_valid=1,status_result=target,status_reserved=0,
            status_frame=900,drained_seq=100,completed_seq=100,pool_bytes=8<<30,largest_free_extent=3<<30,driver_bytes=2<<30,
            required_headroom_bytes=1<<30,transient_capacity_bytes=512<<20,descriptor_pools=32,command_buffers=32,counter_query_pools=16)
    def test_slot_depth_commands_are_exact(self):
        for value in (8,16,32,64,'8','16','32','64'):
            self.assertEqual(client.text_command(SID,1,'slot_depth',value),f'{SID} 1 slot_depth {value}\n'.encode())
        for value in (True,16.0,'08','016','+8','16 extra',24,-8,0,'',None,[],{}):
            with self.subTest(value=value),self.assertRaises(ValueError):client.text_command(SID,1,'slot_depth',value)
        with self.assertRaises(ValueError):client.text_command(SID,1,'slot_depth',16,1)
    def test_slot_depth_actual_collect_matches_local_intent(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            for target in (8,16,32,64):
                ack=self.ack(target)
                record=client.collect(FakeFTP(ack),SID,1,out,expected_slot_depth=target)
                self.assertEqual(record['ack'],ack);self.assertFalse(record['files'])
            # 8 remains available without a successful memory query.
            ack={**self.ack(8),'budget_valid':0,'largest_free_extent':0}
            self.assertEqual(client.collect(FakeFTP(ack),SID,1,out,expected_slot_depth='8')['ack']['active_slots'],8)
            for target in (None,8,True,'016',16.0):
                with self.assertRaises(ValueError):client.collect(FakeFTP(self.ack()),SID,1,out,expected_slot_depth=target)
            with self.assertRaises(ValueError):client.collect(FakeFTP(self.ack(8)),SID,1,out,expected_slot_depth=16)
    def test_slot_depth_bad_applied_receipts_cannot_write(self):
        ack=self.ack()
        cases=[{'op':'preparation'},{'requested_slots':8},{'requested_slots':True},{'status_requested_slots':8},
            {'active_slots':8},{'capacity_slots':32},{'status_abi_version':2},{'previous_slots':0},{'status_result':8},
            {'runtime_result':8},{'runtime_result':True},{'runtime_result':0},{'status_result':True},
            {'status_frame':899},{'frame':0},{'frame':True},{'completed_seq':99},{'drained_seq':-1},
            {'budget_valid':0},{'budget_valid':True},{'budget_valid':2},{'largest_free_extent':(1<<30)-1},
            {'required_headroom_bytes':0},{'required_headroom_bytes':(1<<30)-1},{'pool_bytes':-1},
            {'pool_bytes':0},{'pool_bytes':(64<<30)+1},{'largest_free_extent':(8<<30)+1},{'driver_bytes':(8<<30)+1},
            {'driver_bytes':2**64},{'transient_capacity_bytes':True},{'descriptor_pools':-1},{'command_buffers':None},
            {'counter_query_pools':'16'},{'status_reserved':1},{'status_valid':False},{'status_valid':1},
            {'cost_ns':True},{'result':'queued'},{'file':'frame_900_1.png'}]
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)/'must-not-exist'
            for change in cases:
                with self.subTest(change=change),self.assertRaises(ValueError):
                    client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_slot_depth=16)
                self.assertFalse(out.exists())
            for change in ({'session':'0'*16},{'seq':True},{'seq':2}):
                with self.assertRaises(RuntimeError):client.collect(FakeFTP({**ack,**change}),SID,1,out,expected_slot_depth=16)
                self.assertFalse(out.exists())
    def test_slot_depth_failures_and_old_status_are_distinct(self):
        ack={**self.ack(),'active_slots':8}
        negative={'rejected_depth':-1,'drain_failed':-3,'memory_gate':-4,'incompatible_profile':-5,'preflight_failed':-6}
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp)
            for result,code in negative.items():
                item={**ack,'result':result,'runtime_result':code,'status_result':code}
                self.assertEqual(client.collect(FakeFTP(item),SID,1,out,expected_slot_depth=16)['ack']['result'],result)
                for change in ({'active_slots':16},{'status_frame':899},{'status_result':16},{'runtime_result':16}):
                    with self.subTest(result=result,change=change),self.assertRaises(ValueError):
                        client.collect(FakeFTP({**item,**change}),SID,1,out,expected_slot_depth=16)
            # No runtime call: a coherent older status is explicitly identified.
            for result,frame in (('rejected_boundary',901),('rejected_boundary',0),('rejected_in_menu',0)):
                item={**self.ack(8),'result':result,'requested_slots':16,'runtime_result':0,'cost_ns':0,'frame':frame,'status_frame':700}
                self.assertEqual(client.collect(FakeFTP(item),SID,1,out,expected_slot_depth=16)['ack']['status_frame'],700)
                with self.assertRaises(ValueError):client.collect(FakeFTP({**item,'cost_ns':1}),SID,1,out,expected_slot_depth=16)
            for changes in ({'status_abi_version':2},{'active_slots':7},{'capacity_slots':32},{'status_reserved':1}):
                item={**ack,**changes,'status_valid':False,'result':'receipt_mismatch'}
                self.assertEqual(client.collect(FakeFTP(item),SID,1,out,expected_slot_depth=16)['ack']['result'],'receipt_mismatch')
            with self.assertRaises(ValueError):client.collect(FakeFTP({**ack,'status_valid':False,'result':'receipt_mismatch'}),SID,1,out,expected_slot_depth=16)


if __name__ == '__main__': unittest.main()

