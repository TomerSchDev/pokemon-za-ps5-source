"""Offline r23 slot-depth phase/CSV/profiler validation; never accesses console.

Use --session SID --expected-sha SHA --log SNAPSHOT --out ANALYSIS. Comparisons
stay within exact identity and recorded fps_mode. Per-report counters are summed,
high-water values use maxima, resource snapshots use ranges; no winner is chosen.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
from pathlib import Path
import re
import sys
from analyze_spans import read_intervals, verify_ack, sha, uint, TIMER_PATTERNS

ROOT=Path(__file__).resolve().parents[2]
SUM_FIELDS=('samples','incomplete_on_entry','ready_on_entry','wait_ns','incomplete_ns','ready_ns','logical_sum','physical_sum','held_sum')
MAX_FIELDS=('max_wait_ns','logical_high','physical_high','held_high')
GAUGES=('chunks','transient_capacity','transient_high','descriptor_pools','command_buffers','counter_query_pools')
LIMITATIONS=[
    'CSV rates are CPU intervals between present submissions, not scanout or simulation speed.',
    'Only phases with the same runtime SHA, SID, PID, run and fps_mode can be compared. Mode0 and mode1 are never pooled.',
    'Slot counters reset per report. Sum complete intervals, take maxima of high-water counters, and retain resource gauges as snapshots; never difference reset counters.',
    'Old-mode reports emitted at switches and the first partial interval afterward are excluded.',
    'largest_free_extent is the largest free contiguous direct-memory range at explicit admission, not total free RAM. Memory is not queried during measurement.',
    'Transient capacity is allocated/recyclable ring capacity, not free memory; switching back to8 does not promise all transient capacity is released.',
    'Profiler timer buckets nest/overlap; GPU query totals can overlap. Do not add them, subtract them into a critical path, or infer a causal winner.',
    'Evidence validation does not establish equivalent scene/camera, visual correctness or long-run stability. Whole-window profiler coverage can be smaller than CSV coverage.',
]

def validator():
    """Use the actual reviewed offline client validator without its CLI/network."""
    path=ROOT/'port/slot-depth-r23-observer/client.py'
    spec=importlib.util.spec_from_file_location('za_r23_receipt_validation',path)
    module=importlib.util.module_from_spec(spec)
    sys.path.insert(0,str(path.parent))
    try:spec.loader.exec_module(module)
    finally:sys.path.pop(0)
    return module.validate_slot_depth_ack,sha(path.read_bytes())

VALIDATE_SLOT,VALIDATOR_SHA=validator()

def parse_log_text(text,name='<memory>'):
    windows=[];events=[];captures=[];diagnostics=[];sessions={0:set()};boot_max={}
    boot=0;epoch=0;startup=False;pending={};previous=None;last_frame=None
    for line_no,line in enumerate(text.splitlines(),1):
        if re.search(r'\[za-r20b?-submit\] startup',line):
            if startup or last_frame is not None:boot+=1
            startup=True;epoch=0;previous=None;pending={};last_frame=None;sessions.setdefault(boot,set())
        sid=re.search(r'session_([0-9a-f]{16})(?:/|\b)',line)
        if sid:sessions.setdefault(boot,set()).add(sid[1])
        cap=re.search(r'session_([0-9a-f]{16})/frame_(\d+)_(\d+)\.png',line)
        if cap:captures.append(dict(boot=boot,line=line_no,session=cap[1],frame=int(cap[2]),seq=int(cap[3])))
        switch=re.search(r'\[za-r23-slots\] switch (.*)',line)
        event=None
        if switch:
            values={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',switch[1])}
            required={'frame','requested','active','previous','result','drained_seq','completed_seq','budget_valid','pool','largest_free_extent','driver','required'}
            if required<=values.keys():event=dict(control='slot_depth',**values)
        for control,pattern in (
            ('preparation',r'\[za-r21-prep\] applied frame=(\d+) profile=([\w-]+) flags=(\d+)'),
            ('immutable_spans',r'\[za-r22-immutable\] applied frame=(\d+) mode=(\w+) flags=(\d+)'),
            ('submission',r'\[za-r20b?-submit\] applied frame=(\d+) profile=([\w-]+)')):
            m=re.search(pattern,line)
            if m:event=dict(control=control,frame=int(m[1]),profile=m[2])
        control_prefix=re.search(r'\[(?:za-r23-slots\] switch|za-r21-prep\] applied|za-r22-immutable\] applied|za-r20b?-submit\] applied)\b',line)
        if control_prefix and event is None:
            # An incomplete control record is not proof that no control ran.
            # Invalidate this boot conservatively and never bridge its counters.
            diagnostics.append(dict(line=line_no,boot=boot,reason='malformed_control_record'))
            epoch+=1;pending={};previous=None;continue
        if event is not None:
            epoch+=1;event.update(line=line_no,boot=boot,epoch=epoch);events.append(event)
            # Even a refused slot change may drain/query/allocate. Its interval
            # is excluded, and it cannot occur inside a certified measurement.
            pending={};previous=None;continue
        stats=re.search(r'\[za-r23-slots\] active=(\d+) capacity=(\d+) (.*)',line)
        if stats:
            errors=pending.setdefault('errors',[])
            if 'slots' in pending:errors.append('duplicate_slot_report')
            values={k:int(v) for k,v in re.findall(r'(\w+)=(-?\d+)',stats[3])}
            needed=set(SUM_FIELDS+MAX_FIELDS+GAUGES+('preparation','immutable'))
            if not needed<=values.keys():errors.append('missing_slot_counters')
            else:
                if any(not uint(v) for v in values.values()):errors.append('invalid_unsigned_counter')
                if values['samples']!=values['incomplete_on_entry']+values['ready_on_entry']:errors.append('sample_partition_mismatch')
                if values['wait_ns']!=values['incomplete_ns']+values['ready_ns'] or values['max_wait_ns']>values['wait_ns']:errors.append('wait_partition_mismatch')
                for field in ('logical','physical','held'):
                    if values[field+'_sum']>values[field+'_high']*values['samples']:errors.append(field+'_high_invariant')
                if values['transient_capacity']>values['transient_high']:errors.append('transient_high_invariant')
                if not values['samples'] and any(values[k] for k in SUM_FIELDS+MAX_FIELDS):errors.append('zero_sample_nonzero_counters')
                if values['preparation']!=0 or values['immutable']!=0:errors.append('preparation_or_immutable_not_baseline')
            if int(stats[1]) not in (8,16) or int(stats[2])!=16:errors.append('invalid_active_or_capacity')
            pending['slots']=dict(active=int(stats[1]),capacity=int(stats[2]),values=values,line=line_no)
        prep=re.search(r'\[za-r21-prep\] profile=([\w-]+) flags=(\d+)',line)
        if prep:pending['preparation']=(prep[1],int(prep[2]))
        submit=re.search(r'\[za-r20b?-submit\] profile=(\w+) logical=\d+ vk_calls=\d+',line)
        if submit:pending['submission']=submit[1]
        report=re.search(r'\[vk\] t=[\d.]+ frame (\d+) [\d.]+ fps',line)
        if not report:continue
        frame=int(report[1])
        if last_frame is not None and frame<=last_frame:
            diagnostics.append(dict(line=line_no,reason='duplicate_or_reset_frame'));previous=None
            if frame<last_frame:boot+=1;epoch=0;sessions.setdefault(boot,set())
        errors=list(pending.get('errors',[]));slots=pending.get('slots')
        if not slots:errors.append('missing_slot_report')
        if pending.get('preparation')!=('baseline',0):errors.append('preparation_not_confirmed_baseline')
        if pending.get('submission')!='batch4':errors.append('submission_not_confirmed_batch4')
        current=dict(frame=frame,line=line_no,boot=boot,epoch=epoch,valid=not errors)
        if previous is not None:
            if not previous['valid']:errors.append('previous_report_boundary_incomplete')
            w=dict(log=name,line=line_no,previous_line=previous['line'],boot=boot,epoch=epoch,
                start=previous['frame']+1,end=frame,frames=frame-previous['frame'],active_slots=slots['active'] if slots else None,
                capacity_slots=slots['capacity'] if slots else None,values=slots['values'] if slots else {},
                preparation=pending.get('preparation'),submission=pending.get('submission'),valid=not errors,rejected_reasons=errors)
            for field,pattern in TIMER_PATTERNS.items():
                m=re.search(pattern,line)
                if m:w[field]=int(m[1])
            windows.append(w)
        previous=current;last_frame=frame;pending={};boot_max[boot]=max(frame,boot_max.get(boot,0))
    return dict(log=name,windows=windows,events=events,captures=captures,diagnostics=diagnostics,
        sessions_by_boot={str(k):sorted(v) for k,v in sessions.items()},max_frame_by_boot={str(k):v for k,v in boot_max.items()})

def parse_log(path):
    raw=Path(path).read_bytes();result=parse_log_text(raw.decode('utf-8',errors='replace'),str(path))
    result.update(sha256=sha(raw),bytes=len(raw));return result

def summarize(windows):
    frames=sum(w['frames'] for w in windows);totals={k:sum(w['values'][k] for w in windows) for k in SUM_FIELDS}
    highs={k:max(w['values'][k] for w in windows) for k in MAX_FIELDS};samples=totals['samples']
    gauges={k:dict(min=min(w['values'][k] for w in windows),max=max(w['values'][k] for w in windows),last=windows[-1]['values'][k]) for k in GAUGES}
    return dict(aggregation='sum_reset_counters_max_highwaters_resource_snapshot_ranges',covered_frames=frames,reports=len(windows),
        counters_total=totals,highwaters=highs,resources=gauges,
        wait_ms_per_frame=totals['wait_ns']/frames/1e6 if frames else None,
        incomplete_wait_ms_per_frame=totals['incomplete_ns']/frames/1e6 if frames else None,
        ready_wait_ms_per_frame=totals['ready_ns']/frames/1e6 if frames else None,
        incomplete_on_entry_fraction=totals['incomplete_on_entry']/samples if samples else None,
        mean_outstanding_at_sample={k:totals[k+'_sum']/samples if samples else None for k in ('logical','physical','held')},
        profiler_per_frame={k:sum(w[k] for w in windows)/frames for k in TIMER_PATTERNS if frames and all(k in w for w in windows)},windows=windows)

def analyze_phase(path,logs,expected_sha=None,boot=None):
    path=Path(path);out=dict(phase=str(path),label=path.parent.name,status='invalid')
    try:
        raw=path.read_bytes();phase=json.loads(raw);out['phase_sha256']=sha(raw)
        if not isinstance(phase,dict):raise ValueError('Phase must be an object')
        sid=phase.get('session');depth=phase.get('profile');seq=phase.get('sequence_start');fps=phase.get('fps_mode')
        out.update(session=sid,slot_depth=depth,fps_mode=fps,pid=phase.get('pid'),run=phase.get('run'))
        if not isinstance(sid,str) or not re.fullmatch('[0-9a-f]{16}',sid) or type(depth) is not int or depth not in (8,16) or not uint(seq) or not seq or seq+5>=2**64:
            raise ValueError('Invalid session/depth/sequence')
        if type(fps) is not int or fps not in (0,1):raise ValueError('Explicit fps_mode0 or1 is required')
        if phase.get('control')!='slot_depth' or phase.get('preparation')!='baseline' or phase.get('immutable_spans')!='off':raise ValueError('Incorrect isolated slot experiment context')
        if not uint(phase.get('seconds')) or not 10<=phase['seconds']<=40:raise ValueError('Invalid requested duration')
        if path.parent.parent.name!='session-'+sid:raise ValueError('Phase directory/session mismatch')
        identity_path=path.parent.parent/'identity.json';identity_raw=identity_path.read_bytes();identity=json.loads(identity_raw)
        if not isinstance(identity,dict):raise ValueError('Identity must be an object')
        if identity.get('client')!='r23' or identity.get('backup_verified') is not True or any(identity.get(k)!=phase.get(k) for k in ('session','pid','run')):
            raise ValueError('r23 SID/PID/run identity mismatch')
        if not uint(identity.get('pid')) or not identity['pid'] or not isinstance(identity.get('run'),str) or not identity['run']:raise ValueError('Invalid PID/run')
        artifact=identity.get('eboot_sha256')
        if not isinstance(artifact,str) or not re.fullmatch('[0-9a-f]{64}',artifact) or (expected_sha is not None and artifact!=expected_sha):raise ValueError('Exact runtime artifact SHA mismatch')
        out.update(runtime_sha256=artifact,identity_sha256=sha(identity_raw))
        transition=phase.get('transition')
        if transition is None and phase.get('completed') is False:return {**out,'status':'incomplete','reason':'awaiting applied transition'}
        if not isinstance(transition,dict):raise ValueError('Transition must be an object')
        VALIDATE_SLOT(transition,depth)
        verify_ack(transition,sid,seq,'slot_depth',transition['result'])
        out['transition']=transition
        if transition['result']!='applied':
            if phase.get('completed') is not False or phase.get('status')!='not_measured_'+transition['result'] or any(k in phase for k in ('measurement','before','after','settling')):
                raise ValueError('Rejected transition must not claim measurement')
            return {**out,'status':phase['status'],'reason':'runtime refused requested depth; no timing comparison'}
        if phase.get('completed') is not True:return {**out,'status':'incomplete','reason':'recorder phase incomplete'}
        settle=phase['settling'];verify_ack(settle.get('ack',settle),sid,seq+2,'measure','settling')
        measurement=phase['measurement'];ack=measurement['ack'];verify_ack(ack,sid,seq+2,'measure','complete')
        filename=f'measure_{seq+2}.csv';files=measurement.get('files',[])
        if ack.get('file')!=filename or len(files)!=1 or files[0].get('name')!=filename or files[0].get('readback_verified') is not True:raise ValueError('No exact verified measurement file')
        rows,timing=read_intervals(path.parent/filename)
        if files[0].get('sha256')!=timing['csv_sha256'] or type(files[0].get('bytes')) is not int or files[0]['bytes']!=timing['csv_bytes']:raise ValueError('CSV hash/size mismatch')
        if timing['fps_modes']!=[fps] or timing['all_intervals']['duration_s']<phase['seconds']-.15:raise ValueError('CSV FPS mode differs from phase or duration incomplete')
        if any(not uint(v) for row in rows for v in row.values()) or any(rows[i]['frame']!=rows[i-1]['frame']+1 for i in range(1,len(rows))):raise ValueError('Noncontiguous or invalid unsigned CSV')
        lo,hi=timing['csv_frames']
        if not transition['frame']<lo:raise ValueError('Slot switch not before CSV')
        for key,offset in (('before',1),('after',3)):
            cap=phase[key]['ack'];verify_ack(cap,sid,seq+offset,'snapshot','saved')
            m=re.fullmatch(r'frame_([1-9][0-9]*)_'+str(seq+offset)+r'\.png',cap.get('file',''))
            if not m or not uint(int(m[1])) or (key=='before' and int(m[1])>=lo) or (key=='after' and int(m[1])<=hi):raise ValueError('Snapshot overlaps CSV or identity mismatched')
        out.update(status='timing_valid_no_profiler_match',timing=timing)
        matches=[]
        binding={'frame':'frame','requested':'requested_slots','active':'active_slots','previous':'previous_slots','result':'runtime_result',
            'drained_seq':'drained_seq','completed_seq':'completed_seq','budget_valid':'budget_valid','pool':'pool_bytes',
            'largest_free_extent':'largest_free_extent','driver':'driver_bytes','required':'required_headroom_bytes'}
        for log in logs:
            for e in log['events']:
                if e['control']=='slot_depth' and all(e.get(k)==transition[v] for k,v in binding.items()) and (boot is None or e['boot']==boot):
                    if sid in log['sessions_by_boot'].get(str(e['boot']),[]):matches.append((log,e))
        if len(matches)!=1:return {**out,'profiler_reason':'missing_or_ambiguous_exact_logged_switch','transition_candidates':len(matches)}
        log,event=matches[0];out.update(log=log['log'],log_sha256=log['sha256'],boot=event['boot'],logged_transition=event)
        malformed=[d for d in log['diagnostics'] if d.get('boot')==event['boot'] and d['reason']=='malformed_control_record']
        if malformed:return {**out,'status':'log_control_unverified','malformed_control_records':malformed}
        unexpected=[e for e in log['events'] if e['boot']==event['boot'] and e['line']>event['line'] and event['frame']<=e['frame']<=hi]
        if unexpected:return {**out,'status':'mixed_control_measurement','unexpected_transitions':unexpected}
        captures=[c for c in log['captures'] if c['boot']==event['boot'] and c['session']==sid and lo<=c['frame']<=hi]
        if captures:return {**out,'status':'capture_inside_measurement','unexpected_captures':captures}
        if log['max_frame_by_boot'].get(str(event['boot']),0)<hi:return {**out,'profiler_reason':'log_does_not_cover_measurement_end'}
        inside=[w for w in log['windows'] if w['boot']==event['boot'] and lo<=w['start'] and w['end']<=hi]
        selected=[];rejected=[]
        for w in inside:
            reasons=list(w['rejected_reasons'])
            if w['active_slots']!=depth or w['epoch']!=event['epoch']:reasons.append('wrong_depth_or_control_epoch')
            if reasons:rejected.append(dict(line=w['line'],start=w['start'],end=w['end'],reasons=reasons))
            else:selected.append(w)
        out['rejected_profiler_windows']=rejected
        if any(w['active_slots']!=depth or w['preparation']!=('baseline',0) or w['submission']!='batch4' or w['values'].get('preparation')!=0 or w['values'].get('immutable')!=0 for w in inside):
            return {**out,'status':'runtime_state_unverified','profiler_reason':'unconfirmed depth/baseline/spans-off/batch4 report'}
        if not selected:return {**out,'profiler_reason':'no_complete_valid_counter_window'}
        out.update(status='complete',slots=summarize(selected),slot_depth=depth)
        out['slots']['coverage_fraction_of_csv_intervals']=out['slots']['covered_frames']/len(rows)
        return out
    except (OSError,ValueError,TypeError,KeyError,IndexError,AttributeError) as exc:
        return {**out,'status':'invalid','reason':str(exc)}

def comparison_groups(phases):
    groups={}
    for p in phases:
        if p['status']!='complete':continue
        key=(p['runtime_sha256'],p['session'],p['pid'],p['run'],p['fps_mode'])
        group=groups.setdefault(key,dict(runtime_sha256=key[0],session=key[1],pid=key[2],run=key[3],fps_mode=key[4],samples=[]))
        group['samples'].append(dict(label=p['label'],slot_depth=p['slot_depth'],timing=p['timing']['all_intervals'],
            shader_affected_intervals=p['timing']['shader_affected_intervals'],covered_frames=p['slots']['covered_frames'],
            wait_ms_per_frame=p['slots']['wait_ms_per_frame'],incomplete_on_entry_fraction=p['slots']['incomplete_on_entry_fraction'],
            resources=p['slots']['resources'],highwaters=p['slots']['highwaters'],profiler_per_frame=p['slots']['profiler_per_frame']))
    return list(groups.values())

def analyze_suite(evidence,logs,session,expected_sha,phase_paths=None,boot=None):
    root=Path(evidence)
    if not re.fullmatch('[0-9a-f]{16}',session) or not re.fullmatch('[0-9a-f]{64}',expected_sha):raise ValueError('Explicit SID and expected SHA required')
    if not logs or (boot is not None and len(logs)!=1):raise ValueError('Supply log snapshot(s); boot requires one log')
    parsed=[parse_log(p) for p in logs];paths=list(map(Path,phase_paths)) if phase_paths else sorted((root/('session-'+session)).glob('*/phase.json'))
    phases=[analyze_phase(p,parsed,expected_sha,boot) for p in paths]
    for p in phases:
        if p.get('session')!=session:p.update(status='invalid',reason='Phase differs from requested SID')
    return dict(schema_version=1,session=session,runtime_sha256=expected_sha,preparation='baseline',immutable_spans='off',submission='batch4',
        receipt_validator_sha256=VALIDATOR_SHA,phases=phases,comparison_groups=comparison_groups(phases),
        logs=[{k:v for k,v in log.items() if k!='windows'} for log in parsed],limitations=LIMITATIONS,recommendation=None)

def self_test():
    from unittest.mock import patch
    sid='0000000000000023';digest='a'*64
    def report(frame,samples=10,depth=16,immutable=0,submission='batch4'):
        values=dict(samples=samples,incomplete_on_entry=samples//2,ready_on_entry=samples-samples//2,
            wait_ns=1000*samples,incomplete_ns=500*samples,ready_ns=500*samples,max_wait_ns=1000,
            logical_sum=4*samples,physical_sum=2*samples,held_sum=samples,logical_high=5,physical_high=3,held_high=2,
            chunks=10,transient_capacity=100000,transient_high=120000,descriptor_pools=16,command_buffers=32,counter_query_pools=16,preparation=0,immutable=immutable)
        return (f'[za-r20b-submit] profile={submission} logical={frame} vk_calls={frame}\n'+
            f'[za-r23-slots] active={depth} capacity=16 '+' '.join(f'{k}={v}' for k,v in values.items())+'\n'+
            '[za-r21-prep] profile=baseline flags=0\n'+f'[vk] t=1.0 frame {frame} 25.0 fps (100 draws, 5 passes)\n')
    switch='[za-r23-slots] switch frame=1 requested=16 active=16 previous=8 result=16 drained_seq=100 completed_seq=100 budget_valid=1 pool=8589934592 largest_free_extent=3221225472 driver=2147483648 required=1073741824\n'
    text=f'[za-r20b-submit] startup profile=batch4\n[observer] session_{sid}/frame_2_11.png\n'+switch+report(100)+report(200,12)+report(300,7)+report(400)
    parsed=parse_log_text(text);parsed['sha256']='synthetic'
    summary=summarize(parsed['windows'][:2]);assert summary['counters_total']['samples']==19 and summary['highwaters']['max_wait_ns']==1000
    assert summary['resources']['command_buffers']=={'min':32,'max':32,'last':32}
    path=Path('/virtual/session-'+sid+'/slot16-1/phase.json');csvpath=path.parent/'measure_12.csv';identity=path.parent.parent/'identity.json'
    def csvdata(mode):return ('frame,now_ns,dt_ns,submitted_interval,represented_interval,shader_before,shader_after,mode,observer_ns\n'+''.join(f'{f},{f*40000000},40000000,1,0,0,0,{mode},1000\n' for f in range(51,301))).encode()
    rawcsv=csvdata(0)
    def ack(seq,op,result,**kw):return dict(session=sid,seq=seq,op=op,result=result,**kw)
    transition=ack(10,'slot_depth','applied',file='',frame=1,cost_ns=123,runtime_result=16,requested_slots=16,status_valid=True,
        status_abi_version=1,active_slots=16,capacity_slots=16,status_requested_slots=16,previous_slots=8,budget_valid=1,status_result=16,status_reserved=0,
        status_frame=1,drained_seq=100,completed_seq=100,pool_bytes=8<<30,largest_free_extent=3<<30,driver_bytes=2<<30,required_headroom_bytes=1<<30,
        transient_capacity_bytes=100000,descriptor_pools=16,command_buffers=32,counter_query_pools=16)
    phase=dict(completed=True,session=sid,pid=42,run='run1',control='slot_depth',preparation='baseline',immutable_spans='off',profile=16,fps_mode=0,sequence_start=10,seconds=10,
        transition=transition,settling=ack(12,'measure','settling'),before={'ack':ack(11,'snapshot','saved',file='frame_2_11.png')},after={'ack':ack(13,'snapshot','saved',file='frame_301_13.png')},
        measurement={'ack':ack(12,'measure','complete',file='measure_12.csv'),'files':[dict(name='measure_12.csv',sha256=sha(rawcsv),bytes=len(rawcsv),readback_verified=True)]})
    fixtures={str(path):json.dumps(phase).encode(),str(csvpath):rawcsv,str(identity):json.dumps(dict(session=sid,pid=42,run='run1',client='r23',eboot_sha256=digest,backup_verified=True)).encode()}
    with patch.object(Path,'read_bytes',lambda p:fixtures[str(p)]):
        result=analyze_phase(path,[parsed],digest);assert result['status']=='complete',result
        assert result['slots']['counters_total']['samples']==19
        groups=comparison_groups([result,{**result,'fps_mode':1},{**result,'slot_depth':8}])
        assert len(groups)==2 and {g['fps_mode']:len(g['samples']) for g in groups}=={0:2,1:1}
        for malformed_phase in ([],{**phase,'transition':None},{**phase,'measurement':[]}):
            fixtures[str(path)]=json.dumps(malformed_phase).encode();assert analyze_phase(path,[parsed],digest)['status']=='invalid'
        fixtures[str(path)]=json.dumps(phase).encode()
        fixtures[str(csvpath)]=rawcsv+b'\n';assert analyze_phase(path,[parsed],digest)['status']=='invalid';fixtures[str(csvpath)]=rawcsv
        for change in ({'fps_mode':1},{'fps_mode':True},{'profile':8},{'immutable_spans':'on'},{'pid':43}):
            fixtures[str(path)]=json.dumps({**phase,**change}).encode();assert analyze_phase(path,[parsed],digest)['status']=='invalid',change
        for change in ({'active_slots':8},{'pool_bytes':0},{'seq':True},{'largest_free_extent':9<<30},{'completed_seq':99}):
            fixtures[str(path)]=json.dumps({**phase,'transition':{**transition,**change}}).encode();assert analyze_phase(path,[parsed],digest)['status']=='invalid',change
        fixtures[str(path)]=json.dumps(phase).encode();assert analyze_phase(path,[parsed],'b'*64)['status']=='invalid'
        for extra in ('[za-r23-slots] switch frame=150 requested=8 active=8 previous=16 result=8 drained_seq=110 completed_seq=110 budget_valid=0 pool=0 largest_free_extent=0 driver=0 required=1073741824\n',
            '[za-r21-prep] applied frame=150 profile=optimized flags=3\n','[za-r22-immutable] applied frame=150 mode=on flags=1\n','[za-r20b-submit] applied frame=150 profile=each\n'):
            altered=parse_log_text(text+extra);altered['sha256']='synthetic';assert analyze_phase(path,[altered],digest)['status']=='mixed_control_measurement'
        captured=parse_log_text(text+f'[observer] session_{sid}/frame_150_99.png\n');captured['sha256']='synthetic'
        assert analyze_phase(path,[captured],digest)['status']=='capture_inside_measurement'
        for badtext in (text.replace('immutable=0','immutable=1'),text.replace('profile=batch4 logical=200','profile=each logical=200')):
            bad=parse_log_text(badtext);bad['sha256']='synthetic';assert analyze_phase(path,[bad],digest)['status']=='runtime_state_unverified'
        assert analyze_phase(path,[parsed,parsed],digest)['status']=='timing_valid_no_profiler_match'
        for malformed_control in ('[za-r23-slots] switch frame=150 requested=8\n','[za-r21-prep] applied truncated\n','[za-r22-immutable] applied frame=150\n','[za-r20b-submit] applied missing\n'):
            broken=parse_log_text(text+malformed_control);broken['sha256']='synthetic'
            assert analyze_phase(path,[broken],digest)['status']=='log_control_unverified'
        # Refusal is retained as admission evidence and never a timing result.
        refused={**phase,'completed':False,'status':'not_measured_memory_gate','transition':{**transition,'result':'memory_gate','runtime_result':-4,'status_result':-4,'active_slots':8,'largest_free_extent':512<<20}}
        for key in ('measurement','before','after','settling'):refused.pop(key)
        fixtures[str(path)]=json.dumps(refused).encode();assert analyze_phase(path,[parsed],digest)['status']=='not_measured_memory_gate'
        # Explicit mode1 is valid, but remains a separate comparison group.
        unlocked={**phase,'fps_mode':1,'measurement':{**phase['measurement'],'files':[dict(name='measure_12.csv',sha256=sha(csvdata(1)),bytes=len(csvdata(1)),readback_verified=True)]}}
        fixtures[str(path)]=json.dumps(unlocked).encode();fixtures[str(csvpath)]=csvdata(1)
        assert analyze_phase(path,[parsed],digest)['status']=='complete'
    malformed=parse_log_text(text.replace('ready_on_entry=6','ready_on_entry=5'))
    assert any('sample_partition_mismatch' in w['rejected_reasons'] for w in malformed['windows'])
    partial=parse_log_text(report(50,10,8)+switch+report(100,5)+report(200,12))
    assert len(partial['windows'])==1 and partial['windows'][0]['start']==101
    print('PASS: exact identity/client receipt/memory/log switch binding; malformed containers and control records; CSV/hash/duration and separate fps-mode groups; switch/screenshot contamination; sum falling reset counters, maxima/gauges; refusal evidence; partial-window exclusion')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evidence',type=Path,default=ROOT/'evidence/preparation-r21-hardware')
    p.add_argument('--session');p.add_argument('--expected-sha');p.add_argument('--log',type=Path,action='append')
    p.add_argument('--phase',type=Path,action='append');p.add_argument('--boot',type=int);p.add_argument('--out',type=Path);p.add_argument('--self-test',action='store_true')
    a=p.parse_args()
    if a.self_test:self_test();return
    if not a.session or not a.expected_sha:p.error('--session and --expected-sha are required')
    result=analyze_suite(a.evidence,a.log,a.session,a.expected_sha,a.phase,a.boot);text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if a.out:a.out.write_text(text,encoding='utf-8')
    print(text,end='')

if __name__=='__main__':main()
