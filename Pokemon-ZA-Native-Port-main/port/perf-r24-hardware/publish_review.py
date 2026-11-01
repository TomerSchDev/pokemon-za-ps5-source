"""Package this thread's independent r24 review, never a console deployment.

Default: validate inputs and print the plan without writing deliverables or NAS.
--publish: create/reuse the exact local version, then copy four final files to
the fixed project NAS directory and verify SHA-256. Different files are never
overwritten. No game/runtime archive, save, raw capture or raw klog is included.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re
import zipfile

ROOT = Path(__file__).resolve().parents[2]
NAS_ROOT = Path(r'\\TheOnePiece\Software\PS5-13.60\Pokemon-ZA-Native-Port')
REVIEW_ROOTS = ('evidence/perf-r24-review', 'evidence/perf-r24-analysis-review',
                'evidence/perf-r24-config-review')
ALLOWED = {'.txt', '.json', '.py', '.c', '.h', '.inc', '.sh', '.patch'}
REFERENCES = ('port/perf-r24/HANDOFF-r24-perf-HE.md', 'port/perf-r24/README-HE.md',
              'artifacts/randomizer-r24-perf/BUILD-INFO.txt')
FINAL_NAMES = {'Review-HE.txt', 'Review.json', 'Review-Tools.zip', 'SHA256.json'}
MAX_FILE = 8 << 20
MAX_TOTAL = 64 << 20


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n').encode('utf-8')


def under(path, root):
    path.resolve().relative_to(root.resolve())


def regular(path, root=None):
    root = ROOT if root is None else root
    under(path, root)
    relative = path.absolute().relative_to(root.absolute())
    current = root
    for part in relative.parts:
        current = current / part
        st = current.lstat()
        if current.is_symlink() or getattr(st, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Reparse/symlink path refused: ' + str(current))
    if not path.is_file():
        raise ValueError('Not a regular file: ' + str(path))


def read_small(path):
    regular(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError('Review file too large: ' + str(path))
    data = path.read_bytes()
    data.decode('utf-8-sig')
    if len(data) > MAX_FILE:
        raise ValueError('Review file grew past limit: ' + str(path))
    return data


def allowed_review_file(path, native):
    rel = path.relative_to(ROOT)
    parts = tuple(p.casefold() for p in rel.parts)
    if any(p in ('__pycache__', '.git', 'originals', 'save', 'saves', 'save-backup', 'credentials')
           or p.startswith('run-20261029') or 'klog' in p for p in parts):
        return False
    snapshots = [p for p in rel.parents if p.name.startswith('native-review-')]
    if snapshots and (ROOT / snapshots[0]).resolve() != native.resolve():
        return False
    return path.suffix.lower() in ALLOWED or path.name in ('tests.log', 'hardware-helper-tests.log', 'publisher-tests.log')


def collect_sources(native):
    candidates = set((ROOT / 'port/perf-r24-hardware').glob('*.py'))
    for folder in REVIEW_ROOTS:
        base = ROOT / folder
        if not base.is_dir():
            raise ValueError('Missing required review directory: ' + folder)
        candidates.update(p for p in base.rglob('*') if p.is_file() and allowed_review_file(p, native))
    candidates.update(ROOT / name for name in REFERENCES)
    candidates.update((ROOT / 'port/perf-r24/patches').glob('*.patch'))
    result = {}
    total = 0
    for path in sorted(candidates, key=lambda p: p.relative_to(ROOT).as_posix()):
        data = read_small(path)
        if path.suffix.lower() == '.json':
            json.loads(data.decode('utf-8-sig'))
        total += len(data)
        if total > MAX_TOTAL:
            raise ValueError('Review source bundle exceeds 64 MiB')
        result[path.relative_to(ROOT).as_posix()] = data
    if not any(name.startswith(native.relative_to(ROOT).as_posix() + '/results/') for name in result):
        raise ValueError('Selected native review has no packaged result JSON files')
    return result


def validate_scope(metadata, report):
    if not isinstance(metadata, dict):
        raise ValueError('Report metadata must be an object')
    required = {'review_role': 'independent_review', 'hardware_executor': 'other_thread',
                'installed_by_this_thread': False, 'hardware_tests_run_by_this_thread': False}
    for key, value in required.items():
        if type(metadata.get(key)) is not type(value) or metadata[key] != value:
            raise ValueError('Independent-review scope required: ' + key)
    if metadata.get('status') not in ('complete', 'partial'):
        raise ValueError('Metadata status must be complete or partial')
    for statement in ('סקירה עצמאית', 'ההרצות בחומרה בוצעו במשימה אחרת'):
        if statement not in report:
            raise ValueError('Report must explicitly disclose: ' + statement)


def archive(sources):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in sorted(sources.items()):
            item = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            z.writestr(item, data)
    content = buf.getvalue()
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        if z.testzip() is not None or set(z.namelist()) != set(sources):
            raise ValueError('ZIP entry verification failed')
        for name, data in sources.items():
            if z.read(name) != data:
                raise ValueError('ZIP content verification failed: ' + name)
    return content


def prepare(report_path, metadata_path, native, stamp):
    if not re.fullmatch(r'\d{8}-\d{6}Z', stamp):
        raise ValueError('UTC stamp must be YYYYMMDD-HHMMSSZ')
    datetime.strptime(stamp, '%Y%m%d-%H%M%SZ')
    native = native.resolve()
    base = (ROOT / 'evidence/perf-r24-analysis-review').resolve()
    if native.parent != base or not re.fullmatch(r'native-review-\d{8}-\d{6}Z', native.name):
        raise ValueError('Native review must be a direct timestamped analysis-review snapshot')
    latest = max((p for p in base.glob('native-review-*') if p.is_dir()), key=lambda p:p.name)
    if native != latest.resolve():
        raise ValueError('Selected native review is not the latest snapshot: ' + str(latest))
    summary = read_small(native / 'summary.json')
    json.loads(summary.decode('utf-8-sig'))
    report_bytes = read_small(report_path)
    report = report_bytes.decode('utf-8-sig')
    meta_bytes = read_small(metadata_path)
    metadata = json.loads(meta_bytes.decode('utf-8-sig'))
    validate_scope(metadata, report)
    sources = collect_sources(native)
    if sources[native.relative_to(ROOT).as_posix() + '/summary.json'] != summary:
        raise ValueError('Native summary changed while preparing the package')
    leaf = 'ZA-r24-Independent-Review-' + stamp
    details = {'bundle': leaf, 'scope': 'Independent review; other thread executes hardware.',
               'report_metadata': metadata,
               'input_report': {'path': report_path.relative_to(ROOT).as_posix(), 'sha256': digest(report_bytes)},
               'input_metadata': {'path': metadata_path.relative_to(ROOT).as_posix(), 'sha256': digest(meta_bytes)},
               'native_review': {'path': native.relative_to(ROOT).as_posix(), 'summary_sha256': digest(summary)},
               'source_inventory': {name: {'bytes': len(data), 'sha256': digest(data)} for name,data in sources.items()},
               'excluded': ['game/runtime archives', 'saves', 'raw klog', 'raw PNG', 'originals/',
                            'earlier native-review snapshots', 'host executables', 'caches', 'credentials'],
               'console_access_by_publisher': False}
    files = {'Review-HE.txt': report.encode('utf-8'), 'Review.json': encoded(details),
             'Review-Tools.zip': archive(sources)}
    files['SHA256.json'] = encoded({name: {'bytes': len(data), 'sha256': digest(data)}
                                   for name,data in sorted(files.items())})
    for name, data in sources.items():
        if read_small(ROOT / name) != data:
            raise ValueError('Source changed while packaging: ' + name)
    if read_small(report_path) != report_bytes or read_small(metadata_path) != meta_bytes:
        raise ValueError('Report inputs changed while packaging')
    return leaf, files, len(sources)


def write_version(destination, files):
    if destination.exists():
        if (not destination.is_dir() or destination.is_symlink()
                or getattr(destination.lstat(), 'st_file_attributes', 0) & 0x400):
            raise ValueError('Version destination is not a normal directory')
        extra = {p.name for p in destination.iterdir()} - FINAL_NAMES
        if extra:
            raise ValueError('Version contains unexpected files: ' + repr(sorted(extra)))
    destination.mkdir(parents=True, exist_ok=True)
    # Validate every existing file before creating any missing file.
    for name, data in files.items():
        path = destination / name
        if path.exists():
            regular(path, destination)
            if path.read_bytes() != data:
                raise ValueError('Refusing to overwrite different version: ' + str(path))
    for name, data in files.items():
        path = destination / name
        if not path.exists():
            with path.open('xb') as out:
                out.write(data)
        if digest(path.read_bytes()) != digest(data):
            raise ValueError('Final file readback mismatch: ' + str(path))
    return {name: {'bytes': len(data), 'sha256': digest(data), 'readback_verified': True}
            for name,data in sorted(files.items())}


def publish(leaf, files):
    destination = ROOT / 'deliverables' / leaf
    under(destination, ROOT / 'deliverables')
    local = write_version(destination, files)
    result = {'local': str(destination), 'files': local, 'nas_completed': False}
    try:
        if not NAS_ROOT.is_dir():
            raise OSError('Project NAS directory is unavailable: ' + str(NAS_ROOT))
        nas = NAS_ROOT / leaf
        under(nas, NAS_ROOT)
        copied = write_version(nas, files)
        result.update(nas_completed=True, nas=str(nas), nas_files=copied)
    except (OSError, ValueError) as error:
        result['nas_error'] = str(error)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--report', type=Path, required=True)
    p.add_argument('--metadata', type=Path, required=True)
    p.add_argument('--native-review', type=Path, required=True)
    p.add_argument('--stamp', default=datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%SZ'))
    p.add_argument('--publish', action='store_true')
    a = p.parse_args()
    inputs = [(v if v.is_absolute() else ROOT/v).absolute() for v in (a.report,a.metadata,a.native_review)]
    leaf, files, count = prepare(*inputs, a.stamp)
    if a.publish:
        result = publish(leaf, files)
    else:
        result = {'validated': True, 'publish_requested': False, 'leaf': leaf,
                  'source_files': count, 'files': {n:{'bytes':len(b),'sha256':digest(b)} for n,b in files.items()},
                  'nas': str(NAS_ROOT / leaf)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
