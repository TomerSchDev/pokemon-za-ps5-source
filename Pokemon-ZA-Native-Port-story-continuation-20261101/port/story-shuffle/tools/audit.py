"""Record data-only validation of story orders; never publish game data or mark gameplay ready.

Run through the canonical zw story-shuffle-tool audit after claiming its PC queue.
OUT must be new and outside any git checkout. Existing generator/oracle are the authorities.
"""
import argparse
import datetime
import hashlib
import itertools
import importlib.util
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
import oracle
import story_shuffle as S


def sha(data):
    return hashlib.sha256(data).hexdigest()


def outside_git(path):
    return not any((p / '.git').exists() for p in (path, *path.parents))


class Inputs:
    def __init__(self, game):
        self.game, self.cache, self.hashes = game, {}, {}

    def has(self, path):
        return self.game.has(path)

    def read(self, path):
        if path not in self.cache:
            self.cache[path] = self.game.read(path)
            self.hashes[path] = {'bytes': len(self.cache[path]), 'sha256': sha(self.cache[path])}
        return self.cache[path]


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('out', type=Path)
    ap.add_argument('--romfs', default=str(Path(S.HL) / 'qa-game-reference-20261030' / 'romfs.bin'))
    ap.add_argument('--order', action='append', help='repeat to check selected orders; default: all24')
    ap.add_argument('--oracle-source', type=Path, help='explicit historical checker for baseline comparison; pinned in report')
    a = ap.parse_args()
    out = a.out.resolve()
    if out.exists() or not outside_git(out):
        ap.error('OUT must be new and outside every git checkout')
    out.mkdir(parents=True)
    tools = Path(__file__).resolve().parent
    sources = {str(p.relative_to(tools.parent)): sha(p.read_bytes())
               for p in sorted(tools.parent.rglob('*.py'))}
    sources['lua-context-manifest.json'] = sha((tools.parent / 'lua-context-manifest.json').read_bytes())
    sources['../story-rando/tools/luadump.py'] = sha((tools.parent.parent / 'story-rando/tools/luadump.py').read_bytes())
    checker = oracle
    if a.oracle_source:
        spec = importlib.util.spec_from_file_location('story_historical_oracle', a.oracle_source.resolve())
        checker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(checker)
        sources['explicit_historical_oracle'] = sha(a.oracle_source.read_bytes())
    orders = [[int(x) for x in o.split(',')] for o in a.order] if a.order else [
        [4, *middle] for middle in itertools.permutations(S.SHUFFLED)]
    game = Inputs(S.Romfs(a.romfs))
    results = []
    for order in orders:
        started = time.monotonic()
        try:
            files, plan_json, plan = S.generate(game, order, lua=True)
            check = checker.check(game, files, plan)
            row = {'order': order, 'ok': check['ok'], 'summary': check['summary'],
                   'hard_failures': check['fails'], 'soft_count': len(check['soft']),
                   'unmodeled_condition_count': len(check.get('unmodeled_conditions', [])),
                   'condition_factory_counts': check.get('condition_factory_counts', {}),
                   'schema_complete': check.get('schema_complete', False),
                   'invariant_failures': check.get('invariant_failures', check['fails']),
                   'clamped_ranges': len(plan.warn), 'lua_constants': len(plan_json.get('lua_constants', [])),
                   'lua_context_changes': plan_json.get('lua_constants', []),
                   'lua_dlc_preserved': True if check['ok'] else None,
                   'file_sha256': {p: sha(d) for p, d in sorted(files.items())}}
            # Reports contain identifiers and checks, never table bytes, Lua or save data.
            name = ''.join(map(str, order))
            evidence = dict(check)
            pairs = evidence.pop('condition_pairs', [])
            # The complete condition projection is game-derived metadata. Keep only its
            # digest/count in shareable evidence; the small blocked-case diagnostics retain
            # kind/all arguments/operator/source hash without exporting the full corpus.
            evidence['condition_pairs_count'] = len(pairs)
            evidence['condition_pairs_sha256'] = sha(json.dumps(pairs, sort_keys=True, separators=(',', ':')).encode())
            phase_ids = evidence.pop('new_phase_order', [])
            evidence['phase_entries_count'] = len(phase_ids)
            evidence['phase_order_sha256'] = sha(json.dumps(phase_ids, separators=(',', ':')).encode())
            (out / (name + '.json')).write_text(json.dumps(evidence, indent=2), encoding='utf-8')
        except (Exception, SystemExit) as exc:
            row = {'order': order, 'ok': False, 'error': type(exc).__name__ + ': ' + str(exc)}
        row['seconds'] = round(time.monotonic() - started, 3)
        results.append(row)
        print(json.dumps(row, separators=(',', ':')), flush=True)
        summary = {'schema': 'za-story-data-audit-1', 'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   'status': 'DATA_VALIDATED_GAMEPLAY_PENDING' if all(r['ok'] for r in results) and len(results) == len(orders)
                             else 'IN_PROGRESS_OR_FAILED',
                   'completed': len(results), 'requested': len(orders), 'all_ok': all(r['ok'] for r in results),
                   'ready_for_ui': False, 'ready_for_ps5': False, 'hardware_verified': False,
                   'full_chapter_playthrough_verified': False, 'source_sha256': sources,
                   'input_sha256': game.hashes, 'results': results,
                   'limitations': ['Data checks and earlier boundary experiment are not a full chapter playthrough.',
                                   'Clamped ranges and changed onward thresholds remain gameplay review items.',
                                   'New runs only; no save migration and no existing-save writes.']}
        (out / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return 0 if all(r['ok'] for r in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
