"""Bounded local DLC00 candidate; existing RomFS/FlatBuffers readers only.

Game bytes are written only to NEW private OUT. Evidence is hashes and a change
contract, never decoded game content. Requires the canonical PC turn.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time


def digest(b):
    return hashlib.sha256(b).hexdigest()


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    obj = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    return obj


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    for key in ('repo', 'story-tools', 'lab-tools', 'romfs', 'out', 'evidence'):
        ap.add_argument('--' + key, type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists() or a.evidence.exists():
        ap.error('OUT and EVIDENCE must be new')
    if not a.out.resolve().is_relative_to(Path(os.environ['TEMP']).resolve()):
        ap.error('Game-byte output must be a private local TEMP directory')
    queue = load('canonical_queue', a.repo / 'tools/console-install-queue/console_queue.py')
    agent, ticket, token = (os.environ.get('PC_TEST_' + k, '') for k in ('AGENT', 'TICKET', 'TOKEN'))
    if not all((agent, ticket, token)):
        ap.error('Canonical PC turn required')
    board = queue.Board(resource='pc')
    board.check(agent, ticket, token)
    sys.path.insert(0, str(a.story_tools))
    sys.path.insert(0, str(a.lab_tools))
    import fbedit as F
    import story_shuffle as S
    from za_romfs import Game
    started = time.monotonic()
    game = Game(str(a.romfs))
    board.heartbeat(agent, ticket, token)
    prefix = 'ik_event/bin/'
    paths = {'main': prefix + 'trigger/main/trigger_main_04.bin',
             'entry': prefix + 'trigger/main/trigger_main_10.bin',
             'quest': prefix + 'quest/sub_quest.bin',
             'phase': prefix + 'phase/phase.bin'}
    original = {key: game.read(path) for key, path in paths.items()}
    if not all(len(data) < 1024 * 1024 for data in original.values()):
        raise ValueError('Reviewed bounded table exceeds1MiB')
    mainroot = F.root(original['main'], 'TrigRoot')
    oldtree = F.to_py(mainroot)
    entryroot = F.root(original['entry'], 'TrigRoot')
    # Reviewed original DLC entrance, retaining the AoC gate exactly as stored.
    source = entryroot.kids[0].items[5].kids[0]
    assert source.i32(0) == 5 and S.sv(source.kids[1]) == ['pos_t1_Ev_m10_0200']
    case = source.kids[2].items[0].clone()
    assert S.cond_list(case) == [('phase_condition', 1, ['100200']), ('is_disable_aoc', 2, [])]
    assert [len(g.kids[0].items) for g in case.kids[0].items] == [1, 1]
    assert S.events(S.cmd_list(case)) == ['Ev_m10_0200', 'Ev_d00_0000']
    phase = case.kids[0].items[0].kids[0].items[0]
    S.set_vstr(phase, 2, ['40100'])
    cmds = case.kids[1].items[0].kids[0]
    cmds.items = [cmds.items[1]]
    assert S.cmd_args(cmds.items[0]) == ['Ev_d00_0000', '0']
    # Use a real loaded map-transition callback rather than MAIN10 position data.
    callback = mainroot.kids[0].items[15].clone()
    trigger = callback.kids[0]
    assert trigger.i32(0) == 2 and S.sv(trigger.kids[1]) == ['t1', 'EV_CMN_TRANSITION_IN']
    trigger.kids[2].items = [case]
    # Guard against replay; clone a real flag-condition table to preserve layout.
    candidates = []
    def collect(t, ancestors):
        if t.type == 'Cond' and 0 in t.kids and t.kids[0].text() == 'flag_condition' and t.i32(1) == 2:
            candidates.append(t)
    S.walk(mainroot, collect)
    assert candidates, 'Expected reviewed false-flag condition template'
    guard = candidates[0].clone()
    S.set_vstr(guard, 2, ['flag_Ev_d00_0000'])
    group = case.kids[0].items[0].clone()
    group.kids[0].items = [guard]
    case.kids[0].items.append(group)
    # Native builder: inner group uses OR(mode1); outer groups use AND(mode0).
    # Preserve singleton groups: phase AND AoC AND not-already-started.
    assert [len(g.kids[0].items) for g in case.kids[0].items] == [1, 1, 1]
    mainroot.kids[0].items.append(callback)
    w = F.Writer()
    w.put(mainroot, root=True)
    main_bytes = bytes(w.b)
    checkroot = F.root(main_bytes, 'TrigRoot')
    projected = F.to_py(checkroot)
    assert projected[0][:-1] == oldtree[0]
    assert F.to_py(checkroot.kids[0].items[-1]) == F.to_py(callback)
    assert [len(g.kids[0].items) for g in checkroot.kids[0].items[-1].kids[0].kids[2].items[0].kids[0].items] == [1, 1, 1]
    assert S.cond_list(checkroot.kids[0].items[-1].kids[0].kids[2].items[0]) == [
        ('phase_condition', 1, ['40100']), ('is_disable_aoc', 2, []),
        ('flag_condition', 2, ['flag_Ev_d00_0000'])]
    assert S.events(S.cmd_list(checkroot.kids[0].items[-1].kids[0].kids[2].items[0])) == ['Ev_d00_0000']
    sf = S.SlotFile(original['quest'])
    slots = S.quest_start_slots(sf, 'sub_0122')
    assert [sf.get(slot) for slot in slots] == ['101000', 'flag_Ev_d00_0000']
    assert [(op, [sf.get(x) for x in ss]) for _, op, ss in sf.conds('phase_condition') if slots[0] in ss] == [(5, ['101000'])]
    sf.put(slots[0], '40100')
    quest_bytes = bytes(sf.w.b)
    sfcheck = S.SlotFile(quest_bytes)
    assert [sfcheck.get(slot) for slot in S.quest_start_slots(sfcheck, 'sub_0122')] == ['40100', 'flag_Ev_d00_0000']
    differences = [i for i, (x, y) in enumerate(zip(original['quest'], quest_bytes)) if x != y]
    assert all(slots[0] <= i < slots[0] + 4 for i in differences)
    assert len(quest_bytes) >= len(original['quest'])
    phase40100 = [r for r in F.root(original['phase'], 'PhaseRoot').kids[0].items if r.i32(0) == 40100]
    assert len(phase40100) == 1
    mega = [c for c in phase40100[0].kids[2].items if c.i32(0) == 8 and S.cmd_args(c) == ['flag_megaevo_disable', 'FALSE']]
    assert len(mega) == 1, 'Capability init must match actual phase40100 command'
    outputs = {paths['main']: main_bytes, paths['quest']: quest_bytes}
    board.check(agent, ticket, token)
    for relative, data in outputs.items():
        dst = a.out / 'early-dlc00' / 'romfs' / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
    result = {'schema': 'za-controlled-early-dlc00-1', 'ticket': ticket,
              'classification': 'EXPERIMENTAL_NOT_RELEASE', 'runtime_verdict': 'NOT_RUN',
              'original_romfs_dlc00_present': game.has(prefix + 'trigger/dlc/trigger_dlc_00.bin'),
              'inputs': {paths[k]: {'sha256': digest(v), 'bytes': len(v)} for k, v in original.items()},
              'outputs': {k: {'sha256': digest(v), 'bytes': len(v)} for k, v in outputs.items()},
              'source_reader_pins': {str(p): digest(p.read_bytes()) for p in [a.story_tools / 'fbedit.py', a.story_tools / 'story_shuffle.py', a.lab_tools / 'za_romfs.py']},
              'contract': {'main_phase': 40100, 'entry_callback': 't1/EV_CMN_TRANSITION_IN',
                           'entry_events': ['Ev_d00_0000'], 'omitted_postgame_event': 'Ev_m10_0200',
                           'aoc_predicate_preserved': True, 'idempotence_flag': 'flag_Ev_d00_0000',
                           'boolean_tree': {'outer': 'AND', 'inner': 'OR', 'group_sizes': [1, 1, 1],
                                            'provenance': ['main_061.c:14486', 'main_061.c:14627',
                                                           'main_472.c:21461', 'main_472.c:21502',
                                                           'main_472.c:21120-21173']},
                           'quest': 'sub_0122', 'quest_threshold': {'old': 101000, 'new': 40100},
                           'quest_other_bytes_unchanged': True, 'existing_main_wrappers_unchanged': True,
                           'dlc_phase_writes': 0, 'main_phase_writes': 0, 'dlc_completion_writes': 0,
                           'capability_init_source': {'phase': 40100, 'cmd': 8, 'identifier': 'flag_megaevo_disable', 'value': 'FALSE'}},
              'assertions': ['intro event completes in actual runtime', 'sub_0122 becomes active',
                             'first objective completed by gameplay, not fixture writes',
                             'MAIN counter remains40100', 'no unexplained fault'],
              'unknowns': ['AoC delegate status3 meaning', 'omitted MAIN10 event effects',
                           'transition callback invoked on saved city load', 'NPC/map prerequisites',
                           'native DLC phase advancement and save persistence'],
              'elapsed_seconds': time.monotonic() - started}
    a.evidence.parent.mkdir(parents=True, exist_ok=True)
    a.evidence.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'evidence': str(a.evidence), 'dlc00_exists': result['original_romfs_dlc00_present'], 'seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()
