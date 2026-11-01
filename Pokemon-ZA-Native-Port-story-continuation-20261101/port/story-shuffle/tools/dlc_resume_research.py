"""Read-only research projection of existing DLC return/resume gates.

No writer, patch generation, save access, game process, or bytecode output.
The historical readers are identified in the output; this is not build approval.
"""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
import fbedit as F
import story_shuffle as S


def digest(data):
    return hashlib.sha256(data).hexdigest()


def groups(node):
    return [[{'kind': c.kids[0].text() if 0 in c.kids else None,
              'wire_operator': c.i32(1),
              'all_arguments': S.sv(c.kids[2]) if 2 in c.kids else []}
             for c in g.kids[0].items] for g in node.items]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--romfs', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    a = ap.parse_args()
    if a.out.exists():
        ap.error('Research output must be new')
    game = S.Romfs(str(a.romfs))
    inputs, returns, dlc1_cases, boundaries = {}, [], [], []
    counts = Counter()
    for chapter in range(1, 10):
        path = 'ik_event/bin/trigger/dlc/trigger_dlc_%02d.bin' % chapter
        data = game.read(path)
        if len(data) > 1024 * 1024:
            raise ValueError('Bounded research input exceeded')
        inputs[path] = {'bytes': len(data), 'sha256': digest(data)}
        root = F.root(data, 'TrigRoot')
        for wi, wrap in enumerate(root.kids[0].items):
            t = wrap.kids.get(0)
            if t is None:
                continue
            for ci, case in enumerate(t.kids.get(2, F.Vec([], 'Case')).items):
                cmds = S.cmd_list(case)
                cs = [{'index': i, 'kind': c.i32(0), 'args': S.cmd_args(c)} for i, c in enumerate(cmds)]
                facts = {'input': path, 'wrapper': wi, 'case': ci,
                         'trigger_kind': t.i32(0),
                         'trigger_args': S.sv(t.kids[1]) if 1 in t.kids else [],
                         'condition_groups': groups(case.kids[0]) if 0 in case.kids else [],
                         'events': S.events(cmds),
                         'command_kind_sequence': [c.i32(0) for c in cmds],
                         'state_effects': [c for c in cs if c['kind'] in (8, 9, 111, 112, 117)],
                         'maps': [c for c in cs if c['kind'] in (6, 7, 44, 50, 83)]}
                for c in cs:
                    if c['kind'] == 9 and c['args']:
                        counts['CMD9_' + c['args'][0]] += 1
                    if c['kind'] in (111, 112):
                        counts['CMD_' + str(c['kind'])] += 1
                if any(c['kind'] == 6 and c['args'][:1] == ['t1'] for c in cs):
                    returns.append(facts)
                if chapter == 1:
                    dlc1_cases.append(facts)
                if any(c['kind'] in (111, 112) for c in cs):
                    boundaries.append(facts)
    prologue_cases, generic_exit_cases = [], []
    for path in ('ik_event/bin/trigger/main/trigger_main_10.bin',
                 'ik_event/bin/trigger/global/trigger_global.bin'):
        data = game.read(path)
        if len(data) > 4 * 1024 * 1024:
            raise ValueError('Bounded research input exceeded')
        inputs[path] = {'bytes': len(data), 'sha256': digest(data)}
        root = F.root(data, 'TrigRoot')
        for wi, wrap in enumerate(root.kids[0].items):
            t = wrap.kids.get(0)
            if t is None:
                continue
            ta = S.sv(t.kids[1]) if 1 in t.kids else []
            for ci, case in enumerate(t.kids.get(2, F.Vec([], 'Case')).items):
                cmds = S.cmd_list(case)
                events = S.events(cmds)
                prologue = path.endswith('main_10.bin') and any(e.startswith('Ev_d00_') for e in events)
                exitcase = 'Ev_sys_izigen_exit' in events or 'Ev_sys_izigen_exit' in ta
                if not (prologue or exitcase):
                    continue
                cs = [{'index': i, 'kind': c.i32(0), 'args': S.cmd_args(c)} for i, c in enumerate(cmds)]
                fact = {'input': path, 'wrapper': wi, 'case': ci,
                        'trigger_kind': t.i32(0), 'trigger_args': ta,
                        'condition_groups': groups(case.kids[0]) if 0 in case.kids else [],
                        'events': events, 'command_kind_sequence': [c.i32(0) for c in cmds],
                        'state_effects': [c for c in cs if c['kind'] in (8, 9, 111, 112, 117, 137)],
                        'maps': [c for c in cs if c['kind'] in (6, 7, 44, 50, 83)]}
                if prologue:
                    prologue_cases.append(fact)
                if exitcase:
                    generic_exit_cases.append(fact)
    phase_path = 'ik_event/bin/phase/dlc_phase.bin'
    data = game.read(phase_path)
    inputs[phase_path] = {'bytes': len(data), 'sha256': digest(data)}
    rows = []
    phase = F.root(data, 'PhaseRoot')
    for row in phase.kids[0].items:
        pid = row.i32(0) or 0
        if 10000 <= pid <= 20100:
            rows.append({'dlc_phase': pid,
                         'condition_groups': groups(row.kids[1]) if 1 in row.kids else [],
                         'effects': [{'kind': c.i32(0), 'args': S.cmd_args(c)}
                                     for c in row.kids.get(2, F.Vec([], 'Cmd')).items]})
    source_files = {str(Path(module.__file__).resolve()): digest(Path(module.__file__).read_bytes())
                    for module in (F, S, sys.modules[S.Romfs.__module__])}
    result = {'schema': 'za-main-dlc-resume-readonly-research-1',
              'read_utc': datetime.now(timezone.utc).isoformat(),
              'research_only_not_current_build_approval': True,
              'game_started': False, 'game_or_save_written': False,
              'romfs_path': str(a.romfs.resolve()), 'inputs': inputs,
              'source_files_measured': source_files,
              'research_helper_sha256': digest(Path(__file__).read_bytes()),
              'boolean_structure': 'Original groups retained; innerOR/outerAND proven separately',
              'return_city_cases': returns, 'dlc1_cases': dlc1_cases,
              'main10_dlc00_cases': prologue_cases, 'global_exit_cases': generic_exit_cases,
              'advance_command_cases': boundaries, 'counter_and_advance_counts': dict(counts),
              'selected_dlc_phase_rows': rows,
              'gameplay_return_or_resume_verified': False,
              'limitations': ['Does not model Lua/native command effects',
                              'Historical reader source; current parser approval unresolved in M02',
                              'No UI route/collision/quest scheduling guarantee from table predicates alone']}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(a.out), 'return_city_cases': len(returns),
                      'dlc1_cases': len(dlc1_cases), 'advance_cases': len(boundaries),
                      'counts': dict(counts)}))


if __name__ == '__main__':
    main()
