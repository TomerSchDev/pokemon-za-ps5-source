"""open-world: "World: open from the start" as an opt-in randomizer option (Pokemon Legends: Z-A 2.0.2).

What it does: lowers story-progress thresholds (`phase_condition` with the table op 5 = ">=") on the world-content
gates (shops, taxis, side quests, training, Mega Shards shop, ...) to an early "floor" phase. Every write is an
in-place same-length rewrite of a 5-digit ASCII number inside the FlatBuffers table - no re-encode, no size change.
Story-critical data (phase.bin, main quests, main-story triggers, stoppers, battle triggers, return points, NPC talk,
menus) is never touched; the oracle (`verify`) proves that from the bytes.

usage:
  open_world.py build OUTMOD [--romfs R] [--tier open|open-postgame] [--glide-early]
  open_world.py verify OUTMOD [--romfs R]          independent oracle over the written mod (exit 1 on any finding)
  open_world.py inventory [--romfs R] [--json F]   every phase_condition in every table, classified (no writes)
OUTMOD must be outside git (it holds game data). It gets OUTMOD/romfs/<path> for changed files, OUTMOD/open-world-log.json
(every changed condition) and OUTMOD/save-ops.json (optional starting-save flags; empty unless --glide-early).

Order with other story options: apply open-world LAST (after a chapter shuffle / skip-intro data patch). It is
independent of the phase numbering of chapters 4-8 because (a) it classifies gates by what they are (taxi NPC, shop
lineup, side quest id), never by their number, and (b) its floors are derived from phase.bin (chapters 1-2, which no
shuffle moves). test_open_world.py checks that open-world and chapter_swap commute byte-for-byte.
"""
import argparse, collections, hashlib, json, os, re, struct, sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..'))
HL = os.path.abspath(os.path.join(REPO, '..', 'hebrew-lab'))
DEFAULT_ROMFS = os.environ.get('ZA_ROMFS', os.path.join(HL, 'qa-game-reference-20261030', 'romfs.bin'))
VERSION = 'open-world-1'

# Every table that reads the story phase (found by scanning all 73 ik_event table paths the game references + shops).
TABLES = ['ik_event/bin/phase/phase', 'ik_event/bin/quest/main_quest', 'ik_event/bin/quest/sub_quest',
          'ik_event/bin/quest/momiji_quest', 'ik_event/bin/npc_talk_data/npc_talk_data',
          'ik_event/bin/return_point/fiexd_return_point', 'ik_event/bin/menu_visible_type/menu_visible_type',
          'ik_event/bin/destination_data/destination_data',
          'ik_event/bin/door_jump_name_overwrite/door_jump_name_overwrite',
          'ik_event/bin/trigger/global/trigger_global', 'ik_event/bin/trigger/map/trigger_map_t2',
          'ik_event/bin/trigger/boss_battle/trigger_boss_battle_global',
          'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global',
          'ik_event/bin/trigger/wild_battle/trigger_wild_battle_global',
          'world/exl/shop/shop_item_lineup/shop_item_lineup'] + \
         ['ik_event/bin/trigger/main/trigger_main_%02d' % i for i in range(11)]
SHOP = 'world/exl/shop/shop_item_lineup/shop_item_lineup.bin'
SUBQ = 'ik_event/bin/quest/sub_quest.bin'
MOMIJI = 'ik_event/bin/quest/momiji_quest.bin'
MAPT = 'ik_event/bin/trigger/map/trigger_map_t2.bin'
PHASE = 'ik_event/bin/phase/phase.bin'
# Files open-world may write. Everything else is protected (story order, stoppers, battles, talk, menus, returns).
WRITABLE = {SHOP, SUBQ, MOMIJI, MAPT}
STORY_FILES = [PHASE, 'ik_event/bin/quest/main_quest.bin'] + \
              ['ik_event/bin/trigger/main/trigger_main_%02d.bin' % i for i in range(11)]

OP_GE = 5          # table-side op codes (loader-mapped): 1 ==, 2 !=, 4 <, 5 >=, 6 <=, 8 range
POSTGAME_MIN = 90000   # chapter 9+ (climax, post-game): never opened
GAME_CLEAR = 'SYS_FLAG_GAME_CLEAR'
# same length (19), set TRUE by the phase.bin transition into 21110 (chapter 2) and never cleared afterwards
GAME_CLEAR_STANDIN = 'FLAG_POKEDEX_ENABLE'

# category -> (floor name, description). A gate is opened only if its category is listed for the tier.
CATEGORIES = {
    'shop':        ('shop',      'shop lineup rows (friendly shop, stone shop, Mega shop) with phase >= X'),
    'taxi':        ('freeroam',  'taxi drivers (Ev_sys_taxi), all 22 of them'),
    'pc_event':    ('freeroam',  'Pokemon Center lady events (PokemonCenterEvent)'),
    'training':    ('freeroam',  'training NPC (Ev_sys_tokkun)'),
    'mega_shards': ('freeroam',  'Mega Shards shop NPC (Ev_sys_kakera)'),
    'base_points': ('freeroam',  'base-points NPC (Ev_sys_kisopoint)'),
    'npc_gift':    ('freeroam',  'one-time NPC item gifts (flag_ReceiveNPC_*)'),
    'side_quest':  ('freeroam',  'side quests (sub_quest.bin) up to chapter 8, minus story-linked ones'),
    'mable':       ('mable',     "Mable's research tasks (momiji_quest.bin)"),
}
TIERS = {'normal': set(), 'open': set(CATEGORIES), 'open-postgame': set(CATEGORIES) | {'shop_postgame'}}


# ----------------------------------------------------------------------------------------------- FlatBuffers walker
class FB:
    def __init__(s, d): s.d = d; s.n = len(d)
    def u32(s, p): return struct.unpack_from('<I', s.d, p)[0]
    def i32(s, p): return struct.unpack_from('<i', s.d, p)[0]
    def u16(s, p): return struct.unpack_from('<H', s.d, p)[0]

    def string(s, p):
        if p < 0 or p % 4 or p + 4 > s.n: return None
        k = s.u32(p)
        if not 0 < k <= 512 or p + 4 + k >= s.n or s.d[p + 4 + k] != 0: return None
        try:
            t = bytes(s.d[p + 4:p + 4 + k]).decode('utf-8')
        except UnicodeDecodeError:
            return None
        return None if any(ord(c) < 32 for c in t) else t

    def table(s, t):
        if t < 4 or t % 4 or t + 4 > s.n: return None
        v = t - s.i32(t)
        if v < 0 or v + 4 > s.n or v % 2: return None
        vs, ts = s.u16(v), s.u16(v + 2)
        if not (4 <= vs <= 256 and vs % 2 == 0 and 4 <= ts <= 8192 and v + vs <= s.n and t + ts <= s.n): return None
        offs = [s.u16(v + 4 + 2 * i) for i in range((vs - 4) // 2)]
        if any(o and (o < 4 or o >= ts) for o in offs): return None
        return offs, ts

    def field_str(s, t, i):
        offs, _ = s.table(t)
        if i >= len(offs) or not offs[i]: return None
        q = t + offs[i]
        return s.string(q + s.u32(q)) if q % 4 == 0 else None

    def field_i32(s, t, i, default=0):
        offs, _ = s.table(t)
        return s.i32(t + offs[i]) if i < len(offs) and offs[i] else default

    def str_vec(s, t, i):
        """[(offset of the string, text)] of the string vector in field i"""
        offs, _ = s.table(t)
        if i >= len(offs) or not offs[i]: return []
        q = t + offs[i]; v = q + s.u32(q); out = []
        for k in range(s.u32(v)):
            e = v + 4 + 4 * k; p = e + s.u32(e); out.append((p, s.string(p)))
        return out


def walk(d):
    """Structural walk from the root. Returns (fb, tables {offset: top}, strings {top: [(off, text)]}).
    top = (root field, index) of the root vector element the table belongs to."""
    fb = FB(d); seen = {}; strs = collections.defaultdict(list)

    def visit_table(t, top, depth):
        if t in seen or depth > 40: return
        r = fb.table(t)
        if not r: return
        seen[t] = top
        offs, ts = r
        present = sorted(o for o in offs if o)
        for o in present:
            nxt = min([x for x in present if x > o] + [ts])
            if nxt - o >= 4 and (t + o) % 4 == 0: visit_ref(t + o, top, depth)

    def visit_ref(q, top, depth):
        r = fb.u32(q); x = q + r
        if r < 4 or x >= fb.n: return
        st = fb.string(x)
        if st is not None:
            strs[top].append((x, st)); return
        if x % 4 == 0 and x + 4 <= fb.n:
            cnt = fb.u32(x)
            if 0 < cnt < 100000 and x + 4 + 4 * cnt <= fb.n:
                els = [x + 4 + 4 * k for k in range(cnt)]
                tg = [e + fb.u32(e) for e in els]
                if all(t < fb.n and (fb.string(t) is not None or fb.table(t)) for t in tg) and not fb.table(x):
                    for e in els: visit_ref(e, top, depth + 1)
                    return
        if fb.table(x): visit_table(x, top, depth + 1)

    root = fb.u32(0)
    offs, _ = fb.table(root)
    for i, o in enumerate(offs):
        if not o: continue
        q = root + o; x = q + fb.u32(q)
        if x + 4 > fb.n: continue
        cnt = fb.u32(x)
        if 0 < cnt < 100000 and x + 4 + 4 * cnt <= fb.n and \
                all(fb.table(x + 4 + 4 * k + fb.u32(x + 4 + 4 * k)) for k in range(min(cnt, 4))):
            for k in range(cnt):
                e = x + 4 + 4 * k
                visit_table(e + fb.u32(e), (i, k), 0)
    return fb, seen, strs


def conditions(d, name='phase_condition'):
    """every condition table called NAME: dict(t, op, args=[(off, text)], top, ctx=[strings of the top element])"""
    fb, seen, strs = walk(d)
    out = []
    for t, top in seen.items():
        if fb.field_str(t, 0) != name: continue
        out.append(dict(t=t, op=fb.field_i32(t, 1), args=fb.str_vec(t, 2), top=top,
                        ctx=[x for _, x in strs[top]]))
    out.sort(key=lambda c: c['t'])
    return out


# ------------------------------------------------------------------------------------------------- game data access
class Game:
    """romfs reader with optional overlays: BASE mod folders (OUT/romfs/<path>) written by earlier story options
    (chapter shuffle, skip-intro). The last overlay that has a file wins, like the runtime mod loader."""
    def __init__(s, romfs, base_mods=()):
        sys.path.insert(0, os.path.join(HL, 'tools'))
        import za_romfs  # noqa: E402  (hebrew-lab reader; read-only)
        s.g = za_romfs.Game(romfs)
        s.base_mods = [os.path.abspath(m) for m in base_mods]
        s.cache = {}

    def read(s, path):
        if path not in s.cache:
            src = [os.path.join(m, 'romfs', path) for m in s.base_mods if os.path.exists(os.path.join(m, 'romfs', path))]
            s.cache[path] = open(src[-1], 'rb').read() if src else bytes(s.g.read(path))
        return s.cache[path]


def phase_entries(d):
    """phase.bin -> [(id, [(action type, [args])])] in vector order"""
    fb = FB(d)
    root = fb.u32(0); offs, _ = fb.table(root)
    q = root + offs[0]; v = q + fb.u32(q)
    out = []
    for k in range(fb.u32(v)):
        e = v + 4 + 4 * k; t = e + fb.u32(e)
        pid = fb.field_i32(t, 0)
        acts = []
        o, _ = fb.table(t)
        if len(o) > 2 and o[2]:
            aq = t + o[2]; av = aq + fb.u32(aq)
            for j in range(fb.u32(av)):
                ae = av + 4 + 4 * j; a = ae + fb.u32(ae)
                ao, _ = fb.table(a)
                typ = fb.i32(a + ao[0]) if ao and ao[0] else 0
                acts.append((typ, [x for _, x in fb.str_vec(a, 1)]))
        out.append((pid, acts))
    return out


def floors(phase_bin):
    """Floors are derived from the data, so they follow any renumbering of the table:
    shop     = the first phase id (right after the opening scene, 10000)
    freeroam = the phase reached when the map/fast-travel/Pokedex tutorial ends (entry after the one that sets
               flag_FastTravel_Enable; vanilla 21110, chapter 2)
    mable    = the phase reached when Mable's research unlocks (entry after FLAG_MOMIJI_ENABLE; vanilla 21600)"""
    ents = phase_entries(phase_bin)
    ids = [pid for pid, _ in ents]

    def after(flag):
        for i, (pid, acts) in enumerate(ents):
            if any(typ == 8 and a[:2] == [flag, 'TRUE'] for typ, a in acts):
                return ids[i + 1]
        raise SystemExit('phase.bin: no transition sets ' + flag)
    return {'shop': next(x for x in ids if x), 'freeroam': after('flag_FastTravel_Enable'),
            'mable': after('FLAG_MOMIJI_ENABLE')}


def story_strings(game):
    """identifiers the main story itself reads or writes (phase transitions, main quests, main triggers)"""
    s = set()
    for p in STORY_FILES:
        s |= set(m.group().decode() for m in re.finditer(rb'[A-Za-z0-9_]{4,}', game.read(p)))
    return {x for x in s if re.match(r'(SYS_WORK_QUEST_\d+|flag_Ev_sub_\d+\w*|sub_\d+|SYS_WORK_sub\d+\w*)$', x)}


# --------------------------------------------------------------------------------------------------- classification
def classify(path, c, story_ids):
    """-> (category or None, key, reason). Pure function of the gate's identity, never of its threshold."""
    ctx = c['ctx']
    if path == SHOP:
        return 'shop', ctx[0] if ctx else '?', ''
    if path == MOMIJI:
        return 'mable', next((x for x in ctx if x.startswith('momiji_')), '?'), ''
    if path == SUBQ:
        key = next((x for x in ctx if re.match(r'sub_\d+$', x)), '?')
        linked = sorted(x for x in ctx if x in story_ids)
        if linked: return None, key, 'story-linked: ' + ','.join(linked[:4])
        return 'side_quest', key, ''
    if path == MAPT:
        key = ctx[0] if ctx else '?'
        if 'Ev_sys_taxi' in ctx: return 'taxi', key, ''
        if 'PokemonCenterEvent' in ctx: return 'pc_event', key, ''
        if 'Ev_sys_tokkun' in ctx: return 'training', key, ''
        if 'Ev_sys_kakera' in ctx: return 'mega_shards', key, ''
        if 'Ev_sys_kisopoint' in ctx: return 'base_points', key, ''
        if any(x.startswith('flag_ReceiveNPC_') for x in ctx): return 'npc_gift', key, ''
        return None, key, 'map trigger not in the open list'
    return None, (c['ctx'][0] if c['ctx'] else '?'), 'protected table'


def stopperish(ctx):
    return any(re.search(r'stopper|Ev_m\d\d_|^main_\d', x) for x in ctx)


# --------------------------------------------------------------------------------------------------------- build
def plan(game, tier):
    fl = floors(game.read(PHASE))
    sid = story_strings(game)
    cats = TIERS[tier]
    changes, kept = [], collections.Counter()
    for base in TABLES:
        path = base + '.bin'
        d = game.read(path)
        if b'phase_condition' not in d: continue
        for c in conditions(d):
            cat, key, why = classify(path, c, sid)
            vals = [x for _, x in c['args']]
            if cat not in cats:
                kept[(path, why or 'not in tier')] += 1; continue
            if c['op'] != OP_GE or len(c['args']) != 1:
                kept[(path, 'op %s (only >= is lowered)' % c['op'])] += 1; continue
            off, old = c['args'][0]
            floor = fl[CATEGORIES[cat][0]]
            if not old.isdigit() or int(old) >= POSTGAME_MIN:
                kept[(path, 'post-game threshold')] += 1; continue
            if int(old) <= floor:
                kept[(path, 'already open at the floor')] += 1; continue
            new = str(floor)
            if len(new) != len(old):
                kept[(path, 'length differs')] += 1; continue
            if path == MAPT and stopperish(c['ctx']):
                kept[(path, 'main-story context')] += 1; continue
            changes.append(dict(file=path, cat=cat, key=key, op=c['op'], old=old, new=new, offset=off))
    if 'shop_postgame' in cats:
        for c in conditions(game.read(SHOP), 'flag_condition'):
            for off, txt in c['args']:
                if txt == GAME_CLEAR and c['op'] == 1:
                    changes.append(dict(file=SHOP, cat='shop_postgame', key=c['ctx'][0] if c['ctx'] else '?',
                                        op=c['op'], old=txt, new=GAME_CLEAR_STANDIN, offset=off))
    return fl, changes, kept


def apply(data, changes):
    """in-place same-length writes; returns {path: bytearray}"""
    out = {}
    for ch in changes:
        b = out.setdefault(ch['file'], bytearray(data[ch['file']]))
        o, old, new = ch['offset'], ch['old'].encode(), ch['new'].encode()
        assert len(old) == len(new) and struct.unpack_from('<I', b, o)[0] == len(old) and b[o + 4:o + 4 + len(old)] == old, ch
        b[o + 4:o + 4 + len(new)] = new
    return out


def sha(b): return hashlib.sha256(b).hexdigest()


def outside_git(path):
    p = os.path.abspath(path)
    if os.path.commonpath([p, REPO]) == REPO: sys.exit('OUTMOD must be outside the repository (game data never goes into git)')
    return p


def cmd_build(a):
    out = outside_git(a.out)
    if os.path.exists(os.path.join(out, 'romfs')): sys.exit('OUTMOD/romfs already exists; use a new folder')
    game = Game(a.romfs, a.base_mod)
    fl, changes, kept = plan(game, a.tier)
    patched = apply({ch['file']: game.read(ch['file']) for ch in changes}, changes)
    for path, b in sorted(patched.items()):
        dst = os.path.join(out, 'romfs', path); os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(b)
    save_ops = []
    if a.glide_early:
        save_ops.append(dict(op='sysflag', name='FLAG_ROTOM_GLIDE_ENABLE', value=1,
                             why='Rotom glide from the start (vanilla: chapter 5 transition 50200). Experimental.'))
    log = dict(tool=VERSION, tier=a.tier, floors=fl, romfs=os.path.basename(a.romfs), base_mods=game.base_mods,
               files={p: dict(sha256_in=sha(game.read(p)), sha256_out=sha(b), size=len(b)) for p, b in patched.items()},
               counts=dict(collections.Counter(ch['cat'] for ch in changes)),
               changes=changes, kept={'%s | %s' % k: v for k, v in sorted(kept.items())}, save_ops=save_ops)
    json.dump(log, open(os.path.join(out, 'open-world-log.json'), 'w'), indent=1)
    json.dump(save_ops, open(os.path.join(out, 'save-ops.json'), 'w'), indent=1)
    print('floors', fl)
    print('changed %d conditions in %d files:' % (len(changes), len(patched)), log['counts'])
    return 0


# --------------------------------------------------------------------------------------------------------- oracle
def verify(game, out, quiet=False):
    """Independent checks on the written mod. Returns a list of findings (empty = pass)."""
    bad = []
    log = json.load(open(os.path.join(out, 'open-world-log.json')))
    fl = floors(game.read(PHASE))
    sid = story_strings(game)
    allowed_new = {str(v) for v in fl.values()} | {GAME_CLEAR_STANDIN}
    root = os.path.join(out, 'romfs')
    written = []
    for dp, _, fs in os.walk(root):
        written += [os.path.relpath(os.path.join(dp, f), root).replace('\\', '/') for f in fs]
    n_changed = 0
    for path in written:
        if path not in WRITABLE: bad.append('%s: protected file written' % path); continue
        a, b = game.read(path), open(os.path.join(root, path), 'rb').read()
        if len(a) != len(b): bad.append('%s: size changed' % path); continue
        diff = [i for i in range(len(a)) if a[i] != b[i]]
        conds = conditions(a) + (conditions(a, 'flag_condition') if path == SHOP else [])
        spans = {}
        for c in conds:
            for off, txt in c['args']:
                spans[off] = (c, txt)
        hit = set()
        for i in diff:
            owner = next(((o, c, t) for o, (c, t) in spans.items() if o + 4 <= i < o + 4 + len(t or '')), None)
            if owner is None: bad.append('%s @%d: byte changed outside any condition argument' % (path, i)); continue
            hit.add(owner[0])
        for o in sorted(hit):
            c, old = spans[o]
            new = b[o + 4:o + 4 + len(old)].decode()
            name = FB(a).field_str(c['t'], 0)
            n_changed += 1
            if new not in allowed_new: bad.append('%s @%d: new value %s is not a floor' % (path, o, new))
            if name == 'phase_condition':
                if c['op'] != OP_GE: bad.append('%s @%d: op %s changed (only >= may be lowered)' % (path, o, c['op']))
                if not (new.isdigit() and old.isdigit() and int(new) < int(old) < POSTGAME_MIN):
                    bad.append('%s @%d: %s -> %s is not a lowering below chapter 9' % (path, o, old, new))
                cat, key, why = classify(path, c, sid)
                if cat is None: bad.append('%s @%d (%s): changed a gate that is not openable: %s' % (path, o, key, why))
                if stopperish(c['ctx']) and path == MAPT: bad.append('%s @%d: main-story context' % (path, o))
                if path == SUBQ and any(x in sid for x in c['ctx']): bad.append('%s @%d (%s): story-linked side quest' % (path, o, key))
            elif not (name == 'flag_condition' and old == GAME_CLEAR and log['tier'] == 'open-postgame'):
                bad.append('%s @%d: %s %s changed' % (path, o, name, old))
        # structure intact: the same conditions decode at the same places
        if [(c['t'], c['op'], len(c['args'])) for c in conditions(b)] != [(c['t'], c['op'], len(c['args'])) for c in conditions(a)]:
            bad.append('%s: condition structure changed' % path)
    if n_changed != len(log['changes']): bad.append('log lists %d changes, bytes show %d' % (len(log['changes']), n_changed))
    # main-story triggers and phase order: unchanged by construction (not in WRITABLE); re-state it explicitly
    for p in STORY_FILES:
        if p in written: bad.append('%s: story file in the mod' % p)
    if not quiet:
        print('verify:', 'PASS' if not bad else 'FAIL', '- %d files, %d changed conditions' % (len(written), n_changed))
        for x in bad[:50]: print('  ', x)
    return bad


def cmd_verify(a):
    out = os.path.abspath(a.out)
    base = json.load(open(os.path.join(out, 'open-world-log.json'))).get('base_mods', [])
    return 1 if verify(Game(a.romfs, base), out) else 0


def cmd_inventory(a):
    game = Game(a.romfs)
    sid = story_strings(game)
    rows = []
    for base in TABLES:
        path = base + '.bin'
        d = game.read(path)
        for c in conditions(d):
            cat, key, why = classify(path, c, sid)
            rows.append(dict(file=path, op=c['op'], args=[x for _, x in c['args']], cat=cat, key=key, why=why))
    cnt = collections.Counter((r['file'].split('/')[-1], r['cat'] or 'keep') for r in rows)
    for k, v in sorted(cnt.items()): print('%-40s %-12s %d' % (k[0], k[1], v))
    print('total', len(rows))
    if a.json: json.dump(rows, open(a.json, 'w'), indent=0)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = ap.add_subparsers(dest='cmd', required=True)
    b = sp.add_parser('build'); b.add_argument('out'); b.add_argument('--romfs', default=DEFAULT_ROMFS)
    b.add_argument('--tier', default='open', choices=sorted(TIERS)); b.add_argument('--glide-early', action='store_true')
    b.add_argument('--base-mod', action='append', default=[], help='mod folder of an earlier story option (shuffle/skip-intro); repeatable')
    v = sp.add_parser('verify'); v.add_argument('out'); v.add_argument('--romfs', default=DEFAULT_ROMFS)
    i = sp.add_parser('inventory'); i.add_argument('--romfs', default=DEFAULT_ROMFS); i.add_argument('--json')
    a = ap.parse_args()
    return {'build': cmd_build, 'verify': cmd_verify, 'inventory': cmd_inventory}[a.cmd](a)


if __name__ == '__main__':
    sys.exit(main())
