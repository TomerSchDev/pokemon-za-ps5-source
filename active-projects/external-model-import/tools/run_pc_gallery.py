"""Bounded PC-only box gallery; isolated Test saves and verified NAS evidence."""
from pathlib import Path
import argparse, json, subprocess, sys, time, re, hashlib, shutil
from storage_paths import data_root

ROOT=data_root(); QA=ROOT/'qa/all-pokemon-20261030-r2'
WORK=Path(__file__).resolve().parents[3]/'pc-model-tests'
sys.path.insert(0,str(ROOT/'qa/python-lib'))
from PIL import Image,ImageChops,ImageDraw
from pc_body_panel import load_empty_panels,pixels_from_empty,BODY_BOX

def inspect_run(name, targets, shots):
    run=ROOT/'qa/runs'/name
    record=json.loads((run/'run.json').read_text(encoding='utf-8'))
    species_names=json.loads((QA/'species-names.json').read_text(encoding='utf-8')) if (QA/'species-names.json').exists() else []
    log=(run/'stderr.log').read_text(encoding='utf-8',errors='replace')
    reference=Image.open(ROOT/'qa/runs/pc-box-calibration-r28/build/frames/frame_02403.png').convert('RGB')
    header_box=(140,40,445,86)
    reference_mask=reference.crop(header_box).convert('L').point(lambda x:255 if x>220 else 0)
    empty=load_empty_panels(ROOT/'qa/runs')
    rows=[]; sheet=Image.new('RGB',(1920,((len(targets)+5)//6)*340),'#182236')
    draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(targets):
        pair=[run/'build/frames'/('frame_%05d.png'%f) for f in shots[i]]
        row=dict(t,run=name,frames=shots[i],combat_status='not_tested',evolution_status='not_tested')
        row['expected_name']=species_names[t['national']] if t['national']<len(species_names) else t['key']
        row['model_resource_requested']=('ik_pokemon/data/'+t['model_path']) in log
        if all(p.exists() for p in pair):
            pictures=[Image.open(p).convert('RGB') for p in pair]
            a=pictures[0]
            header=a.crop(header_box).convert('L').point(lambda x:255 if x>220 else 0)
            row['summary_header_matches']=ImageChops.difference(reference_mask,header).histogram()[0]/(305*46)>.98
            # Body-only region: exclude names, UI pulses, trainer panel, and icons.
            deltas=[]
            for frame,b in zip(shots[i][1:],pictures[1:]):
                diff=ImageChops.difference(a.crop(BODY_BOX),b.crop(BODY_BOX)).convert('L')
                deltas.append({'frame':frame,'pixels_gt10':sum(n for k,n in enumerate(diff.histogram()) if k>10)})
            row['body_delta_samples']=deltas
            row['body_pixels_changed_gt10']=max(item['pixels_gt10'] for item in deltas)
            row['pixels_different_from_empty_panel']=pixels_from_empty(a.crop(BODY_BOX),empty)
            row['empty_panel_detector']='two_verified_templates_v2'
            row['render_status']='captured_requires_visual_review' if row['summary_header_matches'] else 'wrong_screen_requires_review'
            if row['summary_header_matches'] and row['pixels_different_from_empty_panel']<500:row['render_status']='empty_body'
            row['animation_status']='motion_detected' if row['body_pixels_changed_gt10']>100 else 'no_motion_detected_requires_review'
            tile=a.crop((220,300,970,970));tile.thumbnail((320,255))
            x,y=(i%6)*320,(i//6)*340;sheet.paste(tile,(x,y+75))
            title=a.crop((220,210,855,294));title.thumbnail((320,43));sheet.paste(title,(x,y+30))
            draw.text((x+5,y+4),t['key']+' '+row['expected_name'],fill='white')
            draw.text((x+5,y+18),'delta='+str(row['body_pixels_changed_gt10']),fill='white')
        else:
            row['render_status']='missing_capture';row['animation_status']='not_tested'
        rows.append(row)
    report=dict(run=name,crash_lines=record.get('crash_lines',[]),targets=rows)
    (run/'gallery-results.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
    sheet.save(run/'gallery-contact-sheet.jpg',quality=90)
    for i,top in enumerate(range(0,sheet.height,1700),1):
        sheet.crop((0,top,1920,min(top+1700,sheet.height))).save(run/('gallery-box-%02d.jpg'%i),quality=90)
    return report

def clean_owned_run(name):
    # Evidence was copied and content-checked by run_pc_nas before this call.
    for parent in ('runs','prepared'):
        target=WORK/parent/name
        assert re.fullmatch(r'pc-gallery-\d{3}-r\d+',name)
        assert target.resolve().is_relative_to((WORK/parent).resolve())
        if target.exists():
            assert not target.is_symlink()
            shutil.rmtree(target)

def main():
    p=argparse.ArgumentParser();p.add_argument('--start',type=int,default=1);p.add_argument('--end',type=int,default=49)
    p.add_argument('--revision',type=int,default=1);p.add_argument('--keep-local',action='store_true');args=p.parse_args()
    statefile=QA/'gallery'/('progress-r%d.json'%args.revision)
    state={'PC_only':True,'total_models':1468,'completed_batches':[],'failed_batches':[]}
    if statefile.exists():state=json.loads(statefile.read_text(encoding='utf-8'))
    for number in range(args.start,args.end+1):
        batch='gallery-%03d'%number;name='pc-'+batch+'-r%d'%args.revision
        if any(x['name']==name for x in state['completed_batches']):continue
        spec=QA/'gallery'/(batch+'.json');targets=json.loads(spec.read_text(encoding='utf-8'))['targets']
        bundle=QA/'bundles'/(batch+'-r2')
        while not (bundle/'bundle.json').exists():
            print('Waiting for NAS bundle '+batch,flush=True);time.sleep(20)
        inputs=['240:A:8','420:A:8','1200:X:8','1450:A:8','1800:A:8','1950:A:8','2100:DOWN:8','2250:A:8']
        # The two observations intentionally differ by 37, avoiding common 30/50/60-frame loops.
        shots=[]
        for i in range(len(targets)):
            base=2403+i*100
            shots.append((base,base+37))
            if i:inputs.append('%d:R:8'%(base-50))
        budget=int((shots[-1][-1]+100)/27)+45
        cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,
             '--bundle',str(bundle),'--seconds',str(budget),'--save-src',str(QA/'gallery'/batch),
             '--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
             '--input',','.join(inputs),'--shot-at',','.join(str(f) for pair in shots for f in pair),
             '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
        print('Starting '+name+' '+str(len(targets))+' models',flush=True)
        transcript=QA/'gallery'/(name+'-driver.log')
        with transcript.open('xb') as out:result=subprocess.run(cmd,stdout=out,stderr=subprocess.STDOUT)
        if result.returncode!=0:
            state['failed_batches'].append({'name':name,'driver_exit':result.returncode})
        else:
            report=inspect_run(name,targets,shots)
            state['completed_batches'].append({'name':name,'captured':sum(t['render_status']=='captured_requires_visual_review' for t in report['targets']),
                'models':len(targets),'crash_lines':report['crash_lines']})
            if not args.keep_local:clean_owned_run(name)
        statefile.write_text(json.dumps(state,indent=1),encoding='utf-8')
        print(json.dumps(state['completed_batches'][-1:] or state['failed_batches'][-1:]),flush=True)

if __name__=='__main__':main()
