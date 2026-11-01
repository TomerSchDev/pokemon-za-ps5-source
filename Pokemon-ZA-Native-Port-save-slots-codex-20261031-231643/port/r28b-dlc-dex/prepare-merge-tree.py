"""Copy all explicit linked inputs of a pinned existing build into a fresh merge tree.

Run on WSL through prepare-merge.sh. No existing input is edited and no build is
selected from a version label alone. A conflicting main_287 fails later at the
byte-identical control instead of replacing another feature's code.
"""
from pathlib import Path
import argparse
import hashlib
import json
import shlex
import shutil
import subprocess

ALLOWED = Path('/home/tomer/ps5-za-native')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(options):
    runtime_tree = options.runtime_tree.resolve(strict=True)
    base_out = options.base_out.resolve(strict=True)
    base_archive = options.archive.resolve(strict=True)
    work = options.work.resolve()
    if work.parent != ALLOWED or not work.name.startswith('r28b-dlc-dex-') or work.exists():
        raise ValueError('work must be a new r28b-dlc-dex-* tree under the approved root')
    if sha(base_out / 'eboot.bin') != options.eboot_sha256:
        raise ValueError('base eboot does not match its explicit expected hash')
    if sha(base_out / 'llvm-pie.elf') != options.pie_sha256:
        raise ValueError('base PIE does not match its explicit expected hash')
    if sha(base_archive) != options.archive_sha256:
        raise ValueError('base archive does not match its explicit expected hash')
    project = Path(__file__).resolve().parents[2]
    relative_runtime = (base_out / 'evidence/runtime-inputs.txt').read_text().split()
    extra = shlex.split((base_out / 'evidence/link-inputs.txt').read_text())
    linked_files = [Path(token) for token in extra if token.endswith(('.o', '.a'))]
    for relative in relative_runtime:
        source = (runtime_tree / 'source' / relative).resolve(strict=True)
        if not source.is_relative_to(runtime_tree / 'source'):
            raise ValueError('runtime object escapes the supplied source tree')
    if any(not path.is_file() or any(c.isspace() for c in str(path)) for path in linked_files):
        raise ValueError('linked object/library is missing or its path is unsupported')
    if options.audit_only:
        print(json.dumps({'audit_only': True, 'base_pins_match': True,
                          'runtime_objects': len(relative_runtime), 'extra_files': len(linked_files),
                          'new_work_tree_available': str(work), 'output_written': False}))
        return
    work.mkdir()
    out = work / 'r28b'
    for directory in ('evidence', 'src', 'control', 'inputs', 'base'):
        (out / directory).mkdir(parents=True)
    (work / 'source').mkdir()
    # Headers, runtime source and link tools only; no game data or caches.
    for relative in ('runtime', 'tools/ps5'):
        source = runtime_tree / 'source' / relative
        destination = work / 'source' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cp', '-a', '--reflink=auto', str(source), str(destination)], check=True)
    records = []
    for relative in relative_runtime:
        source = runtime_tree / 'source' / relative
        destination = work / 'source' / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        records.append({'kind': 'runtime', 'base': str(source), 'copy': str(destination), 'sha256': sha(source)})
    mapped = []
    index = 0
    for token in extra:
        if not token.endswith(('.o', '.a')):
            mapped.append(token)
            continue
        source = Path(token)
        destination = out / 'inputs' / f'{index:03d}' / source.name
        destination.parent.mkdir()
        shutil.copy2(source, destination)
        records.append({'kind': 'extra', 'base': str(source), 'copy': str(destination), 'sha256': sha(source)})
        mapped.append(str(destination))
        index += 1
    archive_copy = out / 'base/liblasgame-base.a'
    subprocess.run(['cp', '--reflink=auto', str(base_archive), str(archive_copy)], check=True)
    records.append({'kind': 'archive', 'base': str(base_archive), 'copy': str(archive_copy), 'sha256': sha(base_archive)})
    for record in records:
        if sha(Path(record['copy'])) != record['sha256']:
            raise ValueError('copied input differs: ' + record['base'])
    for filename, source in {
        'verify-r28a.py': project / 'port/runtime-texfix/verify-r28a.py',
        'verify-registration.py': project / 'port/local-shader-r19/verify-registration.py',
        'verify-image.py': project / 'port/title/verify-image.py',
        'compare_ar.py': project / 'port/rando-dexcount/ps5/compare_ar.py',
    }.items():
        shutil.copy2(source, out / 'src' / filename)
    (out / 'shader-probe-r18').mkdir()
    shutil.copy2(project / 'port/shader-probe-r18/verify-image.py', out / 'shader-probe-r18/verify-image.py')
    evidence = out / 'evidence'
    (evidence / 'runtime-inputs.txt').write_text('\n'.join(relative_runtime) + '\n')
    (evidence / 'control-link-inputs.txt').write_text(' '.join(mapped) + '\n')
    config = {'runtime_tree': str(runtime_tree), 'base_out': str(base_out), 'base_archive': str(base_archive),
              'base_archive_copy': str(archive_copy), 'expected_eboot_sha256': options.eboot_sha256,
              'expected_pie_sha256': options.pie_sha256, 'expected_archive_sha256': options.archive_sha256,
              'work': str(work), 'copied_inputs': records, 'all_identical': True,
              'contains_unrecognized_model_changes': 'preserved from explicit linked inputs; not inferred from a label'}
    (evidence / 'merge-base.json').write_text(json.dumps(config, indent=2) + '\n')
    print(json.dumps({'work': str(work), 'copied_link_inputs': len(records), 'all_identical': True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-tree', 'base-out', 'archive', 'work'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('eboot-sha256', 'pie-sha256', 'archive-sha256'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--audit-only', action='store_true', help='Validate base pins/inputs without copying or creating output')
    prepare(parser.parse_args())
