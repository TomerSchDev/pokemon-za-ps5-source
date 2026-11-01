"""Bounded PC proof using an isolated data root and a fresh copy of a test save.
Only this script's child PID is stopped. No console, desktop input, or real saves.
"""
from pathlib import Path
import argparse,hashlib,json,os,shutil,subprocess,time
p=argparse.ArgumentParser();p.add_argument('--exe',type=Path,required=True);p.add_argument('--game',type=Path,required=True)
p.add_argument('--dll',type=Path,required=True);p.add_argument('--save',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
p.add_argument('--seconds',type=int,default=100);p.add_argument('--input',default='240:A:8,420:A:8,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8')
p.add_argument('--shots',default='700,950,1050,1200,1500,2200');p.add_argument('--cache',type=Path)
p.add_argument('--money-after-shot',type=int,default=0);p.add_argument('--amount',type=int,choices=[1,10,99,999],default=99)
p.add_argument('--item-id',type=int,default=50);p.add_argument('--all-items',action='store_true')
a=p.parse_args();assert 1<=a.seconds<=600
out=a.out.resolve();out.mkdir(parents=True,exist_ok=False);(out/'save/save_0').mkdir(parents=True);(out/'build').mkdir()
shutil.copy2(a.save,out/'save/save_0/main');os.chmod(out/'save/save_0/main',0o666)
if a.cache and a.cache.is_dir():shutil.copytree(a.cache,out/'cache')
(out/'larecomp.ini').write_text('aspect = original\nfullscreen = 0\nvolume = 0\nshow_fps = 0\nfps60 = 0\nresolution = 1x\ndynamic_res = off\ntex_hd = 0\nantialias = smaa\nupscaler = fsr1\nlanguage = en-US\nmouse_camera = off\nprompts = nintendo\n')
env={k:v for k,v in os.environ.items() if not k.startswith(('LARECOMP_','POKELAB_','ZA_MONEY_'))}
env.update(PATH='C:/msys64/ucrt64/bin;'+env['PATH'],LARECOMP_DATA_ROOT=str(out),LARECOMP_NO_UPDATE_CHECK='1',LARECOMP_REEXEC='20',
  LARECOMP_SAVE_DIR=str(out/'save'),LARECOMP_SETTINGS=str(out/'larecomp.ini'),LARECOMP_GAME_LIB=str(a.dll.resolve()),
  LARECOMP_SCREENSHOT_EVERY='0',LARECOMP_SHOT_AT=a.shots,LARECOMP_WAIT_DUMP='10',LARECOMP_SKIP_WHY='1',LARECOMP_KBD_AUTO='Test',
  LARECOMP_NO_USER_INPUT='1',LARECOMP_INPUT=a.input,ZA_MONEY_PC_COMMAND=str(out/'money-command.txt'))
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
record=dict(game=str(a.game.resolve()),runtime_sha256=sha(a.exe),dll_sha256=sha(a.dll),fixture=str(a.save.resolve()),
  source_save_sha256=sha(a.save),copy_before_sha256=sha(out/'save/save_0/main'),seconds=a.seconds,input=a.input,shots=a.shots)
for attempt in range(4):
    started=time.monotonic()
    with (out/'stdout.log').open('wb') as so,(out/'stderr.log').open('wb') as se:
        proc=subprocess.Popen([str(a.exe.resolve()),str(a.game.resolve()),'--play'],cwd=out,env=env,stdout=so,stderr=se)
        record['pid']=proc.pid;(out/'run.json').write_text(json.dumps(record,indent=2));print(json.dumps(dict(pid=proc.pid,run=str(out))),flush=True)
        sent=False;sequence=0;completed=0;queue=json.loads((Path(__file__).resolve().parents[1]/'research/menu-catalog.json').read_text()) if a.all_items else [{'id':a.item_id}]
        try:
            while proc.poll() is None:
                if time.monotonic()-started>=a.seconds:raise subprocess.TimeoutExpired(proc.args,a.seconds)
                log=(out/'r28items-control.log').read_text() if (out/'r28items-control.log').exists() else ''
                if sequence and f'done={sequence} ' in log:completed=sequence
                if a.money_after_shot and completed==sequence and sequence<len(queue) and (out/'build/frames'/f'frame_{a.money_after_shot:05d}.png').exists():
                    item=queue[sequence];sequence+=1
                    (out/'money-command.txt').write_text(f'{sequence} {item['id']} {a.amount}\n');sent=True
                    record['item_requests_sent']=sequence
                    record['item_requests_completed']=completed
                record['item_requests_completed']=completed
                try:proc.wait(timeout=0.1)
                except subprocess.TimeoutExpired:pass
            record['exit_code']=proc.returncode;record['terminated_by_harness']=False
        except subprocess.TimeoutExpired:
            proc.terminate();record['exit_code']=proc.wait(timeout=15);record['terminated_by_harness']=True
        finally:
            if proc.poll() is None:proc.kill();proc.wait()
    if time.monotonic()-started<10 and b'guest address range' in (out/'stderr.log').read_bytes():
        (out/'stderr.log').rename(out/f'collision-{attempt}.log');continue
    break
record.update(elapsed=round(time.monotonic()-started,3),copy_after_sha256=sha(out/'save/save_0/main'),source_unchanged=sha(a.save)==record['source_save_sha256'])
(out/'run.json').write_text(json.dumps(record,indent=2));print(json.dumps(record,indent=2))
