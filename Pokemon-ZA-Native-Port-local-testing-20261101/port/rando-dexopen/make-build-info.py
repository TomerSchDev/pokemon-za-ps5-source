"""BUILD-INFO.json for r28b-play, from the build's evidence (no guessing: every number is read from a file).

    py -3 make-build-info.py <build dir: .../r28b> <out BUILD-INFO.json> [--repro <reproducibility.json>] [--host-tests <log>]
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sums(path):
    return {Path(line.split()[1]).name: line.split()[0] for line in Path(path).read_text().splitlines() if line.strip()}


def main():
    build, out = Path(sys.argv[1]), Path(sys.argv[2])
    repro = Path(sys.argv[sys.argv.index('--repro') + 1]) if '--repro' in sys.argv else None
    hostlog = Path(sys.argv[sys.argv.index('--host-tests') + 1]) if '--host-tests' in sys.argv else None
    ev = build / 'evidence'
    s = sums(ev / 'SHA256SUMS.txt')
    r28a = sums(ev / 'r28a-SHA256SUMS.txt')
    r28a_info = json.loads(Path(__file__).resolve().parents[2].joinpath('artifacts/randomizer-r28a-play/BUILD-INFO.json').read_text(encoding='utf-8'))
    manifest = json.loads((ev / 'dexopen-r28b-manifest.json').read_text(encoding='utf-8'))
    dexchk = json.loads((ev / 'dexopen-checks.json').read_text(encoding='utf-8'))
    img = json.loads((ev / 'image-r28b.json').read_text(encoding='utf-8'))
    r28chk = json.loads((ev / 'image-checks.json').read_text(encoding='utf-8'))
    inp = json.loads((ev / 'inputs.json').read_text(encoding='utf-8'))
    basecopy = json.loads((ev / 'base-copy.json').read_text(encoding='utf-8'))
    reg = json.loads((ev / 'registration.json').read_text(encoding='utf-8'))
    info = dict(
        revision='randomizer-r28b-play',
        created_utc=datetime.now(timezone.utc).isoformat(),
        title_id='PPSA91762',
        game_version='2.0.2 + Mega Dimension',
        eboot_sha256=s['eboot.bin'],
        pie_sha256=s['llvm-pie.elf'],
        base=dict(revision='randomizer-r28a-play', eboot_sha256=r28a['eboot.bin'], pie_sha256=r28a['llvm-pie.elf'],
                  tree='/home/tomer/ps5-za-native/r28a-play-final-20261030 (read-only)'),
        rollback=dict(r28a_play=r28a['eboot.bin'], r28_play=r28a_info['base']['eboot_sha256'],
                      r27b_play=r28a_info['rollback']['r27b_play']),
        inherited_from_r28a=dict(
            texfix=r28a_info['texfix']['purpose'],
            texfix_klog_marker=r28a_info['texfix']['klog_marker'],
            dexcount=r28a_info['dexcount']['purpose'],
            dexcount_archive_sha256=basecopy['dexcount_archive_sha256'],
            dexcount_object_sha256=basecopy['dexcount_object_sha256'],
            note='the 64 runtime objects, the title objects and za_dexcount.o are r28a\'s files byte for byte (base-copy.json, inputs.json)'),
        dexopen=dict(
            purpose=manifest['purpose'],
            design='FLAG_DLC_DEX_ENABLE is never written; its two translated readers treat it as set whenever the flag manager is ready: '
                   'f_70008d4178 DLC::IsHyperspaceDexEnabled returns readiness alone, f_700033f8d8 Pokedex::GetMegaDexCount forces its '
                   '"include Hyperspace rows" filter; one switch (za_dexopen_set_enabled, default on) restores both originals',
            game_units=manifest['game_units'],
            archive_base_sha256=dexchk['base_archive_sha256'],
            archive_sha256=dexchk['archive_sha256'],
            archive_members=dexchk['members'],
            archive_members_changed=dexchk['changed_members'],
            object_sha256=dexchk['object_sha256'],
            object_imports=dexchk['object_undefined'],
            patched_units_new_imports=dexchk['patched_units_new_imports'],
            linked_calls=img['required_calls'][:2],
            globals_added=img['globals_added'],
            klog_lines=dict(
                first_use='[dexopen] DLC::IsHyperspaceDexEnabled (f_70008d4178): FLAG_DLC_DEX_ENABLE=0 -> 1 (forced: Hyperspace Pokedex list open) (call N)',
                mega_dex='[dexopen] Pokedex::GetMegaDexCount (f_700033f8d8): FLAG_DLC_DEX_ENABLE=0 -> 1 (forced: Hyperspace Pokedex list open) (call N)',
                not_ready='[dexopen] <site>: flag manager not ready, FLAG_DLC_DEX_ENABLE not read -> 0 (call N)',
                note='one line per site on first use, then only when the game\'s own flag value changes; also on stderr'),
            host_tests=(' | '.join(l.strip() for l in hostlog.read_text(encoding='utf-8', errors='replace').splitlines()
                                   if l.startswith(('test_dexopen:', 'patcher tests passed', 'ALL HOST TESTS')))
                        if hostlog else 'see port/rando-dexopen/evidence/host-tests.log'),
            pc_in_game_proof=False,
            pc_in_game_proof_note='shipped without an in-game PC proof at Tomer\'s decision for this line of fixes; host tests only; the console is the test',
            data_side='the flag name appears in exactly two data files of one ik_event pack (dimension task point rate tables), nowhere else by name or FNV-1a hash; see evidence/data-side/'),
        link=dict(runtime_objects=inp['runtime_objects'], title_objects=inp['title_objects'],
                  link_additions=[Path(p).name for p in inp['link_additions']],
                  everything_else='byte-identical to r28a-play (inputs.json, base-copy.json)'),
        registrations_preserved=all(v['preserved_count'] for v in reg),
        dynamic_imports='identical to r28a-play and r28-play (%d)' % img['dynamic_imports'],
        r28_image_checks=dict(required_calls_linked=len(r28chk['required_calls']), globals_added_vs_r28=r28chk['globals_added']),
        reproducibility=dict(
            files=(json.loads(repro.read_text(encoding='utf-8')) if repro else 'not recorded'),
            note='two builds from the same inputs into two new trees (r28b-play-20261030, r28b-play-20261030-repro); the five '
                 'outputs matched; the record is the sha256sum lines of both build logs (evidence/build.log, evidence/repro-build-2.log). '
                 'The second tree was removed afterwards: the host disk (C:) filled during its last writes and WSL lost those blocks; '
                 'the first tree was re-verified with sha256sum -c.'),
        console_access_performed=False, console_tested=False, real_saves_written=False,
        installation='eboot replacement only, by the console operator after the game is closed and every run\'s save is backed up and verified')
    out.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(eboot=info['eboot_sha256'], pie=info['pie_sha256'], dexopen_members=dexchk['changed_members'],
                          globals_added=img['globals_added']), indent=1))


if __name__ == '__main__':
    main()
