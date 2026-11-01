"""Prepare private r20b from r20 without changing r20 or generated game data."""
import difflib
import hashlib
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PORT = ROOT/'port/submission-r20b'
EVIDENCE = ROOT/'evidence/submission-r20b'
BASE = Path('/home/tomer/ps5-za-native/batch-r20-20261028')
WORK = Path('/home/tomer/ps5-za-native/batch-r20b-20261028')
PINS = {
 'runtime/nvn/vulkan/exec.c': '18b0af77ab34ecb662312a9e709b30a5a56cd82ec9ff3a79192921527ee00dcd',
 'runtime/nvn/objects.c': '0e29cfa47d3381c100d47278184f6771293f754cb49c71d5cc107f966e69adbe',
 'runtime/nvn/nvn.h': '1fdd0bd77b78c81b13315ee030a8022d5997730cb339dfae8871dd76a1cb5d2d',
}
def once(s,a,b):
    assert s.count(a)==1, (s.count(a),a[:100])
    return s.replace(a,b)
def main():
    assert not WORK.exists(), 'Do not overwrite another build.'
    for r,h in PINS.items(): assert hashlib.sha256((BASE/'source'/r).read_bytes()).hexdigest()==h, r
    WORK.mkdir()
    for name in ('source','port','inc','shaders','evidence'):
        shutil.copytree(BASE/name,WORK/name,symlinks=True,
            ignore=shutil.ignore_patterns('build','.git') if name=='source' else None)
    for name in ('rt','inc'):
        shutil.copytree(BASE/'source/build/ps5'/name,WORK/'source/build/ps5'/name,symlinks=True)
    shutil.copytree(BASE/'objects-r20',WORK/'objects-r20b')
    EVIDENCE.mkdir(parents=True,exist_ok=True)
    patch=[]
    for r in PINS:
        p=WORK/'source'/r; old=p.read_text(); new=old
        if r.endswith('nvn.h'):
            new=once(new,'void backend_execute_batch(const uint64_t *handles, int n);',
                'void backend_execute_batch(const uint64_t *handles, int n);\nint backend_submission_switch_profile(const char *profile, uint64_t frame);')
        elif r.endswith('objects.c'):
            new=once(new,'NVN(nvnQueueSubmitCommands) {', '''/* Observer only, after a successful present. Serialize the drain/profile
 * transition with all recorded-list execution and protected finalization. */
int za_submission_switch_profile(const char *profile, uint64_t frame) {
    exec_lock_take();
    int applied = backend_submission_switch_profile(profile, frame);
    exec_lock_give();
    return applied;
}

NVN(nvnQueueSubmitCommands) {''')
        else:
            new=once(new,'#include "za_submission_executor_r20.inc"',
                '#include "za_submission_executor_r20.inc"\n#include "za_submission_boundary_r20b.inc"')
        p.write_text(new)
        patch += list(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='r20/'+r,tofile='r20b/'+r))
    for src,dst in [('submission.h','za_submission_r20.h'),('queue.inc','za_submission_queue_r20.inc'),
                    ('executor.inc','za_submission_executor_r20.inc'),('boundary.inc','za_submission_boundary_r20b.inc')]:
        path=WORK/'source/runtime/nvn/vulkan'/dst
        old=path.read_text() if path.exists() else ''
        new=(PORT/src).read_text();path.write_text(new)
        patch += list(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='r20/'+dst,tofile='r20b/'+dst))
    observer_old=(ROOT/'port/local-shader-r19/observer-r19.c').read_text()
    observer_new=(PORT/'observer-r20b.c').read_text()
    patch += list(difflib.unified_diff(observer_old.splitlines(True),observer_new.splitlines(True),fromfile='r19a/observer.c',tofile='r20b/observer.c'))
    (EVIDENCE/'runtime-r20b.patch').write_text(''.join(patch))
    receipt={'base':str(BASE),'work':str(WORK),'base_sources':PINS,
        'base_eboot_sha256':'33e435707b787fe23391996a5063b724d1c74627f4fea6e52d7b6d637b2f3819',
        'canonical_files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in PORT.iterdir() if p.is_file()}}
    (EVIDENCE/'preparation.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print('Prepared',WORK)
if __name__=='__main__':main()
