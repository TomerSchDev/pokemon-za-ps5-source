"""Package only measurement evidence; no game binaries, save contents or credentials."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main(out, destination):
    state = json.loads((out / 'state.json').read_text())
    assert len(state['phases']) == 13
    assert state['current']['build'] == 'r23c' and state.get('configs_restored_at')
    final = json.loads((out / 'final-state.json').read_text())
    assert final['installed_sha256_verified'] and final['save_unchanged'] and final['original_configs_verified']
    destination.mkdir(parents=True, exist_ok=False)
    results = out / 'Results-r24-20261029.json'
    shutil.copy2(results, destination / results.name)
    entries = {results.name: results, 'raw/all.klog.log': out / 'all.klog.log',
               'raw/final-state.json': out / 'final-state.json',
               'raw/save-preservation.json': out / 'save-backup/verification.json'}
    for boot in state['boots']:
        for name in ('identity.json', 'deploy.json', 'close.json', 'boot.klog.log'):
            path = out / boot['label'] / name
            if path.exists():
                entries['raw/' + str(path.relative_to(out)).replace('\\', '/')] = path
    for phase in state['phases']:
        folder = (out / phase['csv']).parent
        for path in folder.iterdir():
            assert path.is_file() and path.suffix in ('.json', '.csv', '.png'), path
            entries['raw/' + str(path.relative_to(out)).replace('\\', '/')] = path
    for name in ('hardware_run.py', 'summarize_hardware.py', 'analyze_r24.py', 'package_hardware_results.py', 'HANDOFF-r24-perf-HE.md', 'README-HE.md'):
        entries['tools/' + name] = ROOT / 'port/perf-r24' / name
    manifest = [{'path': key, 'bytes': value.stat().st_size, 'sha256': digest(value)} for key, value in sorted(entries.items())]
    archive = destination / 'r24-hardware-evidence-20261029.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for key, path in sorted(entries.items()):
            z.write(path, key)
        z.writestr('Manifest.json', json.dumps(manifest, indent=2) + '\n')
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
    files = [destination / results.name, archive]
    sums = destination / 'SHA256SUMS.txt'
    sums.write_text(''.join(digest(path) + '  ' + path.name + '\n' for path in files), encoding='ascii')
    print(json.dumps(dict(directory=str(destination), files=[dict(name=p.name, bytes=p.stat().st_size, sha256=digest(p)) for p in (*files, sums)],
                          archive_entries=len(entries) + 1, archive_crc_verified=True), indent=2), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('out', type=Path); p.add_argument('destination', type=Path)
    a = p.parse_args(); main(a.out.resolve(), a.destination.resolve())
