"""Read-only bounded DLC/main gate experiment using existing story readers.

Reads an existing extraction from Tomer's dump, never generates mods/saves/game
bytes. Exports selected entry-gate metadata, counts, hashes and modeled truth values.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
import time


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--story-tools', type=Path, required=True)
    p.add_argument('--extracted-root', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--lua', type=Path, help='Optional existing original Lua for two explicit entry-associated prototypes')
    p.add_argument('--lua-reader', type=Path, help='Existing luadump.py; no new decoder')
    a = p.parse_args()
    if a.out.exists():
        p.error('OUT must be new')
    sys.path.insert(0, str(a.story_tools))
    import fbedit as F
    import story_shuffle as S
    import oracle
    started = time.monotonic()
    inputs = {}

    def read(relative, schema):
        data = (a.extracted_root / relative).read_bytes()
        if len(data) > 1024 * 1024:
            raise ValueError('Input exceeds1MiB bound')
        inputs[relative] = {'bytes': len(data), 'sha256': sha(data)}
        return F.root(data, schema)

    main_phase = read('ik_event/bin/phase/phase.bin', 'PhaseRoot')
    dlc_phase = read('ik_event/bin/phase/dlc_phase.bin', 'PhaseRoot')
    summary = {}
    unlocks = []
    prologue_rows = []
    for kind, root in [('main', main_phase), ('dlc', dlc_phase)]:
        ids = [row.i32(0) or 0 for row in root.kids[0].items]
        summary[kind] = {'count': len(ids), 'first': ids[0], 'last': ids[-1]}
        for row in root.kids[0].items:
            if kind == 'dlc' and (row.i32(0) or 0) <= 2200:
                conditions = []
                def condition(tab, path):
                    if isinstance(tab, F.Tab) and tab.type == 'Cond':
                        conditions.append({'factory': tab.kids[0].text() if 0 in tab.kids else None,
                                           'operator': tab.i32(1),
                                           'arguments': S.sv(tab.kids[2]) if 2 in tab.kids else []})
                if 1 in row.kids:
                    S.walk(row.kids[1], condition)
                commands = row.kids.get(2, F.Vec([], 'Cmd')).items
                prologue_rows.append({'dlc_phase': row.i32(0) or 0, 'entry_conditions': conditions,
                                       'command_ids': [cmd.i32(0) for cmd in commands],
                                       'explicit_state_effects': [{'command': cmd.i32(0), 'arguments': S.cmd_args(cmd)}
                                                                  for cmd in commands if cmd.i32(0) in (8, 9, 117)]})
            for cmd in row.kids.get(2, F.Vec([], 'Cmd')).items:
                args = S.cmd_args(cmd)
                if cmd.i32(0) == 8 and args and (args[0] == 'SYS_FLAG_GAME_CLEAR' or args[0].startswith('FLAG_DLC_')):
                    unlocks.append({'namespace': kind, 'phase': row.i32(0) or 0,
                                    'flag_identifier': args[0], 'value': args[1:]})

    gate_rows, cross_reads, counter_writes = [], [], []
    map_commands = Counter()
    map_identifiers = Counter()
    for chapter in range(1, 11):
        namespace = 'dlc' if chapter <= 9 else 'main'
        relative = ('ik_event/bin/trigger/dlc/trigger_dlc_%02d.bin' % chapter if chapter <= 9 else
                    'ik_event/bin/trigger/main/trigger_main_10.bin')
        root = read(relative, 'TrigRoot')
        for wi, wrapper in enumerate(root.kids[0].items):
            trigger = wrapper.kids.get(0)
            if trigger is None:
                continue
            for ci, case in enumerate(trigger.kids.get(2, F.Vec([], 'Case')).items):
                conditions = S.cond_list(case)
                commands = S.cmd_list(case)
                events = S.events(commands)
                location = {'input': relative, 'wrapper': wi, 'case': ci}
                if namespace == 'main' and 'Ev_d00_0000' in events:
                    gate_rows.append({**location, 'conditions': conditions,
                                      'events': events, 'trigger_identifiers': S.sv(trigger.kids[1]) if 1 in trigger.kids else []})
                for name, op, args in conditions:
                    if namespace == 'dlc' and (name == 'phase_condition' or
                       (name == 'work_condition' and args and args[0] == 'SYS_WORK_PHASE')):
                        cross_reads.append({**location, 'factory': name, 'operator': op, 'arguments': args})
                for cmd in commands:
                    args = S.cmd_args(cmd)
                    if cmd.i32(0) == 9 and args and args[0] in ('SYS_WORK_PHASE', 'SYS_WORK_DLC_PHASE'):
                        counter_writes.append({**location, 'namespace': namespace, 'counter': args[0], 'value': args[1:]})
                    if namespace == 'dlc' and cmd.i32(0) in (6, 7, 44, 50):
                        map_commands[str(cmd.i32(0))] += 1
                        if args:
                            map_identifiers[args[0]] += 1

    if len(gate_rows) != 1:
        raise ValueError('Expected exactly one reviewed DLCprologue entry case in main10')
    gate = gate_rows[0]
    phase_gates = [(op, args) for kind, op, args in gate['conditions'] if kind == 'phase_condition']
    if len(phase_gates) != 1:
        raise ValueError('Entry gate phase shape changed')
    op, args = phase_gates[0]
    if op != 1 or args != ['100200']:
        raise ValueError('Original entry gate differs from reviewed shape')
    quest_path = 'ik_event/bin/quest/sub_quest.bin'
    quest_data = (a.extracted_root / quest_path).read_bytes()
    if len(quest_data) > 1024 * 1024:
        raise ValueError('Quest input exceeds1MiB bound')
    inputs[quest_path] = {'bytes': len(quest_data), 'sha256': sha(quest_data)}
    sf = S.SlotFile(quest_data)
    quest_slots = S.quest_start_slots(sf, 'sub_0122')
    if [sf.get(slot) for slot in quest_slots] != ['101000', 'flag_Ev_d00_0000']:
        raise ValueError('DLC prologue quest start arguments changed')
    quest_conditions = []
    for factory, slot in zip(('phase_condition', 'flag_condition'), quest_slots):
        matches = [(t, operation, slots) for t, operation, slots in sf.conds(factory) if slot in slots]
        if len(matches) != 1:
            raise ValueError('Quest condition owner is ambiguous')
        table, operation, slots = matches[0]
        quest_conditions.append({'factory': factory, 'table_offset': table, 'operator': operation,
                                 'arguments': [sf.get(x) for x in slots]})
    if [row['operator'] for row in quest_conditions] != [5, 1]:
        raise ValueError('Original quest start operators changed')
    first_step = next(row for row in prologue_rows if row['dlc_phase'] == 100)
    last_step = next(row for row in prologue_rows if row['dlc_phase'] == 2200)
    if first_step['entry_conditions'] != [{'factory': 'flag_condition', 'operator': 1, 'arguments': ['flag_Ev_d00_0110']}] or \
       last_step['entry_conditions'] != [{'factory': 'flag_condition', 'operator': 1, 'arguments': ['flag_Ev_d01_0010']}]:
        raise ValueError('Reviewed prologue dependency endpoints changed')
    experiments = []
    for phase in (40100, 51000, 62000, 74000, 93000, 100200, 101000):
        experiments.append({'main_phase': phase,
                            'original_entry_phase_predicate': oracle.runtime_eval(oracle.normalize_wire(op), phase, [100200]),
                            'hypothetical_relocated_entry_at40100_phase_predicate': oracle.runtime_eval(2, phase, [40100]),
                            'subquest122_ge101000_phase_predicate': oracle.runtime_eval(7, phase, [101000]),
                            'other_gates': 'unknown; numeric predicate truth alone never proves event/map/gameplay safety'})

    # This checks ownership of explicit CMD9 rows only, never Lua/native side effects.
    counter_model = {'SYS_WORK_PHASE': 40100, 'SYS_WORK_DLC_PHASE': 0}
    modeled_writes = 0
    for row in counter_writes:
        if row['namespace'] != 'dlc':
            continue
        if len(row['value']) != 1 or not row['value'][0].isdigit():
            raise ValueError('Unsupported explicit DLC counter-write argument')
        counter_model[row['counter']] = int(row['value'][0])
        modeled_writes += 1

    lua_context = []
    if a.lua:
        if not a.lua_reader or a.lua.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Existing bounded Lua reader and <=8MiB original input required')
        import importlib.util
        spec = importlib.util.spec_from_file_location('existing_dlc_luadump', a.lua_reader)
        L = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(L)
        data = a.lua.read_bytes()
        root = L.load(data)
        for index, event in ((189, 'Ev_d00_0000'), (2391, 'Ev_m10_0200')):
            proto = root['p'][index]
            if len(proto['code']) > 4096:
                raise ValueError('Entry-associated Lua prototype exceeds4096instruction bound')
            identifiers = [k for k in proto['k'] if isinstance(k, str)]
            keys = [k for k in identifiers if k.startswith(('SYS_WORK_', 'SYS_FLAG_', 'FLAG_', 'flag_'))]
            lua_context.append({'prototype': 'r/' + str(index), 'event_identifier': event,
                                'association': 'derived from matching message identifiers; native event-to-prototype binding unproved',
                                'matching_message_identifier_count': sum(k.startswith('msg_' + event) for k in identifiers),
                                'instruction_count': len(proto['code']),
                                'code_sha256': sha(b''.join(int(i).to_bytes(4, 'little') for i in proto['code'])),
                                'literal_state_keys': keys,
                                'call_instruction_count': sum(L.ins(i)[0] in (68, 69) for i in proto['code']),
                                'prerequisites_proved_absent': False,
                                'reason': 'Hashed API effects and interprocedural calls have not been resolved'})
        inputs['original_event_ik_lua'] = {'bytes': len(data), 'sha256': sha(data)}
        inputs['existing_lua_reader_source'] = {'bytes': a.lua_reader.stat().st_size, 'sha256': sha(a.lua_reader.read_bytes())}

    result = {'schema': 'za-dlc-interleave-data-probe-1', 'console_access': False, 'game_process_launched': False,
              'experiment_scope': 'Read-only original trigger/phase inventory and bounded numeric gate counterfactuals; no game or save writes',
              'source_sha256': sha(Path(__file__).read_bytes()),
              'reader_sources': {name: sha((a.story_tools / name).read_bytes()) for name in ('fbedit.py', 'story_shuffle.py', 'oracle.py')},
              'inputs': inputs, 'phase_table_counts': summary, 'selected_capability_unlocks': unlocks,
              'dlc_prologue_phase_rows_0_to2200': prologue_rows,
              'prologue_first_step_fixture': {'intro_event_completion_flag_only': ['flag_Ev_d00_0000'],
                                              'first_phase100_requires': ['flag_Ev_d00_0110'],
                                              'intro_flag_alone_satisfies_first_step': False,
                                              'after_first_quest_objective_flag_fixture': ['flag_Ev_d00_0000', 'flag_Ev_d00_0110'],
                                              'first_step_identifier_dependency_then_satisfied': True,
                                              'last_phase2200_requires': ['flag_Ev_d01_0010'],
                                              'scope': 'Dependency fixture only; event auto-flag handling, quest objective dispatch and native phase0 advancement have not run'},
              'dlc_prologue_entry': gate,
              'dlc_trigger_main_phase_reads': cross_reads, 'counter_writes': counter_writes,
              'dlc_map_command_counts': dict(map_commands),
              'dlc_explicit_map_identifiers': dict(map_identifiers),
              'entry_associated_lua_contexts': lua_context,
              'main_preservation_data_model': {'initial_main_phase': 40100, 'explicit_dlc_counter_commands': modeled_writes,
                                               'final_main_phase': counter_model['SYS_WORK_PHASE'],
                                               'explicit_counter_ownership_preserved': counter_model['SYS_WORK_PHASE'] == 40100,
                                               'scope': 'Only explicit CMD9 counter rows, no flags, Lua, event scheduler, maps or save persistence are modeled'},
              'modeled_predicates': experiments,
              'subquest122_start_gate': {'input': quest_path, 'quest_identifier': 'sub_0122', 'conditions': quest_conditions},
              'gameplay_verified': False, 'return_to_main_verified': False,
              'elapsed_seconds': time.monotonic() - started}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(a.out), 'inputs': len(inputs), 'main_reads_in_dlc': len(cross_reads),
                      'counter_writes': len(counter_writes), 'seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()
