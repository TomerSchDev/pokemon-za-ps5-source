"""Reproduce only the separate r23 observer/client from finalized r22 sources."""
from pathlib import Path
import hashlib,json,shutil,difflib
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE=ROOT/'port/immutable-spans-r22-integration'
EVID=ROOT/'evidence/slot-depth-r23-observer'

def once(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected unique anchor: '+old[:80])
    return text.replace(old,new,1)
def write(path,text):path.write_text(text,encoding='utf-8',newline='\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ready=json.loads((ROOT/'evidence/immutable-spans-r22-integration/ready.json').read_text())
    for name,h in ready['files'].items():assert sha(BASE/name)==h,name
    for name in ('analyze.py','observer.h','preparation-observer-api.h','immutable-control.h','immutable-observer.inc',
                 'retire-capture.inc','test-retire.inc','test-immutable-observer-stubs.inc','test-immutable-observer.inc'):
        shutil.copy2(BASE/name,HERE/name)
    original=(BASE/'observer-r22.c').read_text();s=original
    s=once(s,'#include "immutable-control.h"','#include "immutable-control.h"\n#include "slot-depth-control.h"')
    s=once(s,'#include "immutable-observer.inc"','#include "immutable-observer.inc"\n#include "slot-depth-observer.inc"')
    s=once(s,'    if (!strcmp(op,"immutable_spans") && count == 4 && immutable_mode(arg) >= 0) valid = true;',
        '    if (!strcmp(op,"immutable_spans") && count == 4 && immutable_mode(arg) >= 0) valid = true;\n    if (!strcmp(op,"slot_depth") && count == 4 && slot_depth_value(arg)) valid = true;')
    s=once(s,'    if (!strcmp(c.op,"immutable_spans")) { ack_immutable(&c,"rejected_in_menu",0,0,0); return false; }',
        '    if (!strcmp(c.op,"immutable_spans")) { ack_immutable(&c,"rejected_in_menu",0,0,0); return false; }\n    if (!strcmp(c.op,"slot_depth")) { ack_slot_depth(&c,"rejected_in_menu",0,0,0); return false; }')
    s=once(s,'    } else if(!strcmp(c.op,"fps")) {','''    } else if(!strcmp(c.op,"slot_depth")) {
        if (!frame || !submitted || represented) { ack_slot_depth(&c,"rejected_boundary",0,frame,0); return; }
        uint64_t before=plat_now_ns();
        int applied=za_slot_depth_switch(c.arg,frame);
        ack_slot_depth(&c,slot_depth_result(applied),applied,frame,plat_now_ns()-before);
    } else if(!strcmp(c.op,"fps")) {''')
    write(HERE/'observer-r23.c',s)
    patch=list(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='r22/observer-r22.c',tofile='r23/observer-r23.c'))
    original=(BASE/'client.py').read_text();s=original
    s=once(s,"    elif op=='retire_capture':",'''    elif op=='slot_depth':
        canonical_slot_depth(arg)
        if frames is not None:raise ValueError('Slot depth command takes exactly one target')
    elif op=='retire_capture':''')
    s=once(s,'def validate_retire_capture_ack(',(HERE/'slot-depth-client.inc').read_text()+'\ndef validate_retire_capture_ack(')
    s=once(s,'expected_immutable_spans=None):','expected_immutable_spans=None,expected_slot_depth=None):')
    s=once(s,'    validate_submission_ack(ack)','''    if ack.get('op')=='slot_depth' or expected_slot_depth is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_slot_depth_ack(ack,expected_slot_depth)
    validate_submission_ack(ack)''')
    s=once(s,"'immutable_spans','retire_capture','collect'","'immutable_spans','slot_depth','retire_capture','collect'")
    s=once(s,"        if op=='immutable_spans':s.add_argument('value',choices=tuple(IMMUTABLE_MODES))",
        "        if op=='immutable_spans':s.add_argument('value',choices=tuple(IMMUTABLE_MODES))\n        if op=='slot_depth':s.add_argument('value',type=int,choices=(8,16))")
    s=once(s,"            s.add_argument('--immutable-spans',", "            s.add_argument('--slot-depth',type=int,choices=(8,16),help='Exact intended slot depth; required for its receipt')\n            s.add_argument('--immutable-spans',")
    s=once(s,'args.retire_capture,args.immutable_spans)','args.retire_capture,args.immutable_spans,args.slot_depth)')
    write(HERE/'client.py',s)
    patch.extend(difflib.unified_diff(original.splitlines(True),s.splitlines(True),fromfile='r22/client.py',tofile='r23/client.py'))
    s=(BASE/'test-observer.c').read_text().replace('#include "observer-r22.c"','#include "observer-r23.c"')
    s=once(s,'char path[320],buf[900]','char path[320],buf[2400]')
    s=once(s,'#include "test-immutable-observer-stubs.inc"','#include "test-immutable-observer-stubs.inc"\n#include "test-slot-depth-stubs.inc"')
    s=once(s,'#include "test-immutable-observer.inc"','#include "test-immutable-observer.inc"\n#include "test-slot-depth.inc"')
    s=once(s,'    test_immutable_observer(&serial,&i);','    test_immutable_observer(&serial,&i);\n    test_slot_depth(&serial,&i);')
    write(HERE/'test-observer.c',s)
    s=(BASE/'test-client.py').read_text()
    s=once(s,"if __name__ == '__main__': unittest.main()",(HERE/'test-slot-depth-client.inc').read_text()+"\nif __name__ == '__main__': unittest.main()")
    write(HERE/'test-client.py',s)
    EVID.mkdir(parents=True,exist_ok=True)
    write(EVID/'observer-client-r23.patch',''.join(patch))
    write(EVID/'base-manifest.json',json.dumps({'base':'r22 integration','base_files':ready['files'],
        'copied_retirement_sha256':sha(HERE/'retire-capture.inc'),'source_files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()}},indent=2)+'\n')
    print('Separate r23 observer/client generated; r22 source unchanged')

if __name__=='__main__':main()
