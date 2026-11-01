"""Prepare/validate a scoped performance release; only --publish writes ZIPs/NAS.

Required final-result binding: selected_artifact_sha256, artifact_sha256,
eboot_sha256, artifact.sha256, or selected_artifact.sha256 must match the explicit
--expected-sha. Every present binding must agree. Configuration is explicit via
repeatable --config NAME=PATH. No profile default or winning result is invented.

Example (run only after the parent finalizes the selected binary and summary):
  python package_result.py --artifact PATH/eboot.bin --expected-sha SHA256 \
    --result final-result.json --summary Summary-HE.txt --label r21b \
    --config submission-options.txt=PATH/submission-options.txt --publish

Without --publish this only validates inputs and prints the planned file list.
It does not create delivery files, connect to the console, or access the NAS.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
TITLE = 'PPSA91762'
NAS_ROOT = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')
SOURCE_ROOTS = (
    'port/preparation-r21', 'port/preparation-r21b', 'port/preparation-r21c', 'port/preparation-r21-observer', 'port/preparation-r21-hardware',
    'port/immutable-spans-r22', 'port/immutable-spans-r22-integration', 'port/submission-r20b', 'port/submission-r20-hardware',
    'port/slot-depth-r23', 'port/slot-depth-r23-observer',
    'port/slot-depth-r23b', 'port/slot-depth-r23b-observer',
    'port/slot-depth-r23c', 'port/slot-depth-r23c-observer',
    'port/observer-r17', 'research_notes/repeated-preparation-r20b',
    'research_notes/ps5-resource-fit-r21', 'evidence/preparation-r21-review',
    'evidence/preparation-r21b-review', 'evidence/preparation-r21c-review', 'evidence/immutable-spans-r22-review',
    'evidence/immutable-spans-r22-integration', 'evidence/immutable-spans-r22-integration-review',
    'evidence/slot-depth-r23', 'evidence/slot-depth-r23-review',
    'evidence/slot-depth-r23b', 'evidence/slot-depth-r23b-review',
    'evidence/slot-depth-r23c', 'evidence/slot-depth-r23c-review',
    'research_notes/performance-r21-r23',
)
SOURCE_FILES = ('run_r3.py',)  # inspected generic transport; anonymous FTP, no embedded credentials
EVIDENCE_ROOTS = (
    'evidence/preparation-r21-hardware', 'evidence/preparation-r21', 'evidence/preparation-r21b', 'evidence/preparation-r21c',
    'evidence/preparation-r21-observer', 'evidence/preparation-r21-review',
    'evidence/preparation-r21b-review', 'evidence/preparation-r21c-review', 'evidence/immutable-spans-r22', 'evidence/immutable-spans-r22-review',
    'evidence/immutable-spans-r22-integration', 'evidence/immutable-spans-r22-integration-review',
    'evidence/slot-depth-r23', 'evidence/slot-depth-r23-observer', 'evidence/slot-depth-r23-review',
    'evidence/slot-depth-r23-driver-submit',
    'evidence/slot-depth-r23b', 'evidence/slot-depth-r23b-observer', 'evidence/slot-depth-r23b-review',
    'evidence/slot-depth-r23c', 'evidence/slot-depth-r23c-observer', 'evidence/slot-depth-r23c-review',
)
RUNTIME_READY = {
    'r20b':'evidence/submission-r20b/ready.json',
    'r21':'evidence/preparation-r21/ready.json',
    'r21b':'evidence/preparation-r21b/ready.json',
    'r21c':'evidence/preparation-r21c/ready.json',
    'r22':'evidence/immutable-spans-r22-integration/ready.json',
    'r23':'evidence/slot-depth-r23/ready.json',
    'r23b':'evidence/slot-depth-r23b/ready.json',
    'r23c':'evidence/slot-depth-r23c/ready.json',
}
SOURCE_EXT = {'.c','.h','.inc','.py','.sh','.md','.txt','.patch','.mk','.json'}
EVIDENCE_EXT = {'.json','.csv','.txt','.log','.md','.sha256'}
CONFIG_NAMES = {
    'submission-options.txt','performance-options.txt','performance-profile.txt',
    'local-shader-options.txt','preparation-options.txt','observer-enable.txt',
    'slot-depth-options.txt',
}
BLOCK_DIRS = {
    '.git','.ssh','node_modules','__pycache__','deps','dependencies','third_party',
    'romfs','dlc','saves','save-backups','backups','cache','caches','shader-cache',
    'shader-caches','sdk','compiler','driver','drivers','keys','credentials',
    'build','artifacts','generated','tb1-generated','apply-check','objects','binaries',
}
LOG_MARKERS = (
    '[vk]', '[za-', '[shader-local]', '[shaderc-cache]', '[hitch]',
    '[xfb]', 'radv/ps5 submissions:', '[nvn]', '[r22-', '[r21-',
)
SAFE_FULL_LOGS = {'tests.log','client-tests.log','host-tests.log','test.log','build.log'}
MAX_TEXT = 4 << 20
MAX_PNG = 40 << 20
MAX_SOURCE_TOTAL = 128 << 20
MAX_EVIDENCE_TOTAL = 256 << 20

def digest(path: Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1 << 20),b''): h.update(chunk)
    return h.hexdigest()

def write_json(path: Path,value) -> None:
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def safe_relative(path: Path,root: Path | None=None) -> str:
    if root is None:root=ROOT
    resolved=path.resolve(strict=True)
    try: return resolved.relative_to(root.resolve()).as_posix()
    except ValueError as exc: raise ValueError('Selected source/evidence is outside project: '+str(path)) from exc

def blocked(relative: str,source: bool) -> bool:
    parts=PurePosixPath(relative).parts
    if any(p.lower() in BLOCK_DIRS or p.lower().startswith(('backup-','baseline-backup','save-backup')) for p in parts[:-1]): return True
    if source and any(p.startswith('host-tests-') for p in parts): return True
    leaf=parts[-1].lower()
    if leaf.startswith('.') or leaf.startswith('log-capture.') or leaf.endswith(('.pid','.part')): return True
    if re.search(r'(^|[-_.])(secret|secrets|credential|credentials|password|token|private-key|signing-key)([-_.]|$)',leaf): return True
    if any(term in leaf.replace('_','-') for term in ('api-key','apikey','access-token')):return True
    if leaf in ('id_rsa','id_ed25519','known_hosts','config.json','auth.json'): return True
    if 'save' in leaf and not any(x in leaf for x in ('preserv','receipt','manifest','readme','summary')): return True
    return False

def collect_files(roots,*,source: bool,extra=()):
    selected={};skipped=[]
    for name in roots:
        folder=ROOT/name
        if not folder.is_dir():
            skipped.append({'path':name,'reason':'directory absent'});continue
        for path in sorted(folder.rglob('*')):
            if not path.is_file():continue
            relative=path.relative_to(ROOT).as_posix()
            if path.is_symlink() or blocked(relative,source):
                skipped.append({'path':relative,'reason':'excluded path'});continue
            safe_relative(path)
            if path.suffix.lower() not in (SOURCE_EXT if source else EVIDENCE_EXT):continue
            if path.stat().st_size>MAX_TEXT:
                skipped.append({'path':relative,'reason':'larger than text evidence limit'});continue
            selected[relative]=path
    for path in extra:
        relative=safe_relative(path)
        if path.is_symlink() or blocked(relative,source):raise ValueError('Disallowed explicit input: '+relative)
        if path.suffix.lower() not in (SOURCE_EXT if source else EVIDENCE_EXT):raise ValueError('Disallowed explicit input type: '+relative)
        if path.stat().st_size>MAX_TEXT:raise ValueError('Explicit text input exceeds limit: '+relative)
        selected[relative]=path
    total=sum(p.stat().st_size for p in selected.values())
    if total>(MAX_SOURCE_TOTAL if source else MAX_EVIDENCE_TOTAL):raise ValueError('Selected text set exceeds bounded archive size')
    return selected,skipped

def result_binding(result: dict,expected: str) -> None:
    if result.get('title',TITLE)!=TITLE:raise ValueError('Wrong title in final result')
    values=[result[k] for k in ('selected_artifact_sha256','artifact_sha256','eboot_sha256') if k in result]
    for key in ('artifact','selected_artifact'):
        if isinstance(result.get(key),dict) and 'sha256' in result[key]:values.append(result[key]['sha256'])
    if not values:raise ValueError('Final result must explicitly bind the selected artifact SHA-256')
    if any(not isinstance(v,str) or v.lower()!=expected for v in values):raise ValueError('Final result artifact SHA-256 disagrees with selected binary')
    for key in ('r22_installed','r23_installed','r23b_installed','r23c_installed'):
        if key in result and type(result[key]) is not bool:raise ValueError(key+' must be an explicit boolean')

def runtime_selection(result,expected):
    matches=[]
    for name,relative in RUNTIME_READY.items():
        path=ROOT/relative
        if not path.is_file():continue
        try:ready=json.loads(path.read_text(encoding='utf-8-sig'))
        except (ValueError,OSError):continue
        if not isinstance(ready,dict) or not isinstance(ready.get('eboot'),dict):continue
        if ready.get('title_id',ready.get('title'))==TITLE and ready['eboot'].get('sha256')==expected:
            matches.append({'runtime':name,'ready_path':path,'ready_sha256':digest(path)})
    if len(matches)>1:raise ValueError('Ambiguous selected runtime ready-artifact hash')
    selection=matches[0] if matches else {'runtime':'unclassified','ready_path':None,'ready_sha256':None}
    if 'selected_runtime' in result and result['selected_runtime']!=selection['runtime']:
        raise ValueError('selected_runtime differs from the selected ready-artifact hash')
    if result.get('r23b_installed',False) and selection['runtime']!='r23b':
        raise ValueError('Installed r23b label requires the selected r23b ready-artifact hash')
    if result.get('r23c_installed',False) and selection['runtime']!='r23c':
        raise ValueError('Installed r23c label requires the selected r23c ready-artifact hash')
    if result.get('r23_installed',False) and selection['runtime'] not in ('r23','r23b','r23c'):
        raise ValueError('Installed r23 label requires the selected integrated r23 ready-artifact hash')
    if result.get('r22_installed',False) and selection['runtime'] not in ('r22','r23','r23b','r23c'):
        raise ValueError('Installed r22 label requires a selected r22 or inherited-r22 r23 ready-artifact hash')
    return selection

def parse_configs(items):
    configs={}
    for item in items:
        name,separator,raw=item.partition('=')
        if not separator or name not in CONFIG_NAMES or name in configs:raise ValueError('Invalid/duplicate configuration mapping: '+item)
        path=Path(raw).resolve(strict=True)
        if not path.is_file() or path.stat().st_size>16384:raise ValueError('Configuration is not a small regular text file')
        data=path.read_bytes();data.decode('utf-8-sig')
        if b'\0' in data:raise ValueError('Configuration contains binary data')
        if name=='slot-depth-options.txt' and data not in (b'8',b'8\n',b'16',b'16\n'):
            raise ValueError('slot-depth-options.txt must be exactly 8 or 16 with optional final LF')
        configs[name]=path
    return configs

def filtered_log(path: Path) -> bytes:
    if path.name in SAFE_FULL_LOGS or 'filtered' in path.name.lower():return path.read_bytes()
    lines=path.read_text(encoding='utf-8',errors='replace').splitlines()
    return ('\n'.join(line for line in lines if any(marker in line for marker in LOG_MARKERS))+'\n').encode('utf-8')

def add_entry(z,entries,name,*,path=None,data=None):
    if name in entries or name.startswith('/') or '..' in PurePosixPath(name).parts:raise ValueError('Invalid/duplicate archive path: '+name)
    if (path is None)==(data is None):raise ValueError('Exactly one entry source is required')
    if path is not None:
        size=path.stat().st_size;sha=digest(path);z.write(path,name)
    else:
        size=len(data);sha=hashlib.sha256(data).hexdigest();z.writestr(name,data)
    entries[name]={'bytes':size,'sha256':sha}

def finish_archive(z,entries):
    z.writestr('Archive-SHA256.json',json.dumps(entries,sort_keys=True,indent=2)+'\n')

def verify_archive(path,entries,*,has_manifest=True):
    with zipfile.ZipFile(path) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC verification failed: '+str(path))
        if set(z.namelist())!=set(entries)|({'Archive-SHA256.json'} if has_manifest else set()):raise ValueError('Unexpected ZIP members')
        for name,info in entries.items():
            h=hashlib.sha256();size=0
            with z.open(name) as f:
                for chunk in iter(lambda:f.read(1 << 20),b''):h.update(chunk);size+=len(chunk)
            if h.hexdigest()!=info['sha256'] or size!=info['bytes']:raise ValueError('ZIP entry changed while packaging: '+name)

def copy_nas(local: Path):
    target=NAS_ROOT/local.name
    files=sorted(p for p in local.iterdir() if p.is_file())
    result={'path':str(target),'verified':False,'files_verified':0}
    try:
        # Existing identical files can be reused after interruption. Different
        # versions are preserved: never overwrite a mismatched destination.
        target.mkdir(parents=True,exist_ok=True)
        for path in files:
            dest=target/path.name;expected=digest(path)
            if dest.exists():
                if not dest.is_file() or digest(dest)!=expected:raise ValueError('Existing different NAS file: '+str(dest))
            else:
                temporary=target/(path.name+'.'+os.urandom(6).hex()+'.part')
                shutil.copy2(path,temporary)
                if digest(temporary)!=expected:raise ValueError('NAS temporary copy SHA mismatch: '+str(path))
                # An exclusive destination create prevents silently replacing a
                # concurrently created different version on the share.
                with dest.open('xb') as output,temporary.open('rb') as source:
                    shutil.copyfileobj(source,output,1 << 20)
                temporary.unlink()
            if digest(dest)!=expected:raise ValueError('NAS readback SHA mismatch: '+str(dest))
            result['files_verified']+=1
        result['verified']=True
    except Exception as exc:result['error']=str(exc)
    return result

def plan(args):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',args.label):raise ValueError('Label must be a short lowercase version name')
    expected=args.expected_sha.lower()
    if not re.fullmatch(r'[0-9a-f]{64}',expected):raise ValueError('Expected SHA-256 must contain 64 hex digits')
    artifact=args.artifact.resolve(strict=True)
    if not artifact.is_file() or artifact.name!='eboot.bin' or artifact.stat().st_size==0:raise ValueError('Select the actual eboot.bin file')
    if digest(artifact)!=expected:raise ValueError('Selected eboot SHA-256 mismatch')
    result_path=args.result.resolve(strict=True);summary=args.summary.resolve(strict=True)
    if result_path.stat().st_size>MAX_TEXT or summary.stat().st_size>MAX_TEXT:raise ValueError('Final result or summary too large')
    result=json.loads(result_path.read_text(encoding='utf-8-sig'))
    if not isinstance(result,dict):raise ValueError('Final result must be a JSON object')
    result_binding(result,expected)
    r22_installed=result.get('r22_installed',False)
    selection=runtime_selection(result,expected)
    summary_text=summary.read_text(encoding='utf-8-sig')
    if not summary_text.strip() or '\0' in summary_text:raise ValueError('Summary must be nonempty UTF-8 text')
    configs=parse_configs(args.config)
    if 'slot-depth-options.txt' in configs and selection['runtime'] not in ('r23b','r23c'):
        raise ValueError('slot-depth-options.txt requires the selected r23b/r23c ready-artifact hash')
    sources,source_skipped=collect_files(SOURCE_ROOTS,source=True,extra=[ROOT/name for name in SOURCE_FILES]+args.source_file)
    evidence,evidence_skipped=collect_files(EVIDENCE_ROOTS,source=False,extra=args.evidence_file)
    pngs={}
    for path in args.png:
        relative=safe_relative(path)
        if path.is_symlink() or blocked(relative,False) or path.suffix.lower()!='.png':raise ValueError('Invalid explicit PNG')
        if path.stat().st_size>MAX_PNG or path.read_bytes()[:8]!=b'\x89PNG\r\n\x1a\n':raise ValueError('PNG is too large or invalid')
        pngs[relative]=path
    return {'artifact':artifact,'expected':expected,'result_path':result_path,'summary':summary,
            'result':result,'r22_installed':r22_installed,'r23_installed':result.get('r23_installed',False),
            'r23b_installed':result.get('r23b_installed',False),
            'r23c_installed':result.get('r23c_installed',False),
            'selection':selection,'configs':configs,'sources':sources,'evidence':evidence,'pngs':pngs,
            'skipped':source_skipped+evidence_skipped}

def publish(args,p):
    now=datetime.now(timezone.utc)
    name='ZA-Performance-'+args.label+'-'+now.strftime('%Y%m%d-%H%M%SZ')
    deliverables=ROOT/'deliverables';deliverables.mkdir(exist_ok=True)
    out=deliverables/name
    if out.exists():out=deliverables/(name+'-'+os.urandom(3).hex())
    # All creation happens only after validation. A failed build is visibly
    # incomplete and is not copied to NAS.
    out.mkdir(exist_ok=False)
    (out/'INCOMPLETE.txt').write_text('Package verification has not completed.\n')
    shutil.copy2(p['summary'],out/'Summary-HE.txt')
    shutil.copy2(p['result_path'],out/'Final-result.json')
    selected=p['selection']['runtime']
    if selected in ('r23','r23b','r23c'):
        r22_status='The r22 immutable-span implementation is inherited by the selected '+selected+' binary; active mode and installation are recorded in Final-result.json.'
    elif selected=='r22':
        r22_status='Integrated r22 runtime selected; installation and active mode are recorded by the parent in Final-result.json.'
    else:
        r22_status='Integrated r22 is included as candidate source/evidence only; it is NOT INSTALLED by this release.'
    r23_status=('Integrated r23 slot-depth runtime selected; active depth and installation are recorded by the parent in Final-result.json.' if selected=='r23' else
                'The selected r23b binary inherits the r23 slot-depth runtime and adds a checked process-once startup preference; actual startup depth and installation are recorded in Final-result.json.' if selected=='r23b' else
                'The selected r23c binary inherits the unchanged r23 slot-depth runtime and uses a bounded POSIX reader for the checked process-once startup preference; actual startup depth and installation are recorded in Final-result.json.' if selected=='r23c' else
                'The r23 slot-depth integration is included as candidate source/evidence only, not as the selected runtime.')
    r23_status+=' Historical r23b startup configuration failed safely on hardware and remained at 8; its source/tests are retained as prior evidence, not proof of startup success.'
    candidate_note=('port/immutable-spans-r22 is the original standalone TB1 candidate-only source, not a separately installed runtime.\n'
                    'The complete controlled integration is port/immutable-spans-r22-integration.\n'+r22_status+'\n'
                    'Read Final-result.json for the selected off/on mode and hardware findings. Host tests alone do not establish GPU correctness or a performance gain.\n')
    note=('Update for the existing '+TITLE+' installation only. Contains the explicitly selected binary and configuration files.\n'
          'No ROMFS, game archive, saves, shader caches, compiler/driver packages, dependencies or credentials are included.\n'
          'Read Summary-HE.txt and Final-result.json for the selected runtime/profile and measured limitations.\n'
          +'Selected runtime binding: '+selected+'.\n'+r22_status+'\n'+r23_status+'\n')
    verification={'at':now.isoformat(),'title':TITLE,'label':args.label,
                  'selected_artifact':{'path':str(p['artifact']),'bytes':p['artifact'].stat().st_size,'sha256':p['expected']},
                  'explicit_configs':{n:{'bytes':f.stat().st_size,'sha256':digest(f)} for n,f in p['configs'].items()},
                  'summary_sha256':digest(p['summary']),'final_result_sha256':digest(p['result_path']),
                  'r22_installed_as_recorded':p['r22_installed'],'r22_status':r22_status,
                  'r23_installed_as_recorded':p['r23_installed'],'r23_status':r23_status,
                  'r23b_installed_as_recorded':p['r23b_installed'],
                  'r23c_installed_as_recorded':p['r23c_installed'],
                  'selected_runtime':selected,'runtime_ready_binding':{'path':str(p['selection']['ready_path']) if p['selection']['ready_path'] else None,'sha256':p['selection']['ready_sha256']},
                  'tb1_source_status':'original standalone candidate; see separate r22 integration','pngs_explicit_only':True,
                  'skipped_files':p['skipped'],
                  'note':'Packaging verifies bytes and archive scope. It does not establish hardware correctness, installation, or FPS improvement.'}
    write_json(out/'Packaging.json',verification)
    entries={}
    with zipfile.ZipFile(out/'Update.zip','w',zipfile.ZIP_DEFLATED,compresslevel=1) as z:
        add_entry(z,entries,TITLE+'/eboot.bin',path=p['artifact'])
        for config,path in sorted(p['configs'].items()):add_entry(z,entries,TITLE+'/'+config,path=path)
        add_entry(z,entries,'UPDATE-NOTE.txt',data=note.encode('utf-8'))
    verify_archive(out/'Update.zip',entries,has_manifest=False)
    if entries[TITLE+'/eboot.bin']['sha256']!=p['expected']:raise ValueError('Archived binary differs from selected binary')
    for name,info in verification['explicit_configs'].items():
        if entries[TITLE+'/'+name]!=info:raise ValueError('Configuration changed during packaging')
    entries={}
    with zipfile.ZipFile(out/'Source.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in sorted(p['sources'].items()):add_entry(z,entries,name,path=path)
        add_entry(z,entries,'R22-SOURCE-STATUS.txt',data=candidate_note.encode())
        add_entry(z,entries,'R23-SOURCE-STATUS.txt',data=(r23_status+'\nThe original TB1 folder is historical candidate-only source; r23 inherits the separately integrated r22 implementation.\n').encode())
        add_entry(z,entries,'SOURCE-SCOPE.txt',data=(
            'Project-authored changes, patches, test sources, hardware tools and research/reviews only.\n'
            'Building requires separately held base sources and dependencies; no proprietary game/driver/compiler archives are included.\n').encode())
        finish_archive(z,entries)
    verify_archive(out/'Source.zip',entries)
    entries={}
    with zipfile.ZipFile(out/'Hardware-Evidence.zip','w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,path in sorted(p['evidence'].items()):
            if path.suffix.lower()=='.log':
                data=filtered_log(path)
                if not data.strip():continue
                # Preserve no raw klog file: archive labels make the filtering explicit.
                name=name[:-4]+'-selected.log' if path.name not in SAFE_FULL_LOGS and 'filtered' not in path.name.lower() else name
                add_entry(z,entries,name,data=data)
            else:add_entry(z,entries,name,path=path)
        for name,path in sorted(p['pngs'].items()):add_entry(z,entries,name,path=path)
        add_entry(z,entries,'Final-result.json',path=p['result_path'])
        finish_archive(z,entries)
    verify_archive(out/'Hardware-Evidence.zip',entries)
    # Revalidate the selected binary and final decision after reading all inputs.
    if digest(p['artifact'])!=p['expected'] or digest(p['result_path'])!=verification['final_result_sha256'] or digest(p['summary'])!=verification['summary_sha256']:
        raise ValueError('Selected release input changed during packaging')
    if digest(out/'Summary-HE.txt')!=verification['summary_sha256'] or digest(out/'Final-result.json')!=verification['final_result_sha256']:
        raise ValueError('Copied release decision or summary differs from selected input')
    if any(digest(p['configs'][name])!=info['sha256'] for name,info in verification['explicit_configs'].items()):
        raise ValueError('Selected configuration changed during packaging')
    if p['selection']['ready_path'] and digest(p['selection']['ready_path'])!=p['selection']['ready_sha256']:
        raise ValueError('Selected runtime ready-artifact binding changed during packaging')
    (out/'INCOMPLETE.txt').unlink()
    manifest={f.name:{'bytes':f.stat().st_size,'sha256':digest(f)} for f in sorted(out.iterdir()) if f.is_file()}
    write_json(out/'SHA256.json',manifest)
    nas=copy_nas(out)
    receipt={'at':now.isoformat(),'local':str(out),'sha_manifest_sha256':digest(out/'SHA256.json'),'nas':nas}
    receipt_path=ROOT/'port/preparation-r21-hardware'/('delivery-'+out.name+'.json')
    write_json(receipt_path,receipt)
    return receipt

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact',type=Path,required=True)
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--result',type=Path,required=True)
    parser.add_argument('--summary',type=Path,required=True)
    parser.add_argument('--label',required=True)
    parser.add_argument('--config',action='append',default=[],metavar='NAME=PATH')
    parser.add_argument('--source-file',type=Path,action='append',default=[])
    parser.add_argument('--evidence-file',type=Path,action='append',default=[])
    parser.add_argument('--png',type=Path,action='append',default=[])
    parser.add_argument('--publish',action='store_true',help='Create verified versioned archives and copy final files to the NAS')
    args=parser.parse_args();p=plan(args)
    result=publish(args,p) if args.publish else {
        'validated_only':True,'artifact_sha256':p['expected'],'config_files':sorted(p['configs']),
        'source_files':sorted(p['sources']),'evidence_files':sorted(p['evidence']),
        'explicit_pngs':sorted(p['pngs']),'skipped':p['skipped'],'nas_accessed':False}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.publish and not result['nas']['verified']:raise SystemExit(2)

if __name__=='__main__':main()
