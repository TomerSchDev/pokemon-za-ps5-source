"""Publish compact evidence after PC-only QA and removal of the heavy local cache."""
from datetime import datetime,timezone
from pathlib import Path
import hashlib,json,shutil
from collect_pc_model_results import collect
from run_pc_gallery import ROOT,QA,WORK,Image,ImageDraw
from storage_paths import NAS

def read(path):return json.loads(path.read_text(encoding='utf-8'))

def main():
    assert (QA/'retests/final-retests-r1-results.json').exists()
    assert (QA/'exact-form-probes-r1/results.json').exists()
    overview=collect()
    assert overview['counts']['all']['observed']==1465,'All planned bodies must have an actual observation.'
    review=read(QA/'wide/visual-review-r1.json')
    assert set(review['reviewed_import_batches'])==set(range(1,11)),'Finish visual inspection of all imported batches first.'
    assert not WORK.exists(),'Remove the owned heavy PC cache before claiming cleanup.'
    directory=Path(__file__).resolve().parents[3]/'pc-check-results';directory.mkdir(exist_ok=True)
    cleanup=sorted(directory.glob('temporary-cache-cleanup-*.json'))
    assert cleanup,'Missing measured temporary-cache cleanup record.'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    targets={t['key']:t for t in overview['targets']}
    chosen=['0205-00-0','0442-00-0','0125-00-0','0722-00-0','0045-00-1','0964-01-0']
    sheet=Image.new('RGB',(1920,800),'#182236');draw=ImageDraw.Draw(sheet)
    draw.text((15,10),'Actual PC game captures: model rendering and idle-motion screening. Combat and evolution are not verified.',fill='white')
    evidence=[]
    for i,key in enumerate(chosen):
        target=targets[key];assert target['body_visible']
        if target.get('form_probe_mode'):assert target['model_resource_requested']
        x,y=(i%3)*640,40+(i//3)*380
        draw.text((x+8,y),key+' '+target['expected_name'],fill='white')
        frames=target['frames'];selected=[frames[0],frames[-1]]
        for j,number in enumerate(selected):
            source=ROOT/'qa/runs'/target['run']/'build/frames'/('frame_%05d.png'%number)
            with Image.open(source) as original:
                picture=original.convert('RGB');body=picture.crop((220,300,970,970));body.thumbnail((312,320))
                sheet.paste(body,(x+8+j*320,y+40))
            draw.text((x+8+j*320,y+22),'frame '+str(number),fill='#b3c5df')
            evidence.append({'key':key,'run':target['run'],'frame':number,'source':str(source)})
        if target.get('form_probe_mode'):draw.text((x+8,y+365),'Isolated QA form-resource override; gameplay transition is not verified.',fill='#b3c5df')
    picture=directory/('pc-model-examples-'+stamp+'.jpg');sheet.save(picture,quality=92)
    overview['manual_visual_review']=review
    overview['coverage_exclusions']=read(QA/'wide/coverage-exclusions-r1.json')
    overview['cache_cleanup']=read(cleanup[-1])
    overview['material_binding_audit']=read(QA/'material-name-repairs-r1/material-bindings-audit.json')
    overview['transparency_repairs']=read(QA/'transparency-repairs-r1/transparency-repairs.json')
    overview['exact_form_resource_probes']=read(QA/'exact-form-probes-r1/results.json')
    early_results=sorted(QA.glob('exact-form-early-r*/results.json'))
    early_targets={row['key']:row for path in early_results for row in read(path)['targets'] if row.get('requested_form_resource_loaded')}
    overview['exact_form_resource_probes']['targets']=list(early_targets.values())+overview['exact_form_resource_probes']['targets']
    overview['dependency_audit_summary']=read(QA/'effective-model-dependency-audit-r2.json')
    overview['examples']=evidence
    overview['requested_imported_resource_observed']=sum(t['imported'] and t['body_visible'] and t.get('model_resource_requested',False) for t in overview['targets'])
    overview['console_tested_or_deployed']=False
    overview['production_build_status']='Original release build unchanged. Repairs and exact-form resource probes are isolated PC QA overlays on the NAS.'
    report=directory/('pc-model-checks-'+stamp+'.json');report.write_text(json.dumps(overview,indent=1,ensure_ascii=False),encoding='utf-8')
    (QA/'wide/runtime-overview-r1.json').write_text(json.dumps(overview,indent=1),encoding='utf-8')
    destination=NAS.parent/'PC-Checks-20261031';destination.mkdir(exist_ok=True)
    copied=[]
    for source in (report,picture):
        target=destination/source.name
        assert not target.exists()
        shutil.copyfile(source,target)
        assert hashlib.sha256(source.read_bytes()).digest()==hashlib.sha256(target.read_bytes()).digest()
        copied.append(str(target))
    print(json.dumps({'local':[str(report),str(picture)],'NAS':copied,'counts':overview['counts'],'requested_imported_resources':overview['requested_imported_resource_observed']},ensure_ascii=True),flush=True)

if __name__=='__main__':main()
