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

