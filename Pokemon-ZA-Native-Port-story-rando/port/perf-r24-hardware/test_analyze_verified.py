"""Offline malformed-evidence and aggregation tests; no console access."""
import copy
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
import analyze_verified as a

SID='0123456789abcdef'
SHA='a'*64


def perf(frame, threads=-1, gaps=1):
    v={k:0 for k in a.BASE_KEYS+a.GPU_KEYS}
    v.update(frame=frame,frames=20,logic_ns=100000000,logic_n=20,
             present_ns=200000000,present_n=20,klock_takes=100,klock_blocked=2,
             klock_wait_ns=500000,dcache_tables=0,dcb=40,kwords=10,
             flush_ns=1000,dcb_submit_ns=2000,kick_ns=3000,gaps=gaps,
             spans=10,gpu_span_ns=30000000,gpu_busy_ns=20000000,idle_ns=10000000,
             idle_between_ns=10000000,ngaps=1,gap_ge8ms=1,threads=threads)
    if not gaps:
        for k in a.GPU_KEYS:del v[k]
    if threads>=0:v.update(thread_cpu_ns=10000000,top='1:10000000:10:2:abcd')
    return '[za-r24-perf] '+' '.join(f'{k}={v}' for k,v in v.items())


def report(frame,threads=-1,gaps=1,slots=16):
    return '\n'.join([
        f'[za-r23-slots] active={slots} capacity=64 preparation=0 immutable=0',
        '[za-r21-prep] profile=baseline flags=0',
        '[za-r20b-submit] profile=batch4 logical=100 vk_calls=25',
        perf(frame,threads,gaps),
        f'[vk] t=20.0 frame {frame} 5.0 fps (20 draws, 5 passes, 1 dispatches) | submit 20 ms | cpu exec 40 draw 5 sets 1 (pre 2 key 3 dyn 4 tex 5 (upload 6) vtx 7) | gpu 30'])


def fixture():
    columns=['frame','now_ns','dt_ns','submitted_interval','represented_interval','shader_before','shader_after','mode','observer_ns']
    rows=[dict(zip(columns,[f,10000000000+f*200000000,200000000,1,0,5<<32,5<<32,0,1000])) for f in range(101,201)]
    log='\n'.join(['[za-title-randomizer-r24-perf] main reached',
                   '[za-r24-options] gaps=1','[za-r24-options] dcache=tls','[za-r24-options] prof=0',
                   '[za-r24] dispatch cache: thread-local (as r20b)',
                   '[za-r24] GPU timeline: on (timestamp period 1.000 ns)',
                   f'[vk] saved /observer/session_{SID}/frame_90_2.png',
                   *[report(f) for f in range(100,221,20)],
                   f'[vk] saved /observer/session_{SID}/frame_221_4.png'])
    ident=dict(client='r24',backup_verified=True,session=SID,pid=123,run='same-run',eboot_sha256=SHA)
    return ident,rows,log


class EvidenceTest(unittest.TestCase):
    def run_fixture(self,mutate=None,**kwargs):
        ident,rows,log=fixture()
        state=dict(identity=ident,rows=rows,log=log)
        if mutate:mutate(state)
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            buf=io.StringIO(newline='')
            writer=csv.DictWriter(buf,fieldnames=list(state['rows'][0]))
            writer.writeheader();writer.writerows(state['rows'])
            raw=buf.getvalue().encode()
            receipt=dict(ack=dict(session=SID,seq=3,op='measure',result='complete',file='measure_3.csv'),
                         files=[dict(name='measure_3.csv',bytes=len(raw),sha256=a.sha(raw),readback_verified=True)])
            if state.get('phase'):
                phase=dict(completed=True,session=SID,pid=123,run='same-run',client='r24',eboot_sha256=SHA,fps_mode=0,measurement=receipt)
                for key,frame,seq in (('before',90,2),('after',221,4)):
                    name=f'frame_{frame}_{seq}.png';image=b'fixture image bytes'
                    (root/name).write_bytes(image)
                    phase[key]=dict(ack=dict(session=SID,seq=seq,op='snapshot',result='saved',file=name),
                                    files=[dict(name=name,bytes=len(image),sha256=a.sha(image),readback_verified=True)])
                receipt=phase
            if 'receipt_mutator' in state:state['receipt_mutator'](receipt)
            (root/'identity.json').write_text(json.dumps(state['identity']))
            (root/'receipt.json').write_text(json.dumps(receipt))
            (root/'measure_3.csv').write_bytes(raw)
            (root/'klog').write_text(state['log'])
            return a.analyze(root/'identity.json',root/'receipt.json',root/'measure_3.csv',root/'klog',SHA,**kwargs)

    def bad(self,mutate,part):
        result=self.run_fixture(mutate)
        self.assertEqual(result['status'],'invalid',result)
        self.assertIn(part,result['reason'],result)

    def test_valid_resets_sum_and_units(self):
        r=self.run_fixture();self.assertEqual(r['status'],'verified',r)
        self.assertEqual(r['r24']['covered_frames'],100)
        self.assertEqual(r['r24']['counter_totals']['dcb'],200)
        self.assertEqual(r['r24']['logic_ms_mean'],5)
        self.assertEqual(r['r24']['cpu_ms_per_report_frame']['present_ns'],10)
        self.assertEqual(r['r24']['gpu']['observed_span_union_ms_per_report_frame'],1)
        self.assertEqual(r['r24']['gpu']['histogram']['gap_ge8ms'],5)
        self.assertIsNone(r['r24']['threads'])

    def test_available_threads(self):
        r=self.run_fixture(lambda s:s.update(log=s['log'].replace('threads=-1','threads=1 thread_cpu_ns=10000000 top=1:10000000:10:2:abcd')))
        self.assertEqual(r['status'],'verified',r)
        self.assertEqual(r['r24']['threads']['cpu_ms_per_available_report_frame'],.5)

    def test_gaps_disabled_stays_null(self):
        def change(s):
            s['log']=s['log'].replace('gaps=1','gaps=0').replace('GPU timeline: on','GPU timeline: off')
        r=self.run_fixture(change,expected_gaps=0)
        self.assertEqual(r['status'],'verified',r);self.assertIsNone(r['r24']['gpu'])

    def test_right_boot_not_last_reaching_frames(self):
        r=self.run_fixture(lambda s:s.update(log=s['log']+'\n[za-title-randomizer-r24-perf] main reached\n'+report(10000)))
        self.assertEqual(r['status'],'verified',r)
        self.assertEqual(r['r24']['covered_frames'],100)

    def test_no_boot_header(self):self.bad(lambda s:s.update(log=s['log'].replace('[za-title-randomizer-r24-perf] main reached','')),'log boot')
    def test_wrong_sid(self):self.bad(lambda s:s['identity'].update(session='b'*16),'acknowledgement')
    def test_wrong_sha(self):self.bad(lambda s:s['identity'].update(eboot_sha256='b'*64),'artifact hash')
    def test_unverified_backup(self):self.bad(lambda s:s['identity'].update(backup_verified=False),'backup')
    def test_csv_hash(self):self.bad(lambda s:s.update(receipt_mutator=lambda r:r['files'][0].update(sha256='c'*64)),'exact verified receipt')
    def test_receipt_wrong_seq(self):self.bad(lambda s:s.update(receipt_mutator=lambda r:r['ack'].update(seq=4)),'filename/sequence')
    def test_unverified_readback(self):self.bad(lambda s:s.update(receipt_mutator=lambda r:r['files'][0].update(readback_verified=False)),'exact verified receipt')
    def test_mixed_mode(self):self.bad(lambda s:s['rows'][1].update(mode=1),'FPS mode')
    def test_shader_active(self):self.bad(lambda s:s['rows'][1].update(shader_before=(5<<32)|1),'shader work')
    def test_shader_completed_inside(self):self.bad(lambda s:s['rows'][1].update(shader_after=6<<32),'shader work')
    def test_represented(self):self.bad(lambda s:s['rows'][1].update(represented_interval=1),'represented')
    def test_unsubmitted(self):self.bad(lambda s:s['rows'][1].update(submitted_interval=0),'unsubmitted')
    def test_noncontiguous(self):self.bad(lambda s:s['rows'][1].update(frame=103),'CSV')
    def test_short(self):self.bad(lambda s:s.update(rows=s['rows'][:20]),'shorter')
    def test_capture_during(self):self.bad(lambda s:s.update(log=s['log']+f'\n[vk] saved /observer/session_{SID}/frame_150_9.png'),'capture overlaps')
    def test_control_during(self):self.bad(lambda s:s.update(log=s['log']+'\n[za-r23-slots] switch frame=150 active=32'),'control transition')
    def test_malformed_control(self):self.bad(lambda s:s.update(log=s['log']+'\n[za-r23-slots] switch partial'),'malformed control')
    def test_duplicate_sid_across_boots(self):self.bad(lambda s:s.update(log=s['log']+f'\n[za-title-randomizer-r24-perf] main reached\n/v/session_{SID}/'), 'ambiguous')
    def test_multiple_sids_same_boot(self):self.bad(lambda s:s.update(log=s['log']+'\n/v/session_aaaaaaaaaaaaaaaa/'),'multiple sessions')
    def test_negative_counter(self):self.bad(lambda s:s.update(log=s['log'].replace('flush_ns=1000','flush_ns=-1')),'unsigned')
    def test_missing_counter(self):self.bad(lambda s:s.update(log=s['log'].replace('flush_ns=1000','')),'missing r24')
    def test_duplicate_counter(self):self.bad(lambda s:s.update(log=s['log'].replace('flush_ns=1000','flush_ns=1000 flush_ns=1000')),'duplicate field')
    def test_histogram_invariant(self):self.bad(lambda s:s.update(log=s['log'].replace('ngaps=1','ngaps=2')),'histogram')
    def test_span_union_invariant(self):self.bad(lambda s:s.update(log=s['log'].replace('gpu_span_ns=30000000','gpu_span_ns=40000000')),'span union')
    def test_wrong_slots(self):self.bad(lambda s:s.update(log=s['log'].replace('active=16','active=32')),'runtime slot')
    def test_wrong_dispatch(self):self.bad(lambda s:s.update(log=s['log'].replace('thread-local (as r20b)','per Cpu (no emulated TLS)')),'dispatch mode')
    def test_truncated_tail(self):self.bad(lambda s:s.update(log=s['log'].split(report(200))[0]),'log does not extend')
    def test_counter_frames_mismatch(self):self.bad(lambda s:s.update(log=s['log'].replace('frames=20','frames=19')),'counter interval')
    def test_phase_positive(self):
        r=self.run_fixture(lambda s:s.update(phase=True));self.assertEqual(r['status'],'verified',r)
    def test_phase_wrong_pid(self):self.bad(lambda s:s.update(phase=True,receipt_mutator=lambda r:r.update(pid=999)),'phase identity')
    def test_phase_wrong_snapshot_hash(self):self.bad(lambda s:s.update(phase=True,receipt_mutator=lambda r:r['before']['files'][0].update(sha256='f'*64)),'snapshot hash')
    def test_phase_wrong_snapshot_sid(self):self.bad(lambda s:s.update(phase=True,receipt_mutator=lambda r:r['after']['ack'].update(session='f'*16)),'snapshot acknowledgement')
    def test_aba_weighted(self):
        r=self.run_fixture();q=copy.deepcopy(r)
        q['timing']['all_intervals']['interval_rate_fps']=6
        comp=a.compare_aba(r,q,r,'synthetic')
        self.assertAlmostEqual(comp['candidate_gain_pct'],20)
        q['identity']['run']='wrong'
        with self.assertRaisesRegex(ValueError,'different randomizer'):a.compare_aba(r,q,r,'x')
    def test_aba_external_interference_rejected(self):
        r=self.run_fixture();q=copy.deepcopy(r);q['comparison_eligible']=False
        with self.assertRaisesRegex(ValueError,'external interference'):a.compare_aba(r,q,r,'x')


if __name__=='__main__':unittest.main()
