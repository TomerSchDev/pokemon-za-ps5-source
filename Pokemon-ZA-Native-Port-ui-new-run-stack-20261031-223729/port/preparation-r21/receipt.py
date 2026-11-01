"""Gate ready.json on tests, preservation and final artifact identity. No network."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
WORK=Path('/home/tomer/ps5-za-native/preparation-r21-20261028')
EVID=ROOT/'evidence/preparation-r21'
ART=ROOT/'artifacts/randomizer-r21-preparation/PPSA91762'
def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        while b:=f.read(1<<20):h.update(b)
    return h.hexdigest()
tests=json.loads((EVID/'host-tests.json').read_text())
assert tests['passed'] and tests['candidate_exec_sha256']==sha(WORK/'source/runtime/nvn/vulkan/exec.c')
for n,h in tests['files'].items():assert sha(HERE/n)==h,n
audit=json.loads((EVID/'preservation-audit.json').read_text())
assert audit['same_dynamic_imports'] and audit['vma_instruction_and_relocation_disassembly_equal']
matches={}
for a,b in [('preparation.h','za_preparation_r21.h'),('counters.inc','za_preparation_counters_r21.inc'),('boundary.inc','za_preparation_boundary_r21.inc')]:
    h=sha(HERE/a);assert h==sha(WORK/'source/runtime/nvn/vulkan'/b),a
    matches[a]={'canonical_sha256':h,'build_source_sha256':h}
obs=ROOT/'port/preparation-r21-observer'
obsreceipts=list((ROOT/'evidence/preparation-r21-observer').glob('host-tests-*/result.json'))
obsreceipt=max(obsreceipts,key=lambda p:p.stat().st_mtime)
r=json.loads(obsreceipt.read_text());assert r['observer_tests']=='passed ASan+UBSan' and r['client_tests']=='passed'
result={'title_revision':'randomizer-r21-preparation','title_id':'PPSA91762',
 'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':sha(ART/'eboot.bin')},
 'source_matches':matches,'base':'batch-r20b-20261028','snapshot':str(WORK),
 'profile_startup':'baseline','profile_flags':{'baseline':0,'plan-only':1,'lazy-only':2,'optimized':3},
 'switch_contract':'za_preparation_switch_profile returns flags+1 only after checked drain at post-present exec-lock boundary; negative preserves previous profile.',
 'packaged_defaults':{n:(ART/n).read_text() for n in ('submission-options.txt','local-shader-options.txt')},
 'host_tests':tests,'observer_tests':{'receipt':str(obsreceipt),'result':r},
 'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
 'observer_files':{p.name:sha(p) for p in obs.iterdir() if p.is_file()},
 'preservation_audit_sha256':sha(EVID/'preservation-audit.json'),
 'registration_sha256':sha(EVID/'registration.json'),
 'runtime_patch_sha256':sha(EVID/'runtime-r21.patch'),
 'runtime_sources':{str(p.relative_to(WORK/'source/runtime')):sha(p) for p in (WORK/'source/runtime').rglob('*') if p.is_file()},
 'console_access_by_agent':False,'saves_modified':False,'hardware_validation':'pending',
 'note':'Four profiles use the same binary. Descriptor allocation/update/bind and copy lifetimes remain unchanged. Cumulative per-profile counters add the same lightweight bookkeeping to every mode; baseline stage_set body otherwise retains r20b behavior.'}
(EVID/'ready.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'ready':True,'eboot':result['eboot'],'startup':'baseline'},indent=2))
