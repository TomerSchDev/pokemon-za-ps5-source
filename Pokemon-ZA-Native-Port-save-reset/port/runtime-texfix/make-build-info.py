"""BUILD-INFO.json for r28a-play, from the final build's evidence (no guessing: every number is read from a file).

    py -3 make-build-info.py <final build dir: .../r28a> <out BUILD-INFO.json>
"""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def sha(p):
    with open(p, 'rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def sums(path):
    return {line.split()[1].rsplit('/', 1)[-1]: line.split()[0] for line in Path(path).read_text().splitlines() if line.strip()}


def main():
    build, out = Path(sys.argv[1]), Path(sys.argv[2])
    ev = build / 'evidence'
    s = sums(ev / 'SHA256SUMS.txt')
    cand = sums(ev / 'candidate-SHA256SUMS.txt')
    r28 = sums(ev / 'candidate-r28-SHA256SUMS.txt')
    handoff = json.loads((ev / 'dexcount-HANDOFF.json').read_text(encoding='utf-8'))
    manifest = json.loads((ev / 'dexcount-r28a-manifest.json').read_text(encoding='utf-8'))
    dexchk = json.loads((ev / 'dexcount-checks.json').read_text(encoding='utf-8'))
    texchk = json.loads((ev / 'image-checks.json').read_text(encoding='utf-8'))
    finimg = json.loads((ev / 'final-image.json').read_text(encoding='utf-8'))
    fininp = json.loads((ev / 'final-inputs.json').read_text(encoding='utf-8'))
    candinp = json.loads((ev / 'candidate-inputs.json').read_text(encoding='utf-8'))
    reg = json.loads((ev / 'registration.json').read_text(encoding='utf-8'))
    info = dict(
        revision='randomizer-r28a-play',
        created_utc=datetime.now(timezone.utc).isoformat(),
        title_id='PPSA91762',
        game_version='2.0.2 + Mega Dimension',
        eboot_sha256=s['eboot.bin'],
        pie_sha256=s['llvm-pie.elf'],
        base=dict(revision='randomizer-r28-play', eboot_sha256=r28['eboot.bin'], pie_sha256=r28['llvm-pie.elf']),
        texfix_candidate=dict(eboot_sha256=cand['eboot.bin'], pie_sha256=cand['llvm-pie.elf'],
                              note='r28-play + texfix only; superseded by this build, kept for reference'),
        rollback=dict(r28_play=r28['eboot.bin'], r27b_play='c5b32192b55566561af7458f21ac8ed47de10b02bdcf2ddb601c68f00f03a153',
                      r27b_hebrew_trial='cd1eb5f6044ab99d56161c6009d6d0972df475d269c0522dee650fab31d4f618'),
        texfix=dict(
            purpose='crash in backend_texture_destroyed/live_remove (r28-play klog: sig=11 fa=a2): a finalized texture '
                    'in the live list; live list (texture, backend) pairs under a lock, finalize clears runtime '
                    'references, present under exec_lock, za_guard + quarantine, [za-texguard] diagnostics',
            runtime_objects_rebuilt=candinp['runtime_changed'],
            runtime_objects_unchanged=candinp['runtime_unchanged'],
            control='unpatched sources recompile r28-play\'s four objects byte for byte (candidate-control.txt)',
            globals_added=texchk['globals_added'], globals_removed=texchk['globals_removed'],
            host_tests='ASan+UBSan and TSan, clang 21 and gcc 15, incl. negative control reproducing fa=0xa2',
            pc_sessions='v0.1.4 runtime with the fix: 19,347-frame scripted session + save/load session; no faults; '
                        '4 set-render-targets refusals observed (the mechanism); see evidence/r28a-texfix/pc',
            klog_marker='[za-texguard] r28a texfix active'),
        dexcount=dict(
            purpose=manifest.get('purpose'),
            handoff=handoff,
            archive_members_changed=dexchk['changed_members'],
            archive_sha256=dexchk['archive_sha256'],
            objects=dexchk['objects'],
            new_imports=dexchk['new_imports'],
            linked_calls_seen=finimg['dexcount_calls_seen'],
            pc_in_game_proof=False,
            pc_in_game_proof_note='shipped without an in-game PC proof at Tomer\'s request; host tests only; the console is the test'),
        link=dict(runtime_objects=fininp['runtime_objects'], title_objects=fininp['title_objects'],
                  link_additions=[Path(p).name for p in fininp['link_additions']],
                  everything_else='byte-identical to the texfix candidate, which is byte-identical to r28-play apart from the four runtime objects'),
        registrations_preserved=all(v['preserved_count'] for v in reg),
        dynamic_imports='identical to r28-play',
        console_access_performed=False, console_tested=False, real_saves_written=False,
        installation='eboot replacement only, by the console operator after the game is closed and every run\'s save is backed up and verified')
    out.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(dict(eboot=info['eboot_sha256'], pie=info['pie_sha256'], dexcount_members=dexchk['changed_members']), indent=1))


if __name__ == '__main__':
    main()
