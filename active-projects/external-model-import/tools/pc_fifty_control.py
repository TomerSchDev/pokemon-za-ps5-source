"""Control only the existing scripted-input test hooks of our own isolated PC run.

No arbitrary memory addresses or guest data writes are exposed. The executable,
PID creation time, run metadata, disabled user input and completed frame script
are checked before touching the known host test-hook variables.
"""
from pathlib import Path
from datetime import datetime,timezone
import argparse,ctypes,ctypes.wintypes as W,hashlib,json,re,shutil,struct,time
import importlib.util,os

LAB=Path(__file__).resolve().parents[3]/'hebrew-lab'
EXE=LAB/'runtime/lasrecomp.exe'
EXPECTED='c74c94359182e6749b92eab82c066b6963dd33c25b0d0314e2a3667e1623e7fc'
# COFF symbols from this exact executable, relative to its PE image base 0x140000000.
RVA=dict(script_buttons=0x8825a0,script_lx=0x8825a8,script_ly=0x8825ac,
         script_rx=0x8825b0,script_ry=0x8825b4,shot_every=0x25ea10,total_frames=0xbad9a0,
         g_fnprof=0x67ab84,fnprof_slots=0x27ab80)
RVA.update(g_test_buttons=0x85b140,g_test_buttons_until=0x85b148,g_test_lx=0x85b134,
           g_test_ly=0x85b138,g_test_stick_until=0x855de0)
BUTTONS={name:1<<i for i,name in enumerate(('A','B','X','Y','LSTICK','RSTICK','L','R','ZL','ZR','PLUS','MINUS','LEFT','UP','RIGHT','DOWN'))}


def mask(names):
    return sum(BUTTONS[n] for n in set(filter(None,re.split(r'[,+]',names.upper()))))


def sequence_steps(value):
    steps=[]
    for entry in value.split(','):
        buttons,frames=entry.split('@');frames=int(frames);assert 1<=frames<=120
        names=buttons.split('+');assert all(v in BUTTONS or v in ('NONE','STICK_UP') for v in names)
        assert 'NONE' not in names or names==['NONE']
        steps.append((mask('+'.join(v for v in names if v in BUTTONS)),frames,32767 if 'STICK_UP' in names else 0))
    assert sum(frames for _,frames,_ in steps)<=650
    return steps


def play_sequence(h,steps,deadline):
    try:
        for bits,frames,ly in steps:
            for axis in ('script_lx','script_ly','script_rx','script_ry'):h.write(axis,struct.pack('<i',ly if axis=='script_ly' else 0))
            h.buttons(bits);start=h.frame()
            while h.frame()-start<frames:
                assert time.monotonic()<deadline,'Sequence timed out'
                time.sleep(.01)
    except Exception:
        h.buttons(0);raise
    finally:
        for axis in ('script_lx','script_ly','script_rx','script_ry'):h.write(axis,struct.pack('<i',0))


class Hooks:
    def __init__(self,root,record,terminate=False,await_script=False):
        assert record['runtime_sha256']==EXPECTED and hashlib.sha256(EXE.read_bytes()).hexdigest()==EXPECTED
        assert 'finished_utc' not in record,'Run has already finished'
        env=record['extra_env'];self.script=env.get('LARECOMP_INPUT') or record.get('input_script') or ''
        assert env['LARECOMP_NO_USER_INPUT']=='1' and Path(env['LARECOMP_DATA_ROOT']).resolve()==root.resolve()
        self.k=ctypes.WinDLL('kernel32',use_last_error=True)
        self.k.OpenProcess.argtypes=[W.DWORD,W.BOOL,W.DWORD];self.k.OpenProcess.restype=W.HANDLE
        self.k.CloseHandle.argtypes=[W.HANDLE]
        self.k.QueryFullProcessImageNameW.argtypes=[W.HANDLE,W.DWORD,W.LPWSTR,ctypes.POINTER(W.DWORD)]
        self.k.K32EnumProcessModules.argtypes=[W.HANDLE,ctypes.POINTER(W.HMODULE),W.DWORD,ctypes.POINTER(W.DWORD)]
        self.k.K32GetModuleFileNameExW.argtypes=[W.HANDLE,W.HMODULE,W.LPWSTR,W.DWORD]
        self.k.ReadProcessMemory.argtypes=[W.HANDLE,W.LPCVOID,W.LPVOID,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.k.WriteProcessMemory.argtypes=[W.HANDLE,W.LPVOID,W.LPCVOID,ctypes.c_size_t,ctypes.POINTER(ctypes.c_size_t)]
        self.k.GetProcessTimes.argtypes=[W.HANDLE]+[ctypes.POINTER(W.FILETIME)]*4
        self.handle=self.k.OpenProcess(0x0400|0x0010|0x0020|0x0008|0x0800|(0x0001 if terminate else 0),False,record['pid'])
        if not self.handle:raise ctypes.WinError(ctypes.get_last_error())
        path=ctypes.create_unicode_buffer(32768);size=W.DWORD(len(path))
        assert self.k.QueryFullProcessImageNameW(self.handle,0,path,ctypes.byref(size))
        assert Path(path.value).resolve()==EXE.resolve(),'PID does not belong to the expected runtime'
        times=[W.FILETIME() for _ in range(4)]
        assert self.k.GetProcessTimes(self.handle,*[ctypes.byref(t) for t in times])
        created=((times[0].dwHighDateTime<<32)|times[0].dwLowDateTime)/1e7-11644473600
        assert abs(created-datetime.fromisoformat(record.get('process_started_utc',record['started_utc'])).timestamp())<30,'PID creation time differs from run'
        modules=(W.HMODULE*1024)();needed=W.DWORD()
        deadline=time.monotonic()+15
        while not self.k.K32EnumProcessModules(self.handle,modules,ctypes.sizeof(modules),ctypes.byref(needed)):
            if time.monotonic()>=deadline:raise ctypes.WinError(ctypes.get_last_error())
            time.sleep(.05)  # the owned process can publish its PID before its module list is ready
        bases=[]
        for m in modules[:needed.value//ctypes.sizeof(W.HMODULE)]:
            p=ctypes.create_unicode_buffer(32768)
            if self.k.K32GetModuleFileNameExW(self.handle,m,p,len(p)) and Path(p.value).resolve()==EXE.resolve():bases.append(m)
        assert len(bases)==1;b=bases[0];self.base=b if isinstance(b,int) else b.value
        self.pause_file=root/'live-paused.json';self.pid=record['pid']
        self.nt=ctypes.WinDLL('ntdll');self.nt.NtSuspendProcess.argtypes=[W.HANDLE];self.nt.NtSuspendProcess.restype=W.LONG
        self.nt.NtResumeProcess.argtypes=[W.HANDLE];self.nt.NtResumeProcess.restype=W.LONG
        if self.script and not terminate and not await_script:
            ends=[int(p[0])+(int(p[2]) if len(p)>2 else 10) for v in self.script.split(',') if len(p:=v.split(':'))>=2]
            assert ends and self.frame()>max(ends)+20,'The frame script is still active; do not interfere with the scripted test'

    def paused(self):
        return self.pause_file.is_file() and json.loads(self.pause_file.read_text()).get('paused',False)

    def pause(self):
        if not self.paused():
            assert self.nt.NtSuspendProcess(self.handle)==0
            self.pause_file.write_text(json.dumps(dict(pid=self.pid,paused=True)))

    def resume(self):
        if self.paused():
            assert json.loads(self.pause_file.read_text())['pid']==self.pid
            assert self.nt.NtResumeProcess(self.handle)==0
            self.pause_file.write_text(json.dumps(dict(pid=self.pid,paused=False)))

    def read(self,name,size):
        assert name in RVA
        buf=ctypes.create_string_buffer(size);n=ctypes.c_size_t()
        if not self.k.ReadProcessMemory(self.handle,self.base+RVA[name],buf,size,ctypes.byref(n)):raise ctypes.WinError(ctypes.get_last_error())
        assert n.value==size;return buf.raw

    def write(self,name,data):
        assert name in RVA and name not in ('total_frames','fnprof_slots')
        if self.script and name=='script_buttons':
            self.write('g_test_buttons_until',struct.pack('<Q',(1<<64)-1));name='g_test_buttons'
        elif self.script and name in ('script_lx','script_ly'):
            self.write('g_test_stick_until',struct.pack('<Q',(1<<64)-1));name='g_test_'+name[-2:]
        elif self.script and name in ('script_rx','script_ry'):
            assert data==bytes(4),'The completed-script adapter supports buttons and left stick only'
            return
        assert len(data)==(8 if name in ('script_buttons','g_test_buttons','g_test_buttons_until','g_test_stick_until') else 4)
        buf=ctypes.create_string_buffer(data);n=ctypes.c_size_t()
        if not self.k.WriteProcessMemory(self.handle,self.base+RVA[name],buf,len(data),ctypes.byref(n)):raise ctypes.WinError(ctypes.get_last_error())
        assert n.value==len(data)

    def frame(self):return struct.unpack('<Q',self.read('total_frames',8))[0]
    def buttons(self,value):self.write('script_buttons',struct.pack('<Q',value))
    def close(self):self.k.CloseHandle(self.handle)


def main():
    # The existing live-input hooks must never operate under another agent's turn.
    queue_path=LAB.parent/'Pokemon-ZA-Native-Port/tools/console-install-queue/console_queue.py'
    spec=importlib.util.spec_from_file_location('species_control_queue',queue_path)
    queue=importlib.util.module_from_spec(spec);spec.loader.exec_module(queue)
    for key in ('PC_TEST_AGENT','PC_TEST_TICKET','PC_TEST_TOKEN'):
        if not os.environ.get(key):raise ValueError('Canonical PC ownership is required: '+key)
    queue.Board(resource='pc').check(os.environ['PC_TEST_AGENT'],os.environ['PC_TEST_TICKET'],os.environ['PC_TEST_TOKEN'])
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run')
    p.add_argument('action',choices=('status','set','tap','release','shot','record','profile','pause','resume','sequence','stop','wait'))
    p.add_argument('--until-frame',type=int,default=0,help='For wait, pause after this presented frame without modifying scripted input')
    p.add_argument('--buttons',default='');p.add_argument('--hold',default='');p.add_argument('--seconds',type=float,default=.3)
    p.add_argument('--frames',type=int,default=0,help='For tap, hold for this many presented frames (bounded to 30 seconds)')
    p.add_argument('--lx',type=int,default=0);p.add_argument('--ly',type=int,default=0)
    p.add_argument('--rx',type=int,default=0);p.add_argument('--ry',type=int,default=0)
    p.add_argument('--sequence',default='',help='Known buttons and presented frames, e.g. DOWN@25,NONE@30,LEFT@5,NONE@5,UP@25,NONE@45')
    p.add_argument('--every',type=int,default=3,help='For record, capture each Nth actual presented frame')
    p.add_argument('--label',default='capture');a=p.parse_args()
    assert re.fullmatch(r'pc-fifty-[a-z0-9-]+',a.run)
    assert 0<a.seconds<=10 and 0<=a.frames<=300 and all(-32767<=v<=32767 for v in (a.lx,a.ly,a.rx,a.ry))
    root=LAB/'runs'/a.run
    if a.action=='wait':
        deadline=time.monotonic()+120
        while True:
            try:
                candidate=json.loads((root/'run.json').read_text(encoding='utf-8-sig'))
                if candidate.get('pid'):break
            except (FileNotFoundError,json.JSONDecodeError):pass
            assert time.monotonic()<deadline,'Waiting for owned run metadata timed out'
            time.sleep(.1)
    record=json.loads((root/'run.json').read_text(encoding='utf-8-sig'))
    if a.action not in ('stop','status','pause'):
        remaining=record['budget_seconds']-(datetime.now(timezone.utc)-datetime.fromisoformat(record.get('process_started_utc',record['started_utc']))).total_seconds()
        frames=sum(step[1] for step in sequence_steps(a.sequence)) if a.action=='sequence' else a.frames
        need=max(15,frames/15+25) if a.action in ('record','tap','sequence') else 15
        assert remaining>need,f'Only {remaining:.1f}s remain; action needs {need:.1f}s including capture/cleanup margin. Do not start it.'
    h=Hooks(root,record,terminate=a.action=='stop',await_script=a.action=='wait')
    if a.action=='stop':
        # Hooks already proved the exact executable, creation time, PID and isolated data root.
        result=dict(run=a.run,pid=record['pid'],utc=datetime.now(timezone.utc).isoformat(),controlled_stop=True,reason=a.label)
        h.k.TerminateProcess.argtypes=[W.HANDLE,W.UINT]
        try:
            assert h.k.TerminateProcess(h.handle,0),ctypes.WinError(ctypes.get_last_error())
            (root/'controlled-stop.json').write_text(json.dumps(result,indent=1))
            print(json.dumps(result),flush=True)
        finally:h.close()
        return
    result=dict(run=a.run,action=a.action,frame_before=h.frame(),utc=datetime.now(timezone.utc).isoformat(),
                requested=dict(buttons=a.buttons,hold=a.hold,seconds=a.seconds,frames=a.frames,lx=a.lx,ly=a.ly,rx=a.rx,ry=a.ry))
    try:
        if a.action not in ('status','pause'):h.resume()
        if a.action=='pause':h.pause()
        elif a.action=='resume':h.resume()
        if a.action=='wait':
            assert 1<=a.until_frame<=20000
            deadline=time.monotonic()+180
            while h.frame()<a.until_frame:
                assert time.monotonic()<deadline,'Waiting for the requested frame timed out'
                time.sleep(.02)
        if a.action=='sequence':
            steps=sequence_steps(a.sequence)
            result['sequence']=a.sequence;deadline=time.monotonic()+50
            play_sequence(h,steps,deadline)
        if a.action in ('set','tap','release'):
            bits=0 if a.action=='release' else mask(a.buttons)|mask(a.hold)
            h.buttons(bits)
            for name,value in zip(('script_lx','script_ly','script_rx','script_ry'),(a.lx,a.ly,a.rx,a.ry)):
                h.write(name,struct.pack('<i',value if a.action!='release' else 0))
            if a.action=='tap':
                try:
                    if a.frames:
                        start=h.frame();deadline=time.monotonic()+30
                        while h.frame()-start<a.frames:
                            assert time.monotonic()<deadline,'Frame input timed out'
                            time.sleep(.01)
                    else:time.sleep(a.seconds)
                finally:
                    h.buttons(mask(a.hold))
                    for name in ('script_lx','script_ly','script_rx','script_ry'):h.write(name,struct.pack('<i',0))
                    start=h.frame();deadline=time.monotonic()+5
                    while h.frame()-start<6 and time.monotonic()<deadline:time.sleep(.01)
            result['held_buttons']=struct.unpack('<Q',h.read('script_buttons',8))[0]
        elif a.action=='profile':
            assert re.fullmatch(r'[a-z0-9-]+',a.label)
            assert struct.unpack('<i',h.read('g_fnprof',4))[0]==0
            def counters():return {addr:count for addr,count in struct.iter_unpack('<QQ',h.read('fnprof_slots',16*(1<<18))) if addr}
            before=counters();h.buttons(mask(a.buttons)|mask(a.hold));h.write('g_fnprof',struct.pack('<i',1))
            try:time.sleep(a.seconds)
            finally:h.write('g_fnprof',struct.pack('<i',0));h.buttons(mask(a.hold))
            after=counters();counts=sorted(((addr,count-before.get(addr,0)) for addr,count in after.items() if count>before.get(addr,0)),key=lambda v:-v[1])
            target=root/f'build/profile-{a.label}-{h.frame()}.json';assert not target.exists()
            target.write_text(json.dumps(dict(label=a.label,seconds=a.seconds,functions=[dict(address=f'{a:x}',calls=c) for a,c in counts]),indent=1))
            result.update(profile=str(target),functions=len(counts))
        elif a.action=='record':
            assert 30<=a.frames<=300 and 1<=a.every<=10
            assert shutil.disk_usage(root).free>1024**3,'Less than 1 GiB free; do not begin another recording'
            previous=h.read('shot_every',4);assert struct.unpack('<i',previous)[0]==0
            first=h.frame();deadline=time.monotonic()+55
            h.buttons(mask(a.buttons));h.write('shot_every',struct.pack('<i',a.every))
            try:
                if a.sequence:
                    steps=sequence_steps(a.sequence)
                    assert sum(frames for _,frames,_ in steps)<=a.frames
                    result['sequence']=a.sequence;play_sequence(h,steps,deadline)
                while h.frame()-first<a.frames:
                    if not a.sequence and h.frame()-first>=6:h.buttons(0)
                    assert time.monotonic()<deadline,'Recording timed out'
                    time.sleep(.02)
            finally:
                h.write('shot_every',previous);h.buttons(0)
            # Complete the last asynchronous PNG before suspending its writer.
            end=h.frame();last=root/f'build/frame_{end-end%a.every:05d}.png'
            while last.is_file():
                try:
                    if last.read_bytes()[-8:]==b'IEND\xaeB`\x82':break
                except PermissionError:pass
                assert time.monotonic()<deadline,'The final recording PNG did not complete'
                time.sleep(.05)
            result.update(label=a.label,record_first=first,record_last=h.frame(),record_every=a.every)
        elif a.action=='shot':
            assert re.fullmatch(r'[a-z0-9-]+',a.label)
            at=h.frame()+10;path=root/f'build/frame_{at:05d}.png';assert not path.exists()
            previous=h.read('shot_every',4);assert struct.unpack('<i',previous)[0]==0
            h.write('shot_every',struct.pack('<i',at))
            deadline=time.monotonic()+10
            try:
                while time.monotonic()<deadline:
                    try:
                        if path.is_file() and path.stat().st_size>12 and path.read_bytes()[-8:]==b'IEND\xaeB`\x82':break
                    except PermissionError:
                        pass  # the renderer still owns the PNG while writing it
                    time.sleep(.1)
            finally:h.write('shot_every',previous)
            assert path.is_file() and path.read_bytes()[-8:]==b'IEND\xaeB`\x82','Screenshot did not complete'
            result.update(label=a.label,screenshot=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if a.action!='resume':h.pause()
        result['frame_after']=h.frame();result['paused']=h.paused()
        if a.action=='status':result['held_buttons']=struct.unpack('<Q',h.read('script_buttons',8))[0]
        with (root/'live-controls.jsonl').open('a',encoding='utf-8') as log:log.write(json.dumps(result)+'\n')
        print(json.dumps(result),flush=True)
    finally:
        if a.action!='resume':h.pause()
        h.close()


if __name__=='__main__':main()
