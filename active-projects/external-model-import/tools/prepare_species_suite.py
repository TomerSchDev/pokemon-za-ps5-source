"""Prepare explicitly resolved species inputs in a fresh workspace BEFORE FIFO enrollment.
No implicit donor/schema/PKHeX locations or inherited historical bytecode.
Guarded legacy adapter for mods/fonts; no automatic gameplay or Logic verdict.
"""
import argparse,hashlib,importlib.util,json,os,re,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
LAB=Path(__file__).resolve().parents[3]
REPO=LAB/'Pokemon-ZA-Native-Port'
RUNS=LAB/'hebrew-lab/runs'
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def write(path,value):
    path=Path(path)
    if path.exists():raise ValueError('Immutable output exists; use a new version: '+str(path))
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def reject_links(path):
    path=Path(os.path.abspath(path))
    for p in (path,*path.parents):
        if p.exists() and (p.is_symlink() or p.is_junction()):raise ValueError('Linked input/output ancestor: '+str(p))
    return path
def fresh_workspace(path):
    p=reject_links(path).resolve()
    if p.parent!=LAB or not re.fullmatch(r'pc-species-validation-fresh-[A-Za-z0-9-]+',p.name):raise ValueError('Use a declared fresh species workspace directly under the lab')
    if read(p/'RESTART.json').get('old_execution_plan_superseded') is not True:raise ValueError('Fresh restart declaration missing')
    return p
def output_path(workspace,relative):
    r=Path(relative)
    if r.is_absolute() or r.drive or '..' in r.parts:raise ValueError('Output must be a relative descendant')
    p=reject_links(workspace/r).resolve()
    if not p.is_relative_to(workspace) or p==workspace:raise ValueError('Output escapes fresh workspace')
    return p
def current_input(path):
    p=reject_links(path).resolve()
    if not p.is_file():raise ValueError('Missing current input: '+str(p))
    for parent in p.parents:
        if parent.name=='pc-fifty-20261031-r1' or parent.name.startswith('prepared-suite-20261101-r1'):raise ValueError('Retired execution path is not a current input: '+str(p))
        if parent.parent==LAB and any(parent.glob('RETIRED-*.json')):raise ValueError('Retired input root: '+str(parent))
    if p.suffix=='.pyc':raise ValueError('Explicit historical bytecode is forbidden')
    return p
def row(p):
    p=current_input(p);before=p.stat();digest=sha(p);after=p.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):raise ValueError('Input changed while hashing')
    return dict(path=str(p),sha256=digest,bytes=after.st_size,mtime_ns=after.st_mtime_ns)
def check_inputs(path,workspace):
    check=read(path)
    if check.get('status')!='READY_FOR_SCOPED_BUILD' or check.get('allowed_to_start') is not True or check.get('blockers'):raise ValueError('Current-input check is blocked')
    if Path(check['workspace']).resolve()!=workspace:raise ValueError('Input-check workspace differs')
    if sha(REPO/'docs/testing/BUILD_DEPENDENCY_MAP.json')!=check['map_sha256']:raise ValueError('Dependency map changed; refresh before preparation')
    descriptor=check['dependency_supplement']
    if sha(descriptor['path'])!=descriptor['sha256']:raise ValueError('Input dependency supplement changed')
    mapped={str(Path(r['path']).resolve()) for r in read(descriptor['path'])['nodes'] if r.get('path')}
    if not check.get('files'):raise ValueError('Empty current input closure')
    for item in check['files']:
        p=current_input(item['path'])
        if str(p) not in mapped:raise ValueError('Unmapped input: '+str(p))
        if not item.get('approved_current') or not item.get('authority') or item.get('current_counterpart')!=str(p):raise ValueError('Current authority unresolved: '+str(p))
        if sha(p)!=item['sha256']:raise ValueError('Input SHA drift: '+str(p))
    return check
def command(args):
    result=subprocess.run([sys.executable,'-I','-B',str(REPO/'workbench/zw.py'),*args],cwd=REPO,capture_output=True,text=True,encoding='utf-8',errors='replace')
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    return json.loads(result.stdout)
def config(path,workspace):
    data=read(path)
    if data.get('schema_version')!=3:raise ValueError('Explicit version-3 species recipe required')
    check=check_inputs(data['input_check'],workspace);pins={str(Path(i['path']).resolve()):i for i in check['files']}
    def pinned(p):
        p=current_input(p)
        if str(p) not in pins:raise ValueError('Recipe input absent from closure: '+str(p))
        return p
    for key in ('game_dll','game_romfs','runtime_exe','font','control_source','runner_source'):pinned(data[key])
    pinned(Path(data['tools_root'])/'compiled-tools.json')
    if Path(data['runner_source']).resolve()!=LAB/'hebrew-lab/tools/run_poc.py':raise ValueError('Use the canonical current runner')
    for case in data['cases']:
        if not re.fullmatch('[a-z0-9-]+',case['id']):raise ValueError('Unsafe case ID')
        if not re.fullmatch('pc-fifty-fresh-[a-z0-9-]+',case['run_name']):raise ValueError('Fresh run prefix required')
        pinned(case['fixture_save'])
        if not all(case.get(k) for k in ('species','evolved_species','initial_level')):raise ValueError('Explicit family identities/level required')
        if not case.get('payloads') or not case.get('phases'):raise ValueError('Complete resolved payload and phases required')
        for payload in case['payloads']:pinned(payload['source']);output_path(workspace,payload['destination'])
        for phase in case['phases']:
            if not all(phase.get(k) for k in ('id','precondition','actions','assertions','on_failure')):raise ValueError('Unprepared phase')
        if not {'field','attack','evolution','evolved-attack'}<={p['id'] for p in case['phases']}:raise ValueError('Whole family recipe required before enrollment')
    return data,check
def models(data,workspace):
    copied=[]
    for case in data['cases']:
        for payload in case['payloads']:
            source=current_input(payload['source']);dest=output_path(workspace,payload['destination'])
            if dest.exists():
                if sha(dest)!=sha(source):raise ValueError('Different immutable payload already exists')
            else:dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            if sha(dest)!=sha(source):raise ValueError('Payload copy mismatch')
            copied.append(row(dest))
    write(workspace/'suite-payloads.json',dict(files=copied,game_launched=False))
    return dict(payloads=len(copied),game_launched=False)
def stage(data,check,workspace):
    spec=importlib.util.spec_from_file_location('current_species_runner',data['runner_source'])
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    for case in data['cases']:
        case_root=output_path(workspace,'cases/'+case['id']);case_root.mkdir(parents=True,exist_ok=True)
        inspection=command(['species-save','Inspect-PreparedSpeciesFixture','-ToolsRoot',data['tools_root'],'-SourceSave',case['fixture_save'],'-ExpectedNational',str(case['species']),'-ExpectedLevel',str(case['initial_level'])])
        if not inspection['party'][0]['ChecksumValid']:raise ValueError('Invalid primary fixture')
        write(case_root/'compiled-inspection.json',inspection)
        fixture=output_path(workspace,'cases/'+case['id']+'/fixture/save_0/main');fixture.parent.mkdir(parents=True,exist_ok=True)
        if fixture.exists():raise ValueError('Use a fresh single-use case version')
        shutil.copy2(case['fixture_save'],fixture)
        mods=output_path(workspace,case['mods_relative'])
        payloads=[output_path(workspace,p['destination']) for p in case['payloads']]
        if not mods.is_dir() or any(not p.is_file() or not p.is_relative_to(mods) for p in payloads):raise ValueError('Resolved model payloads are not staged under mods')
        files={Path(r['path']).resolve():row(r['path']) for r in check['files']}
        for p in payloads+[fixture,Path(__file__)]:files[p.resolve()]=row(p)
        router=REPO/'workbench/zw.py'
        entries=list(files.values())+[dict(kind='canonical_router',path=str(router),scope_sha256=runner.canonical_router_scope(router))]
        manifest=case_root/'artifact-manifest.json';write(manifest,dict(version=3,files=entries))
        seconds=int(case['budget_seconds'])
        if not 60<=seconds<=275:raise ValueError('Case budget must leave FIFO cleanup margin')
        name=case['run_name'];game=Path(data['game_dll']).parent
        args=['pc','run',name,'--seconds',str(seconds),'--game',str(game),'--stage-only','--artifact-manifest',str(manifest),'--save-src',str(fixture.parents[1]),'--mods',str(mods),'--junction-mods','--font',data['font'],'--input','240:A:8,420:A:8','--shot-at','600,1200,1800,2400,3000,3600,4200,4800,5400,6000']
        command(args)
        staged=RUNS/name/'staged-run.json';pin=sha(staged)
        common=['pc','run',name,'--seconds',str(seconds),'--game',str(game),'--staged-sha256',pin]
        verified=command(common+['--verify-staged'])
        if not verified['staged_verified']:raise ValueError('Literal sealed verification failed')
        write(case_root/'sealed-job.json',dict(schema_version=3,name=name,owner_agent=case['owner_agent'],prepared_utc=datetime.now(timezone.utc).isoformat(),staged=str(staged),staged_sha256=pin,input_check=data['input_check'],artifact_manifest=str(manifest),artifact_manifest_sha256=sha(manifest),verify=common+['--verify-staged'],launch=common+['--from-staged'],phases=case['phases'],assertions=case['assertions'],budget_seconds=seconds,timeout_seconds=seconds+25,stop_cleanup='Canonical heartbeat20s; own child stop at FIFO margin; verify exit, release with evidence, archive NAS after turn; no rebuild while queued',fallback='Guarded canonical legacy runner: structured v1 cannot accept prepared mods and explicit font',runtime_status='NOT_RUN',automatic_gameplay_pass=False,all_preparation_complete=True))
    return dict(staged_cases=len(data['cases']),game_launched=False)
def readiness(workspace,case_id,enroll=False):
    root=output_path(workspace,'cases/'+case_id);jobpath=root/'sealed-job.json';job=read(jobpath)
    if (root/'enrollment.json').exists():raise ValueError('Exact case already enrolled; do not duplicate')
    check_inputs(job['input_check'],workspace)
    if sha(job['staged'])!=job['staged_sha256']:raise ValueError('Sealed staged recipe changed')
    if sha(job['artifact_manifest'])!=job['artifact_manifest_sha256']:raise ValueError('Artifact manifest changed')
    verified=command(job['verify']);capacity=command(['test','capacity'])
    receipt=dict(ready=bool(verified['staged_verified'] and capacity['ready']),job_sha256=sha(jobpath),capacity=capacity,game_launched=False)
    if enroll:
        if not receipt['ready']:raise ValueError('Capacity unavailable; no speculative enrollment')
        request='fresh-'+case_id+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        queued=root/'queue-job.json';write(queued,dict(name=request,notes=job['fallback'],recipe=str(jobpath),recipe_sha256=sha(jobpath),readiness=receipt))
        receipt['queue']=command(['pc-queue','enqueue','--agent',job['owner_agent'],'--request-id',request,'--job',str(queued)])
        write(root/'enrollment.json',receipt)
    return receipt
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('check','models','stage','ready','enqueue'))
    p.add_argument('--workspace',required=True,type=Path);p.add_argument('--config',type=Path);p.add_argument('--case');a=p.parse_args()
    workspace=fresh_workspace(a.workspace)
    if a.action in ('ready','enqueue'):
        if not a.case or not re.fullmatch('[a-z0-9-]+',a.case):p.error('Explicit safe case required')
        result=readiness(workspace,a.case,a.action=='enqueue')
    else:
        if not a.config:p.error('Explicit current-input config required')
        data,check=config(a.config,workspace)
        result={'check':lambda:dict(checked=True,cases=len(data['cases']),game_launched=False),'models':lambda:models(data,workspace),'stage':lambda:stage(data,check,workspace)}[a.action]()
    print(json.dumps(result,ensure_ascii=True),flush=True)
if __name__=='__main__':main()
