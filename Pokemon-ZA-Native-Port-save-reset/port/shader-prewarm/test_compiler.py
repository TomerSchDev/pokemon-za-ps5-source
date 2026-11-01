"""WSL host execution of the same portable compiler adapter; NOT PS5 timings."""
from pathlib import Path
import argparse, hashlib, json, statistics, subprocess

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--probe', type=Path, required=True)
p.add_argument('--captured', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args(); a.out.mkdir(parents=True, exist_ok=True)
results = []
for item in json.loads((a.captured/'manifest.json').read_bytes()):
    source = a.captured/item['source']
    assert hashlib.sha256(source.read_bytes()).hexdigest() == item['source_sha256']
    target = a.out/(source.name+'.spv')
    proc = subprocess.run([str(a.probe), source.suffix[1:], str(source), str(target)], capture_output=True, text=True, timeout=45)
    assert proc.returncode == 0, (source.name, proc.stdout, proc.stderr)
    result = json.loads(proc.stdout)
    val = subprocess.run(['spirv-val', '--target-env', 'vulkan1.3', str(target)], capture_output=True, text=True, timeout=30)
    assert val.returncode == 0, (source.name, val.stderr)
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    results.append(dict(source=source.name, source_sha256=item['source_sha256'], output_sha256=digest,
        validated=True, identical_to_previous_cli=digest==item['spv_sha256'], compile_ms=result['compile_ms']))

smokes = {
    'smoke.vert': '#version 450\nvoid main(){gl_Position=vec4(0.0);}\n',
    'smoke.frag': '#version 450\nlayout(location=0) out vec4 color; void main(){color=vec4(1.0);}\n',
    'smoke.comp': '#version 450\nlayout(local_size_x=1) in; void main(){}\n'}
for name, text in smokes.items():
    path=a.out/name; path.write_text(text); target=path.with_suffix('.test.spv')
    subprocess.run([str(a.probe),path.suffix[1:],str(path),str(target)],check=True,capture_output=True,timeout=30)
    subprocess.run(['spirv-val','--target-env','vulkan1.3',str(target)],check=True,capture_output=True,timeout=30)
negative=[]
include=a.out/'actual-include.glsl'; include.write_text('void main(){gl_Position=vec4(0.0);}\n')
for name,stage,text in [('invalid','vert','#version 450\nthis is not GLSL'),
    ('include','vert','#version 450\n#extension GL_GOOGLE_include_directive : require\n#include "'+str(include)+'"\n'),
    ('stage','bogus',smokes['smoke.vert'])]:
    path=a.out/(name+'.glsl');path.write_text(text);target=a.out/(name+'.rejected.spv')
    proc=subprocess.run([str(a.probe),stage,str(path),str(target)],capture_output=True,text=True,timeout=30)
    assert proc.returncode!=0 and not target.exists(),(name,proc.stdout,proc.stderr)
    negative.append(dict(case=name,rejected=True,diagnostic=proc.stderr[:700]))
times=[r['compile_ms'] for r in results]
receipt=dict(execution_platform='Linux host PC; not PS5',compiler='glslang 16.2.0, no optimizer',
    captured_passed=len(results),smoke_stages_passed=list(smokes),negative_cases=negative,
    compile_ms=dict(min=min(times),median=statistics.median(times),max=max(times)),
    identical_to_previous_cli=sum(r['identical_to_previous_cli'] for r in results),results=results,
    limits=['Host timings exclude initialization, disk IO, validation and GPU pipeline construction.',
        'Cross-built PS5 archive has not been executed on hardware.',
        'No prediction of PS5 time/memory or rendered correctness follows from this host test.'])
(a.out/'compiler-validation.json').write_text(json.dumps(receipt,indent=2))
print(json.dumps({k:v for k,v in receipt.items() if k!='results'},indent=2))
