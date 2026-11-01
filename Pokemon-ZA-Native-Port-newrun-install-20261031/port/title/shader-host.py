"""Bounded developer helper for PPSA91761 only. Compile dumped GLSL, validate,
then publish SPIR-V atomically with SHA-256 readback to its shipped cache.
The title reads this through /app0; the live sandbox rejects FTP file creation.
No commands are read from the console; only fixed shader extensions and hashes.
"""
from pathlib import Path
import ftplib, hashlib, json, re, subprocess, sys, time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import run_r3 as r

ROOT=Path(__file__).resolve().parents[2]
LIVE='/mnt/sandbox/PPSA91761_000/download0/zarecomp/cache'
SHIPPED='/data/homebrew/PPSA91761/cache/spirv'
STAGES={'vert':0,'frag':1,'geom':2,'tesc':3,'tese':4,'comp':5}
PATTERN=re.compile(r'([0-9a-f]{16})\.(vert|frag|geom|tesc|tese|comp)\Z')

def wsl_path(p):
    p=p.resolve().as_posix()
    if not p.startswith('C:/'): raise ValueError('Expected workspace on C:')
    return '/mnt/c/'+p[3:]

def main():
    global LIVE, SHIPPED
    seconds=int(sys.argv[1]) if len(sys.argv)>1 else 360
    if not 1 <= seconds <= 900: raise ValueError('Bound must be 1..900 seconds')
    title=sys.argv[2] if len(sys.argv)>2 else 'PPSA91761'
    if title not in {'PPSA91761','PPSA91762'}:raise ValueError('Not an owned native title')
    LIVE=f'/mnt/sandbox/{title}_000/download0/zarecomp/cache'
    SHIPPED=f'/data/homebrew/{title}/cache/spirv'
    out=ROOT/'evidence'/(( 'title-r11' if title=='PPSA91761' else 'randomizer')+'-shaders-'+r.stamp())
    out.mkdir(); done=set(); rows=[]; c=r.Console(); deadline=time.monotonic()+seconds
    seen_title=False; idle_after_title=0
    worker=subprocess.Popen(['wsl','-d','Ubuntu','--','python3',wsl_path(ROOT/'port/title/shader-compiler-worker.py'),wsl_path(out)],
                            stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True,encoding='utf-8',bufsize=1)
    try:
        # Reuse previous validated deliveries instead of recompiling every old
        # dump ahead of a newly waiting shader. Verify the actual remote bytes.
        known={}
        manifests=list((ROOT/'evidence').glob('title-r11-shaders-*/manifest.json'))+list((ROOT/'evidence').glob('randomizer-shaders-*/manifest.json'))
        for manifest in sorted(manifests):
            for row in json.loads(manifest.read_text(encoding='utf-8')):
                if PATTERN.fullmatch(row['source']): known[row['source']]=row
        for name,row in known.items():
            remote=SHIPPED+'/'+name.split('.')[0]+'.spv'
            if c.sha256(remote)==row['spv_sha256']: done.add(name)
        r.log(f'Host shader helper ready; {len(done)} prior deliveries verified and reused')
        while time.monotonic()<deadline:
            try:
                c.ftp.cwd(LIVE+'/spirv-missing')
                names=[n for n,f in c.ftp.mlsd() if f.get('type')=='file']
                seen_title=True; idle_after_title=0
            except ftplib.error_perm:
                if seen_title:
                    idle_after_title+=1
                    if idle_after_title>=5: break
                time.sleep(.5); continue
            for name in names:
                m=PATTERN.fullmatch(name)
                if not m or name in done: continue
                data=c.read(LIVE+'/spirv-missing/'+name,4<<20)
                if data is None: continue
                h=(0xcbf29ce484222325 ^ STAGES[m[2]])+3
                for b in data.split(b'\0',1)[0]: h=((h^b)*0x100000001b3)&0xffffffffffffffff
                if f'{h:016x}'!=m[1]: continue # incomplete write, or unexpected API/hash format
                src=out/name; spv=out/(m[1]+'.spv'); src.write_bytes(data)
                worker.stdin.write(json.dumps({'source':name})+'\n');worker.stdin.flush()
                response=worker.stdout.readline()
                if not response:raise RuntimeError('Shader compiler worker stopped unexpectedly')
                checked=json.loads(response)
                if not checked.get('ok') or checked.get('source')!=name:raise RuntimeError('Shader compilation failed: '+str(checked))
                sha=hashlib.sha256(spv.read_bytes()).hexdigest()
                for folder in [SHIPPED]:
                    try:c.ftp.mkd(folder)
                    except ftplib.error_perm:c.ftp.cwd(folder)
                    remote=folder+'/'+spv.name; old=c.sha256(remote)
                    if old is not None and old!=sha: raise RuntimeError('Refusing different existing cache entry: '+remote)
                    if old is None:
                        with spv.open('rb') as f:c.ftp.storbinary('STOR '+remote+'.host-new',f,1<<20)
                        if c.sha256(remote+'.host-new')!=sha: raise RuntimeError('Readback mismatch')
                        c.ftp.rename(remote+'.host-new',remote)
                        c.ftp.sendcmd('SITE CHMOD 644 '+remote)
                done.add(name)
                rows.append({'source':name,'source_sha256':hashlib.sha256(data).hexdigest(),
                             'spv_sha256':sha,'bytes':spv.stat().st_size,'utc':r.utc_now(),
                             'compile_and_validate_ms':checked['compile_and_validate_ms']})
                manifest=out/'manifest.json'
                temporary=out/'manifest.json.new'
                temporary.write_text(json.dumps(rows,indent=2))
                temporary.replace(manifest)
                r.log(f'Compiled, validated and delivered {name} ({len(rows)} this session)')
            time.sleep(.5)
        r.log(f'Host shader helper ended: {len(rows)} entries; evidence {out}')
    finally:
        c.close()
        worker.stdin.close()
        try:worker.wait(timeout=5)
        except subprocess.TimeoutExpired:worker.terminate();worker.wait(timeout=5)

if __name__=='__main__':main()
