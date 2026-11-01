"""Bounded reproducible PC QA, using a private data root and a copied lab test save.

This CLI never installs into the reference game or accesses the PS5. An automation/visibility
pass is not linguistic/visual acceptance: screenshots still need human inspection.
"""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

from pack_translation import LAB, local, sha256
from run_poc import GAME, EXE

SCENARIOS = {
    'menu_save': dict(seconds=200, save='city-orig',
        input='240:A:8,420:A:8,750:STICK_UP:60,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8',
        shots='1050,1200,1410,1440,1470,1500,2200',
        coverage=['main menu','save dialog','test-save write'],
        provenance='Existing poc05 recorded route; copied city-orig test save'),
    'appearance': dict(seconds=200, save=None,
        input='240:A:8,420:A:8,600:A:8,780:A:8',shots='600,900,1200,1500,1800',
        coverage=['language selection','new-game appearance'],
        provenance='Candidate route, must inspect captures; no existing save'),
}
PLANNED = {
    'bag':'A stable bag entry/exit route and translated bag strings are still required.',
    'battle':'A reproducible battle test save and translated battle strings are still required.',
    'first_dialogue':'A story-opening test save/route and approved dialogue batch are still required.',
}


def snapshot_tree(root):
    return {str(path.relative_to(root)).replace('\\','/'):dict(bytes=path.stat().st_size,mtime_ns=path.stat().st_mtime_ns)
            for path in sorted(root.rglob('*')) if path.is_file()}


def tree_diff(before,after):
    return [name for name in sorted(before.keys()|after.keys()) if before.get(name)!=after.get(name)]


def package_hashes(root):
    return {str(path.relative_to(root)).replace('\\','/'):sha256(path) for path in sorted(root.rglob('*')) if path.is_file()}


def run_qa(*,name,package,scenario='menu_save',seconds=None):
    if not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,95}',name):
        raise ValueError('Run name must be a simple unique basename')
    if scenario not in SCENARIOS:
        raise ValueError('Unsupported route; planned coverage is not a tested route')
    package=local(package)
    manifest=json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('slot')!='English' or not (package/'mods/hebrew/romfs').is_dir():
        raise ValueError('Expected an English-slot package with mods/hebrew/romfs')
    runroot=local(LAB/'runs'/name)
    reportpath=local(LAB/'reports'/('qa-'+name+'.json'))
    if runroot.exists() or reportpath.exists():
        raise FileExistsError('Use a new run name; existing evidence is preserved')
    route=SCENARIOS[scenario]
    budget=route['seconds'] if seconds is None else int(seconds)
    if not 30<=budget<=900:
        raise ValueError('QA budget must be 30..900 seconds')
    before=snapshot_tree(GAME)
    critical={name:sha256(GAME/name) for name in ('lasgame.dll','romfs.bin')}
    package_before=package_hashes(package)
    save_src=local(LAB/'saves'/route['save']) if route['save'] else None
    save_hashes=package_hashes(save_src) if save_src else {}
    args=[sys.executable,'-X','utf8',str(LAB/'tools/run_poc.py'),name,'--seconds',str(budget),
          '--mods',str(package/'mods'),'--input',route['input'],'--shot-at',route['shots'],
          '--cache-src','poc05-english-slot-final']
    if save_src:
        args+=['--save-src',str(save_src)]
    record=dict(started_utc=datetime.now(timezone.utc).isoformat(),scenario=scenario,route=route,
        planned_unimplemented_routes=PLANNED,package=str(package),package_manifest_sha256=sha256(package/'manifest.json'),
        game_reference=str(GAME),reference_before=before,critical_before=critical,
        save_source=str(save_src) if save_src else None,test_save_source_before=save_hashes,
        runtime_sha256=sha256(EXE),budget_seconds=budget,source_game_writes=False,console_access=False,
        visual_review_status='pending')
    reportpath.parent.mkdir(parents=True,exist_ok=True)
    reportpath.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # The child runner owns/terminates only its game subprocess and bounds each run.
    # Do not kill that runner using a second timeout: doing so could orphan its game child.
    # Address collisions are retried at most four times and only after an early child exit.
    completed=subprocess.run(args,cwd=LAB)
    record['runner_exit_code']=completed.returncode
    run_record=json.loads((runroot/'run.json').read_text(encoding='utf-8')) if (runroot/'run.json').exists() else None
    after=snapshot_tree(GAME)
    critical_after={name:sha256(GAME/name) for name in critical}
    record.update(finished_utc=datetime.now(timezone.utc).isoformat(),run=run_record,
        reference_metadata_changes=tree_diff(before,after),critical_after=critical_after,
        critical_hashes_unchanged=critical==critical_after,
        package_unchanged=package_before==package_hashes(package),
        test_save_source_unchanged=save_hashes==(package_hashes(save_src) if save_src else {}))
    captures=[]
    from PIL import Image
    for path in sorted((runroot/'build/frames').glob('*.png')):
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            captures.append(dict(path=str(path.relative_to(LAB)).replace('\\','/'),sha256=sha256(path),
                                 width=image.width,height=image.height))
    log=(runroot/'stderr.log').read_text(encoding='utf-8',errors='replace') if (runroot/'stderr.log').exists() else ''
    record['captures']=captures
    record['mod_detected']='[fs] mod: hebrew' in log
    record['automation_passed']=bool(completed.returncode==0 and run_record and run_record.get('terminated_by_harness')
        and captures and record['mod_detected'] and not record['reference_metadata_changes']
        and record['critical_hashes_unchanged'] and record['package_unchanged'] and record['test_save_source_unchanged'])
    record['limitations']=['Automation pass does not certify visible Hebrew or layout; inspect images.',
        'Only selected route coverage is exercised; bag, battle and story are not claimed.',
        'All reference files have metadata checks; content hashes cover lasgame.dll and romfs.bin.']
    reportpath.write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return record,reportpath


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--package',type=Path,required=True)
    parser.add_argument('--scenario',choices=SCENARIOS,default='menu_save')
    parser.add_argument('--seconds',type=int)
    args=parser.parse_args()
    record,path=run_qa(name=args.name,package=args.package,scenario=args.scenario,seconds=args.seconds)
    print(json.dumps(dict(report=str(path),automation_passed=record['automation_passed'],captures=len(record['captures']),visual_review_status=record['visual_review_status'])))
    if not record['automation_passed']:
        raise SystemExit(1)


if __name__=='__main__':
    main()
