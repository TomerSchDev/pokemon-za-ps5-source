"""Current-input asset package and coordinated idle pre-enrollment readbacks.
Never writes to the console; installation remains in zw install-bundle."""
import argparse,hashlib,importlib.util,json,time
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[2]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def proof(p):return {'path':str(Path(p).resolve()),'sha256':sha(p)}
def load(name,path):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
ap=argparse.ArgumentParser();ap.add_argument('operation',choices=['prepare','preflight']);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--helper',type=Path);ap.add_argument('--pc-evidence',type=Path);ap.add_argument('--package',type=Path);ap.add_argument('--console-ok',action='store_true');a=ap.parse_args();out=a.out.resolve()
if a.operation=='prepare':
    if not a.helper or not a.pc_evidence:raise ValueError('Prepared helper and executed PC evidence required')
    out.mkdir(parents=True,exist_ok=False);native=read(a.helper/'native-manifest.json');review=read(native['review']['path'])
    for r in [native['review'],native['payload'],*review['sources']]:
        if sha(r['path'])!=r['sha256']:raise ValueError('Reviewed helper input changed: '+r['path'])
    tests=read(a.pc_evidence)
    if not tests['passed'] or len(tests['tests'])!=6 or not all(t['passed'] for t in tests['tests']):raise ValueError('Six executed safety cases required')
    old=read(ROOT/'evidence/hebrew-choice-console-20261101-game-local/manifest.json');all_old=old['artifacts']+[old['game']]
    state=read(ROOT.parent/'console-install-state/state.json')['payload'];base=state['baselines']['PPSA91990'];main=state['baselines']['PPSA91762']
    if main['files']['/data/homebrew/PPSA91762/eboot.bin']!=old['entry_main_sha256']:raise ValueError('Main changed; merge/rebuild outside queue')
    current=ROOT.parent/'hebrew-lab/build/hebrew-assistant-20261031-r6';candidate=read(current/'candidate.json')
    historical=ROOT/'artifacts/randomizer-r29-hebrew-rtl-20261031-r4';older=read(historical/'PACKAGE.json');legacy={r['path']:r for r in older['mods']}
    assets=[];comparisons=[]
    for row in candidate['files']:
        if not row['path'].startswith('mods/hebrew/'):raise ValueError('Unexpected current mod path')
        rel=row['path'][len('mods/hebrew/'):];source=current/row['path'];previous=legacy.get('hebrew/'+rel)
        if '..' in Path(rel).parts or not previous or previous['sha256']!=row['sha256'] or sha(source)!=row['sha256'] or sha(historical/'mods'/previous['path'])!=row['sha256']:raise ValueError('Current asset differs from installed seed: '+rel)
        assets.append({'path':str(source),'sha256':row['sha256'],'remote_path':'/data/homebrew/PPSA91990/hebrew-choice-mods/'+rel});comparisons.append({'relative':rel,'current':proof(source),'legacy_sha256':previous['sha256'],'byte_identity':'verified'})
    if len(assets)!=564 or len(assets)!=len(legacy):raise ValueError('Incomplete mod closure')
    refs={};sizes={};bases=[]
    for remote,digest in base['files'].items():
        rows=[r for r in all_old if r['remote_path']==remote]
        if len(rows)!=1 or rows[0]['sha256']!=digest or sha(rows[0]['path'])!=digest:raise ValueError('Baseline reference changed: '+remote)
        refs[remote]=proof(rows[0]['path']);sizes[remote]=Path(rows[0]['path']).stat().st_size;bases.append({'remote_path':remote,'sha256':digest})
    helper={'path':native['payload']['path'],'sha256':native['payload']['sha256'],'remote_path':'/data/homebrew/PPSA91990/relocate-side-mods.elf'}
    required=[r for r in all_old if r['remote_path'].endswith(('/eboot.bin','/sce_sys/param.json'))]
    # Review closes before any bundle generation. No game compile/save generation.
    check={'schema_version':1,'status':'READY_FOR_SCOPED_BUILD','allowed_to_start':True,'checked_at_utc':datetime.now(timezone.utc).isoformat(),'operation':'Generate this isolated immutable-asset bundle only','mapping_snapshot':proof(ROOT/'docs/testing/BUILD_DEPENDENCY_MAP.json'),'recipe':proof(__file__),'helper_review':proof(native['review']['path']),'helper_source':review['sources'],'pc_evidence':proof(a.pc_evidence),'current_authority':proof(current/'candidate.json'),'historical_reference':proof(historical/'PACKAGE.json'),'current_mod_comparisons':comparisons,'baseline_control':{'title':'PPSA91990','files':bases,'role':'existing immutable installed baseline, not a new game build input'},'main_preserved':main['files'],'source_roles':'Upload only current r6 files; compare older r4-named package solely to prove seed identity. Keep exact existing e082 binary and its36b3 JSON fix. No old worktree/bytecode imported.','scoped_dependencies':{'nodes':['current-r6-candidate','current-r6-assets','reviewed-native-helper','existing-side-baseline','canonical-package-recipe'],'edges':[['current-r6-candidate','current-r6-assets'],['reviewed-native-helper','helper_review'],['canonical-package-recipe','current-r6-assets'],['canonical-package-recipe','existing-side-baseline'],['canonical-package-recipe','reviewed-native-helper']]},'final_candidate_validation':'NOT_RUN','blocking_conditions':[]}
    write(out/'package-input-check.json',check)
    job={'console':'192.168.1.135','title_id':'PPSA91990','name':'Prepared current read-only Hebrew assets and exact choice-fix console QA','deployment':{'mode':'side_app','base_sizes':sizes,'base_reference_files':refs},'artifacts':required+assets+[helper],'expected_base':bases,'notes':'Current-input reviews and564 current r6 assets verified against original seed; prepared native migration and six PC safety cases passed. Install immediately via install-bundle with readback/rollback. Launch isolated side at native menu, migrate verified immutable copies, preserve rando/save progress and verify128MiB free, close/relaunch, continue copied run and inspect actual lab elevator, bag/party/map/dialogue. Stop on mismatch/fault; exact owned PID/session cleanup and generic crash helper r6 ready. Main/vanilla untouched; local journals then NAS after turn. No unexecuted UI test passes.'}
    write(out/'job.json',job);manifest={**old,'artifacts':all_old+assets+[helper],'current_input_review':proof(out/'package-input-check.json'),'readonly_mod_files':564,'new_helper':helper,'previous_side_baseline':base,'write_scope':'Only own immutable Hebrew copies move to app0; rando/save never restored or overwritten'};write(out/'manifest.json',manifest)
    write(out/'handoff.json',{'name':'Isolated e082 Hebrew candidate with current read-only r6 assets; UI QA pending','preserved_features':base['preserved_features']+['Protected main/vanilla unchanged; newer side save retained','Current r6 bytes verified; all side immutable files and rollback retained'],'rebuild_instructions':'Helper review '+str(a.helper)+' and package-input-check.json close the current inputs. Install only through install-bundle. Migration compares every old/new mod against the seed before unlink; skips all rando/save. Retain old empty directory as metadata. No main promotion before real regression evidence.','manifest':proof(out/'manifest.json')})
    print(json.dumps({'package':str(out),'artifacts':len(job['artifacts']),'baseline_files':len(bases),'current_mod_bytes_verified':len(assets),'console_access':False}))
else:
    if not a.console_ok or not a.package:raise ValueError('Coordinated --console-ok and prepared package required')
    q=load('storage_preflight_queue',ROOT/'tools/console-install-queue/console_queue.py');board=q.Board()
    class Preparation:
        last=float('-inf')
        def check(self):
            now=time.monotonic()
            if now-self.last<.1:return
            state=board.load()
            if state.get('active') or any(r['state']=='queued' for r in state['jobs']):raise RuntimeError('Another console participant appeared; stop preparatory reads')
            self.last=now
    lease=Preparation();lease.check();m=load('storage_preflight_helpers',ROOT/'port/main-install/install-main.py');job=q.normalized_job(a.package/'job.json');q.install_policy(job,a.package)
    out.mkdir(parents=True,exist_ok=False);refs=job['deployment']['base_reference_files'];records=[];c=m.api.Console()
    try:
        if m.api.eboot_processes():raise RuntimeError('Game active; no preparatory readbacks')
        for row in job['expected_base']:
            lease.check();r=m.m.compare_readback(c,row['remote_path'],q.local_path(refs[row['remote_path']]['path']),lease)
            if r['sha256']!=row['sha256']:raise RuntimeError('Live side baseline changed')
            write(out/('readback-%04d.json'%len(records)),r);records.append({'remote_path':row['remote_path'],'sha256':r['sha256'],'evidence':proof(r['path'])})
        main=m.m.bounded_file(c,m.m.EBOOT,out/'main-eboot.bin',lease)
        if main['sha256']!='36b3d5d650bd1a8171c39a788785678fa395ab5c0043d6b02a0d028946944699':raise RuntimeError('Live main changed; preserve it and rebuild outside queue')
        lease.check();closed={'at':m.api.utc_now(),'processes':m.api.eboot_processes(),'main_sha256':main['sha256'],'game_closed':True}
        if closed['processes']:raise RuntimeError('Console state changed during preparation')
        write(out/'closed-and-main.json',closed)
    finally:c.close()
    previous=read(ROOT/'evidence/hebrew-choice-console-20261101-game-local/readiness.json')
    write(out/'backup-continuity.json',{'at':m.api.utc_now(),'backup':previous['save_backup'],'basis':'Original verified full main backup remains latest: no main execution/input/save restore/write since verified backup close; only isolated side sessions. User away from TV. Continuity, not a claim of a newly copied backup.','source_handoff':proof(ROOT/'evidence/hebrew-choice-transfer-polling-20261101-r1/final-handoff-inspect/inspection.json')})
    ready={'console':'192.168.1.135','ticket':'pending','checked_at':m.api.utc_now(),'pc_validation':{'passed':True,'evidence':proof(a.package/'package-input-check.json')},'external_owner_handoff':previous['external_owner_handoff'],'game_closed':{'verified':True,'evidence':proof(out/'closed-and-main.json')},'save_backup':previous['save_backup'],'base_readbacks':records};write(out/'readiness-template.json',ready)
    print(json.dumps({'preflight_completed':str(out),'readbacks':len(records),'console_queue_claimed':False,'writes_to_console':False}))
