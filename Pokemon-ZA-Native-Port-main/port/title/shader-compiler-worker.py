"""Persistent WSL compiler for this task's bounded, content-addressed shaders.
One process avoids starting WSL twice for every new shader. Protocol is local
JSON on stdin/stdout; compiler command lines are fixed, never read from GLSL.
"""
from pathlib import Path
import json,re,subprocess,sys,time
directory=Path(sys.argv[1]).resolve()
pattern=re.compile(r'[0-9a-f]{16}\.(vert|frag|geom|tesc|tese|comp)\Z')
for line in sys.stdin:
    try:
        request=json.loads(line);name=request['source']
        if not pattern.fullmatch(name):raise ValueError('Invalid shader filename')
        src=directory/name;spv=directory/(name.split('.')[0]+'.spv')
        if src.resolve().parent!=directory:raise ValueError('Source escapes session directory')
        start=time.monotonic()
        build=subprocess.run(['glslangValidator','-V','--target-env','vulkan1.3','-o',str(spv),str(src)],capture_output=True,text=True,timeout=45)
        (directory/(name+'.compile.log')).write_text(build.stdout+build.stderr,encoding='utf-8')
        if build.returncode:raise RuntimeError('GLSL compile failed; see compile.log')
        valid=subprocess.run(['spirv-val','--target-env','vulkan1.3',str(spv)],capture_output=True,text=True,timeout=30)
        if valid.returncode:raise RuntimeError('SPIR-V validation failed: '+valid.stderr[:2000])
        reply={'source':name,'ok':True,'compile_and_validate_ms':round((time.monotonic()-start)*1000,1)}
    except Exception as e:reply={'ok':False,'error':str(e)}
    print(json.dumps(reply),flush=True)
