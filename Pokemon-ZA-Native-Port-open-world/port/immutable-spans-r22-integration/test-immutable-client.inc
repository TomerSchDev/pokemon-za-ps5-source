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

