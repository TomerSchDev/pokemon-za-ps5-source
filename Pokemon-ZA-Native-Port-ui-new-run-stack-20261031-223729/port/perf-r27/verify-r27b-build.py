#!/usr/bin/env python3
"""r27b: retain the pinned r27 verifier and require an isolated two-object fix."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE_CHECKER_SHA = '9b535286b37aae6060be632ec574aa812a68aff9cd8638fb48425f8e26353341'
R27_PIE_SHA = 'ca6984037a7bd09b65ac857f910ce236f6674c909534d1ad46a2f1127f67faf1'
R27_ARCHIVE_SHA = '0453e8b047b14bee5ce5024094750f9042eb95bd1475b736ca9ae4c95af46d83'
R27_RECORD_SHA = '853daa62b57b4889b71bc291b5b7068f7b77c0c4306a91c5cca708f42010330e'
R27_LINK_SHA = '267836f046767df13d713efab58c9d3f8289a14432737342027546d98382ab98'
R27_WORK = Path('/home/tomer/ps5-za-native/r27-play-20261029')
OBSERVER_CALL = ('_ZN2za6native8bootMenuEv', 'za_observer_menu')
NEW_INPUTS = ('port/perf-r27/build-r27b-play.sh', 'port/perf-r27/verify-r27b-build.py',
              'port/observer-r17/observer.h')


def digest(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


if digest(HERE / 'verify-r27-build.py') != BASE_CHECKER_SHA:
    raise RuntimeError('Pinned r27 verifier changed; original r27 evidence must remain intact')
spec = importlib.util.spec_from_file_location('r27_base_verifier', HERE / 'verify-r27-build.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
original_source_map = base.source_map


def source_map(project):
    result = original_source_map(project)
    result.update({name: digest(project / name) for name in NEW_INPUTS})
    return dict(sorted(result.items()))


# The complete r26p1 structural checks remain active, with the missing launcher
# contract added to the actual linked callers, not just source/symbol presence.
base.source_map = source_map
base.MENU_CALLS = base.MENU_CALLS + [OBSERVER_CALL]


def baseline(project):
    path = project / 'evidence/perf-r27/build-verification.json'
    base.require(digest(path) == R27_RECORD_SHA, 'Original r27 build record changed')
    base.require(digest(project / 'evidence/perf-r27/link-inputs.txt') == R27_LINK_SHA,
                 'Original r27 wrappers/library link record changed')
    record = base.read(path)
    base.require(record.get('verified') is True and record['work'] == str(R27_WORK), 'Wrong r27 baseline')
    base.require(digest(R27_WORK / 'source/build/ps5/title/llvm-pie.elf') == R27_PIE_SHA,
                 'Original r27 PIE changed')
    base.require(digest(R27_WORK / 'money-r27/liblasgame-r27.a') == R27_ARCHIVE_SHA,
                 'Original r27 MONEY archive changed')
    base.require(base.tree_map(R27_WORK / 'objects-r27', '*.o') == record['candidate_objects'],
                 'Original r27 title objects changed')
    base.require(base.tree_map(R27_WORK / 'source/build/ps5/rt', '*.o') == record['runtime_objects'],
                 'Original r27 runtime objects changed')
    current = source_map(project)
    prior = record['sources']
    changed = sorted(n for n in prior if current.get(n) != prior[n])
    added = sorted(current.keys() - prior.keys())
    base.require(changed == ['port/rando-v2/native_menu.cpp'] and added == sorted(NEW_INPUTS),
                 f'Unexpected source delta from r27: changed={changed}, added={added}')
    return record


def incremental(project, work, evidence, before_build=False):
    record = baseline(project)
    objects = base.tree_map(work / 'objects-r27', '*.o')
    old = record['candidate_objects']
    base.require(objects.keys() == old.keys(), 'Incremental title object list changed')
    changed = sorted(n for n in old if old[n] != objects[n])
    wanted = [] if before_build else ['native_menu.o', 'title_entry.o']
    base.require(changed == wanted, f'Incremental title object delta is {changed}, expected {wanted}')
    base.require(base.tree_map(work / 'source/build/ps5/rt', '*.o') == record['runtime_objects'],
                 'Incremental runtime differs from r27')
    base.require(base.tree_map(work / 'money-r27') == base.tree_map(R27_WORK / 'money-r27'),
                 'Incremental MONEY source, control, archive or object changed')
    base.require(base.tree_map(work / 'dyn-r26') == base.tree_map(R27_WORK / 'dyn-r26'),
                 'Inherited r26 archive or timing source changed')
    if not before_build:
        title = (work / 'objects-r27/title_entry.o').read_bytes()
        base.require(b'[za-title-randomizer-r27b-play]' in title, 'r27b title marker missing')
        base.require(b'[za-title-randomizer-r27-play]' not in title, 'Old r27 title marker retained')
    result = dict(verified=True, phase='copied' if before_build else 'linked', baseline_work=str(R27_WORK),
                  baseline_record_sha256=R27_RECORD_SHA, baseline_pie_sha256=R27_PIE_SHA,
                  unchanged_money_archive_sha256=R27_ARCHIVE_SHA, changed_objects=changed,
                  source_changes=['port/rando-v2/native_menu.cpp'], new_inputs=list(NEW_INPUTS),
                  runtime_byte_identical=True, money_tree_byte_identical=True, timing_tree_byte_identical=True,
                  required_observer_call=list(OBSERVER_CALL))
    base.write(evidence / ('copy-verification.json' if before_build else 'incremental-verification.json'), result)
    return result


def verify(project, previous, work, evidence):
    delta = incremental(project, work, evidence)
    base.verify(project, previous, work, evidence)
    record = base.read(evidence / 'build-verification.json')
    record.update(version='r27b-play', incremental=delta, launcher_observer_call_verified=True)
    base.write(evidence / 'build-verification.json', record)
    print('PASS: r27b differs from r27 only in native_menu.o/title_entry.o; bootMenu calls za_observer_menu')


def gate(project, previous, work, evidence, proof):
    incremental(project, work, evidence)
    record = base.read(evidence / 'build-verification.json')
    base.require(record.get('version') == 'r27b-play' and record.get('launcher_observer_call_verified') is True,
                 'r27b linked launcher observer proof missing')
    base.require(list(OBSERVER_CALL) in record['image']['required_calls'] and
                 list(OBSERVER_CALL) in record['image']['observed_calls'], 'Observer call receipt missing')
    base.gate(project, previous, work, evidence, proof)


def package(before, after, evidence):
    record = base.read(evidence / 'build-verification.json')
    accepted = base.read(evidence / 'pc-proof-accepted.json')
    gate(HERE.parents[1], Path(record['previous']), Path(record['work']), evidence, Path(accepted['proof_path']))
    # Run the original exact package-list/options checks before enriching its receipt.
    base.package(before, after, evidence)
    receipt_path = after.parent / 'r27-package-verification.json'
    receipt = base.read(receipt_path)
    receipt.update(version='r27b-play', supersedes_rejected_revision='r27-play',
                   launcher_observer_call_verified=True, incremental=record['incremental'])
    shipped = after.parent / 'evidence/r27'
    for name in ('incremental-verification.json', 'copy-verification.json'):
        shutil.copyfile(evidence / name, shipped / name)
        receipt['evidence'][str(Path('evidence/r27') / name)] = digest(shipped / name)
    base.write(receipt_path, receipt)
    print('PASS: r27b package accepted with unchanged source-matched MONEY proof; hardware acceptance pending')


def main():
    mode, *args = sys.argv[1:]
    paths = list(map(Path, args))
    if mode == 'snapshot' and len(paths) == 2:
        baseline(paths[0])
        base.write(paths[1], source_map(paths[0]))
    elif mode == 'copied' and len(paths) == 3:
        incremental(*paths, before_build=True)
    elif mode == 'verify' and len(paths) == 4:
        verify(*paths)
    elif mode == 'gate' and len(paths) == 5:
        gate(*paths)
    elif mode == 'package' and len(paths) == 3:
        package(*paths)
    else:
        raise SystemExit('Expected snapshot PROJECT OUT; copied PROJECT WORK EVIDENCE; '
                         'verify PROJECT R26P1 WORK EVIDENCE; gate PROJECT R26P1 WORK EVIDENCE PROOF; '
                         'package BASE_APP NEW_APP EVIDENCE')


if __name__ == '__main__':
    main()
