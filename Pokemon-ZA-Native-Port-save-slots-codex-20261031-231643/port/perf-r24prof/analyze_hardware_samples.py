"""Extended offline analysis: self functions, runtime files, external callers and sampling bias."""
import argparse
from collections import Counter,defaultdict
import json
from pathlib import Path
import re
import subprocess

import symbolize_samples as z
OWNERS={}
GIANTS={}


def source_map(work,nm):
    rt=work/'source/build/ps5/rt';source=work/'source/runtime'
    objects=sorted(rt.rglob('*.o'));owners=defaultdict(set)
    text=subprocess.check_output([nm,'--defined-only','--print-size','--print-file-name',*map(str,objects)],text=True)
    for line in text.splitlines():
        m=re.match(r'(.+?):\s*([0-9a-f]+)\s+([0-9a-f]+)\s+([tTwW])\s+(.+)',line)
        if not m:continue
        rel=Path(m[1]).relative_to(rt).with_suffix('.c')
        actual_source=False
        for ext in ('.c','.cpp','.mm','.S'):
            candidate=rel.with_suffix(ext)
            if (source/candidate).exists():rel=candidate;actual_source=True;break
        owners[m[5]].add(('runtime/'+str(rel)) if actual_source else ('unmapped-build-object/'+str(rel.with_suffix('.o'))))
    for name,groups in owners.items():
        if len(groups)==1:OWNERS[name]=next(iter(groups))
    mk=work/'source/build/ps5/gen/giants.mk';text=mk.read_text()
    aot=Path(re.search(r'^GIANTS_AOT := (.+)$',text,re.M)[1])
    for stem in re.search(r'^GIANTS :=(.*)$',text,re.M)[1].split():
        with (aot/(stem+'.c')).open() as f:
            for line in f:
                m=re.match(r'void (f_[0-9a-f]+)\(Cpu \*c\) \{',line)
                if m:GIANTS[m[1]]=dict(unit=stem,policy='giant compiled at -O0');break
    return dict(runtime_object_root=str(rt),unique_function_owners=len(OWNERS),giants_manifest=str(mk),giant_functions=len(GIANTS),
                note='Runtime grouping uses unique function definitions in the build objects where DWARF is missing or misleading. Translated-game symbols retain their game category.')


def ranked(c,total,n=20):
    return [dict(name=k,samples=v,percent=100*v/total if total else 0) for k,v in c.most_common(n)]


def decode(files,syms):
    found=set();decoded=[]
    for f in files:
        base=f['anchor']-syms.anchor
        for slot,flags,rip,caller in f['records']:
            info=f['threads'].get(slot,{})
            inside=syms.in_image(rip-base)
            fn=syms.function(rip-base) if inside else None
            cf=syms.function(caller-base) if caller and syms.in_image(caller-base) else None
            for item in (fn,cf):
                if item:found.add(item[0])
            decoded.append((f,slot,info,flags,rip,inside,fn,cf))
    syms.resolve_files(found)
    return decoded


def summarize(decoded,files,syms):
    ts=defaultdict(lambda:dict(samples=0,external=0,text_known=0,hardware_external=0,nofp=0,
                              functions=Counter(),internal_functions=Counter(),groups=Counter(),pairs=Counter(),external_rips=Counter(),game=Counter()))
    global_groups=Counter();global_fn=Counter();global_game=Counter()
    for f,slot,info,flags,rip,inside,fn,cf in decoded:
        key=(f['boot'],slot,info.get('gid',0),info.get('name','?'))
        t=ts[key];t['info']=info;t['samples']+=1
        name=fn[1] if fn else '<ext>' if not inside else '<unknown>'
        group=z.group_of(fn[1] if fn else None,syms.files.get(fn[0],'') if fn else '',inside)
        if inside and name in OWNERS:group=OWNERS[name]
        t['functions'][(name,group)]+=1;t['groups'][group]+=1
        global_groups[group]+=1;global_fn[(name,group)]+=1
        if inside:t['internal_functions'][(name,group)]+=1
        else:t['external']+=1;t['external_rips'][hex(rip)]+=1
        if flags&z.F_TEXT_KNOWN:
            t['text_known']+=1
            if not flags&z.F_IN_TEXT:t['hardware_external']+=1
        if not flags&z.F_CALLER:t['nofp']+=1
        if cf:t['pairs'][(cf[1],name)]+=1
        if group=='game (translated code)':t['game'][name]+=1;global_game[name]+=1
    threads=[];total=sum(t['samples'] for t in ts.values());equal_thread=Counter()
    for key,t in sorted(ts.items(),key=lambda item:-item[1]['samples']):
        n=t['samples'];info=t['info'];known=t['text_known']
        funcs=lambda c:[dict(name=k[0],group=k[1],samples=v,percent=100*v/n) for k,v in c.most_common(20)]
        row=dict(boot=key[0],slot=key[1],gid=key[2],name=key[3],kind=info.get('kind'),entry=hex(info.get('entry',0)),
                 samples=n,ext_percent_hardware=100*t['hardware_external']/known if known else None,
                 external_percent_from_exact_pie=100*t['external']/n,inside_image_percent=100*(n-t['external'])/n,
                 no_caller_percent=100*t['nofp']/n,groups=dict(t['groups']),top20_self=funcs(t['functions']),
                 top20_inside_image_self=funcs(t['internal_functions']),
                 top20_pairs=[dict(caller=k[0],function=k[1],samples=v,percent=100*v/n) for k,v in t['pairs'].most_common(20)],
                 top20_external_addresses=ranked(t['external_rips'],n),top20_game_functions=ranked(t['game'],n))
        row['role']='render thread' if info.get('kind')=='render' else 'RADV kick' if info.get('kind')=='radv-kick' else 'main guest thread' if key[2]==0x50 else 'guest worker'
        threads.append(row)
        for group,count in t['groups'].items():equal_thread[group]+=count/n
    return dict(files=[Path(f['path']).name for f in files],total_samples=total,threads=threads,
                raw_sample_groups=[dict(group=k,samples=v,percent=100*v/total) for k,v in global_groups.most_common()],
                equal_thread_weighted_groups=[dict(group=k,weight=v,percent=100*v/len(threads)) for k,v in equal_thread.most_common()],
                top20_all_self=[dict(name=k[0],group=k[1],samples=v,percent=100*v/total) for k,v in global_fn.most_common(20)],
                top20_game_functions=ranked(global_game,total),
                top20_giant_functions=[dict(name=k,samples=v,percent=100*v/total,**GIANTS[k]) for k,v in global_game.most_common() if k in GIANTS][:20],
                notes=['Render is sampled every period; other threads are sampled round-robin. Raw all-thread samples are not an unbiased CPU utilization breakdown.',
                       'Equal-thread weighting is a descriptive estimate, not measured CPU time or scheduler accounting.',
                       'ext means outside the eboot text, including waiting, system calls and active libc work; it does not prove a wait.',
                       'Caller pairs come from one plausible frame-pointer slot and are not guaranteed call stacks.',
                       'There is no per-record timestamp. Per-measurement reports select whole overlapping sample-file windows.'])


def main(a):
    out=a.out;state=json.loads((out/'state.json').read_text())
    phases=[p for p in state['phases'] if p['sampling']]
    all_files=[z.parse_file(p) for p in sorted((out/'samples').glob('*.bin'))]
    stable_lo=min(p['from_ns'] for p in phases)-25_000_000_000
    stable_hi=max(p['to_ns'] for p in phases)+22_000_000_000
    files=[f for f in all_files if f['t0']>=stable_lo and f['t1']<=stable_hi]
    assert files,'No complete sample windows in the stable scene guard'
    syms=z.Symbols(str(a.pie),a.nm,a.symbolizer)
    mapping=source_map(a.work,a.nm)
    decoded=decode(files,syms)
    result=summarize(decoded,files,syms)
    result['source_mapping']=mapping
    result['stable_guard_ns']=[stable_lo,stable_hi]
    result['window_quality']=[dict(file=Path(f['path']).name,t0=f['t0'],t1=f['t1'],sent=f['sent'],records=len(f['records']),
                                 kill_errors=f['kill_errors'],dropped=f['dropped'],skipped=f['skipped'],text=f['text']) for f in files]
    reports=[]
    for p in phases:
        selected=[f for f in files if f['t1']>=p['from_ns'] and f['t0']<=p['to_ns']]
        ids={(f['boot'],f['window']) for f in selected}
        report=summarize([d for d in decoded if (d[0]['boot'],d[0]['window']) in ids],selected,syms)
        report.update(boot=p['boot'],label=p['label'],from_ns=p['from_ns'],to_ns=p['to_ns'])
        reports.append(report)
    result['measurements']=reports
    target=out/'Profile-functions-and-threads.json';target.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(files=result['files'],samples=result['total_samples'],target=str(target),
                          threads=[{k:t[k] for k in ('name','role','samples','ext_percent_hardware','inside_image_percent')} for t in result['threads'][:8]]),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--pie',type=Path,required=True)
    p.add_argument('--nm',default='/usr/lib/llvm-21/bin/llvm-nm');p.add_argument('--symbolizer',default='/usr/lib/llvm-21/bin/llvm-symbolizer')
    p.add_argument('--work',type=Path,default=Path('/home/tomer/ps5-za-native/perf-r24prof-20261029'))
    main(p.parse_args())
