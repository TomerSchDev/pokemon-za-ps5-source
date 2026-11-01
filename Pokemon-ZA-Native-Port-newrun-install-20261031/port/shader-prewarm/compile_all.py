"""Bounded four-worker offline GLSL compile/validation, resumable by content hash.

WSL only. Watches the translation journal while its process runs. No console IO.
"""
from pathlib import Path
import argparse, concurrent.futures, hashlib, json, os, select, shutil, subprocess, threading, time
from forecast import ROOT
from translate_all import WORK, cache_hash


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--watch',action='store_true')
    ap.add_argument('--workers',type=int,choices=range(1,13),default=4);a=ap.parse_args()
    evidence=ROOT/'evidence/offline-shaders-20261028';out=WORK/'compiled';out.mkdir(exist_ok=True)
    executable=WORK.parent/'host-build/compiler-worker';local=threading.local();workers=[];lock=threading.Lock()
    progress=evidence/'compile-progress.json';receipt=evidence/'compile-validation.json';journal=WORK/'compile-journal.jsonl'
    done={};failures={};sources={};start=time.monotonic();last=start
    if journal.exists():
        for line in journal.read_text().splitlines():
            try:r=json.loads(line)
            except json.JSONDecodeError:continue
            if r.get('ok') and (out/(r['key']+'.spv')).exists():
                if hashlib.sha256((out/(r['key']+'.spv')).read_bytes()).hexdigest()==r['spv_sha256']:done[r['key']]=r
    jf=journal.open('a',buffering=1)
    def get_worker():
        worker=getattr(local,'worker',None)
        if worker is None or worker.poll() is not None:
            worker=subprocess.Popen([str(executable)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
                text=True,encoding='utf-8',bufsize=1)
            local.worker=worker
            with lock:workers.append(worker)
        return worker
    def job(item):
        key=item['key'];src=WORK/'sources'/(key+'.'+item['ext']);dest=out/(key+'.spv');tmp=out/(key+'.building')
        try:
            data=src.read_bytes()
            assert hashlib.sha256(data).hexdigest()==item['source_sha256'],'Source changed'
            assert cache_hash(data,item['stage'])==key,'Runtime key mismatch'
            if shutil.disk_usage('/mnt/c').free<2<<30:raise RuntimeError('C: free space below 2 GiB')
            worker=get_worker();kind={0:0,1:1,5:2}[item['stage']]
            worker.stdin.write(f'{kind}\t{src}\t{tmp}\n');worker.stdin.flush()
            ready,_,_=select.select([worker.stdout],[],[],60)
            if not ready:worker.kill();worker.wait();raise TimeoutError('Compiler exceeded 60 seconds')
            line=worker.stdout.readline()
            result=json.loads(line)
            if not result['ok']:
                error=Path(str(tmp)+'.error')
                raise ValueError(error.read_text(errors='replace')[:2400] if error.exists() else 'Compiler rejected source')
            val=subprocess.run(['spirv-val','--target-env','vulkan1.3',str(tmp)],capture_output=True,text=True,timeout=30)
            if val.returncode:raise ValueError('spirv-val: '+val.stderr[:2400])
            data=tmp.read_bytes();sha=hashlib.sha256(data).hexdigest()
            if dest.exists():assert hashlib.sha256(dest.read_bytes()).hexdigest()==sha,'Different existing compiler result'
            tmp.replace(dest)
            return dict(key=key,ok=True,source_sha256=item['source_sha256'],spv_sha256=sha,bytes=len(data),
                stage=item['stage'],compile_ms=result['compile_ms'],validated=True,
                previous_key=item['previous_key'],matches_recorded_source=item['matches_recorded_source'])
        except Exception as error:return dict(key=key,ok=False,error=str(error),source_sha256=item['source_sha256'])
    pending={};submitted=set(done);partial_line='';offset=0;idle_since=time.monotonic()
    def update_sources():
        nonlocal offset,partial_line,idle_since
        path=WORK/'translation-journal.jsonl'
        if not path.exists():return
        with path.open() as f:f.seek(offset);text=partial_line+f.read();offset=f.tell()
        lines=text.split('\n');partial_line=lines.pop()
        for line in lines:
            if not line:continue
            item=json.loads(line)
            if item.get('key') and item['key'] not in sources:sources[item['key']]=item;idle_since=time.monotonic()
    def write_progress(complete=False):
        r=dict(complete=complete,sources_seen=len(sources),compiled_validated=len(done),failures=len(failures),
            pending=len(pending),new_keys=sum(not r['previous_key'] for r in done.values()),
            bytes=sum(r['bytes'] for r in done.values()),elapsed_seconds=round(time.monotonic()-start,1))
        tmp=progress.with_suffix('.new');tmp.write_text(json.dumps(r,indent=2));tmp.replace(progress)
        print(json.dumps(r),flush=True)
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            while True:
                update_sources()
                for key,item in sources.items():
                    if len(pending)>=a.workers*3:break
                    if key not in submitted:pending[pool.submit(job,item)]=key;submitted.add(key)
                if pending:
                    ready,_=concurrent.futures.wait(pending,timeout=1,return_when=concurrent.futures.FIRST_COMPLETED)
                    for future in ready:
                        r=future.result();pending.pop(future);jf.write(json.dumps(r)+'\n')
                        (done if r['ok'] else failures)[r['key']]=r
                else:
                    finished=(evidence/'translation.json').exists()
                    if not a.watch or finished:break
                    if time.monotonic()-idle_since>300:raise RuntimeError('No new translation output for five minutes; results preserved')
                    time.sleep(1)
                if time.monotonic()-last>15:write_progress();last=time.monotonic()
            write_progress(True)
            r=dict(schema=1,complete=True,compiler='glslang 16.2.0',target='Vulkan 1.3 / SPIR-V 1.6',
                optimizer=False,workers=a.workers,source='Exact installed runtime GLSL translator, pinned PS5 memory window',
                raw_shaderc_results=True,vertex_no_contraction='Applied by native runtime after shim cache lookup, as with previous host uploads',
                files=[done[k] for k in sorted(done)],failures=[failures[k] for k in sorted(failures)],
                counts=dict(validated=len(done),failed=len(failures),new_keys=sum(not r['previous_key'] for r in done.values()),
                    matched_recorded_sources=sum(r['matches_recorded_source'] for r in done.values())),
                elapsed_seconds=round(time.monotonic()-start,1),console_uploaded=False)
            receipt.write_text(json.dumps(r,indent=2))
    finally:
        jf.close()
        for worker in workers:
            if worker.poll() is None:
                worker.stdin.close()
                try:worker.wait(timeout=5)
                except subprocess.TimeoutExpired:worker.kill();worker.wait()


if __name__=='__main__':main()
