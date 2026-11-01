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

def collect(ftp,session,seq,out,expected_preparation=None):
    path=BASE+'/session_'+session
    ack=json.loads(get(ftp,path+f'/ack_{seq}.json',4096))
    if ack.get('session')!=session or ack.get('seq')!=seq:raise RuntimeError('Mismatched acknowledgement')
    if ack.get('op')=='preparation' or expected_preparation is not None:
        if type(ack.get('seq')) is not int:raise RuntimeError('Invalid acknowledgement sequence')
        validate_preparation_ack(ack,expected_preparation)
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
    for op in ('snapshot','measure','fps','input','continue','submission','preparation','collect'):
        s=sub.add_parser(op);s.add_argument('--session',required=True);s.add_argument('--seq',type=int,required=True)
        if op=='measure':s.add_argument('value',type=int)
        if op=='fps':s.add_argument('value',type=int,choices=(0,1))
        if op=='submission':s.add_argument('value',choices=tuple(PROFILES))
        if op=='preparation':s.add_argument('value',choices=tuple(PREPARATION_PROFILES))
        if op=='input':s.add_argument('value',choices=ACTIONS);s.add_argument('frames',type=int)
        if op=='continue':s.add_argument('value',help='Exact current run ID; preserve/back up its save before play tests')
        if op=='collect':
            s.add_argument('--out',type=Path,required=True)
            s.add_argument('--preparation',choices=tuple(PREPARATION_PROFILES),help='Expected profile for a preparation receipt; required for that command')
    args=p.parse_args()
    with ftplib.FTP() as ftp:
        ftp.connect(args.host,args.port,timeout=10);ftp.login()
        if args.op=='status':result=status(ftp)
        elif args.op=='collect':result=collect(ftp,args.session,args.seq,args.out,args.preparation)
        else:
            payload=issue(ftp,args.session,args.seq,args.op,getattr(args,'value',None),getattr(args,'frames',None))
            result={'queued':payload.decode().strip(),'instruction':'Collect acknowledgement after completion. For measure, allow seconds + 2 seconds settling; do not transfer files during measurement.'}
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
