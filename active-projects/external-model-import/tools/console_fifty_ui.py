"""Short, observed console input sequences; screenshots remain real console captures."""
from pathlib import Path
import json,shutil,sys,time
from console_fifty_live import OUT,LOCAL,STATE,api,guard,command,observer
COMBOS=('ZL_ZR','ZL_A','ZL_B','ZL_X','ZL_Y','ZL_L','ZL_R','L_R_PLUS','L_A','L_B','L_X','L_Y')
observer.ACTIONS=tuple(observer.ACTIONS)+COMBOS
def main():
 state=json.loads(STATE.read_text());c=api.Console()
 try:
  guard(c,state)
  for step in sys.argv[1].split(','):
   parts=step.split(':');action=parts[0]
   if action=='WAIT':
    duration=float(parts[1]);assert 0<=duration<=30;time.sleep(duration)
   elif action=='SHOT':command(c,state,'snapshot',label=parts[1])
   elif action=='SHOW':
    assert len(parts)==2 and '/' not in parts[1] and '\\' not in parts[1]
    source=OUT/'captures'/parts[1];dest=LOCAL/'captures'/parts[1];dest.mkdir(parents=True,exist_ok=True)
    pictures=list(source.glob('*.png'));assert pictures,'No actual console screenshot exists for this label.'
    for p in pictures:
     target=dest/p.name;shutil.copyfile(p,target);assert target.read_bytes()==p.read_bytes();print('DISPLAY_IMAGE '+str(target),flush=True)
   else:
    assert action in observer.ACTIONS
    frames=int(parts[1]) if len(parts)>1 else 8
    receipt=command(c,state,'input',action,frames)
    assert receipt['ack']['result']=='input_armed','The installed observer rejected this input.'
    delay=float(parts[2]) if len(parts)>2 else max(.8,frames/15+.2)
    assert 0<=delay<=30;time.sleep(delay)
 finally:c.close()
if __name__=='__main__':main()
