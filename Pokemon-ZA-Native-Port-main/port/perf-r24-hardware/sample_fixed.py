"""One 20-second stationary sample on recorded r23c/r24, captures outside it.

Does not launch, close, move, change mode/config, or touch saves. Five commands:
before snapshot, measurement, after snapshot, two verified capture retirements.
"""
import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'port/perf-r24'))
import console as wrapper
b=wrapper.base
spec=importlib.util.spec_from_file_location('slots_sampler',ROOT/'port/perf-r24/sample_slots_r24.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--client',choices=('r23c','r24'),required=True)
    p.add_argument('--session',required=True);p.add_argument('--pid',type=int,required=True)
    p.add_argument('--seq',type=int,required=True);p.add_argument('--label',required=True)
    a=p.parse_args()
    assert a.label and all(x.isalnum() or x in '-_' for x in a.label)
    folder='perf-r24/observer' if a.client=='r24' else 'slot-depth-r23c-observer'
    client_path=ROOT/'port'/folder/'client.py'
    client_spec=importlib.util.spec_from_file_location('fixed_client_'+a.client,client_path)
    client=importlib.util.module_from_spec(client_spec);client_spec.loader.exec_module(client)
    s.client=client
    out=b.H/('session-'+a.session)/a.label;out.mkdir(parents=True,exist_ok=False)
    owner=json.loads((out.parent/'identity.json').read_text())
    assert owner['client']==a.client and owner['pid']==a.pid and owner['session']==a.session and owner['backup_verified']
    c=b.r.Console()
    try:
        assert b.check(c,client,a.session,a.pid)==owner['run']
        record=dict(at=b.r.utc_now(),session=a.session,pid=a.pid,run=owner['run'],client=a.client,
                    eboot_sha256=owner['eboot_sha256'],seconds=20,fps_mode=0,sequence_start=a.seq,completed=False)
        s.write(out/'phase.json',record)
        client.issue(c.ftp,a.session,a.seq,'snapshot')
        record['before']=s.collect(c.ftp,a.session,a.seq,out,'saved')
        client.issue(c.ftp,a.session,a.seq+1,'measure',20)
        record['settling']=s.collect(c.ftp,a.session,a.seq+1,out,'settling')
        print(json.dumps(dict(stage='measuring',seq=a.seq+1,label=a.label)),flush=True)
        time.sleep(23) # no FTP, screenshots, input, process poll inside measurement
        record['measurement']=s.collect(c.ftp,a.session,a.seq+1,out,'complete')
        client.issue(c.ftp,a.session,a.seq+2,'snapshot')
        record['after']=s.collect(c.ftp,a.session,a.seq+2,out,'saved')
        s.retire_snapshot(c,a.session,a.seq+3,record['before'],out)
        s.retire_snapshot(c,a.session,a.seq+4,record['after'],out)
        assert b.check(c,client,a.session,a.pid)==owner['run']
        analysis=json.loads((out/f'measure_{a.seq+1}-analysis.json').read_text())
        assert analysis['all_intervals']['duration_s']>=19.85
        assert analysis['fps_modes']==[0] and not analysis['capture_inside_window']
        record['completed']=True;record['completed_at']=b.r.utc_now()
        record['shader_affected_intervals']=analysis['shader_affected_intervals']
        record['clean']=analysis['shader_affected_intervals']==0
        s.write(out/'phase.json',record)
        print(json.dumps(dict(path=str(out),next_sequence=a.seq+5,clean=record['clean'],timing=analysis['all_intervals'])),flush=True)
    finally:c.close()

if __name__=='__main__':main()
