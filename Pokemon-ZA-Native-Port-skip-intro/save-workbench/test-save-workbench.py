"""Integration tests against a copy of the real save, including retention and fail-closed exports."""
from pathlib import Path
import argparse,copy,hashlib,json,subprocess,tempfile

p=argparse.ArgumentParser();p.add_argument('app',type=Path);p.add_argument('save',type=Path);p.add_argument('--dotnet',type=Path);p.add_argument('--report',type=Path,required=True);a=p.parse_args()
cmd=([str(a.dotnet)] if a.dotnet else [])+[str(a.app.resolve())]
checks=[]
def check(name,condition):
    if not condition: raise AssertionError(name)
    checks.append(name)
def run(*args,ok=True):
    result=subprocess.run(cmd+list(map(str,args)),capture_output=True,text=True,encoding='utf-8',timeout=30)
    if ok and result.returncode!=0: raise RuntimeError(result.stdout+result.stderr)
    if not ok and result.returncode==0: raise AssertionError('Unexpected success: '+str(args))
    return json.loads(result.stdout)
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

original=sha(a.save)
with tempfile.TemporaryDirectory(prefix='za-save-test-') as td:
    root=Path(td);source=root/'main';source.write_bytes(a.save.read_bytes())
    before=run('inspect',source);mark=run('bookmark',source,'test')
    check('Valid save, exact no-op encryption roundtrip',before['RoundtripIdentical'])
    bookmark=root/'target.json'
    def save_mark(value):bookmark.write_text(json.dumps(value),encoding='utf-8')
    save_mark(mark);run('move',source,root/'noop',bookmark)
    check('No-op export is byte-identical',sha(root/'noop/main')==original)
    changed=copy.deepcopy(mark);changed['Position']['X']+=.25;save_mark(changed)
    run('move',source,root/'changed',bookmark)
    after=run('inspect',root/'changed/main')
    old={b['Key']:b for b in before['Blocks']};new={b['Key']:b for b in after['Blocks']}
    differences=[k for k in old if old[k]!=new[k]]
    check('Only coordinate block changed',differences==['910D381F'])
    check('All non-coordinate blocks preserved',all(old[k]==new[k] for k in old if k!='910D381F'))
    check('Party, boxes, inventory, trainer, money preserved',all(old[k]==new[k] for k in ['3AA1A9AD','0D66012C','21C9BD44','E3E89BD1','4F35D0DD']))
    check('All indexed story values preserved',before['Story']==after['Story'])
    check('Backup is original and no input writes occurred',sha(root/'changed/original-main.backup')==original==sha(source))
    check('Run binding matches current source',json.loads((root/'changed/run-binding.json').read_text())['SourceContext']['RunId']=='r000000006ae17668-f3167469')
    run('move',source,root/'changed',bookmark,ok=False);check('Existing export rejected and preserved',sha(root/'changed/main')==after['Sha256'])
    bad=copy.deepcopy(mark);bad['Revision']=0;save_mark(bad);run('move',source,root/'bad-rev',bookmark,ok=False);check('Revision mismatch rejected',not (root/'bad-rev').exists())
    city=copy.deepcopy(mark);city['Position']['Map']='t1';save_mark(city);run('move',source,root/'blocked-map',bookmark,ok=False);check('Cross-map requires explicit experimental option',not (root/'blocked-map').exists())
    run('move',source,root/'crossmap',bookmark,'--experimental-map');cross=run('inspect',root/'crossmap/main')
    check('Experimental map export retains every other block',all(old[k]=={b['Key']:b for b in cross['Blocks']}[k] for k in old if k!='910D381F'))
    for name,field,value in [('bounds','X',100001),('nonfinite','X',float('inf')),('map-format','Map','../map'),('rotation','RW',4)]:
        bad=copy.deepcopy(mark);bad['Position'][field]=value;save_mark(bad);run('move',source,root/name,bookmark,ok=False);check(name+' rejected without output',not (root/name).exists())
    invalid=root/'invalid-main';raw=bytearray(source.read_bytes());raw[-1]^=1;invalid.write_bytes(raw)
    run('inspect',invalid,ok=False);check('Corrupt checksum rejected',True)
    diff=run('compare',source,root/'changed/main');check('Comparison isolates location change',diff['ChangedBlocks']==['910D381F'] and diff['StoryDifferences']==[])
check('Retained original file untouched',sha(a.save)==original)
a.report.parent.mkdir(parents=True,exist_ok=True)
a.report.write_text(json.dumps({'passed':len(checks),'checks':checks,'source_sha256':original,'hardware_validation':'pending'},indent=2),encoding='utf-8')
print(json.dumps({'passed':len(checks),'source_sha256':original,'hardware_validation':'pending'}))
