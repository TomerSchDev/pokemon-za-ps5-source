"""Bounded Lua constant-use metadata; reuses luadump.load/ins, never executes Lua.

Only explicit reviewed changes in historical order46578 or seed1 prototypes.
Exports indices, roles and hashes, never instructions, string tables or game bytes.
"""
import argparse
from collections import deque
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import time


PLAN_SHA = 'ee4b7e4119737da5bf707b73e822274e9f22282b9ae6d8443565b4b4d03ac0c6'
TARGETS = {'r/2397': {60050, 60200}, 'r/5884': {51200}, 'r/5990': {51200}}
SEED1_SHA = '5c995f357b6837c5611fedfe00957b738e5087d24dc4dd2c7b273716b19ae3d0'
SEED1_TARGETS = {'r/2397': {60050, 70100, 60200, 71000, 71100, 71200, 74000, 75000, 75100},
                 'r/5848': {74100, 75000, 71000, 71100}, 'r/5884': {51200},
                 'r/5990': {51200}, 'r/6162': {70000}, 'r/6201': {70100}}
LUA_SHA = 'f238160475095b02e8c5302d907adbd1b48b2fd793a4a8c72ee8c9689fdfd698'
PHASE_SHA = '8233506ebb70627a1ea23f0be2b58eafa7fd8f303f3aae35937038f65c61ae27'
# Operand semantics from https://www.lua.org/source/5.4/lopcodes.h.html .
# Bit decoding itself is exclusively the existing luadump.ins function.
COMPARISONS = {57, 58, 59, 60}
BRANCHES = set(range(57, 68))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def imported(path):
    spec = importlib.util.spec_from_file_location('existing_luadump', path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def analyze(mod, proto, path, target_values, inspect=False):
    ks, code = proto['k'], proto['code']
    if len(code) > 10000:
        raise ValueError('Selected prototype exceeds bounded instruction budget')
    decoded = [mod.ins(word) for word in code]
    if inspect and path == 'r/6201':
        # Local terminal only. Never included in the deliverable report.
        for pc in range(57, min(97, len(code))):
            op, a, k, b, c, bx = decoded[pc]
            indices = [bx] if op == 3 else [c] if op in (11, 14) else [b] if op == 60 else []
            names = {i: ks[i] for i in indices if 0 <= i < len(ks) and isinstance(ks[i], str)
                     and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:.]{0,95}', ks[i])}
            print(json.dumps({'local_only_pc': pc, 'op': op, 'a': a, 'k': k, 'b': b, 'c': c,
                              'bx': bx, 'binding_or_key_identifiers': names}))
    targets = {i for i, k in enumerate(ks) if type(k) is int and k in target_values}
    if {ks[i] for i in targets} != target_values:
        raise ValueError('Target constants absent in selected original prototype')

    def kval(index):
        if not 0 <= index < len(ks):
            return None
        return ('constant', index)

    def phase_key(token):
        return token is not None and token[0] == 'constant' and ks[token[1]] == 'SYS_WORK_PHASE'

    def work_namespace(token):
        if token is not None and token[0] == 'constant':
            return {'SYS_WORK_PHASE': 'main', 'SYS_WORK_DLC_PHASE': 'dlc'}.get(ks[token[1]]) if isinstance(ks[token[1]], str) else None
        return None

    def identity(token):
        if token is None:
            return None
        if token[0] == 'constant':
            return ('constant_value_sha256', sha(json.dumps(ks[token[1]], ensure_ascii=True).encode()))
        if token[0] == 'field':
            return ('field', identity(token[1]), identity(token[2]))
        return token

    def description(token):
        if token is None:
            return {'kind': 'unknown'}
        if token[0] == 'constant':
            index = token[1]
            value = ks[index]
            row = {'kind': 'constant', 'constant_index': index,
                   'value_sha256': sha(json.dumps(value, ensure_ascii=True).encode())}
            if index in targets:
                row['reviewed_original_value'] = value
            if phase_key(token):
                row['role'] = 'exact_SYS_WORK_PHASE_key'
            if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_:.]{0,95}', value):
                row['binding_or_key_identifier'] = value
            return row
        if token[0] == 'call':
            return {'kind': 'call_result', 'pc': token[1],
                    'exact_phase_key_argument': token[2] == 'main',
                    'exact_dlc_phase_key_argument': token[2] == 'dlc',
                    'work_key_namespace': token[2], 'callee_fingerprint': token[3]}
        if token[0] == 'field':
            return {'kind': 'table_lookup', 'base': description(token[1]), 'key': description(token[2])}
        return {'kind': token[0], 'fingerprint': sha(repr(token).encode())}

    def edges(pc, ins):
        op, a, k, b, c, bx = ins
        if op in (69, 70, 71, 72):
            return []
        if op == 56:
            # Ax reconstructed from fields returned by existing ins; signed jump bias.
            return [pc + 1 + ((bx << 8) | a) - 16777215]
        if op in BRANCHES or op == 6:
            return [pc + 1, pc + 2]
        if op in (73, 74, 75, 77):
            raise ValueError('Loop opcode in selected prototype: require a separate review')
        return [pc + 1]

    def transfer(pc, state):
        op, a, k, b, c, bx = decoded[pc]
        result = dict(state)
        value = None
        if op == 0:
            value = state.get(b)
        elif op in (3, 4):
            if op == 4:
                if pc + 1 >= len(code) or decoded[pc + 1][0] != 82:
                    raise ValueError('LOADKX without EXTRAARG')
                extra = decoded[pc + 1]
                bx = (extra[5] << 8) | extra[1]
            value = kval(bx)
        elif op == 9:
            value = ('upvalue', b)
        elif op == 11:
            value = ('field', ('upvalue', b), kval(c))
        elif op in (12, 14):
            value = ('field', state.get(b), kval(c) if op == 14 else state.get(c))
        elif op == 68:
            args = [state.get(r) for r in range(a + 1, a + b)] if b else []
            fingerprint = sha(repr(identity(state.get(a))).encode())
            namespaces = {work_namespace(arg) for arg in args} - {None}
            namespace = next(iter(namespaces)) if len(namespaces) == 1 else 'mixed' if namespaces else None
            value = ('call', pc, namespace, fingerprint)
            for register in list(result):
                if register >= a:
                    result.pop(register)
            if c == 2:
                result[a] = value
            return result
        elif op in BRANCHES or op in (10, 15, 16, 17, 18, 54, 55, 56, 70, 71, 72, 78, 81, 82):
            # Comparisons and table/upvalue stores do not overwrite registers.
            # TESTSET has a conditional assignment: forget its destination conservatively.
            if op == 67:
                result.pop(a, None)
            return result
        elif op == 8:
            for register in range(a, a + b + 1):
                result.pop(register, None)
            return result
        elif op in (1, 2, 5, 6, 7, 13, 19, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30,
                    31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45,
                    49, 50, 51, 52, 53, 79):
            pass  # Known register write; value is deliberately unknown.
        else:
            return {}  # Unsupported effects never preserve stale provenance.
        if value is None:
            result.pop(a, None)
        else:
            result[a] = value
        return result

    # Conservative must-analysis: a register origin survives a merge only if identical
    # on every reachable incoming path. No heuristic PHASE substring classification.
    states, work, iterations = {0: {}}, deque([0]), 0
    while work:
        pc = work.popleft()
        iterations += 1
        if iterations > 100000:
            raise ValueError('Bounded dataflow iteration budget exceeded')
        after = transfer(pc, states[pc])
        for target in edges(pc, decoded[pc]):
            if target == len(code):
                continue
            if not 0 <= target < len(code):
                raise ValueError('Invalid control-flow target')
            prior = states.get(target)
            merged = after if prior is None else {r: v for r, v in prior.items() if after.get(r) == v}
            if prior is None or merged != prior:
                states[target] = dict(merged)
                work.append(target)

    # Audit every final incoming CFG edge, including incoming origins discarded by
    # must-intersection even when the destination state itself did not change.
    merge_losses = {index: [] for index in targets}
    call_scratch_losses = {index: [] for index in targets}
    for pc, before in sorted(states.items()):
        op, a, k, b, c, bx = decoded[pc]
        if op == 68:
            definitely_written = set(range(a, a + c - 1)) if c else set()
            for register, token in before.items():
                if register >= a and register not in definitely_written and token[0] == 'constant' and token[1] in targets:
                    call_scratch_losses[token[1]].append({'from_pc': pc, 'to_pc': pc + 1,
                                                         'register': register, 'role': 'non_definite_call_scratch_forget'})
        after = transfer(pc, before)
        for destination in edges(pc, decoded[pc]):
            if destination == len(code):
                continue
            merged = states[destination]
            for register, token in after.items():
                if token is not None and token[0] == 'constant' and token[1] in targets and merged.get(register) != token:
                    merge_losses[token[1]].append({'from_pc': pc, 'to_pc': destination,
                                                  'register': register, 'role': 'target_origin_discarded_by_must_join'})

    rows = []
    def register_reads(ins, state):
        op, a, k, b, c, bx = ins
        if op == 0: return {b}
        if op in (10, 55, 60, 61, 62, 63, 64, 65, 66, 72): return {a}
        if op in (12, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45): return {b, c}
        if op in (13, 14, *range(21, 34), 49, 50, 51, 52, 67): return {b}
        if op == 15: return set() if k else {c}
        if op == 16: return {a, b} | (set() if k else {c})
        if op in (17, 18): return {a} | (set() if k else {c})
        if op == 20: return {b} | (set() if k else {c})
        if op in (46, 57, 58, 59): return {a, b}
        if op in (47, 48): return {a}
        if op == 53: return set(range(a, a + b))
        if op == 54: return {r for r in state if r >= a}
        if op in (68, 69): return set(range(a, a + b)) if b else {r for r in state if r >= a}
        if op == 70: return set(range(a, a + b - 1)) if b else {r for r in state if r >= a}
        if op == 78: return set(range(a, a + b + 1)) if b else {r for r in state if r >= a}
        if op == 79: return set(state)  # Reader omits upvalue descriptors: any live target may escape.
        if op in (1, 2, 3, 4, 5, 6, 7, 8, 9, 11, 19, 56, 71, 80, 81, 82): return set()
        return {a, b, c}  # Conservative unknown-op fallback, never a proof.

    supported_transfer = set(range(0, 46)) - {20}
    supported_transfer |= set(range(49, 73)) | {78, 79, 81, 82}

    def merge_liveness(loss, index):
        """At most40 successor nodes: stop at first read or definite overwrite.

        CALL argument scratch is NOT assumed overwritten: only fixed result slots
        are definite writes. Closures/unsupported effects fail unknown.
        """
        pending, visited, terminals = deque([loss['to_pc']]), set(), []
        register = loss['register']
        while pending:
            pc = pending.popleft()
            if pc == len(code):
                terminals.append({'pc': pc, 'role': 'function_end_without_read'})
                continue
            if pc in visited:
                continue
            if len(visited) >= 40:
                return {'status': 'unknown_budget', 'edge': loss, 'visited_pc': sorted(visited)}
            visited.add(pc)
            op, a, k, b, c, bx = decoded[pc]
            if register in register_reads(decoded[pc], {register: ('constant', index)}):
                return {'status': 'unknown_first_read', 'edge': loss, 'first_read_pc': pc,
                        'opcode': op, 'visited_pc': sorted(visited)}
            if op not in supported_transfer or op == 81:
                return {'status': 'unknown_effect', 'edge': loss, 'effect_pc': pc,
                        'opcode': op, 'visited_pc': sorted(visited)}
            written = set()
            if op == 8:
                written = set(range(a, a + b + 1))
            elif op == 20:
                written = {a, a + 1}
            elif op == 68:
                written = set(range(a, a + c - 1)) if c else set()
                if not c and register >= a:
                    return {'status': 'unknown_open_call_results', 'edge': loss, 'effect_pc': pc}
            elif op in (0, 1, 2, 3, 4, 5, 6, 7, 9, 11, 12, 13, 14, 19, *range(21, 46), 49, 50, 51, 52, 53, 79):
                written = {a}
            if register in written:
                terminals.append({'pc': pc, 'opcode': op, 'role': 'definite_overwrite_before_read'})
                continue
            successors = edges(pc, decoded[pc])
            if not successors:
                terminals.append({'pc': pc, 'opcode': op, 'role': 'function_exit_without_read'})
            for destination in successors:
                if destination == len(code):
                    terminals.append({'pc': pc, 'role': 'function_end_without_read'})
                else:
                    pending.append(destination)
        return {'status': 'dead_before_read_on_all_successors', 'edge': loss,
                'visited_pc': sorted(visited), 'terminals': terminals}

    for index in sorted(targets):
        direct, uses, aliases, unclassified, losses = [], [], [], [], []
        for pc, (op, a, k, b, c, bx) in enumerate(decoded):
            constant_slots = ([bx] if op == 3 else [c] if op in (11, 14, *range(22, 32))
                              else [b] if op in (48, 60) else [])
            if op == 4 and pc + 1 < len(code) and decoded[pc + 1][0] == 82:
                extra = decoded[pc + 1]
                constant_slots.append((extra[5] << 8) | extra[1])
            if op in (15, 18):
                constant_slots.append(b)
            if op in (15, 16, 17, 18, 20) and k:
                constant_slots.append(c)
            if index in constant_slots:
                direct.append({'pc': pc, 'instruction_byte_offset_within_proto': pc * 4,
                               'opcode': op, 'role': 'constant_operand'})
                if op not in (3, 4, 60):
                    unclassified.append({'pc': pc, 'opcode': op, 'role': 'other_direct_constant_operand'})
            state = states.get(pc, {})
            for register in register_reads(decoded[pc], state):
                if state.get(register) != ('constant', index):
                    continue
                if op == 0:
                    aliases.append({'pc': pc, 'source_register': register, 'destination_register': a})
                elif op in COMPARISONS:
                    pass  # Recorded as a comparison below.
                elif op in (68, 69) and register != a and b:
                    pass  # Recorded as a fixed-arity call argument below.
                else:
                    unclassified.append({'pc': pc, 'opcode': op, 'register': register,
                                         'role': 'non_comparison_or_call_register_consumer'})
            if op not in supported_transfer:
                for register, token in state.items():
                    if token == ('constant', index):
                        losses.append({'pc': pc, 'opcode': op, 'register': register,
                                       'role': 'opaque_transfer_forgets_constant_origin'})
            if op in COMPARISONS:
                lhs, rhs = state.get(a), kval(b) if op == 60 else state.get(b)
                if ('constant', index) in (lhs, rhs):
                    other = rhs if lhs == ('constant', index) else lhs
                    uses.append({'pc': pc, 'opcode': op, 'role': 'comparison_operand',
                                 'other_operand': description(other)})
            if op in (68, 69) and b:
                for argument, register in enumerate(range(a + 1, a + b), 1):
                    if state.get(register) == ('constant', index):
                        uses.append({'pc': pc, 'opcode': op, 'role': 'call_argument',
                                     'argument': argument, 'callee': description(state.get(a)),
                                     'exact_phase_key_argument': any(phase_key(state.get(r)) for r in range(a + 1, a + b))})
        phase_uses = [u for u in uses if u.get('exact_phase_key_argument') or
                      u.get('other_operand', {}).get('exact_phase_key_argument')]
        dlc_uses = [u for u in uses if u.get('other_operand', {}).get('exact_dlc_phase_key_argument')]
        merge_checks = [merge_liveness(loss, index) for loss in merge_losses[index]]
        scratch_checks = [merge_liveness(loss, index) for loss in call_scratch_losses[index]]
        merges_safe = all(check['status'] == 'dead_before_read_on_all_successors' for check in merge_checks)
        scratch_safe = all(check['status'] == 'dead_before_read_on_all_successors' for check in scratch_checks)
        rows.append({'constant_index': index, 'original_value': ks[index],
                     'direct_references': direct, 'resolved_uses': uses,
                     'register_aliases': aliases, 'unclassified_consumers': unclassified,
                     'opaque_provenance_losses': losses,
                     'edge_merge_losses': merge_losses[index],
                     'merge_loss_liveness_checks': merge_checks,
                     'call_scratch_forget_losses': call_scratch_losses[index],
                     'call_scratch_liveness_checks': scratch_checks,
                     'bounded_use_closure_complete': bool(uses) and not unclassified and not losses and merges_safe and scratch_safe,
                     'has_proven_phase_key_use': bool(phase_uses),
                     'has_proven_dlc_phase_key_use': bool(dlc_uses),
                     'coverage_limitation': 'A found phase-key use does not prove every use of this constant is phase-related. Unsupported operations forget provenance; no interprocedural or alias analysis.',
                     'getter_setter_semantics': 'unknown_until_native_binding_verified'})
    call_pcs = sorted({u['other_operand']['pc'] for r in rows for u in r['resolved_uses']
                       if u.get('other_operand', {}).get('kind') == 'call_result'})
    calls = []
    for pc in call_pcs:
        op, a, k, b, c, bx = decoded[pc]
        state = states.get(pc, {})
        calls.append({'pc': pc, 'instruction_byte_offset_within_proto': pc * 4,
                      'callee': description(state.get(a)),
                      'arguments': [description(state.get(r)) for r in range(a + 1, a + b)] if b else [],
                      'argument_count_known': b != 0, 'return_count_field': c})
    return {'prototype': path, 'instruction_count': len(code), 'constant_count': len(ks),
            'code_sha256': sha(b''.join(int(w).to_bytes(4, 'little') for w in code)),
            'analysis_iterations': iterations, 'constants': rows, 'resolved_calls': calls}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--reader', type=Path, required=True)
    p.add_argument('--lua', type=Path, required=True)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--profile', choices=('46578', 'seed1', 'union'), default='46578')
    p.add_argument('--phase-bin', type=Path, help='Original35KiB phase file, union discovery only')
    p.add_argument('--flatbuffer-reader', type=Path, help='Existing story-shuffle fbedit.py, union discovery only')
    p.add_argument('--inspect-6201', action='store_true', help='At most40 local terminal instructions around unresolved use; never exported')
    a = p.parse_args()
    if a.lua.stat().st_size > 8 * 1024 * 1024:
        p.error('Only a bounded existing <=8MiB Lua input is permitted')
    if a.out.exists():
        p.error('OUT must be new')
    plan_bytes = a.plan.read_bytes()
    expected_plan_sha = PLAN_SHA if a.profile == '46578' else SEED1_SHA
    targets = TARGETS if a.profile == '46578' else SEED1_TARGETS
    if sha(plan_bytes) != expected_plan_sha:
        p.error('Historical plan differs from reviewed profile pin')
    started = time.monotonic()
    mod = imported(a.reader)
    data = a.lua.read_bytes()
    if sha(data) != LUA_SHA:
        p.error('Original Lua differs from pinned source audited by storyr2')
    root = mod.load(data)
    discovery = None
    if a.profile == 'union':
        if not a.phase_bin or not a.flatbuffer_reader or a.phase_bin.stat().st_size > 65536:
            p.error('Union discovery requires bounded original phase input and existing fbedit reader')
        phase_data = a.phase_bin.read_bytes()
        if sha(phase_data) != PHASE_SHA:
            p.error('Original phase input differs from storyr2 audit pin')
        fb = imported(a.flatbuffer_reader)
        phase_root = fb.root(phase_data, 'PhaseRoot')
        phase_ids = {entry.i32(0) or 0 for entry in phase_root.kids[0].items
                     if 40000 <= (entry.i32(0) or 0) < 90000}
        targets = {}
        visited = 0

        def discover(proto, path):
            nonlocal visited
            visited += 1
            if visited > 20000:
                raise ValueError('Prototype discovery budget exceeded')
            has_phase = any(isinstance(value, str) and 'PHASE' in value for value in proto['k'])
            values = {value for value in proto['k'] if type(value) is int and 50000 <= value < 90000
                      and (value in phase_ids or has_phase)}
            if values:
                targets[path] = values
            for index, child in enumerate(proto['p']):
                discover(child, path + '/' + str(index))

        discover(root, 'r')
        if set(targets) != {'r/2397', 'r/2409', 'r/5848', 'r/5884', 'r/5990', 'r/6162', 'r/6201'} or sum(map(len, targets.values())) != 18:
            print(json.dumps({'bounded_discovery_guard': 'no dataflow run or report written',
                              'prototype_count': len(targets), 'constant_count': sum(map(len, targets.values())),
                              'prototype_identifiers_first16': list(targets)[:16]}))
            raise ValueError('Union differs from reviewed seven-prototype/18-value scope')
        discovery = {'prototypes_visited': visited, 'phase_sha256': PHASE_SHA,
                     'flatbuffer_reader_sha256': sha(a.flatbuffer_reader.read_bytes()),
                     'predicate': 'Old numeric/PHASE-substring heuristic; discovery of would-change candidates only, NOT proof of main-phase role',
                     'completeness': 'Every chapter5..8 value changes under order[4,8,5,6,7]; chapter4 remains fixed in every allowed order'}
    results = []
    for path in targets:
        proto = root
        for part in path.split('/')[1:]:
            proto = proto['p'][int(part)]
        results.append(analyze(mod, proto, path, targets[path], a.inspect_6201))
    if sum(len(r['constants']) for r in results) != sum(map(len, targets.values())):
        raise ValueError('Expected exactly the reviewed constants; do not widen scope')
    result = {'schema': 'za-bounded-lua-constant-uses-1', 'console_access': False,
              'lua_sha256': sha(data), 'lua_bytes': len(data), 'reader_sha256': sha(a.reader.read_bytes()),
              'profile': a.profile, 'plan_sha256': expected_plan_sha, 'source_sha256': sha(Path(__file__).read_bytes()),
              'union_discovery': discovery,
              'opcode_semantics_source': 'https://www.lua.org/source/5.4/lopcodes.h.html',
              'proof_scope': 'Must-dataflow of literal keys, constants, calls and comparisons; native binding semantics remain unknown',
              'results': results, 'elapsed_seconds': time.monotonic() - started}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'out': str(a.out), 'prototypes': len(results),
                      'constants': sum(len(r['constants']) for r in results), 'seconds': result['elapsed_seconds']}))


if __name__ == '__main__':
    main()
