"""Bounded PC evidence for native headers, with isolated saves and source checks."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

from qa_translation import snapshot_tree, tree_diff, package_hashes
from run_poc import LAB, GAME, EXE, sha256

ROUTES = {
    'menu-save': dict(seconds=120, save='city-orig',
        input='240:A:8,420:A:8,750:STICK_UP:60,900:X:8,1000:A:8,1100:R:8,1400:A:8,1700:B:8',
        shots='950,1050,1200,1300,1410,1440,1470,1500,2200'),
    'appearance-confirm': dict(seconds=100, save=None,
        input='300:A:8,480:STICK_RIGHT:8,700:A:8',
        shots='240,360,420,500,600,720,800,900,1100,1400,1800'),
}


def run(name, route_name, package):
    route = ROUTES[route_name]
    package = package.resolve()
    assert package.is_relative_to(LAB) and (package/'mods/hebrew-headers/romfs').is_dir()
    report = LAB/'headers/reports'/f'qa-{name}.json'
    runroot = LAB/'runs'/name
    if report.exists() or runroot.exists():
        raise FileExistsError('Keep earlier evidence; choose a new run name')
    seed = LAB/'saves'/route['save'] if route['save'] else None
    source_before = snapshot_tree(GAME)
    hashes_before = {n: sha256(GAME/n) for n in ('romfs.bin', 'lasgame.dll')}
    package_before = package_hashes(package)
    seed_before = package_hashes(seed) if seed else {}
    record = dict(started_utc=datetime.now(timezone.utc).isoformat(), name=name, route=route,
        package=str(package), package_hashes=package_before, critical_before=hashes_before,
        original_save_used=False, console_accessed=False, visual_review='pending')
    report.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    args = [sys.executable, '-X', 'utf8', str(LAB/'tools/run_poc.py'), name,
        '--seconds', str(route['seconds']), '--language', 'en-US',
        '--mods', str(package/'mods'), '--cache-src', 'poc05-english-slot-final',
        '--input', route['input'], '--shot-at', route['shots'],
        '--env', 'LARECOMP_LOG_FILES=1']
    if seed:
        args += ['--save-src', str(seed)]
    result = subprocess.run(args, cwd=LAB)
    run_record = json.loads((runroot/'run.json').read_text(encoding='utf-8'))
    hashes_after = {n: sha256(GAME/n) for n in hashes_before}
    changes = tree_diff(source_before, snapshot_tree(GAME))
    log = (runroot/'stderr.log').read_text(encoding='utf-8', errors='replace')
    from PIL import Image
    captures = []
    for p in sorted((runroot/'build/frames').glob('*.png')):
        with Image.open(p) as im:
            im.verify()
        captures.append(dict(file=p.relative_to(LAB).as_posix(), sha256=sha256(p)))
    record.update(finished_utc=datetime.now(timezone.utc).isoformat(), runner_exit=result.returncode,
        run=run_record, captures=captures, reference_metadata_changes=changes,
        critical_after=hashes_after, critical_unchanged=hashes_before==hashes_after,
        package_unchanged=package_before==package_hashes(package),
        test_save_seed_unchanged=seed_before==(package_hashes(seed) if seed else {}),
        header_mod_detected='[fs] mod: hebrew-headers' in log)
    record['automation_passed'] = all((result.returncode==0,
        run_record.get('terminated_by_harness'), bool(captures),
        not changes, record['critical_unchanged'], record['package_unchanged'],
        record['test_save_seed_unchanged'], record['header_mod_detected']))
    report.write_text(json.dumps(record, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(report=str(report), automation_passed=record['automation_passed'],
        captures=len(captures), visual_review='pending')), flush=True)
    return record['automation_passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('name')
    parser.add_argument('--route', choices=ROUTES, required=True)
    parser.add_argument('--package', type=Path, required=True)
    options = parser.parse_args()
    if not run(options.name, options.route, options.package):
        raise SystemExit(1)
