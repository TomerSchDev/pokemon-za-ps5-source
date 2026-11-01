"""PC gallery across three boxes, with explicit box changes and NAS evidence."""
from pathlib import Path
import argparse,json,subprocess,sys,time,re,shutil,collections
from run_pc_gallery import QA,WORK,ROOT,inspect_run

def plan(count):
    inputs=['240:A:8','420:A:8','1200:X:8','1450:A:8','1800:A:8','1950:A:8','2100:DOWN:8','2250:A:8']
    shots=[];base=2403
    for i in range(count):
        if i:
            if i%30:
                base+=100;inputs.append('%d:R:8'%(base-50))
            else:
                event=base+50
                # Summary wraps inside the current box. Wrap to its first slot,
                # return to Boxes, advance the box, and reopen its first summary.
                for offset,button in ((0,'R'),(40,'B'),(80,'R'),(120,'A'),(150,'DOWN'),(180,'A')):
                    inputs.append('%d:%s:8'%(event+offset,button))
                base=event+330
        shots.append((base,base+37))
    return inputs,shots

def cleanup(name):
    assert re.fullmatch(r'pc-wide-(?:import|native)-\d{3}-r\d+(?:-s\d+)?',name)
    for parent in ('runs','prepared'):
        path=WORK/parent/name
        if path.exists():
            assert path.resolve().is_relative_to((WORK/parent).resolve()) and not path.is_symlink()
            shutil.rmtree(path)

def import_batches(args,end):
    progress=QA/'wide'/('progress-import-r%d.json'%args.revision)
    state=json.loads(progress.read_text(encoding='utf-8')) if progress.exists() else {'PC_only':True,'batches':[]}
    prefetch_jobs={}
    def bundle_for(number):
        return QA/'bundles'/('wide-import-%03d-r%d'%(number,3 if number in (2,3) else 2))
    def prefetch(number):
        if number>end or number in prefetch_jobs:return
        batch='wide-import-%03d'%number;asset_name='pc-'+batch+'-assets-r%d'%args.revision
        if (WORK/'prepared'/asset_name/'verified-hashes.json').exists():return
        cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),asset_name,'--bundle',str(bundle_for(number)),'--wait-bundle-ready','--prepare-only']
        with (QA/'wide'/(asset_name+'-prefetch-%d.log'%time.time_ns())).open('xb') as out:
            prefetch_jobs[number]=subprocess.Popen(cmd,stdout=out,stderr=subprocess.STDOUT)
        print('Prefetching '+batch+' assets while the game tests the current group',flush=True)
    for number in range(args.start,end+1):
        batch='wide-import-%03d'%number;name='pc-'+batch+'-r%d'%args.revision
        if any(x['name']==name for x in state['batches']):continue
        if number in prefetch_jobs:
            assert prefetch_jobs[number].wait()==0,'Asset prefetch failed for '+batch
        prefetch(number+1)
        original=json.loads((QA/'wide'/(batch+'.json')).read_text(encoding='utf-8'))['targets']
        remaining=original;resolved=[];segments=[];segment_number=0;boot_shift=0
        first_mods=None;owned=[];control_attempts={}
        while remaining:
            segment_number+=1
            if segment_number>len(original)+4:raise RuntimeError('No forward progress in '+name)
            run_name=name if segment_number==1 else name+'-s%02d'%segment_number
            inputs,shots=plan(len(remaining))
            if boot_shift:
                inputs=[('%d:%s'%(int(x.split(':',1)[0])+boot_shift,x.split(':',1)[1])) if int(x.split(':',1)[0])>=1200 else x for x in inputs]
                shots=[(a+boot_shift,b+boot_shift) for a,b in shots]
            spec=QA/'wide/segments'/(run_name+'.json');spec.parent.mkdir(parents=True,exist_ok=True)
            spec.write_text(json.dumps({'mode':'box','targets':remaining,'body_frame_pairs':shots},indent=1),encoding='utf-8')
            save=QA/'wide/segments'/run_name
            if segment_number==1:save=QA/'wide'/batch
            elif not (save/'save_0/main').exists():
                fixture=[args.pwsh,'-NoProfile','-NonInteractive','-File',str(ROOT/'tools/bulkfixture/Run-MultiFixture.ps1'),
                    '-SourceSave',str(ROOT/'qa/saves/multi-six/save_0/main'),'-Manifest',str(spec),'-OutputSave',str(save/'save_0/main')]
                with spec.with_name(run_name+'-fixture.json').open('xb') as out:subprocess.run(fixture,stdout=out,stderr=subprocess.STDOUT,check=True)
            budget=int((shots[-1][-1]+100)/23)+60
            cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),run_name,'--seconds',str(budget),'--stop-after-shots',
                 '--watch-models',str(spec),
                 '--save-src',str(save),'--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
                 '--input',','.join(inputs),'--shot-at','900,1250,1650,2000,'+','.join(str(x) for pair in shots for x in pair),
                 '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
            staged=WORK/'prepared'/('pc-'+batch+'-assets-r%d'%args.revision)/'mods'
            if first_mods is not None:cmd[3:3]=['--link-local-mods',str(first_mods)]
            elif (staged.parent/'verified-hashes.json').exists():cmd[3:3]=['--link-local-mods',str(staged)]
            else:cmd[3:3]=['--bundle',str(bundle_for(number)),'--wait-bundle-ready']
            report_path=ROOT/'qa/runs'/run_name/'gallery-results.json'
            nas_record=ROOT/'qa/runs'/run_name/'run.json'
            if not report_path.exists() and nas_record.exists():
                deadline=time.monotonic()+300
                while not json.loads(nas_record.read_text(encoding='utf-8')).get('canonical_model_and_game_data_on_NAS'):
                    if time.monotonic()>deadline:raise RuntimeError('NAS evidence copy incomplete for '+run_name)
                    time.sleep(2)
                report=inspect_run(run_name,remaining,shots)
            elif not report_path.exists():
                print('Starting '+run_name+' '+str(len(remaining))+' imported models',flush=True)
                with (QA/'wide'/(run_name+'-driver.log')).open('xb') as out:result=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
                if result.returncode:raise RuntimeError('Driver failed for '+run_name+'; local evidence retained')
                report=inspect_run(run_name,remaining,shots)
            else:report=json.loads(report_path.read_text(encoding='utf-8'))
            owned.append(run_name)
            if first_mods is None:first_mods=WORK/'runs'/run_name/'mods'
            rows=report['targets'];record=json.loads((ROOT/'qa/runs'/run_name/'run.json').read_text(encoding='utf-8'))
            for row in rows:
                if row['key'] in control_attempts:
                    row['experimental_control_candidate']=control_attempts[row['key']]
            fault=None;reason=None
            if record.get('loader_stall_watch'):
                fault=record['loader_stall_watch']['index'];reason='loader_stall'
            for i in range(len(rows)-1):
                if fault is not None:break
                if rows[i]['render_status']=='empty_body' and rows[i+1]['render_status']=='empty_body' and not rows[i+1]['model_resource_requested']:
                    fault=i;reason='loader_stall';break
            frame_match=re.search(r'frame (\d+)',record.get('last_frame_line') or '')
            if fault is None and record.get('crash_lines') and frame_match and int(frame_match.group(1))>=2250+boot_shift:
                log=(ROOT/'qa/runs'/run_name/'stderr.log').read_text(encoding='utf-8',errors='replace')
                loads=re.findall(r'^\[fs\] read ik_pokemon/data/(.+\.trmdl)$',log,re.M)
                for path in reversed(loads):
                    matches=[i for i,t in enumerate(remaining) if t['model_path']==path]
                    if matches:fault=matches[-1];reason='runtime_crash_while_loading';break
            if fault is not None:
                rows[fault]['render_status']=reason;rows[fault]['blocks_later_models']=True
                for row in rows[fault+1:]:
                    row['observed_render_status']=row['render_status'];row['render_status']='deferred_after_loader_failure'
                    row['blocked_by_key']=rows[fault]['key']
                report_path.write_text(json.dumps(report,indent=1),encoding='utf-8')
                failed_target=remaining[fault]
                if failed_target['key'] not in control_attempts:
                    from build_simple_render_controls import build
                    candidate=QA/'auto-control-candidates'/(failed_target['key']+'-r1')
                    if not candidate.exists():build([failed_target],candidate)
                    dest=first_mods/'00-auto-render-fixes/romfs'
                    shutil.copytree(candidate/'romfs',dest,dirs_exist_ok=True)
                    control_attempts[failed_target['key']]=str(candidate)
                    resolved.extend(rows[:fault]);remaining=remaining[fault:]
                    print('Testing isolated native-control candidate for '+failed_target['key']+' before continuing '+str(len(remaining))+' models',flush=True)
                else:
                    resolved.extend(rows[:fault+1]);remaining=remaining[fault+1:]
                    print('Confirmed '+reason+' at '+rows[fault]['key']+'; retrying remaining '+str(len(remaining)),flush=True)
            else:
                unresolved=next((i for i,t in enumerate(rows) if t['render_status'] in ('missing_capture','wrong_screen_requires_review')),None)
                if unresolved is None:resolved.extend(rows);remaining=[]
                else:
                    resolved.extend(rows[:unresolved]);remaining=remaining[unresolved:]
                    if unresolved==0:
                        if boot_shift>=2400:raise RuntimeError('Repeated UI/boot failure; models not marked as failures: '+run_name)
                        boot_shift+=1200
                    print('Retrying incomplete captures '+str(len(remaining)),flush=True)
            segments.append({'name':run_name,'resolved':len(resolved),'remaining':len(remaining),'failure':reason})
            checkpoint={'name':name,'models':len(original),'resolved_targets':resolved,'remaining_targets':remaining,'segments':segments}
            (QA/'wide'/(name+'-checkpoint.json')).write_text(json.dumps(checkpoint,indent=1),encoding='utf-8')
        final={'name':name,'targets':resolved,'segments':segments,'counts':dict(collections.Counter(x['render_status'] for x in resolved))}
        (QA/'wide'/(name+'-results.json')).write_text(json.dumps(final,indent=1),encoding='utf-8')
        state['batches'].append({'name':name,'models':len(original),'resolved':len(resolved),'counts':final['counts'],'segments':len(segments)})
        progress.write_text(json.dumps(state,indent=1),encoding='utf-8');print(json.dumps(state['batches'][-1]),flush=True)
        if not args.keep_local:
            for owned_name in owned:cleanup(owned_name)
            if staged.exists():
                assert staged.parent.resolve().is_relative_to((WORK/'prepared').resolve()) and not staged.parent.is_symlink()
                shutil.rmtree(staged.parent)

def main():
    p=argparse.ArgumentParser();p.add_argument('--kind',choices=('import','native'),required=True)
    p.add_argument('--start',type=int,default=1);p.add_argument('--end',type=int)
    p.add_argument('--revision',type=int,default=1);p.add_argument('--keep-local',action='store_true')
    p.add_argument('--pwsh',default='C:/Program Files/PowerShell/7/pwsh.exe')
    args=p.parse_args();end=args.end or (10 if args.kind=='import' else 8)
    if args.kind=='import':return import_batches(args,end)
    progress=QA/'wide'/('progress-%s-r%d.json'%(args.kind,args.revision))
    state=json.loads(progress.read_text(encoding='utf-8')) if progress.exists() else {'PC_only':True,'batches':[]}
    for n in range(args.start,end+1):
        batch='wide-%s-%03d'%(args.kind,n);name='pc-'+batch+'-r%d'%args.revision
        if any(x['name']==name for x in state['batches']):continue
        spec=QA/'wide'/(batch+'.json');targets=json.loads(spec.read_text(encoding='utf-8'))['targets']
        inputs,shots=plan(len(targets));budget=int((shots[-1][-1]+100)/23)+50
        cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,
             '--seconds',str(budget),'--stop-after-shots','--save-src',str(QA/'wide'/batch),
             '--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
             '--input',','.join(inputs),'--shot-at','900,1250,1650,2000,'+','.join(str(x) for pair in shots for x in pair),
             '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
        if args.kind=='native':cmd[3:3]=['--link-local-mods',str(WORK/'common-mods/mods')]
        else:
            bundle=QA/'bundles'/(batch+'-r2')
            while not (bundle/'bundle.json').exists():print('Waiting for '+batch,flush=True);time.sleep(20)
            cmd[3:3]=['--bundle',str(bundle)]
        print('Starting '+name+' '+str(len(targets))+' model identities',flush=True)
        with (QA/'wide'/(name+'-driver.log')).open('xb') as out:
            result=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
        item={'name':name,'models':len(targets),'driver_exit':result.returncode}
        if result.returncode==0:
            report=inspect_run(name,targets,shots)
            item.update(visible=sum(x['render_status']=='captured_requires_visual_review' for x in report['targets']),
                        empty=sum(x['render_status']=='empty_body' for x in report['targets']),
                        missing=sum(x['render_status']=='missing_capture' for x in report['targets']),
                        crash_lines=report['crash_lines'])
            if not args.keep_local:
                import shutil,re
                root=WORK/'runs'/name
                assert re.fullmatch(r'pc-wide-(?:import|native)-\d{3}-r\d+',name) and root.resolve().is_relative_to((WORK/'runs').resolve()) and not root.is_symlink()
                shutil.rmtree(root)
                prepared=WORK/'prepared'/name
                if prepared.exists():
                    assert prepared.resolve().is_relative_to((WORK/'prepared').resolve()) and not prepared.is_symlink()
                    shutil.rmtree(prepared)
        state['batches'].append(item);progress.write_text(json.dumps(state,indent=1),encoding='utf-8')
        print(json.dumps(item),flush=True)

if __name__=='__main__':main()
