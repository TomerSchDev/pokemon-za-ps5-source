"""Run in WSL: validate each unambiguous portable PC cache candidate."""
from pathlib import Path
import concurrent.futures,json,subprocess,hashlib
root=Path(__file__).resolve().parents[2]
source=root/'artifacts/title-r14-pc-shaders'
manifest=json.loads((root/'evidence/title-r14-pc-shader-candidates.json').read_text())
def check(name):
    p=source/name
    assert hashlib.sha256(p.read_bytes()).hexdigest()==manifest['files'][name]['sha256']
    r=subprocess.run(['spirv-val','--target-env','vulkan1.3','--scalar-block-layout',str(p)],capture_output=True,text=True)
    return {'name':name,'valid':r.returncode==0,'error':r.stderr if r.returncode else ''}
with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(check,manifest['files']))
report={'validated':sum(r['valid'] for r in rows),'failures':[r for r in rows if not r['valid']],'keys':[r['name'] for r in rows if r['valid']],
        'not_full_game_coverage':True,'pc_binary_pipeline_caches_included':False}
(root/'evidence/title-r14-pc-shader-validation.json').write_text(json.dumps(report,indent=2))
print('Validated',report['validated'],'SPIR-V files; failures',len(report['failures']))
