"""Prepare a narrow data-only ending callback probe, not a generator change.

The real r3 chapter6 victory command list is copied unchanged. A one-shot map
transition dispatches it instead of a battle-victory event. No phase5/quest05
assignment is added. Every existing global trigger wrapper stays unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import fbedit as F
import story_shuffle as S


def sha(data): return hashlib.sha256(data).hexdigest()


def encoded(node):
    w = F.Writer(); w.put(node, root=True); return bytes(w.b)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--base-mods', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--evidence', type=Path, required=True)
    ap.add_argument('--describe-only', action='store_true', help='Read source commands; no game output or data modification')
    ap.add_argument('--after-victory-dialogue', action='store_true', help='Test-only: omit only the already-seen Ev_m06_4010 conversation; retain every other command')
    a = ap.parse_args()
    if a.out.exists() or a.evidence.exists(): ap.error('Outputs must be NEW')
    if any((p / '.git').exists() for p in (a.out.resolve(), *a.out.resolve().parents)):
        ap.error('Game bytes must remain outside Git')
    canonical = Path(S.REPO).parent / 'Pokemon-ZA-Native-Port'
    summary = json.loads((canonical / 'evidence/story-continuation-20261101-r3/all24-model/summary.json').read_text(encoding='utf-8-sig'))
    pins = next(r['file_sha256'] for r in summary['results'] if r['order'] == [4, 6, 5, 7, 8])
    inputs = {p: (a.base_mods / 'shuffle/romfs' / p).read_bytes() for p in pins}
    if any(sha(data) != pins[path] for path, data in inputs.items()): raise ValueError('Not exact published r3')
    global_path = 'ik_event/bin/trigger/global/trigger_global.bin'
    root = F.root(inputs[global_path], 'TrigRoot'); oldtree = F.to_py(root)
    trainer = F.root(inputs[S.TRAINER], 'TrigRoot')
    matches = []
    for wrapper in trainer.kids[0].items:
        trigger = wrapper.kids[0]
        if trigger.i32(0) != 12 or 1 not in trigger.kids or S.sv(trigger.kids[1]) != ['btr_co_boss']: continue
        for case in trigger.kids[2].items:
            if S.cond_list(case) == [('phase_condition', 1, ['54000'])]: matches.append(case)
    if len(matches) != 1: raise ValueError('Unreviewed chapter6 ending owner')
    case = matches[0].clone()
    original_body = encoded(case.kids[1])
    original_body_ast = F.to_py(case.kids[1])
    commands = S.cmd_list(case)
    full_source_body_sha256 = sha(original_body)
    removed_commands = []
    expected_events = ['Ev_m06_4010', 'Ev_m06_4100', 'Ev_m05_0010', 'Ev_m05_0020', 'Ev_m05_0030']
    if S.events(commands) != expected_events or [c.i32(0) for c in commands].count(111) != 1:
        raise ValueError('Unreviewed ending sequence')
    if any(c.i32(0) == 9 and S.cmd_args(c)[:1] == ['SYS_WORK_PHASE'] for c in commands):
        raise ValueError('Unexpected direct phase assignment in source ending')
    if any(c.i32(0) == 9 and any('MAINQUEST_05' in s for s in S.cmd_args(c)) for c in commands):
        raise ValueError('Unexpected direct quest05 assignment')
    if a.describe_only:
        result = {'schema': 'za-ending-source-description-1', 'source_body_sha256': sha(original_body),
                  'commands': [{'index': i, 'kind': c.i32(0), 'args': S.cmd_args(c)} for i, c in enumerate(commands)],
                  'no_game_output': True, 'source_helper_sha256': sha(Path(__file__).read_bytes())}
        a.evidence.parent.mkdir(parents=True, exist_ok=True)
        a.evidence.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result)); return
    if a.after_victory_dialogue:
        if full_source_body_sha256 != 'efdc93f99d0ea22ff0bf9f58d8e4a37bd757c8349809451d836ebb14debc9955':
            raise ValueError('Narrow probe requires exact reviewed original ending body')
        groups = case.kids[1].items
        if len(groups) != 1 or len(groups[0].kids[0].items) != 19:
            raise ValueError('Unreviewed command group structure')
        if commands[1].i32(0) != 22 or S.cmd_args(commands[1]) != ['Ev_m06_4010']:
            raise ValueError('Unreviewed victory conversation index')
        kept_ast = [F.to_py(c) for i, c in enumerate(commands) if i != 1]
        removed_commands = [{'index': 1, 'kind': 22, 'args': ['Ev_m06_4010']}]
        del groups[0].kids[0].items[1]
        commands = S.cmd_list(case)
        if [F.to_py(c) for c in commands] != kept_ast:
            raise ValueError('Non-dialogue command changed')
        expected_events = expected_events[1:]
        original_body = encoded(case.kids[1]); original_body_ast = F.to_py(case.kids[1])
    game = S.Romfs(str(Path(S.HL) / 'qa-game-reference-20261030/romfs.bin'))
    template_path = 'ik_event/bin/trigger/main/trigger_main_04.bin'
    template_data = game.read(template_path)
    if sha(template_data) != summary['input_sha256'][template_path]['sha256']:
        raise ValueError('Map callback template source mismatch')
    templates = F.root(template_data, 'TrigRoot')
    callback = templates.kids[0].items[15].clone()
    trigger = callback.kids[0]
    if trigger.i32(0) != 2 or S.sv(trigger.kids[1]) != ['t1', 'EV_CMN_TRANSITION_IN']:
        raise ValueError('Map callback template mismatch')
    S.set_vstr(trigger, 1, ['t1_i014_2', 'EV_CMN_TRANSITION_IN'])
    false_flags = []
    S.walk(templates, lambda node, _: false_flags.append(node) if node.type == 'Cond' and
           node.kids.get(0) and node.kids[0].text() == 'flag_condition' and node.i32(1) == 2 else None)
    if not false_flags: raise ValueError('No real false-flag template')
    guard = false_flags[0].clone(); S.set_vstr(guard, 2, ['flag_Ev_m06_4100'])
    group = case.kids[0].items[0].clone(); group.kids[0].items = [guard]
    case.kids[0].items.append(group)
    expected_conds = [('phase_condition', 1, ['54000']), ('flag_condition', 2, ['flag_Ev_m06_4100'])]
    if a.after_victory_dialogue:
        true_flags = []
        S.walk(templates, lambda node, _: true_flags.append(node) if node.type == 'Cond' and
               node.kids.get(0) and node.kids[0].text() == 'flag_condition' and node.i32(1) == 1 else None)
        if not true_flags: raise ValueError('No real true-flag template')
        seen = true_flags[0].clone(); S.set_vstr(seen, 2, ['flag_Ev_m06_4010'])
        seen_group = group.clone(); seen_group.kids[0].items = [seen]
        case.kids[0].items.append(seen_group)
        expected_conds.append(('flag_condition', 1, ['flag_Ev_m06_4010']))
    trigger.kids[2].items = [case]
    root.kids[0].items.append(callback)
    output = encoded(root); check = F.root(output, 'TrigRoot')
    checkcase = check.kids[0].items[-1].kids[0].kids[2].items[0]
    if F.to_py(check)[0][:-1] != oldtree[0]: raise ValueError('Existing wrapper mutated')
    if F.to_py(checkcase.kids[1]) != original_body_ast or encoded(checkcase.kids[1]) != original_body:
        raise ValueError('Ending command list changed')
    if S.cond_list(checkcase) != expected_conds or \
       [len(g.kids[0].items) for g in checkcase.kids[0].items] != [1] * len(expected_conds):
        raise ValueError('One-shot AND guards changed')
    shutil.copytree(a.base_mods, a.out)
    (a.out / 'shuffle/romfs' / global_path).write_bytes(output)
    outputs = {p: sha((a.out / 'shuffle/romfs' / p).read_bytes()) for p in pins}
    if [p for p in pins if outputs[p] != pins[p]] != [global_path]: raise ValueError('Unexpected file modified')
    evidence = {'schema': 'za-test-only-end6-callback-1', 'status': 'PREPARED_NOT_RUNTIME_VERIFIED',
                'base_order': [4, 6, 5, 7, 8], 'base_r3_sha256': pins, 'output_sha256': outputs,
                'modified_file_only': global_path, 'existing_wrappers_unchanged': True,
                'entry': {'kind': 2, 'args': ['t1_i014_2', 'EV_CMN_TRANSITION_IN']},
                'guards': {'outer': 'AND', 'inner': 'OR', 'group_sizes': [1] * len(expected_conds),
                           'phase': 54000, 'exit4100_must_be_false': True},
                'original_ending_owner': {'type': 12, 'args': ['btr_co_boss'], 'phase': 54000},
                'ending_events': expected_events, 'command_list_ast_unchanged': True,
                'command_list_serialized_sha256': sha(original_body), 'command_count': len(commands),
                'full_source_body_sha256': full_source_body_sha256, 'removed_commands': removed_commands,
                'all_remaining_original_commands_unchanged': True,
                'required_seen4010': a.after_victory_dialogue,
                'manual_phase5_or_quest05_assignments_added': 0,
                'simulation': 'Dispatch post-battle ending on map entry instead of winning combat; all original ending commands retained',
                'template_input_sha256': sha(template_data), 'source_sha256': sha(Path(__file__).read_bytes()),
                'ready_for_ui': False, 'ready_for_ps5': False}
    a.evidence.parent.mkdir(parents=True, exist_ok=True)
    a.evidence.write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(a.out), 'ending_body_unchanged': True, 'modified_files': 1,
                      'runtime_verified': False, 'body_sha256': sha(original_body)}))


if __name__ == '__main__': main()
