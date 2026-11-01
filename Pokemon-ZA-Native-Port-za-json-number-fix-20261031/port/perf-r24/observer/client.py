"""Scoped Z-A observer client. No deployment, launch, kill or game-file writes.
Use status first, then repeat its session token on each command. A single caller
owns the mailbox. Fetch only after measure completes to avoid FTP contention.
"""
import argparse
from datetime import datetime, timezone
import ftplib
import hashlib
import io
import json
from pathlib import Path
import re
import time
import uuid
from analyze import analyze

PROFILES={'each':1,'batch2':2,'batch4':4,'batch8':8}
PREPARATION_PROFILES={'baseline':0,'plan-only':1,'lazy-only':2,'optimized':3}
IMMUTABLE_MODES={'off':0,'on':1}
TITLE='PPSA91762'
BASE=f'/mnt/sandbox/{TITLE}_000/download0/zarecomp/observer'
COMMAND=f'/data/homebrew/{TITLE}/observer-command.txt'
ACTIONS=('A','B','X','Y','LSTICK','RSTICK','L','R','ZL','ZR','PLUS','MINUS',
         'LEFT','UP','RIGHT','DOWN','STICK_UP','STICK_DOWN','STICK_LEFT','STICK_RIGHT',
         'RSTICK_UP','RSTICK_DOWN','RSTICK_LEFT','RSTICK_RIGHT','RELEASE')

def get(ftp,path,limit=32*1024*1024):
    data=bytearray()
    def block(chunk):
        if len(data)+len(chunk)>limit:raise ValueError('Remote file exceeds bounded size')
        data.extend(chunk)
    ftp.retrbinary('RETR '+path,block,1<<18)
    return bytes(data)

def status(ftp):
    info=json.loads(get(ftp,BASE+'/session.json',4096))
    if info.get('title')!=TITLE or info.get('protocol')!=17 or not re.fullmatch('[0-9a-f]{16}',info.get('session','')):
        raise ValueError('Not the expected Z-A observer protocol/title')
    return info

def retire_target(token):
    if not isinstance(token,str):raise ValueError('Retirement target must be SID:sequence')
    match=re.fullmatch(r'([0-9a-f]{16}):([1-9][0-9]{0,19})',token)
    if not match or int(match[2])>=2**64:raise ValueError('Noncanonical retirement target')
    return match[1],int(match[2])

def text_command(session,seq,op,arg=None,frames=None):
    assert re.fullmatch('[0-9a-f]{16}',session) and isinstance(seq,int) and 0<seq<2**64
    if op=='snapshot':assert arg is None and frames is None
    elif op=='measure':assert isinstance(arg,int) and 1<=arg<=120 and frames is None
    elif op=='fps':assert arg in (0,1) and frames is None
    elif op=='continue':assert isinstance(arg,str) and re.fullmatch('[A-Za-z0-9_-]{1,79}',arg) and frames is None
    elif op=='submission':assert arg in PROFILES and frames is None
    elif op=='preparation':
        if not isinstance(arg,str) or arg not in PREPARATION_PROFILES or frames is not None:
            raise ValueError('Invalid preparation profile or argument count')
    elif op=='immutable_spans':
        if not isinstance(arg,str) or arg not in IMMUTABLE_MODES or frames is not None:
            raise ValueError('Invalid immutable spans mode or argument count')
    elif op=='slot_depth':
        canonical_slot_depth(arg)
        if frames is not None:raise ValueError('Slot depth command takes exactly one target')
    elif op=='retire_capture':
        target_sid,target_seq=retire_target(arg)
        if frames is not None or (target_sid==session and target_seq>=seq):
            raise ValueError('Retirement must identify a prior snapshot in the current session')
    elif op=='input':assert arg in ACTIONS and isinstance(frames,int) and 1<=frames<=120
    else:raise ValueError('Unsupported command')
    parts=[session,str(seq),op]
    if arg is not None:parts.append(str(arg))
    if frames is not None:parts.append(str(frames))
    return (' '.join(parts)+'\n').encode('ascii')

def issue(ftp,session,seq,op,arg=None,frames=None):
    if status(ftp)['session']!=session:raise RuntimeError('Session changed; inspect the new status first')
    payload=text_command(session,seq,op,arg,frames)
    temp=COMMAND+'.'+uuid.uuid4().hex+'.part'
    ftp.storbinary('STOR '+temp,io.BytesIO(payload))
    if get(ftp,temp,256)!=payload:raise RuntimeError('Command readback mismatch')
    ftp.rename(temp,COMMAND)
    return payload

def validate_submission_ack(ack):
    if ack.get('op') != 'submission': return
    result = ack.get('result')
    if result == 'rejected_in_menu': return
    if result not in ('applied','rejected_boundary','rejected_override','drain_failed'):
        raise ValueError('Unknown submission result')
    if ack.get('requested_profile') not in PROFILES:
        raise ValueError('Invalid requested submission profile')
    if type(ack.get('frame')) is not int or ack['frame'] < 1:
        raise ValueError('Missing successful-frame context')
    if result == 'applied':
        profile = ack.get('profile')
        if profile != ack['requested_profile'] or type(ack.get('max_lists')) is not int or ack['max_lists'] != PROFILES[profile]:
            raise ValueError('Applied submission profile/cap receipt mismatch')
    elif ack.get('profile') != '' or ack.get('max_lists') != 0:
        raise ValueError('Rejected submission falsely reports an applied profile')

def validate_preparation_ack(ack,expected_profile):
    # Bind the receipt to the locally intended request, not only its own echo.
    if expected_profile not in PREPARATION_PROFILES:
        raise ValueError('Preparation collect requires an explicit expected profile')
    if ack.get('op')!='preparation' or ack.get('requested_profile')!=expected_profile:
        raise ValueError('Mismatched preparation command acknowledgement')
    result=ack.get('result')
    if result not in ('applied','rejected_boundary','rejected_in_menu','rejected_profile','drain_failed','receipt_mismatch'):
        raise ValueError('Unknown preparation result')
    if ack.get('file')!='':raise ValueError('Preparation acknowledgement must not name an output file')
    for key in ('frame','cost_ns'):
        if type(ack.get(key)) is not int or not 0<=ack[key]<2**64:
            raise ValueError('Invalid preparation '+key)
    code=ack.get('runtime_result')
    if type(code) is not int or not -(2**31)<=code<2**31:
        raise ValueError('Invalid preparation runtime result')
    actual=ack.get('profile'); flags=ack.get('flags')
    coherent=isinstance(actual,str) and actual in PREPARATION_PROFILES and type(flags) is int and flags==PREPARATION_PROFILES[actual]
    unavailable=actual=='' and type(flags) is int and flags==-1
    if not coherent and not (result=='receipt_mismatch' and unavailable):
        raise ValueError('Preparation actual profile/flags receipt mismatch')
    if result=='applied':
        if actual!=expected_profile or flags!=PREPARATION_PROFILES[expected_profile] or code!=flags+1 or ack['frame']<1:
            raise ValueError('Preparation profile was not confirmed applied')
    elif result in ('rejected_boundary','rejected_in_menu'):
        if code!=0 or ack['cost_ns']!=0 or (result=='rejected_in_menu' and ack['frame']!=0):
            raise ValueError('Invalid preparation rejection context')
    elif result in ('rejected_profile','drain_failed'):
        if code!=(-1 if result=='rejected_profile' else -3) or ack['frame']<1:
            raise ValueError('Invalid preparation failure context')

def validate_immutable_ack(ack,expected_mode):
    # Bind the receipt to the locally intended request, not only its own echo.
    if expected_mode not in IMMUTABLE_MODES:
        raise ValueError('Immutable spans collect requires an explicit expected mode')
    if ack.get('op')!='immutable_spans' or ack.get('requested_mode')!=expected_mode:
        raise ValueError('Mismatched immutable spans command acknowledgement')
    result=ack.get('result')
    if result not in ('applied','rejected_boundary','rejected_in_menu','rejected_mode','drain_failed','receipt_mismatch'):
        raise ValueError('Unknown immutable spans result')
    if ack.get('file')!='':raise ValueError('Immutable spans acknowledgement must not name an output file')
    for key in ('frame','cost_ns'):
        if type(ack.get(key)) is not int or not 0<=ack[key]<2**64:
            raise ValueError('Invalid immutable spans '+key)
    code=ack.get('runtime_result')
    if type(code) is not int or not -(2**31)<=code<2**31:
        raise ValueError('Invalid immutable spans runtime result')
    actual=ack.get('mode'); flags=ack.get('flags')
    coherent=isinstance(actual,str) and actual in IMMUTABLE_MODES and type(flags) is int and flags==IMMUTABLE_MODES[actual]
    unavailable=actual=='' and type(flags) is int and flags==-1
    if not coherent and not (result=='receipt_mismatch' and unavailable):
        raise ValueError('Immutable spans actual mode/flags receipt mismatch')
    if result=='applied':
        if actual!=expected_mode or flags!=IMMUTABLE_MODES[expected_mode] or code!=flags+1 or ack['frame']<1:
            raise ValueError('Immutable spans mode was not confirmed applied')
    elif result in ('rejected_boundary','rejected_in_menu'):
        if code!=0 or ack['cost_ns']!=0 or (result=='rejected_in_menu' and ack['frame']!=0):
            raise ValueError('Invalid immutable spans rejection context')
    elif result in ('rejected_mode','drain_failed'):
        if code!=(-1 if result=='rejected_mode' else -3) or ack['frame']<1:
            raise ValueError('Invalid immutable spans failure context')

SLOT_DEPTHS=(8,16,32,64)  # r24: 32 and 64 added (r23c: 8 and 16); the runtime's capacity is 64
SLOT_CAPACITY=64

def canonical_slot_depth(value):
    if type(value) is int and value in SLOT_DEPTHS:return value
    if type(value) is str and value in tuple(str(d) for d in SLOT_DEPTHS):return int(value)
    raise ValueError('Slot depth must be exactly 8, 16, 32 or 64')

def validate_slot_depth_ack(ack,expected_depth):
    expected=canonical_slot_depth(expected_depth)
    if ack.get('op')!='slot_depth' or type(ack.get('requested_slots')) is not int or ack['requested_slots']!=expected:
        raise ValueError('Slot depth receipt differs from the intended command')
    if ack.get('file')!='':raise ValueError('Slot depth receipt must not name a file')
    result=ack.get('result')
    negative={'rejected_depth':-1,'drain_failed':-3,'memory_gate':-4,'incompatible_profile':-5,'preflight_failed':-6}
    if result not in {'applied','rejected_boundary','rejected_in_menu','receipt_mismatch',*negative}:
        raise ValueError('Unknown slot depth result')
    u32=('status_abi_version','active_slots','capacity_slots','status_requested_slots','previous_slots','budget_valid','status_reserved')
    u64=('frame','cost_ns','status_frame','drained_seq','completed_seq','pool_bytes','largest_free_extent','driver_bytes',
         'required_headroom_bytes','transient_capacity_bytes','descriptor_pools','command_buffers','counter_query_pools')
    for names,limit in ((u32,2**32),(u64,2**64)):
        for key in names:
            if type(ack.get(key)) is not int or not 0<=ack[key]<limit:raise ValueError('Invalid slot depth diagnostic '+key)
    for key in ('runtime_result','status_result'):
        if type(ack.get(key)) is not int or not -(2**31)<=ack[key]<2**31:raise ValueError('Invalid slot depth return '+key)
    valid=(ack['status_abi_version']==1 and ack['capacity_slots']==SLOT_CAPACITY and ack['active_slots'] in SLOT_DEPTHS
        and ack['status_requested_slots'] in (0,*SLOT_DEPTHS) and ack['previous_slots'] in (0,*SLOT_DEPTHS)
        and ack['budget_valid'] in (0,1) and ack['status_reserved']==0 and ack['status_result'] in (0,*SLOT_DEPTHS,-1,-3,-4,-5,-6))
    if type(ack.get('status_valid')) is not bool or ack['status_valid']!=valid:
        raise ValueError('Incorrect slot depth snapshot validity flag')
    if not valid and result!='receipt_mismatch':raise ValueError('Invalid runtime snapshot cannot claim an outcome')
    code=ack['runtime_result']
    if result=='receipt_mismatch':return # Retain diagnostics, never treat this as application.
    if result in ('rejected_boundary','rejected_in_menu'):
        if code!=0 or ack['cost_ns']!=0 or (result=='rejected_in_menu' and ack['frame']!=0):
            raise ValueError('Invalid slot depth observer rejection context')
        return # status_frame can be old; no runtime switch was called.
    if not ack['frame'] or ack['status_frame']!=ack['frame'] or ack['status_requested_slots']!=expected or ack['status_result']!=code or ack['previous_slots'] not in SLOT_DEPTHS:
        raise ValueError('Slot depth last-switch snapshot does not match this call')
    if result=='applied':
        if code!=expected or ack['active_slots']!=expected or ack['completed_seq']<ack['drained_seq']:
            raise ValueError('Slot depth was not confirmed applied after a completed drain')
        if expected>8 and (ack['budget_valid']!=1 or not 0<ack['pool_bytes']<=64<<30 or
            not 0<ack['largest_free_extent']<=ack['pool_bytes'] or ack['driver_bytes']>ack['pool_bytes'] or
            ack['required_headroom_bytes']<2**30 or ack['largest_free_extent']<ack['required_headroom_bytes']):
            raise ValueError('Depths above 8 require a checked free contiguous extent and headroom')
    elif code!=negative[result] or ack['active_slots']!=ack['previous_slots']:
        raise ValueError('Rejected slot depth switch reports an incorrect code or state change')


def validate_retire_capture_ack(ack,expected_target):
    target_sid,target_seq=retire_target(expected_target)
    if ack.get('op')!='retire_capture' or ack.get('target_session')!=target_sid or type(ack.get('target_seq')) is not int or ack['target_seq']!=target_seq:
        raise ValueError('Retirement receipt does not match intended target')
    if ack.get('file')!='':raise ValueError('Retirement receipt cannot advertise a downloadable file')
    result=ack.get('result')
    allowed={'retired','already_absent','rejected_target','invalid_session_directory','missing_snapshot_ack','invalid_snapshot_ack','capture_stat_failed','invalid_capture_file','unlink_failed','session_changed','capture_changed'}
    if result not in allowed:raise ValueError('Unknown retirement result')
    for key in ('cost_ns','bytes'):
        if type(ack.get(key)) is not int or not 0<=ack[key]<2**64:raise ValueError('Invalid retirement '+key)
    if type(ack.get('error_number')) is not int or not 0<=ack['error_number']<2**31:raise ValueError('Invalid retirement errno')
    if type(ack.get('removed')) is not bool or ack['removed']!=(result=='retired'):raise ValueError('Retirement removed flag mismatch')
    name=ack.get('retired_file')
    if not isinstance(name,str):raise ValueError('Invalid retired filename')
    if name:
        m=re.fullmatch(r'frame_([1-9][0-9]{0,19})_([1-9][0-9]{0,19})\.png',name)
        if not m or int(m[1])>=2**64 or int(m[2])!=target_seq:raise ValueError('Retired filename/target mismatch')
    if result in {'retired','already_absent','capture_stat_failed','invalid_capture_file','unlink_failed','session_changed','capture_changed'} and not name:
        raise ValueError('Missing validated retired filename')
    if result in {'rejected_target','invalid_session_directory','missing_snapshot_ack','invalid_snapshot_ack'} and name:
        raise ValueError('Unvalidated retirement filename')
    if result=='retired' and (ack['bytes']<=32 or ack['error_number']!=0):raise ValueError('Invalid successful retirement receipt')
    if result=='already_absent' and ack['bytes']!=0:raise ValueError('Absent file cannot claim freed bytes')
    if 'fs_step' in ack:
        steps={'target','session_open','session_fstat','session_type','ack_open','ack_fstat','ack_type','ack_read',
               'capture_open','capture_fstat','capture_type','session_reopen','session_refstat','session_retype',
               'session_identity','capture_reopen','capture_refstat','capture_retype','capture_identity','unlink'}
        if ack['fs_step'] not in steps:raise ValueError('Invalid filesystem diagnostic step')
        for key in ('fs_result','lstat_result'):
            if type(ack.get(key)) is not int or not -(2**31)<=ack[key]<2**31:raise ValueError('Invalid filesystem diagnostic return')
        for key in ('fs_mode','lstat_mode','lstat_errno'):
            if type(ack.get(key)) is not int or not 0<=ack[key]<2**32:raise ValueError('Invalid filesystem diagnostic value')
        if result=='retired' and (ack['fs_step']!='unlink' or ack['fs_result']!=0):
            raise ValueError('Successful retirement lacks successful unlink diagnostic')

def collect(ftp,session,seq,out,expected_preparation=None,expected_retire_capture=None,expected_immutable_spans=None,expected_slot_depth=None):
    path=BASE+'/session_'+session
    ack=json.loads(get(ftp,path+f'/ack_{seq}.json',4096))
    if ack.get('session')!=session or ack.get('seq')!=seq:raise RuntimeError('Mismatched acknowledgement')
    if ack.get('op')=='preparation' or expected_preparation is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_preparation_ack(ack,expected_preparation)
    if ack.get('op')=='retire_capture' or expected_retire_capture is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_retire_capture_ack(ack,expected_retire_capture)
    if ack.get('op')=='immutable_spans' or expected_immutable_spans is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_immutable_ack(ack,expected_immutable_spans)
    if ack.get('op')=='slot_depth' or expected_slot_depth is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_slot_depth_ack(ack,expected_slot_depth)
    validate_submission_ack(ack)
    if ack.get('result')=='settling':return ack
    out.mkdir(parents=True,exist_ok=True)
    record={'at':datetime.now(timezone.utc).isoformat(),'ack':ack,'files':[]}
    name=ack.get('file','')
    if name:
        if not re.fullmatch(r'(frame_\d+_\d+\.png|measure_\d+\.csv)',name):raise ValueError('Unexpected output name')
        data=get(ftp,path+'/'+name)
        if data!=get(ftp,path+'/'+name):raise RuntimeError('Remote output changed while reading')
        target=out/name
        if target.exists() and target.read_bytes()!=data:raise RuntimeError('Different local output already exists')
        target.write_bytes(data)
        record['files'].append({'name':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'readback_verified':True})
        if name.endswith('.csv') and ack.get('result')=='complete':
            (out/f'measure_{seq}-analysis.json').write_text(json.dumps(analyze(target),indent=2)+'\n')
        elif name.endswith('.png'):
            from PIL import Image
            with Image.open(target) as im:
                im.load(); record['image']={'width':im.width,'height':im.height,'mode':im.mode}
    record_path=out/f'command_{seq}.json'
    if record_path.exists():
        # Preserve prior evidence instead of silently replacing a different record.
        record_path=out/f'command_{seq}-{time.time_ns()}.json'
    record_path.write_text(json.dumps(record,indent=2)+'\n')
    return record

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',default='192.168.1.135');p.add_argument('--port',type=int,default=2121)
    sub=p.add_subparsers(dest='op',required=True);sub.add_parser('status')
    for op in ('snapshot','measure','fps','input','continue','submission','preparation','immutable_spans','slot_depth','retire_capture','collect'):
        s=sub.add_parser(op);s.add_argument('--session',required=True);s.add_argument('--seq',type=int,required=True)
        if op=='measure':s.add_argument('value',type=int)
        if op=='fps':s.add_argument('value',type=int,choices=(0,1))
        if op=='submission':s.add_argument('value',choices=tuple(PROFILES))
        if op=='preparation':s.add_argument('value',choices=tuple(PREPARATION_PROFILES))
        if op=='immutable_spans':s.add_argument('value',choices=tuple(IMMUTABLE_MODES))
        if op=='slot_depth':s.add_argument('value',type=int,choices=SLOT_DEPTHS)
        if op=='retire_capture':s.add_argument('value',help='Verified archived capture target: 16-lowercase-hex observer SID:positive snapshot sequence')
        if op=='input':s.add_argument('value',choices=ACTIONS);s.add_argument('frames',type=int)
        if op=='continue':s.add_argument('value',help='Exact current run ID; preserve/back up its save before play tests')
        if op=='collect':
            s.add_argument('--out',type=Path,required=True)
            s.add_argument('--preparation',choices=tuple(PREPARATION_PROFILES),help='Expected profile for a preparation receipt; required for that command')
            s.add_argument('--slot-depth',type=int,choices=SLOT_DEPTHS,help='Exact intended slot depth; required for its receipt')
            s.add_argument('--immutable-spans',choices=tuple(IMMUTABLE_MODES),help='Expected actual immutable-spans mode; required for its receipt')
            s.add_argument('--retire-capture',help='Exact intended SID:sequence target; required for retirement receipts')
    args=p.parse_args()
    with ftplib.FTP() as ftp:
        ftp.connect(args.host,args.port,timeout=10);ftp.login()
        if args.op=='status':result=status(ftp)
        elif args.op=='collect':result=collect(ftp,args.session,args.seq,args.out,args.preparation,args.retire_capture,args.immutable_spans,args.slot_depth)
        else:
            payload=issue(ftp,args.session,args.seq,args.op,getattr(args,'value',None),getattr(args,'frames',None))
            result={'queued':payload.decode().strip(),'instruction':'Collect acknowledgement after completion. For measure, allow seconds + 2 seconds settling; do not transfer files during measurement.'}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
