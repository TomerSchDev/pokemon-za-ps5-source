"""Replay an observed, bounded street route through the application's test queue."""
import argparse,json,re,subprocess,sys,time
from pathlib import Path
from datetime import datetime,timezone
p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--label',required=True)
p.add_argument('--loops',type=int,default=6);p.add_argument('--ms',type=int,default=5000)
a=p.parse_args();root=Path(__file__).resolve().parent
if not 1<=a.loops<=12 or not 100<=a.ms<=10000:p.error('Route must be bounded')
record=a.run/(a.label+'-route.json')
if record.exists():p.error('Choose a new measurement label')
def stamp():
    s=(a.run/'stderr.log').read_text(errors='replace')
    rows=re.findall(r'\[vk\] t=([\d.]+) frame (\d+) ([\d.]+) fps',s)
    return dict(utc=datetime.now(timezone.utc).isoformat(),last_log_t=float(rows[-1][0]),last_frame=int(rows[-1][1]))
start=stamp();commands=[]
for i in range(a.loops):
    for key in ('UP','DOWN'):
        before=stamp()
        subprocess.run([sys.executable,str(root/'lab_send.py'),str(a.run),key,str(a.ms)],check=True)
        commands.append(dict(key=key,ms=a.ms,start=before,end=stamp()))
end=stamp()
data=dict(label=a.label,start=start,end=end,commands=commands,shots_during_route=False,
    note='Observed street segment, forward/backward movement. Exclude first boundary log interval.')
record.write_text(json.dumps(data,indent=2));print(json.dumps(data))
