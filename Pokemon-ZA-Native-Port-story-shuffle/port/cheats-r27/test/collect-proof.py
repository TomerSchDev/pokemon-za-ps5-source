"""Collect completed, manually inspected PC runs into the final source-bound proof.
Run only after viewing cap frame01750 and OFF reload frame01500. The script also
checks runtime logs, frozen hashes, PKHeX results, and byte-identical OFF save.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil
p=argparse.ArgumentParser();p.add_argument('lab',type=Path);a=p.parse_args();lab=a.lab.resolve()
own=Path(__file__).resolve().parents[1];out=own/'evidence';out.mkdir(exist_ok=True)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
frozen={'za_money.cpp':'8854ec7e508501cd5c6183a9a2e313c60fe6120da236aaf7cd11cc07690871c8',
 'za_money.h':'6f96f8ad54dbceb5c85c8d3d610c1b0e6b3479cf0ef0b3e9bf1e64b7901a66c1',
 'prepare-money-hooks.py':'13e41e8ea85bb839d0f63191d513441bbb09b7357b12a0fe343cfd5193e5610a'}
for name,h in frozen.items():assert sha(own/name)==h,name
dll=sha(lab/'build-ui/lasgame.dll');assert dll=='307b7b122c1b769f1a3f3671580309cc8c25517a161a2bc6c806694147df81c5'
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
runs={}
for name in ('final-ui-10000','final-cap-1000000','final-off-reload'):
    run=lab/name;rec=read(run/'run.json');assert rec['dll_sha256']==dll and rec['source_unchanged'] and rec['terminated_by_harness']
    log=(run/'stderr.log').read_text(errors='replace');traces=[ln for ln in log.splitlines() if ln.startswith('[r27-money]')]
    applies=[ln for ln in traces if ' request=' in ln]
    if name=='final-ui-10000':assert len(applies)==1 and 'before=10384 request=10000 after=20384 applied=1' in applies[0]
    elif name=='final-cap-1000000':assert len(applies)==1 and 'before=9999990 request=1000000 after=9999999 applied=1' in applies[0]
    else:
        assert not applies and rec['copy_before_sha256']==rec['copy_after_sha256']
        assert 'value=9999999' in '\n'.join(traces)
    shutil.copy2(run/'run.json',out/(name+'-run.json'));shutil.copy2(run/'stderr.log',out/(name+'-stderr.log'))
    if (run/'r27money-control.log').exists():shutil.copy2(run/'r27money-control.log',out/(name+'-control.log'))
    runs[name]=dict(pid=rec['pid'],save_before=rec['copy_before_sha256'],save_after=rec['copy_after_sha256'],source_unchanged=True,trace=traces)
for file,amount in (('pc-normal-pkhex.json',20384),('pc-cap-pkhex.json',9999999),('pc-off-pkhex.json',9999999)):
    check=read(out/file);assert check['after_money']==amount and check['hash_valid'] and check['party_checksums_valid']
for run,frame,name in [('final-cap-1000000',950,'cap-before.png'),('final-cap-1000000',1750,'cap-after-before-save.png'),('final-off-reload',1500,'off-reload.png')]:
    shutil.copy2(lab/run/'build/frames'/f'frame_{frame:05d}.png',out/name)
shutil.copy2(lab/'build-ui/build-result.json',out/'pc-build-result.json')
shutil.copy2(lab/'build-ui/generated/money-hook-manifest.json',out/'money-hook-manifest.json')
proof=dict(pc_verified=True,ui_verified=True,save_verified=True,off_verified=True,cap_verified=True,reload_verified=True,
 runtime_sha256=frozen['za_money.cpp'],runtime_header_sha256=frozen['za_money.h'],patcher_sha256=frozen['prepare-money-hooks.py'],
 pc_game_dll_sha256=dll,pc_runtime_exe_sha256='c74c94359182e6749b92eab82c066b6963dd33c25b0d0314e2a3667e1623e7fc',
 game_build_id='b1f12fd919eae86ab8a978317677e64bce443d1f',console_tested=False,
 observed_behavior='Queued request consumes on next money UI read or game Save. Header is cached before UI hook, so close/open menu once more to refresh. Save persists the new balance.',
 visual_inspection='Final-build cap frame950 shows9,999,990; frame1750 shows9,999,999 before first save press2100. OFF reload frame1500 shows9,999,999.',
 normal=dict(before=10384,request=10000,after=20384,actual_applies=1,pkhex_verified=True),
 cap=dict(before=9999990,request=1000000,after=9999999,actual_applies=1,fixture_prepared_with_pkhex=True,ui_before_save=True),
 off=dict(actual_applies=0,copied_save_unchanged=True,reloaded_value=9999999),runs=runs,
 limitations=['PC test controller used production money API, not the PS5 overlay. Parent validates overlay separately.',
              'MSYS2 Clang/LLD relink retained original game objects; PS5 compile/link is separate.',
              'This proof does not claim PS5 hardware validation.'])
proof['evidence_sha256']={p.name:sha(p) for p in sorted(out.iterdir()) if p.is_file() and p.name!='pc-proof.json'}
(out/'pc-proof.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof,indent=2))
