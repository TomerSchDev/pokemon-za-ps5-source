"""Package the installed r14 overlay and explicit backups into a handoff folder.

No console writes. Existing game data and the user's current save are excluded.
Every archived entry is read back and SHA-256 checked before reporting success.
"""
from pathlib import Path
import hashlib
import json
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'artifacts/title-r14-hardware/PPSA91761'
CACHE = Path(r'\\wsl.localhost\Ubuntu\home\tomer\ps5-za-native\title-r1-20261027\shaders')
EXPECTED = '093b5337f1de3ad7a9fb000d3b1b49550ead6080179daa01b9fb3d1e63503d10'


def sha(stream):
    digest = hashlib.sha256()
    for block in iter(lambda: stream.read(1 << 20), b''):
        digest.update(block)
    return digest.hexdigest()


def archive(target, files, texts):
    if target.exists():
        raise FileExistsError(target)
    manifest = {}
    with zipfile.ZipFile(target, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
        for name, path in sorted(files.items()):
            with path.open('rb') as f:
                digest = sha(f)
            manifest[name] = {'bytes': path.stat().st_size, 'sha256': digest}
            z.write(path, name)
        for name, text in texts.items():
            data = text.encode('utf-8')
            manifest[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            z.writestr(name, data)
        z.writestr('MANIFEST.json', json.dumps(manifest, indent=2))
    with zipfile.ZipFile(target) as z:
        for name, record in manifest.items():
            with z.open(name) as f:
                assert sha(f) == record['sha256'], name
    with target.open('rb') as f:
        digest = sha(f)
    return {'path': target.name, 'bytes': target.stat().st_size,
            'sha256': digest, 'verified_entries': len(manifest)}


def main():
    dest = Path(sys.argv[1]).resolve()
    if not dest.is_dir() or dest.parent != ROOT / 'deliverables':
        raise ValueError('Expected an existing versioned handoff folder')
    with (APP / 'eboot.bin').open('rb') as f:
        assert sha(f) == EXPECTED
    files = {'PPSA91761/eboot.bin': APP / 'eboot.bin'}
    for directory in ('sce_sys', 'sce_module', 'fonts'):
        for p in (APP / directory).rglob('*'):
            if p.is_file():
                files['PPSA91761/' + p.relative_to(APP).as_posix()] = p
    shaders = sorted(CACHE.glob('*.spv'))
    assert len(shaders) >= 941
    for p in shaders:
        files['PPSA91761/cache/spirv/' + p.name] = p
    readme = (
        'Pokemon Legends: Z-A native PS5 r14 incremental backup/update.\n'
        'This version is already installed on the tested PS5. No action is needed.\n'
        'For the existing PPSA91761 installation only; NOT a standalone game.\n'
        'Unchanged game assets (~6 GB) and save-import inputs are intentionally absent.\n'
        'Preserve the existing game/ folder, download0 save, import marker and newer cache entries.\n'
        'Close the title and back up the installed binary before any manual restore.\n'
        'Use the scoped update-title.py with the current installed SHA for binary deployment.\n'
        'The archive is an overlay; never delete the installed app folder or replace app.db.\n'
        'Metadata in sce_sys is included for backup; see stage-branding.py for scoped copies.\n'
        'Frame profile stays at original 30 FPS. A stable 60 FPS mode is not verified.\n'
        f'Portable SPIR-V entries in this snapshot: {len(shaders)}. Not full-game coverage.\n'
        'Unseen shaders still need shader-host.py on the PC; its sessions are bounded.\n'
        'PS5 pipeline cache is checkpointed every 10 seconds and survives Close Game.\n'
        'A separate device-specific cache backup is included alongside this update.\n'
    )
    records = [archive(dest / 'ZA-Native-r14-Incremental-Update.zip', files,
                       {'README.txt': readme, 'PPSA91761/performance-profile.txt': '30\n'})]
    source = ROOT / 'evidence/title-r12-save-transfer-20261027-185543Z'
    names = ['prepared-city-tepig.main', 'ps5-original-backup.main', 'imported-readback.main',
             'import.done', 'manifest.json', 'verified-import.json']
    records.append(archive(dest / 'ZA-Native-City-Save-Import-and-Original-Backup.zip',
        {'save-transfer/' + name: source / name for name in names},
        {'README.txt': 'Historical save-transfer backup, not the current gameplay save.\n'
         'ps5-original-backup.main is the authoritative native save before importing the prepared city save.\n'
         'prepared-city-tepig.main is the PC city/Tepig Mission 03 save imported once in r12.\n'
         'Do not restore over newer progress or remove the native completion marker.\n'}))
    records.append(archive(dest / 'ZA-Native-r14-PS5-Pipeline-Cache-Backup.zip',
        {name: ROOT / 'evidence' / name for name in (
            'title-r14-repeat-pipeline-cache.bin', 'title-r14-repeat-pipeline-cache.json')},
        {'README.txt': 'Snapshot from this PS5 and its current RADV build. This is a backup only.\n'
         'The live runtime already keeps and updates its own cache; no restore is required.\n'
         'Do not copy a PC GPU pipeline cache onto the PS5 or overwrite a newer live cache.\n'
         'Compatibility requires matching Vulkan vendor/device and pipelineCacheUUID.\n'}))
    record = {'archives': records, 'spirv_entries': len(shaders), 'native_sha256': EXPECTED}
    (dest / 'R14-DELIVERABLES-VERIFIED.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
