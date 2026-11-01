"""Bounded, read-only context review of r3 swap46578; not a gameplay verdict.

Existing generator/oracle/readers are reused unchanged. Stores metadata only and can
optionally materialize the exact validated mod in a NEW outside-Git directory.
Run with canonical zw and a canonical PC lease.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit
import fbedit as F
import oracle
import story_shuffle as S
sys.path.insert(0, str(Path(S.REPO) / 'port/story-rando/tools'))
import fbdump


def contexts(data):
    found = []
    def visit(value, path, ancestors):
        if isinstance(value, dict):
            labels = [s for i in (0, 1) for s in
                      ([value.get(i)] if isinstance(value.get(i), str) else value.get(i, [])
                       if isinstance(value.get(i), list) else [])
                      if isinstance(s, str) and not s.endswith('_condition')][:4]
            chain = ancestors + ([{'path': path, 'labels': labels}] if labels else [])
            if value.get(0) == 'phase_condition':
                found.append({'operator': value.get(1, 0), 'arguments': value.get(2, []),
                              'path': path, 'ancestor_labels': chain})
            for key, child in value.items(): visit(child, path + '/' + str(key), chain)
        elif isinstance(value, list):
            for i, child in enumerate(value): visit(child, path + '/' + str(i), ancestors)
    visit(fbdump.dump(data), 'root', [])
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path)
    ap.add_argument('--materialize', type=Path)
    args = ap.parse_args()
    out = args.out.resolve()
    if out.exists() or not audit.outside_git(out): ap.error('OUT must be new and outside Git')
    mod = args.materialize.resolve() if args.materialize else None
    if mod and (mod.exists() or not audit.outside_git(mod)): ap.error('mod must be new and outside Git')
    g = audit.Inputs(S.Romfs(str(Path(S.HL) / 'qa-game-reference-20261030/romfs.bin')))
    files, pj, plan = S.generate(g, [4, 6, 5, 7, 8])
    result = oracle.check(g, files, plan)
    if not result['ok']: raise RuntimeError(result['fails'])
    pinned = json.loads((Path(S.REPO).parent / 'Pokemon-ZA-Native-Port/evidence/story-continuation-20261101-r3/all24-model/summary.json').read_text(encoding='utf-8-sig'))
    expected = next(r['file_sha256'] for r in pinned['results'] if r['order'] == plan.order)
    actual = {p: audit.sha(d) for p, d in sorted(files.items())}
    if actual != expected: raise RuntimeError('candidate does not match published r3')
    warnings = []
    for item in plan.warn:
        path = item['where']
        if path not in g.cache: g.read(path)
        candidates = contexts(g.read(path))
        warnings.append(dict(item, matching_contexts=[c for c in candidates if c['arguments'] == list(item['vanilla'])]))
    chapter = 'ik_event/bin/trigger/main/trigger_main_06.bin'
    root = F.root(g.read(chapter), 'TrigRoot')
    conds, commands = [], []
    def collect(node, parents):
        if node.type == 'Cond': conds.append({'kind': node.kids[0].text(), 'operator': node.i32(1) or 0, 'arguments': S.sv(node.kids[2]) if 2 in node.kids else []})
        if node.type == 'Cmd': commands.append({'command': node.i32(0) or 0, 'arguments': S.cmd_args(node)})
    S.walk(root, collect)
    output = {'schema': 'za-story-dependency-review-1', 'order': plan.order, 'exact_r3_file_hashes_match': True,
              'file_sha256': actual, 'input_sha256': g.hashes, 'soft_count': len(result['soft']),
              'soft_by_source': dict(Counter(s.split(': ', 1)[-1].split(' op')[0] for s in result['soft'])),
              'clamps': warnings, 'chapter6_conditions': conds, 'chapter6_commands': commands,
              'chapter6_cond_kinds': dict(Counter(c['kind'] for c in conds)),
              'cross_chapter_flags_read': [c for c in conds if any(a.startswith('flag_Ev_m05_') for a in c['arguments'])],
              'chain': result['chain'], 'gameplay_verified': False, 'ready_for_ui': False, 'ready_for_ps5': False,
              'reader_context_scope': 'Existing schema-less reader supplies diagnostic ancestor labels; native semantic roles are not inferred from labels.'}
    out.mkdir()
    (out / 'review-local.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
    if mod:
        for path, data in files.items():
            dst = mod / 'shuffle/romfs' / path; dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(data)
        (mod / 'r3-file-manifest.json').write_text(json.dumps(actual, indent=2), encoding='utf-8')
    print(json.dumps({'out': str(out), 'exact_r3': True, 'soft': len(result['soft']), 'clamps': len(warnings),
                      'chapter6_kinds': output['chapter6_cond_kinds'], 'chapter5_flags_read': len(output['cross_chapter_flags_read'])}))


if __name__ == '__main__': main()
