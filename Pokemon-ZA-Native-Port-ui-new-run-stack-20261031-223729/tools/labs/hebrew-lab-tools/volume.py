"""Text volume per category (English slot), local analysis; prints aggregate numbers only."""
import collections, glob, json, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfmsg import MsgFile, decode_units
VAR = re.compile(r'\{VAR [^}]*\}')
def cat(sub, name):
    if sub == 'script': return 'story-dialogue (script)'
    if sub == 'sk': return 'DLC Mega Dimension (sk)'
    n = name
    if n == 'monsname' or n.startswith('another_name'): return 'pokemon-names'
    if n.startswith('waza'): return 'moves'
    if n.startswith('tokusei'): return 'abilities'
    if n.startswith('item') or n in ('nuts_name', 'dressup_item_name', 'donut_name'): return 'items'
    if n.startswith('zukan') or n.startswith('zkn') or n == 'pokedex': return 'pokedex'
    if n.startswith('place') or n in ('btlspot',): return 'places'
    if n.startswith('btl_') or n in ('level_up',): return 'battle-messages'
    if n.startswith('tr'): return 'trainers'
    if n.startswith('quest'): return 'quests'
    if n in ('tips', 'load_tips', 'hud_tips', 'information', 'field_action_help'): return 'tips-help'
    if n in ('staff_list',): return 'credits'
    return 'menus-ui'
rows = collections.defaultdict(lambda: dict(files=0, lines=0, nonempty=0, chars=0, words=0, unique_strings=set()))
for p in sorted(glob.glob(os.path.join(sys.argv[1], 'romfs/ik_message/dat/English/*/*.dat'))):
    sub = os.path.basename(os.path.dirname(p)); name = os.path.basename(p)[:-4]
    c = cat(sub, name); r = rows[c]; r['files'] += 1
    for u in MsgFile(open(p, 'rb').read()).lines:
        s = decode_units(u); t = VAR.sub('', s).replace('\n', ' ').strip()
        r['lines'] += 1
        if t:
            r['nonempty'] += 1; r['chars'] += len(t); r['words'] += len(t.split()); r['unique_strings'].add(s)
out = {}
for c, r in sorted(rows.items(), key=lambda x: -x[1]['chars']):
    uc = sum(len(VAR.sub('', s).replace('\n', ' ').strip()) for s in r['unique_strings'])
    out[c] = dict(files=r['files'], lines=r['lines'], nonempty=r['nonempty'], chars=r['chars'], words=r['words'],
                  unique=len(r['unique_strings']), unique_chars=uc)
tot = {k: sum(v[k] for v in out.values()) for k in ('files', 'lines', 'nonempty', 'chars', 'words', 'unique', 'unique_chars')}
out['TOTAL'] = tot
json.dump(out, open(os.path.join(sys.argv[1], 'volume-by-category.json'), 'w'), indent=1)
for c, v in out.items(): print('%-26s %s' % (c, ' '.join('%s=%d' % kv for kv in v.items())))
