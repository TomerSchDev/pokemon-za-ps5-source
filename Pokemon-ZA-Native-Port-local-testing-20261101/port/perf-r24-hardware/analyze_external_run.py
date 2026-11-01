"""Offline adapter for another operator's hardware_run.py evidence.

Snapshots original evidence with SHA-256 provenance into a new review directory.
Does not import hardware_run.py, access a console or modify original evidence.
Derived identity mapping is explicitly marked; no original receipt is synthesized.
"""
from __future__ import annotations
import argparse
from collections import Counter
import datetime
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import analyze_verified as v

SHA = {'r23c':'dd1df4862a08eab80a19790bb2b65b351adb8ff1fc3ce893def4a91417786677',
       'r24':'a7890eca75127adcdb9c464cdeb03e9c1d143fe099fbf853500a9349c56a5610'}


def write(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')


def under(root,relative):
    path=(root/relative.replace('\\','/')).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('evidence path escapes source root')
    return path


def cpu_assessment(boot,rows,logical_cores):
    lo,hi=rows[0]['frame'],rows[-1]['frame']
    byframe={r['frame']:r['dt_ns'] for r in rows}
    checked=[]
    for w in boot['windows']:
        if w.get('start',-1)<lo or w['frame']>hi or 'perf' not in w:continue
        p=w['perf']
        if p['threads']<0:continue
        wall=sum(byframe[f] for f in range(w['start'],w['frame']+1))
        equivalents=p['thread_cpu_ns']/wall
        counts=Counter(t['ns'] for t in p['top_rows'])
        repeated=[dict(ns=ns,count=n) for ns,n in counts.items() if n>1 and ns>0]
        # Allow 5% for different sampling boundaries/clock rounding. A >2x
        # whole-process physical CPU bound remains a decisive invalid metric.
        impossible=logical_cores is not None and equivalents>logical_cores*1.05
        checked.append(dict(line=w['line'],start=w['start'],end=w['frame'],frames=w['frames'],
            wall_ns=wall,threads=p['threads'],raw_thread_cpu_ns=p['thread_cpu_ns'],
            core_equivalents=equivalents,logical_cores=logical_cores,
            exceeds_physical_cpu_bound=impossible,identical_top_deltas=repeated))
    invalid=any(w['exceeds_physical_cpu_bound'] for w in checked)
    return dict(status='unreliable_rejected' if invalid else 'not_disproved_by_bound',
        windows=checked,violating_windows=sum(w['exceeds_physical_cpu_bound'] for w in checked),
        max_core_equivalents=max((w['core_equivalents'] for w in checked),default=None),
        note='Identical deltas across distinct threads plus aggregate CPU exceeding the physical bound make these per-thread totals/rankings unusable. Clock aliasing is a hypothesis; return codes alone do not verify clock semantics.' if invalid else 'Passing the bound does not independently validate thread clock semantics.')


class Snapshot:
    def __init__(self,source,out,reuse=None):
        self.source=source.resolve();self.out=out.resolve();self.manifest=[];self.copied={}
        self.reuse=reuse.resolve() if reuse is not None else None
    def copy(self,relative,prefix_newline=False):
        path=under(self.source,relative);rel=path.relative_to(self.source)
        if str(rel) in self.copied:return self.copied[str(rel)]
        raw=path.read_bytes();original_bytes=len(raw);original_sha=v.sha(raw)
        if prefix_newline:raw=raw[:raw.rfind(b'\n')+1]
        if self.reuse is not None and path.suffix=='.png':
            candidate=self.reuse/'originals'/rel
            if candidate.is_file() and v.sha(candidate.read_bytes())==original_sha:
                self.manifest.append(dict(source=str(path),source_bytes_at_read=original_bytes,source_sha256_at_read=original_sha,
                    copy=None,reused_snapshot=str(candidate),reused_snapshot_sha256=original_sha,
                    transformation='reference to already frozen byte-identical PNG, hash reverified; no second image copy'))
                self.copied[str(rel)]=candidate
                return candidate
        dest=self.out/'originals'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(raw)
        assert v.sha(dest.read_bytes())==v.sha(raw)
        self.manifest.append(dict(source=str(path),source_bytes_at_read=original_bytes,source_sha256_at_read=original_sha,
            copy=str(dest.relative_to(self.out)),copy_bytes=len(raw),copy_sha256=v.sha(raw),
            transformation='complete-newline prefix of one read of growing log' if prefix_newline else 'byte-identical copy'))
        self.copied[str(rel)]=dest
        return dest
    def inspect_hash(self,relative,expected_hash,expected_size):
        path=under(self.source,relative);raw=path.read_bytes()
        if v.sha(raw)!=expected_hash or len(raw)!=expected_size:raise ValueError('original backup hash/size mismatch')
        self.manifest.append(dict(source=str(path),source_bytes_at_read=len(raw),source_sha256_at_read=v.sha(raw),
                                  copy=None,transformation='hash verification only; saved-game contents not duplicated in review'))


def pass_profiles(boottext,lo,hi):
    profiles=[];current=None
    for number,line in enumerate(boottext.splitlines(),1):
        header=re.search(r'\[gpuprof\] frame (\d+): (\d+) marks, ([\d.]+) ms first to last',line)
        if header:
            current=dict(frame=int(header[1]),marks=int(header[2]),first_to_last_ms=float(header[3]),
                         boot_relative_line=number,rows=[])
            profiles.append(current)
        row=re.search(r'\[gpuprof\]\s+([\d.]+) ms\s+([\d.]+)%\s+(.*)',line)
        if row and current is not None:
            current['rows'].append(dict(ms=float(row[1]),reported_pct=float(row[2]),label=row[3],boot_relative_line=number))
    selected=[p for p in profiles if lo<=p['frame']<=hi]
    valid=[];rejected=[]
    for p in selected:
        p['complete']=len(p['rows'])==p['marks']-1
        # Header prints 2 decimals and each row 3; allow accumulated rounding.
        p['sum_rows_ms']=sum(r['ms'] for r in p['rows'])
        p['rounding_consistent']=abs(p['sum_rows_ms']-p['first_to_last_ms']) <= .005 + len(p['rows'])*.0005 + 1e-8
        (valid if p['complete'] and p['rounding_consistent'] else rejected).append(p)
    groups={}
    for p in valid:
        for row in p['rows']:
            if not row['label'].startswith('pass:'):continue
            g=groups.setdefault(row['label'],dict(label=row['label'],sum_ms=0,occurrences=0,max_ms=0))
            g['sum_ms']+=row['ms'];g['occurrences']+=1;g['max_ms']=max(g['max_ms'],row['ms'])
    for g in groups.values():g['mean_ms_per_profiled_frame']=g['sum_ms']/len(valid)
    return dict(selected_profile_frames=[p['frame'] for p in valid],profiles=valid,rejected_profiles=rejected,
        top_pass_labels=sorted(groups.values(),key=lambda g:-g['sum_ms'])[:12],
        note='Diagnostic only. Rows time between adjacent GPU marks, not isolated shader costs. Submission-start rows include GPU idle. Profiler forces renderer_flush and waits for timestamp query results, changing execution; do not compare this FPS to ordinary mode.')


def review(source,out,interference_path=None,reuse=None):
    started_at=datetime.datetime.now(datetime.timezone.utc).isoformat()
    out=out.resolve()
    allowed=(v.ROOT/'evidence/perf-r24-analysis-review').resolve()
    if not out.is_relative_to(allowed):raise ValueError('review output must remain in owned review tree')
    out.mkdir(parents=True,exist_ok=False)
    if reuse is not None and not reuse.resolve().is_relative_to(allowed):raise ValueError('reused snapshot must be inside owned review tree')
    snap=Snapshot(source,out,reuse)
    interference=None
    if interference_path is not None:
        iraw=Path(interference_path).read_bytes();interference=json.loads(iraw)
        (out/'interference-original.json').write_bytes(iraw)
        snap.manifest.append(dict(source=str(Path(interference_path).resolve()),source_bytes_at_read=len(iraw),source_sha256_at_read=v.sha(iraw),
            copy='interference-original.json',copy_bytes=len(iraw),copy_sha256=v.sha(iraw),transformation='byte-identical copy of explicit external-I/O disclosure'))
    state_path=snap.copy('state.json');state=json.loads(state_path.read_bytes())
    log_path=snap.copy('all.klog.log',True);lograw=log_path.read_bytes();logtext=lograw.decode('utf-8',errors='replace')
    boots=v.parse_log(logtext)
    backup_path=snap.copy('save-backup/verification.json');backup=json.loads(backup_path.read_bytes())
    if backup.get('double_read_verified') is not True:raise ValueError('original backup not verified')
    backupfiles={f['path']:f for f in backup['files']}
    for f in backup['files']:snap.inspect_hash('save-backup/'+f['path'],f['sha256'],f['bytes'])
    results=[]
    for phase in state['phases']:
        label=phase['boot']+'/'+phase['label']
        result=dict(phase=label,status='invalid')
        try:
            phasepath=snap.copy(label+'/phase.json')
            actualphase=json.loads(phasepath.read_bytes())
            if actualphase!=phase:raise ValueError('state and phase snapshot differ')
            identpath=snap.copy(phase['boot']+'/identity.json');ident=json.loads(identpath.read_bytes())
            if ident['build']!=phase['build'] or ident['label']!=phase['boot'] or ident['sha256']!=SHA[ident['build']] or ident['run']!=backup['run'] or ident.get('backup_verified') is not True:
                raise ValueError('source build/run/backup identity mismatch')
            if phase['options']!=ident['options']:raise ValueError('phase startup options disagree with original boot')
            source_boots=[b for b in state['boots'] if b['label']==phase['boot']]
            if len(source_boots)!=1 or any(source_boots[0][k]!=ident[k] for k in ('build','sha256','session','pid','run','options')):
                raise ValueError('state boot does not bind exact identity')
            csvpath=snap.copy(phase['csv']);rows,timing=v.read_intervals(csvpath)
            seq=int(re.fullmatch(r'measure_(\d+)\.csv',csvpath.name)[1])
            receiptpath=snap.copy(label+f'/command_{seq}.json')
            # This is a transparent schema adapter, not a claimed console check.
            derived=dict(adapter='external hardware_run.py identity mapping, not an original receipt',
                source_identity_sha256=v.sha(identpath.read_bytes()),source_identity=str(identpath.relative_to(out)),
                client=ident['build'],eboot_sha256=ident['sha256'],session=ident['session'],pid=ident['pid'],run=ident['run'],
                backup_verified=ident['backup_verified'])
            dp=out/'derived'/phase['boot']/'identity-adapter.json';write(dp,derived)
            image_checks=[]
            for key in ('before','after'):
                entries=phase[key]
                if len(entries)!=1:raise ValueError('snapshot entry count')
                f=entries[0];m=re.fullmatch(r'frame_([1-9][0-9]*)_([1-9][0-9]*)\.png',f['name'])
                if not m:raise ValueError('invalid snapshot filename')
                frame,sseq=map(int,m.groups());lo,hi=timing['csv_frames']
                if (key=='before' and frame>=lo-1) or (key=='after' and frame<=hi):raise ValueError('snapshot overlaps measurement')
                srpath=snap.copy(label+f'/command_{sseq}.json');sr=json.loads(srpath.read_bytes())
                if sr['files']!=entries or sr['ack'].get('session')!=ident['session'] or sr['ack'].get('seq')!=sseq or sr['ack'].get('op')!='snapshot' or sr['ack'].get('result')!='saved' or sr['ack'].get('file')!=f['name']:
                    raise ValueError('snapshot not bound to original command acknowledgement')
                image=snap.copy(label+'/'+f['name']);iraw=image.read_bytes()
                if f.get('readback_verified') is not True or len(iraw)!=f['bytes'] or v.sha(iraw)!=f['sha256']:raise ValueError('snapshot hash mismatch')
                if iraw[:8]!=b'\x89PNG\r\n\x1a\n' or iraw[12:16]!=b'IHDR':raise ValueError('snapshot is not a PNG IHDR')
                width,height=struct.unpack('>II',iraw[16:24])
                image_checks.append(dict(kind=key,file=f['name'],sha256=f['sha256'],width=width,height=height,frozen_path=str(image)))
            options=dict(line.split('=',1) for line in ident['options'].splitlines() if line and not line.startswith('#'))
            result=v.analyze(dp,receiptpath,csvpath,log_path,SHA[ident['build']],phase['slots'],int(options.get('gaps','0')),options.get('dcache','tls'))
            result['phase']=label;result['source_operator']='other Codex thread; this review was offline'
            result['original_identity_sha256']=v.sha(identpath.read_bytes());result['original_phase_sha256']=v.sha(phasepath.read_bytes())
            result['original_snapshot_receipts_verified']=True
            result['png_checks']=image_checks
            if result['status']!='verified':raise ValueError(result.get('reason','strict validation failed'))
            checks=phase['save_check']
            if len(checks)!=len(backupfiles) or any(not x.get('unchanged') or x['path'] not in backupfiles or x['sha256']!=backupfiles[x['path']]['sha256'] for x in checks):
                raise ValueError('original save comparison differs from verified backup')
            result['source_save_unchanged_attestation']=checks
            # Stronger binding for live slot changes: exact native receipt and
            # all status fields in the corresponding same-boot logged switch.
            transition_source=under(snap.source,label+'/transition.json')
            matched=[b for b in boots if ident['session'] in b['sessions']]
            assert len(matched)==1;b=matched[0]
            if transition_source.exists():
                tp=snap.copy(label+'/transition.json');tr=json.loads(tp.read_bytes());ta=tr['ack']
                clientpath=v.ROOT/'port/perf-r24/observer/client.py'
                spec=importlib.util.spec_from_file_location('external_offline_client',clientpath)
                client=importlib.util.module_from_spec(spec)
                sys.path.insert(0,str(clientpath.parent))
                try:spec.loader.exec_module(client)
                finally:sys.path.pop(0)
                client.validate_slot_depth_ack(ta,phase['slots'])
                if ta['session']!=ident['session'] or ta['result']!='applied' or ta['frame']>=timing['csv_frames'][0]-1:raise ValueError('slot transition mismatch')
                bindings={'frame':'frame','requested':'requested_slots','active':'active_slots','previous':'previous_slots','result':'runtime_result','drained_seq':'drained_seq','completed_seq':'completed_seq','budget_valid':'budget_valid','pool':'pool_bytes','largest_free_extent':'largest_free_extent','driver':'driver_bytes','required':'required_headroom_bytes'}
                events=[e for e in b['controls'] if '[za-r23-slots] switch' in e['text'] and all(v.fields(e['text']).get(k)==str(ta[x]) for k,x in bindings.items())]
                if len(events)!=1:raise ValueError('slot transition not bound to unique exact log event')
                result['slot_transition_verified']=dict(receipt_sha256=v.sha(tp.read_bytes()),log_line=events[0]['line'],ack=ta)
            if ident['build']=='r24':
                if any(result['options'].get(k)!=value for k,value in options.items()):raise ValueError('requested startup options not confirmed in log')
                expected_mode=options.get('mode','3840x2160')
                if not any('the window is '+expected_mode in m['text'] for m in result['display_log']):raise ValueError('actual output resolution not confirmed')
                start=b['start_line']-1;next_starts=[bb['start_line']-1 for bb in boots if bb['start_line']>b['start_line']]
                boottext='\n'.join(logtext.splitlines()[start:min(next_starts) if next_starts else None])
                swapchains=re.findall(r'\[vk\].*swapchain (\d+x\d+)',boottext)
                if set(swapchains)!={expected_mode}:raise ValueError('actual swapchain resolution not confirmed')
                if any(f"{p['width']}x{p['height']}"!=expected_mode for p in image_checks):raise ValueError('PNG dimensions differ from selected output')
                result['swapchain_sizes']=swapchains
                mc=re.search(r'cpu: (\d+) logical cores',boottext);cores=int(mc[1]) if mc else None
                assessment=cpu_assessment(b,rows,cores);result['thread_clock_assessment']=assessment
                if assessment['status']=='unreliable_rejected':
                    result['unusable_thread_counters']=result['r24']['threads']
                    result['r24']['threads']=None
                    result['rejected_metrics']=['per-thread CPU totals and thread rankings']
                result['actual_output_resolution']=expected_mode
                if options.get('prof')=='1':result['pass_profiles']=pass_profiles(boottext,*timing['csv_frames'])
            result['status']='verified'
            effects=[x for x in interference.get('affected_phases',[]) if x['phase']==label] if interference else []
            result['known_external_interference']=effects
            result['comparison_eligible']=not effects
            result['comparison_eligibility_scope']='No disclosed overlapping external console I/O; operator no-I/O code window and structural checks. Absence of all other system activity cannot be proven.' if not effects else 'Excluded from uncontaminated performance comparisons despite structurally valid receipts/CSV.'
            if options.get('prof')=='1' and ident['build']=='r24':
                result['comparison_eligible']=False
                result['comparison_eligibility_scope']='Diagnostic pass-profiler phase; explicit flush/query WAIT changes execution. Do not pool with ordinary FPS.'
        except (ValueError,KeyError,AssertionError,OSError,TypeError) as exc:
            result['status']='invalid';result['reason']=str(exc)
        write(out/'results'/(label.replace('/','--')+'.json'),result);results.append(result)
    summary=dict(at=datetime.datetime.now(datetime.timezone.utc).isoformat(),snapshot_started_at=started_at,source_run=str(snap.source),
        source_state_sha256=v.sha(state_path.read_bytes()),frozen_log_sha256=v.sha(lograw),offline_only=True,
        phases=[dict(phase=r['phase'],status=r['status'],reason=r.get('reason'),
                     fps=r.get('timing',{}).get('all_intervals',{}).get('interval_rate_fps'),
                     coverage=r.get('coverage_fraction'),thread_metric=r.get('thread_clock_assessment',{}).get('status'),
                     comparison_eligible=r.get('comparison_eligible'),known_external_interference=r.get('known_external_interference')) for r in results],
        note='Only phases present in one state snapshot are reviewed. Source command acknowledgements and file hashes are preserved; no hardware checks are newly claimed.',
        provenance=snap.manifest)
    write(out/'summary.json',summary)
    print(json.dumps(dict(out=str(out),phases=summary['phases'])))
    return summary


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--interference',type=Path)
    p.add_argument('--reuse-review',type=Path)
    a=p.parse_args();review(a.run,a.out,a.interference,a.reuse_review)
