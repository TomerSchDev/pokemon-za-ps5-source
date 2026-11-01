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

if __name__ == '__main__': unittest.main()
