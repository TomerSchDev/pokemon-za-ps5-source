"""Finish build evidence locally; no console or network operations."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
EVIDENCE = ROOT/'evidence/submission-r20b'
WORK = Path('//wsl.localhost/Ubuntu/home/tomer/ps5-za-native/batch-r20b-20261028')
ART = ROOT/'artifacts/randomizer-r20b-batch/PPSA91762'

def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while data := f.read(1 << 20): h.update(data)
    return h.hexdigest()

expected = '9ee7737bb542eae1b804e644733898dce8808a9b85da3c4929c7031f83268852'
assert sha(ART/'eboot.bin') == expected
for name in ('build.sh','test.sh'):
    p = HERE/name
    p.write_text(p.read_text(),newline='\n')
test = subprocess.run([sys.executable,str(HERE/'test-client.py')],capture_output=True,text=True)
(EVIDENCE/'client-tests.log').write_text(test.stdout+test.stderr,newline='\n')
assert test.returncode == 0
matches = {}
for src,dst in [('submission.h','za_submission_r20.h'),('queue.inc','za_submission_queue_r20.inc'),
                ('executor.inc','za_submission_executor_r20.inc'),('boundary.inc','za_submission_boundary_r20b.inc')]:
    canonical = (HERE/src).read_text()
    built = (WORK/'source/runtime/nvn/vulkan'/dst).read_text()
    strip_comments = lambda text: re.sub(r'/\*[\s\S]*?\*/','',text)
    assert strip_comments(canonical) == strip_comments(built), src
    matches[src] = {'canonical_sha256':sha(HERE/src),
                    'build_source_sha256':sha(WORK/'source/runtime/nvn/vulkan'/dst),
                    'same_after_comment_removal':True}
result = {'title_revision':'randomizer-r20b-batch','title_id':'PPSA91762',
    'eboot':{'path':str(ART/'eboot.bin'),'size':(ART/'eboot.bin').stat().st_size,'sha256':expected},
    'source_matches':matches,
    'comment_note':'After compilation the header capacity comment was corrected without changing code or line count; built source is retained untouched.',
    'files':{p.name:sha(p) for p in HERE.iterdir() if p.is_file()},
    'packaged_defaults':{name:(ART/name).read_text() for name in ('submission-options.txt','local-shader-options.txt')},
    'host_tests':'queue/executor/boundary and observer passed ASan/UBSan -Werror; offline client passed',
    'console_access_by_agent':False,
    'hardware_validation':'pending'}
(EVIDENCE/'ready.json').write_text(json.dumps(result,indent=2)+'\n',newline='\n')
print(json.dumps(result['eboot'],indent=2))
