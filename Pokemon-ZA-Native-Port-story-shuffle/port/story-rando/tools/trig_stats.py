import json,re,collections
for i in range(11):
    d=json.load(open('j/trigger_main_%02d.json'%i,encoding='utf-8'))
    phs=collections.Counter(); ntrig=len(d['0'])
    s=json.dumps(d)
    for m in re.finditer(r'"phase_condition", "1": (\d+), "2": \[([^\]]*)\]', s):
        args=[int(x.strip(' "')) for x in m.group(2).split(',') if x.strip(' "').isdigit()]
        for a in args:
            phs[a//10000 if a<100000 else 10]+=1
    evs=collections.Counter(re.findall(r'"Ev_(m\d\d|sub|stopper|d\d\d)', s))
    print('trigger_main_%02d triggers=%d phase-chapters=%s events=%s'%(i,ntrig,dict(sorted(phs.items())),dict(evs)))
