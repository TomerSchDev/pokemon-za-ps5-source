"""Test imported form bodies hidden by Summary normalization, with a QA-only catalogue.

This forces resource selection in isolated Test profiles. It does not implement
form transitions or alter the original build, saves, or console installation.
"""
from pathlib import Path
import argparse,copy,hashlib,json,subprocess,sys,time
from run_pc_gallery import ROOT,QA,WORK,inspect_run
from run_pc_wide import plan
from run_pc_final_retests import PWSH,LINUX_QA
from collect_pc_model_results import collect
from catalog_inventory import Z
from build_smoliv_model import encode_checked

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--early',action='store_true');parser.add_argument('--revision',type=int,default=1);parser.add_argument('--after-early-revision',type=int);args=parser.parse_args()
    marker='retests/material-pilot-r1-results.json' if args.early else 'retests/final-retests-r1-results.json'
    while not (QA/marker).exists():time.sleep(10)
    if args.after_early_revision:
        while not (QA/('exact-form-early-r%d/results.json'%args.after_early_revision)).exists():time.sleep(10)
    overview=collect()
    pending=[t for t in overview['targets'] if t['imported'] and t['body_visible'] and not t.get('model_resource_requested')]
    inventory={t['key']:t for t in json.loads((QA/'inventory-v4.json').read_text(encoding='utf-8'))['targets']}
    groups=[]
    for target in pending:
        group=next((g for g in groups if len(g)<90 and target['internal'] not in {x['internal'] for x in g}),None)
        if group is None:group=[];groups.append(group)
        group.append(inventory[target['key']])
    phase=('exact-form-early-r%d' if args.early else 'exact-form-probes-r%d')%args.revision
    directory=QA/phase;directory.mkdir(exist_ok=True)
    print('Exact imported-form resource probes: '+str(len(pending))+' identities in '+str(len(groups))+' groups',flush=True)
    results=[]
    for number,targets in enumerate(groups,1):
        name=('pc-exact-form-early-%03d-r%d' if args.early else 'pc-exact-form-%03d-r%d')%(number,args.revision)
        inputs,pairs=plan(len(targets));shots=[(a,a+19,b) for a,b in pairs]
        spec=directory/(name+'.json');assert not spec.exists()
        spec.write_text(json.dumps({'targets':targets,'mode':'box','body_frame_pairs':shots,'include_sibling_asset_folders':True},indent=1),encoding='utf-8')
        save=directory/name
        fixture=[PWSH,'-NoProfile','-NonInteractive','-File',str(ROOT/'tools/bulkfixture/Run-MultiFixture.ps1'),
                 '-SourceSave',str(ROOT/'qa/saves/multi-six/save_0/main'),'-Manifest',str(spec),'-OutputSave',str(save/'save_0/main')]
        subprocess.run(fixture,check=True,capture_output=True)
        bundle=('exact-form-early-%03d-r%d' if args.early else 'exact-form-%03d-r%d')%(number,args.revision)
        ssh=['ssh','-i',r'C:\Users\Tomer\.ssh\theonepiece_codex_ed25519','-o','IdentitiesOnly=yes','-o','BatchMode=yes',
             '-o','ConnectTimeout=5','-o','StrictHostKeyChecking=yes','TomerSch@192.168.1.234','python3',
             LINUX_QA+'/build_qa_bundle.py',LINUX_QA+'/'+phase+'/'+name+'.json',bundle]
        with (directory/(name+'-bundle.log')).open('xb') as log:subprocess.run(ssh,stdout=log,stderr=subprocess.STDOUT,check=True)
        asset_name=name+'-assets'
        prepare=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),asset_name,'--bundle',str(QA/'bundles'/bundle),'--prepare-only']
        with (directory/(name+'-prepare.log')).open('xb') as log:subprocess.run(prepare,stdout=log,stderr=subprocess.STDOUT,check=True)
        sc=Z.catalog_schema();catalog=sc.decode((QA/'form-bindings-r1/romfs'/Z.CATALOG).read_bytes())
        selected={t['internal']:t for t in targets};changes=[]
        originals=copy.deepcopy(catalog['table'])
        for i,entry in enumerate(originals):
            info=entry['species_info'];species=info.get('species',0)
            if species not in selected:continue
            target=selected[species]
            desired=next(e for e in originals if tuple(e['species_info'].get(k,0) for k in ('species','form','gender'))==(species,target['form'],target['gender']))
            replacement=copy.deepcopy(desired);replacement['species_info']=copy.deepcopy(info)
            for group in ('animations','locators'):
                for ref in replacement.get(group,[]):ref['form_number']=info.get('form',0)
            assert replacement['model_path']==target['model_path']
            catalog['table'][i]=replacement
            changes.append({'lookup':info,'target_key':target['key'],'model':target['model_path']})
        payload=encode_checked(sc,catalog)
        stage=WORK/'prepared'/asset_name
        relative='mods/00-000-exact-form-probe/romfs/'+Z.CATALOG
        local=stage/relative;local.parent.mkdir(parents=True,exist_ok=True);local.write_bytes(payload)
        certificate=stage/'verified-hashes.json';hashes=json.loads(certificate.read_text(encoding='utf-8'))
        hashes[relative]=hashlib.sha256(payload).hexdigest();certificate.write_text(json.dumps(hashes),encoding='utf-8')
        (directory/(name+'-catalog-probe.json')).write_text(json.dumps({'QA_only':True,'changes':changes,'sha256':hashes[relative],'production_build_unchanged':True},indent=1),encoding='utf-8')
        cmd=[sys.executable,str(Path(__file__).with_name('run_pc_nas.py')),name,'--link-local-mods',str(stage/'mods'),
             '--seconds',str(int(shots[-1][-1]/18)+150),'--stop-after-shots','--watch-models',str(spec),
             '--save-src',str(save),'--cache-src',str(WORK/'runs/pc-native-baseline-r23/cache'),
             '--input',','.join(inputs),'--shot-at','900,1250,1650,2000,'+','.join(str(n) for triple in shots for n in triple),
             '--env','LARECOMP_PHYS_LIMIT=1','LARECOMP_LOG_FILES=1']
        print('Starting '+name+' '+str(len(targets))+' exact imported model resources',flush=True)
        with (directory/(name+'-driver.log')).open('xb') as log:subprocess.run(cmd,stdout=log,stderr=subprocess.STDOUT,check=True)
        report=inspect_run(name,targets,shots)
        for row in report['targets']:
            row['form_probe_mode']='QA catalogue forces requested body in Summary; normal form transitions not tested'
            row['requested_form_resource_loaded']=row['model_resource_requested']
        (ROOT/'qa/runs'/name/'gallery-results.json').write_text(json.dumps(report,indent=1),encoding='utf-8')
        results.extend(report['targets'])
        if not all(row['requested_form_resource_loaded'] for row in report['targets']):
            raise RuntimeError('Requested form resources were not all loaded; preserve evidence and diagnose the QA catalogue before continuing.')
    output={'targets':results,'QA_only':True,'production_build_unchanged':True,'console_untouched':True}
    (directory/'results.json').write_text(json.dumps(output,indent=1),encoding='utf-8')
    print('Exact imported form resource probes complete: '+str(len(results)),flush=True)

if __name__=='__main__':main()
