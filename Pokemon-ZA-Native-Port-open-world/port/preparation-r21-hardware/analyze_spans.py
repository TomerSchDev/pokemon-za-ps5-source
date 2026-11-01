"""Offline r22 phase/CSV/log analyzer. No console or network access.

r22 counters are per-report deltas and are SUMMED, never differenced. Only whole
regular report intervals inside a verified phase are counted. Switch-time old
mode reports are discarded; an uninterrupted, exact-mode logged transition and
session identity are required. No winner or causal performance claim is made.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import re
from analyze_suite import read_intervals, TIMER_PATTERNS

MODES={'off':0,'on':1}
KINDS=('ubo-zero','vertex-default-w1','vertex-zero')
COUNTERS=('requests','hits','misses','bypass','copied_bytes','avoided_bytes','collisions')
LIMITATIONS=[
    'Rates are CPU present-submission intervals, not display scanout or simulation speed.',
    'r22 counters reset at each report. Totals sum whole matching-mode reports; they are not cumulative-counter differences.',
    'Switches emit the old mode counters before application; those partial reports and first post-switch intervals are excluded.',
    'Profiler timers nest and overlap; GPU query sums are not unique frame GPU time. Do not add them or infer a critical path by subtraction.',
    'Counter coverage can be smaller than the CSV. Requests and avoided bytes are copy-work counters, not unique allocated GPU capacity.',
    'The off mode retains candidate instrumentation. Compare its overhead against r21c separately before final selection.',
    'Verified phase/log identity does not prove equivalent camera, scene, visual correctness, long-run stability or causality.',
]

def sha(data):return hashlib.sha256(data).hexdigest()
def uint(value,maximum=2**64):return type(value) is int and 0<=value<maximum
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def parse_log_text(text,name='<memory>'):
    windows=[];events=[];diagnostics=[];sessions={0:set()};boot=0;startup=False
    previous=None;pending={};epoch=0;last_frame=None;boot_max={}
    for number,line in enumerate(text.splitlines(),1):
        if re.search(r'\[za-r20b?-submit\] startup',line):
            if startup or last_frame is not None:boot+=1
            startup=True;previous=None;pending={};last_frame=None;epoch=0;sessions.setdefault(boot,set())
        sid=re.search(r'session_([0-9a-f]{16})(?:/|\b)',line)
        if sid:sessions.setdefault(boot,set()).add(sid[1])
        match=re.search(r'\[za-r22-immutable\] applied frame=(\d+) mode=(\w+) flags=(\d+) previous=(\d+) drained_seq=(\d+)',line)
        category='immutable_spans';mode=None;flags=None
        if match:frame=int(match[1]);mode=match[2];flags=int(match[3])
        else:
            match=re.search(r'\[za-r21-prep\] applied frame=(\d+) profile=([\w-]+) flags=(\d+)',line)
            category='preparation'
            if match:frame=int(match[1]);mode=match[2];flags=int(match[3])
            else:
                match=re.search(r'\[za-r20b?-submit\] applied frame=(\d+) profile=([\w-]+)',line)
                category='submission'
                if match:frame=int(match[1]);mode=match[2]
        if match:
            epoch+=1
            events.append(dict(line=number,boot=boot,frame=frame,control=category,mode=mode,flags=flags,epoch=epoch))
            # The switch itself reports old counters and resets them mid-period.
            # Never attach that report to the following regular stats window.
            pending={};previous=None
            continue
        span=re.search(r'\[za-r22-immutable\] enabled=(\d+) kind=([\w-]+) (.*)',line)
        if span:
            group=pending.setdefault('spans',{});kind=span[2]
            values={k:int(v) for k,v in re.findall(r'(\w+)=(\d+)',span[3])}
            reasons=pending.setdefault('errors',[])
            if kind in group:reasons.append('duplicate_kind_report')
            if kind not in KINDS or int(span[1]) not in (0,1) or not set(COUNTERS+('resets',))<=values.keys():
                reasons.append('malformed_kind_report');continue
            c={k:values[k] for k in COUNTERS}
            if any(not uint(v) for v in values.values()) or c['requests']!=c['hits']+c['misses']+c['bypass']:
                reasons.append('request_counter_invariant')
            if c['collisions']>c['misses'] or (not int(span[1]) and (c['hits'] or c['misses'] or c['avoided_bytes'])):
                reasons.append('mode_or_collision_counter_invariant')
            size={'vertex-default-w1':16,'vertex-zero':256}.get(kind)
            if size and (c['avoided_bytes']!=size*c['hits'] or c['copied_bytes']!=size*(c['misses']+c['bypass'])):
                reasons.append('literal_byte_counter_invariant')
            group[kind]=dict(line=number,enabled=int(span[1]),counters=c,resets=values['resets'])
        prep=re.search(r'\[za-r21-prep\] profile=([\w-]+) flags=(\d+)',line)
        if prep:pending['preparation']=(prep[1],int(prep[2]))
        submit=re.search(r'\[za-r20b?-submit\] profile=(\w+) logical=(\d+) vk_calls=(\d+)',line)
        if submit:pending['submission']=submit[1]
        report=re.search(r'\[vk\] t=[\d.]+ frame (\d+) [\d.]+ fps',line)
        if not report:continue
        frame=int(report[1])
        if last_frame is not None and frame<=last_frame:
            diagnostics.append(dict(line=number,reason='frame_reset_or_duplicate'))
            previous=None
            if frame<last_frame:
                boot+=1;epoch=0;sessions.setdefault(boot,set())
        reasons=list(pending.get('errors',[]));group=pending.get('spans',{})
        if set(group)!=set(KINDS):reasons.append('missing_kind_report')
        enabled={s['enabled'] for s in group.values()};resets={s['resets'] for s in group.values()}
        if len(enabled)!=1 or len(resets)!=1:reasons.append('inconsistent_kind_group')
        if pending.get('preparation')!=('baseline',0):reasons.append('preparation_not_confirmed_baseline')
        if pending.get('submission')!='batch4':reasons.append('submission_not_confirmed_batch4')
        current=dict(frame=frame,line=number,epoch=epoch,boot=boot,valid=not reasons)
        if previous is not None:
            if not previous['valid']:reasons.append('previous_report_boundary_incomplete')
            window=dict(log=name,line=number,previous_line=previous['line'],boot=boot,epoch=epoch,
                start=previous['frame']+1,end=frame,frames=frame-previous['frame'],
                mode=('on' if next(iter(enabled)) else 'off') if len(enabled)==1 else None,
                counters={kind:s['counters'] for kind,s in group.items()},
                resets=next(iter(resets)) if len(resets)==1 else None,
                preparation=pending.get('preparation'),submission=pending.get('submission'),
                rejected_reasons=reasons,valid=not reasons)
            for field,pattern in TIMER_PATTERNS.items():
                m=re.search(pattern,line)
                if m:window[field]=int(m[1])
            windows.append(window)
        previous=current;last_frame=frame;boot_max[boot]=max(frame,boot_max.get(boot,0));pending={}
    return dict(log=name,windows=windows,events=events,diagnostics=diagnostics,
        sessions_by_boot={str(k):sorted(v) for k,v in sessions.items()},max_frame_by_boot={str(k):v for k,v in boot_max.items()})

def parse_log(path):
    data=Path(path).read_bytes();result=parse_log_text(data.decode('utf-8',errors='replace'),str(path))
    result.update(sha256=sha(data),bytes=len(data));return result

def summarize(windows):
    frames=sum(w['frames'] for w in windows)
    kinds={kind:{k:sum(w['counters'][kind][k] for w in windows) for k in COUNTERS} for kind in KINDS}
    totals={k:sum(c[k] for c in kinds.values()) for k in COUNTERS}
    return dict(aggregation='sum_of_per_report_deltas_NEVER_difference',covered_frames=frames,reports=len(windows),
        counters_by_kind=kinds,counters_total=totals,
        counters_per_frame={k:v/frames for k,v in totals.items()} if frames else {},
        hit_fraction=totals['hits']/totals['requests'] if totals['requests'] else None,
        avoided_fraction_of_requested_copy_bytes=totals['avoided_bytes']/(totals['copied_bytes']+totals['avoided_bytes']) if totals['copied_bytes']+totals['avoided_bytes'] else None,
        resets=sum(w['resets'] for w in windows),
        profiler_per_frame={k:sum(w[k] for w in windows)/frames for k in TIMER_PATTERNS if frames and all(k in w for w in windows)},windows=windows)

def verify_ack(ack,session,seq,op,result):
    if not isinstance(ack,dict) or ack.get('session')!=session or type(ack.get('seq')) is not int or ack['seq']!=seq or ack.get('op')!=op or ack.get('result')!=result:
        raise ValueError('Acknowledgement session/sequence/op/result mismatch: '+op)

def analyze_phase(path,logs,expected_sha=None,boot=None):
    path=Path(path);out=dict(phase=str(path),label=path.parent.name,status='invalid')
    try:
        raw=path.read_bytes();phase=json.loads(raw);out['phase_sha256']=sha(raw)
        sid=phase.get('session');mode=phase.get('profile');seq=phase.get('sequence_start')
        out.update(session=sid,mode=mode,pid=phase.get('pid'),run=phase.get('run'))
        if phase.get('completed') is not True:return {**out,'status':'incomplete','reason':'phase not completed'}
        if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{16}',sid) or not isinstance(mode,str) or mode not in MODES or not uint(seq) or not seq or seq+5>=2**64:
            raise ValueError('Invalid phase session/mode/sequence')
        if phase.get('control')!='immutable_spans' or phase.get('preparation')!='baseline':raise ValueError('Wrong phase control/preparation')
        if not uint(phase.get('seconds')) or not 10<=phase['seconds']<=40:raise ValueError('Invalid sample duration')
        identity_path=path.parent.parent/'identity.json';identity=load(identity_path)
        if any(identity.get(k)!=phase.get(k) for k in ('session','pid','run')) or identity.get('client')!='r22' or not uint(identity.get('pid')) or not identity['pid']:
            raise ValueError('r22 session identity differs from phase')
        artifact=identity.get('eboot_sha256')
        if not isinstance(artifact,str) or not re.fullmatch('[0-9a-f]{64}',artifact) or (expected_sha is not None and artifact!=expected_sha):raise ValueError('Runtime artifact identity mismatch')
        out.update(runtime_sha256=artifact,identity_sha256=sha(identity_path.read_bytes()))
        transition=phase['transition'];verify_ack(transition,sid,seq,'immutable_spans','applied')
        if (transition.get('requested_mode')!=mode or transition.get('mode')!=mode or type(transition.get('flags')) is not int or transition['flags']!=MODES[mode]
            or type(transition.get('runtime_result')) is not int or transition['runtime_result']!=MODES[mode]+1
            or transition.get('file')!='' or not uint(transition.get('frame')) or not transition['frame'] or not uint(transition.get('cost_ns'))):
            raise ValueError('Applied immutable mode/status/return context mismatch')
        settling=phase['settling'];settling=settling.get('ack',settling)
        verify_ack(settling,sid,seq+2,'measure','settling')
        measurement=phase['measurement'];ack=measurement['ack'];verify_ack(ack,sid,seq+2,'measure','complete')
        filename=f'measure_{seq+2}.csv'
        if ack.get('file')!=filename:raise ValueError('CSV name does not match measure sequence')
        files=measurement.get('files',[])
        if len(files)!=1 or files[0].get('name')!=filename or files[0].get('readback_verified') is not True:raise ValueError('Missing exact verified CSV receipt')
        rows,timing=read_intervals(path.parent/filename)
        if files[0].get('sha256')!=timing['csv_sha256'] or type(files[0].get('bytes')) is not int or files[0]['bytes']!=timing['csv_bytes']:raise ValueError('CSV hash/size changed')
        if timing['fps_modes']!=[0] or timing['all_intervals']['duration_s']<phase['seconds']-.15:raise ValueError('Wrong FPS mode or incomplete duration')
        if any(not uint(v) for row in rows for v in row.values()) or any(rows[i]['frame']!=rows[i-1]['frame']+1 for i in range(1,len(rows))):raise ValueError('Unsigned CSV or contiguous frame invariant failed')
        lo,hi=timing['csv_frames']
        if not transition['frame']<lo:raise ValueError('Applied transition is not before CSV')
        for key,offset in (('before',1),('after',3)):
            cap=phase[key]['ack'];verify_ack(cap,sid,seq+offset,'snapshot','saved')
            m=re.fullmatch(r'frame_([1-9][0-9]*)_'+str(seq+offset)+r'\.png',cap.get('file',''))
            if not m or not uint(int(m[1])) or (key=='before' and int(m[1])>=lo) or (key=='after' and int(m[1])<=hi):raise ValueError('Snapshot overlaps measurement or has wrong identity')
        out.update(status='timing_valid_no_profiler_match',timing=timing,transition=transition)
        matches=[]
        for log in logs:
            for event in log['events']:
                if event['control']=='immutable_spans' and event['frame']==transition['frame'] and event['mode']==mode and event['flags']==MODES[mode] and (boot is None or event['boot']==boot):
                    known=log['sessions_by_boot'].get(str(event['boot']),[])
                    if sid in known:matches.append((log,event))
        if len(matches)!=1:
            out.update(profiler_reason='missing_or_ambiguous_session_bound_transition',transition_candidates=len(matches));return out
        log,event=matches[0];out.update(log=log['log'],log_sha256=log['sha256'],boot=event['boot'],logged_transition=event)
        unexpected=[e for e in log['events'] if e['boot']==event['boot'] and e['line']>event['line'] and event['frame']<=e['frame']<=hi]
        if unexpected:out.update(status='mixed_control_measurement',unexpected_transitions=unexpected);return out
        if log['max_frame_by_boot'].get(str(event['boot']),0)<hi:
            out['profiler_reason']='log_does_not_cover_measurement_end';return out
        inside=[w for w in log['windows'] if w['boot']==event['boot'] and lo<=w['start'] and w['end']<=hi]
        rejected=[];selected=[]
        for w in inside:
            reasons=list(w['rejected_reasons'])
            if w['epoch']!=event['epoch'] or w['mode']!=mode:reasons.append('wrong_mode_or_control_epoch')
            if reasons:rejected.append(dict(line=w['line'],start=w['start'],end=w['end'],reasons=reasons))
            else:selected.append(w)
        out['rejected_profiler_windows']=rejected
        if any(w.get('preparation')!=('baseline',0) or w.get('submission')!='batch4' or w.get('mode')!=mode for w in inside):
            out.update(status='runtime_state_unverified',profiler_reason='measurement contains unconfirmed baseline/batch4/mode report');return out
        if not selected:out['profiler_reason']='no_complete_valid_counter_window';return out
        out.update(status='complete',immutable=summarize(selected))
        out['immutable']['coverage_fraction_of_csv_intervals']=out['immutable']['covered_frames']/len(rows)
        return out
    except (OSError,ValueError,TypeError,KeyError,IndexError) as exc:
        out.update(status='invalid',reason=str(exc));return out

def analyze_suite(evidence,logs,session,expected_sha,phase_paths=None,boot=None):
    root=Path(evidence)
    if not re.fullmatch('[0-9a-f]{16}',session) or not re.fullmatch('[0-9a-f]{64}',expected_sha):raise ValueError('Explicit session and expected SHA-256 required')
    if not logs or (boot is not None and len(logs)!=1):raise ValueError('Supply log snapshot(s); boot requires one log')
    parsed=[parse_log(p) for p in logs]
    paths=list(map(Path,phase_paths)) if phase_paths else sorted((root/('session-'+session)).glob('*/phase.json'))
    phases=[analyze_phase(p,parsed,expected_sha,boot) for p in paths]
    for p in phases:
        if p.get('session')!=session:p.update(status='invalid',reason='Phase session differs from explicitly requested session')
    samples=[dict(label=p['label'],mode=p['mode'],runtime_sha256=p['runtime_sha256'],
        timing=p['timing']['all_intervals'],shader_affected_intervals=p['timing']['shader_affected_intervals'],
        counters=p['immutable']['counters_total'],covered_frames=p['immutable']['covered_frames'],
        per_frame=p['immutable']['counters_per_frame'],profiler_per_frame=p['immutable']['profiler_per_frame']) for p in phases if p['status']=='complete']
    return dict(schema_version=1,session=session,runtime_sha256=expected_sha,preparation='baseline',submission='batch4',
        phases=phases,mode_samples=samples,logs=[{k:v for k,v in p.items() if k!='windows'} for p in parsed],limitations=LIMITATIONS,recommendation=None)

def self_test():
    from unittest.mock import patch
    sid='0000000000000022';digest='a'*64
    def report(frame,hits=0,requests=4,mode='on',prep='baseline',submit='batch4'):
        lines=[f'[za-r20b-submit] profile={submit} logical={frame} vk_calls={frame}']
        for kind in KINDS:
            size={'ubo-zero':256,'vertex-default-w1':16,'vertex-zero':256}[kind]
            miss=requests-hits if mode=='on' else 0;bypass=requests if mode=='off' else 0
            lines.append(f'[za-r22-immutable] enabled={MODES[mode]} kind={kind} requests={requests} hits={hits} misses={miss} bypass={bypass} copied_bytes={(miss+bypass)*size} avoided_bytes={hits*size} collisions=0 resets=0')
        lines.extend([f'[za-r21-prep] profile={prep} flags={0 if prep=="baseline" else 3}',f'[vk] t=1.0 frame {frame} 25.0 fps (10 draws, 2 passes)'])
        return '\n'.join(lines)+'\n'
    switch='[za-r22-immutable] applied frame=1 mode=on flags=1 previous=0 drained_seq=2\n'
    text=f'[za-r20b-submit] startup profile=batch4\n[observer] session_{sid}/frame_2_11.png\n'+switch
    text+=report(100,0,4)+report(200,1,4)+report(300,2,3)+report(400,1,4)
    parsed=parse_log_text(text);parsed['sha256']='synthetic'
    counts=summarize(parsed['windows'][:2])
    assert counts['counters_total']['requests']==21 and counts['counters_total']['hits']==9 # sum 4+3 per kind; never 3-4
    assert counts['reports']==2 and counts['covered_frames']==200
    path=Path('/virtual/session-'+sid+'/on-1/phase.json');csvpath=path.parent/'measure_12.csv';identity=path.parent.parent/'identity.json'
    csvdata=('frame,now_ns,dt_ns,submitted_interval,represented_interval,shader_before,shader_after,mode,observer_ns\n'+''.join(f'{f},{f*40000000},40000000,1,0,0,0,0,1000\n' for f in range(51,301))).encode()
    def ack(seq,op,result,**kw):return dict(session=sid,seq=seq,op=op,result=result,**kw)
    phase=dict(completed=True,session=sid,pid=42,run='run1',control='immutable_spans',preparation='baseline',profile='on',sequence_start=10,seconds=10,
        transition=ack(10,'immutable_spans','applied',requested_mode='on',mode='on',flags=1,runtime_result=2,frame=1,cost_ns=1,file=''),
        settling=ack(12,'measure','settling'),before={'ack':ack(11,'snapshot','saved',file='frame_2_11.png')},after={'ack':ack(13,'snapshot','saved',file='frame_301_13.png')},
        measurement={'ack':ack(12,'measure','complete',file='measure_12.csv'),'files':[dict(name='measure_12.csv',sha256=sha(csvdata),bytes=len(csvdata),readback_verified=True)]})
    fixtures={str(path):json.dumps(phase).encode(),str(csvpath):csvdata,str(identity):json.dumps(dict(session=sid,pid=42,run='run1',client='r22',eboot_sha256=digest)).encode()}
    with patch.object(Path,'read_bytes',lambda p:fixtures[str(p)]),patch.object(Path,'read_text',lambda p,**kw:fixtures[str(p)].decode()):
        result=analyze_phase(path,[parsed],digest);assert result['status']=='complete',result
        assert result['immutable']['counters_total']['requests']==21 and result['timing']['all_intervals']['interval_rate_fps']==25
        fixtures[str(csvpath)]=csvdata+b'\n';assert analyze_phase(path,[parsed],digest)['status']=='invalid';fixtures[str(csvpath)]=csvdata
        for change in ({'flags':True},{'mode':'off'},{'seq':True},{'runtime_result':1},{'session':'0'*16}):
            bad={**phase,'transition':{**phase['transition'],**change}};fixtures[str(path)]=json.dumps(bad).encode()
            assert analyze_phase(path,[parsed],digest)['status']=='invalid',change
        fixtures[str(path)]=json.dumps(phase).encode()
        assert analyze_phase(path,[parsed],'b'*64)['status']=='invalid'
        assert analyze_phase(path,[parsed,parsed],digest)['status']=='timing_valid_no_profiler_match'
        for change in ('[za-r22-immutable] applied frame=150 mode=off flags=0 previous=1 drained_seq=3\n','[za-r21-prep] applied frame=150 profile=optimized flags=3\n','[za-r20b-submit] applied frame=150 profile=each\n'):
            altered=parse_log_text(text+change);altered['sha256']='synthetic';assert analyze_phase(path,[altered],digest)['status']=='mixed_control_measurement'
        wrong=parse_log_text(text.replace('profile=batch4 logical=200','profile=each logical=200'));wrong['sha256']='synthetic'
        assert analyze_phase(path,[wrong],digest)['status']=='runtime_state_unverified'
        missing=parse_log_text(text.replace('kind=vertex-zero','kind=unknown'));missing['sha256']='synthetic'
        assert analyze_phase(path,[missing],digest)['status']!='complete'
        cut=parse_log_text(text[:text.index(report(300,2,3))]);cut['sha256']='synthetic'
        assert analyze_phase(path,[cut],digest)['profiler_reason']=='log_does_not_cover_measurement_end'
        mismatch={**parsed,'sessions_by_boot':{'0':['0'*16]}}
        assert analyze_phase(path,[mismatch],digest)['status']=='timing_valid_no_profiler_match'
    partial=parse_log_text(report(50,0,4,mode='off')+report(70,0,9,mode='off')+switch+report(100,0,1)+report(200,1,2))
    assert partial['windows'][-1]['counters']['ubo-zero']['requests']==2 and partial['windows'][-1]['start']==101
    duplicate=parse_log_text(text+report(400,1,4));assert duplicate['diagnostics']
    print('PASS: per-report sum (including falling values), exact identity/ack/CSV hash, control epoch and all three mid-window switch types, baseline/batch4 enforcement, missing kind/log/session and ambiguous snapshot rejection, partial switch report exclusion, duplicate frames')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=Path(__file__).resolve().parents[2]/'evidence/preparation-r21-hardware')
    p.add_argument('--log',type=Path,action='append');p.add_argument('--phase',type=Path,action='append')
    p.add_argument('--session');p.add_argument('--expected-sha');p.add_argument('--boot',type=int)
    p.add_argument('--out',type=Path);p.add_argument('--self-test',action='store_true');a=p.parse_args()
    if a.self_test:self_test();return
    if not a.session or not a.expected_sha:p.error('--session and --expected-sha are required')
    result=analyze_suite(a.evidence,a.log,a.session,a.expected_sha,a.phase,a.boot)
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.out:a.out.write_text(text,encoding='utf-8')
    print(text,end='')

if __name__=='__main__':main()
