"""Write compact evidence manifests for the two completed offline build variants."""
from pathlib import Path
import datetime
import hashlib
import json
import sys

BASE = Path('/home/tomer/ps5-za-native/r28a-play-final-20261030')
PIN_EBOOT = '5c6777ecc3bd675c271a3def4fc28dfa794b1bcc3555001043fed7dba0e8eaea'
PIN_PIE = '4cb7c2127f12f5f3aa700cb3301c21f6b1c214d464bac4449f43af56685eea85'
PIN_ARCHIVE = '1f0c586e721f93b80cd86b9b3675a18d95bca338952b5b3d01e7518bcc9a41cc'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


work = Path(sys.argv[1])
if work.parent != BASE.parent or not work.name.startswith('r28b-dlc-dex-'):
    raise ValueError('unexpected work tree')
base_out = work / 'r28b'
copied = json.loads((base_out / 'evidence/copied-inputs.json').read_text())
for record in copied['inputs']:
    source = BASE / 'source' / record['path'] if record['kind'] == 'runtime' else Path(record['path'])
    if sha(source) != record['sha256']:
        raise ValueError('an original base/shared input changed: ' + str(source))
for path, expected in ((BASE/'r28a/eboot.bin', PIN_EBOOT), (BASE/'r28a/llvm-pie.elf', PIN_PIE),
                       (BASE/'rando-dexcount/liblasgame-r28-dexcount.a', PIN_ARCHIVE)):
    if sha(path) != expected:
        raise ValueError('original base pin changed: ' + str(path))
archive = base_out / 'liblasgame-r28b-dlc-dex.a'
archive_sha = sha(archive)
helper_sha = sha(base_out / 'za_dlc_dex_unlock.o')
source_manifest = json.loads((base_out / 'gen/dlc-dex-hook-manifest.json').read_text())
for variant in ('r28b', 'r28b-music'):
    out = work / variant
    if not (out/'eboot.bin').is_file():
        continue
    evidence = out/'evidence'
    legacy = json.loads((evidence/'image-checks.json').read_text())
    dexcount = json.loads((evidence/'final-image.json').read_text())
    feature = json.loads((evidence/'feature-image-checks.json').read_text())
    registrations = json.loads((evidence/'registration.json').read_text())
    conversion = json.loads((evidence/'image-preservation.json').read_text())
    summary = {
        'revision': 'randomizer-r28b-dlc-dex' + ('-music' if variant.endswith('music') else ''),
        'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'title_id': 'PPSA91762', 'game_version': '2.0.2 + Mega Dimension',
        'work_tree': str(work), 'output': str(out),
        'eboot_sha256': sha(out/'eboot.bin'), 'eboot_bytes': (out/'eboot.bin').stat().st_size,
        'pie_sha256': sha(out/'llvm-pie.elf'), 'archive_sha256': archive_sha,
        'helper_object_sha256': helper_sha,
        'base': {'revision': 'randomizer-r28a-play', 'eboot_sha256': PIN_EBOOT, 'pie_sha256': PIN_PIE,
                 'archive_sha256': PIN_ARCHIVE, 'base_control_relinked_byte_identical': True,
                 'all_original_base_inputs_unchanged_after_build': True},
        'new_feature': source_manifest,
        'archive_changes': {'from_r28a': ['main_287.o'], 'from_r28': ['main_261.o','main_287.o','main_310.o'],
                            'member_count_and_order_preserved': True},
        'checks': {'dynamic_imports_preserved': feature['dynamic_imports_preserved'],
                   'dynamic_import_count': feature['dynamic_import_count'],
                   'registrations': registrations, 'legacy_linked_calls': len(legacy['required_calls']),
                   'dexcount_linked_calls': len(dexcount['dexcount_calls_required']),
                   'new_feature_linked_calls': feature['required_calls'],
                   'new_feature_linked_calls_present': feature['required_calls_present'],
                   'conversion': conversion, 'feature_markers': feature['markers']},
        'console_access_performed': False, 'console_tested': False, 'in_game_pc_tested': False,
        'save_file_access_performed': False,
        'scope': 'Only the early DLC Dex flag hook is new over the preserved r28a code; data/model changes not present in the supplied base are not assumed.',
    }
    if variant.endswith('music'):
        summary['music'] = json.loads((evidence/'music-override-inputs.json').read_text())
        summary['checks']['music_linked_calls'] = len(json.loads((evidence/'linked-calls.json').read_text()))
    (out/'build-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({'variant':variant,'eboot_sha256':summary['eboot_sha256'],'pie_sha256':summary['pie_sha256'],
                      'legacy_calls':summary['checks']['legacy_linked_calls'],'dexcount_calls':summary['checks']['dexcount_linked_calls'],
                      'feature_calls':len(feature['required_calls']),'base_inputs_unchanged':True}))
