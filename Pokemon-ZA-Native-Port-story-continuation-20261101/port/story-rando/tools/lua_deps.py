import json,re,collections
d=json.load(open('event_ik.json',encoding='utf-8'))
cross=collections.defaultdict(collections.Counter)
chap_protos=collections.Counter()
other=collections.defaultdict(collections.Counter)
for p in d:
    strs=p['strs']
    ch=collections.Counter(m for s in strs for m in re.findall(r'^(?:msg_)?Ev_m(\d\d)_',s))
    if not ch: continue
    c=int(ch.most_common(1)[0][0]); chap_protos[c]+=1
    for s in strs:
        m=re.match(r'^flag_Ev_m(\d\d)_\d+',s)
        if m and int(m.group(1))!=c: cross[c][s]+=1
        if re.match(r'^(SYS_FLAG|FLAG|flag_(?!Ev_)|SYS_WORK|TEMP_)',s): other[c][s]+=1
out={}
for c in sorted(chap_protos):
    out[c]=dict(protos=chap_protos[c], cross_chapter_flags=dict(cross[c].most_common(30)), other_state=dict(other[c].most_common(40)))
    print('ch',c,'protos',chap_protos[c],'cross',dict(cross[c].most_common(12)))
    print('    state',list(other[c])[:30])
json.dump(out,open('lua_deps.json','w'),indent=1)
