"""Correct prior gallery classifications using visually confirmed empty variants."""
import json,collections,shutil
from run_pc_gallery import ROOT,QA,Image
from pc_body_panel import load_empty_panels,pixels_from_empty,BODY_BOX

def save_versioned(path,value):
    backup=path.with_name(path.stem+'.before-empty-detector-v2.json')
    if not backup.exists():shutil.copyfile(path,backup)
    path.write_text(json.dumps(value,indent=1),encoding='utf-8')

def main():
    panels=load_empty_panels(ROOT/'qa/runs');lookup={};changes=[]
    for path in sorted((ROOT/'qa/runs').glob('pc-*/gallery-results.json')):
        report=json.loads(path.read_text(encoding='utf-8'));changed=False
        for row in report['targets']:
            if row.get('summary_header_matches') and row.get('pixels_different_from_empty_panel',999999)<5000:
                frame=path.parent/'build/frames'/('frame_%05d.png'%row['frames'][0])
                with Image.open(frame) as image:
                    count=pixels_from_empty(image.convert('RGB').crop(BODY_BOX),panels)
                row['pixels_different_from_empty_panel']=count
                row['empty_panel_detector']='two_verified_templates_v2';changed=True
                if count<500 and row['render_status']=='captured_requires_visual_review':
                    row['render_status']='empty_body';changes.append([row['run'],row['key']])
            lookup[(row['run'],row['key'])]=row
        if changed:save_versioned(path,report)
    for path in sorted((QA/'wide').glob('pc-wide-*-results.json')):
        report=json.loads(path.read_text(encoding='utf-8'));changed=False
        for i,row in enumerate(report['targets']):
            newer=lookup.get((row['run'],row['key']))
            if newer and newer.get('empty_panel_detector')=='two_verified_templates_v2':
                report['targets'][i]=newer;changed=True
        if changed:
            report['counts']=dict(collections.Counter(x['render_status'] for x in report['targets']))
            report['classification_note']='Earlier one-template empty detection superseded; empty bodies require fresh isolated retry.'
            save_versioned(path,report)
    print(json.dumps({'newly_identified_empty_bodies':len(changes),'changes':changes}))

if __name__=='__main__':main()
