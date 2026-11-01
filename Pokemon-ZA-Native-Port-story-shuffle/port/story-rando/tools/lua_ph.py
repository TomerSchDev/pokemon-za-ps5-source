import re
from luadump import load
phases=set(int(l.split(' |')[0]) for l in open('phase.txt',encoding='utf-8') if l.split(' |')[0].isdigit())
f=load(open('lua/event_ikevent_ik_0000_7a89ac5cad9881b3.blua','rb').read())
def w(p,path):
    ints=sorted(set(k for k in p['k'] if type(k) is int and k in phases and k>=10100))
    if ints:
        evs=sorted(set(m for s in p['k'] if isinstance(s,str) for m in re.findall(r'(?:Ev|ev)_[a-z]\w{2,12}',s)))[:4]
        hasph=any(isinstance(s,str) and 'PHASE' in s for s in p['k'])
        print(path, ints, 'PHASE' if hasph else '', evs)
    for i,c in enumerate(p['p']): w(c,path+'/'+str(i))
w(f,'r')
