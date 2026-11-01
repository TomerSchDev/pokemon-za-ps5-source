"""Build the music-shuffle plan for Pokemon Legends: Z-A 2.0.2 from the game's own data (read-only).

How Z-A chooses music: BGM.bnk (Wwise v145) holds 65 music switch containers. Game code posts Wwise events named in
world/exl/audio/bgm_command/bgm_command.bin (PLAY_BGM_*, SET_STATE_*); the SET_STATE_* events set Wwise states and
each music switch's decision tree maps a combination of states to one music playlist ("song"). The plan lists every
decision-tree leaf (a u32 audio-node id at a fixed file offset of BGM.bnk) whose song may be replaced, grouped into
categories, so that a run can rewrite those u32 fields only - same file size, no other byte changes.

Rules (all from the game's data, recorded in the plan):
- songs: playlists that are leaves of a music switch, are not silent, contain an infinitely looping item and last
  at least 30 s. Silence, one-shot cues and short loops (victory jingles, adaptive 6.7 s parts) never move, and
  neither does a song with a user cue (a marker the game can wait for: the city's first-play intro advances the
  T1 music state from its cue; PC proof r29 showed a replacement there never reaches the main city loop).
- category by the event that plays the switch (or its ancestor switch):
    town   PLAY_BGM_PLACEMENT / PLAY_BGM_PLACEMENT_SA / PLAY_BGM_SA_FI_T4_SP leaves outside wild/battle zones
    zone   the same switches under the ZONE_WILD_IN / ZONE_BATTLE states (wild zones and battle zones)
    battle trainer and wild-event battles (PLAY_BGM_VS_TRAINER, PLAY_VS_TRAINER_SA, PLAY_BGM_VS_WILD_EVENT,
           PLAY_VS_WILD_EVENT_SUB, PLAY_VS_WILD_EVENT_SA) and the strong-wild layers (SET_STATE_ZONE_WILD_IN,
           SET_STATE_T3_IN, SET_STATE_T4_IN)
    boss   PLAY_BGM_VS_BOSS_01/02/04/05, PLAY_VS_BOSS_SA, PLAY_VS_WILD_MEGA_SA, PLAY_VS_WILD_SP (legendary/special)
  Never changed: the event/story folder (PS, EV_CMN, EV_EXC), the demo (cutscene) folder, the ST/NET folder, the
  adaptive PLAY_BGM_VS_BOSS_03, any leaf under a *WIN* (victory) state, and every event's direct Play target.
- variants: songs of one category in the same switch with the same structure (segments, loop vector, duration) are
  one unit (e.g. the six arrangements of the city theme); units move as a whole.
Usage: make_music_plan.py ROMFS_BIN OUT.json   (OUT must not be inside the git work tree's tracked folders)
"""
import hashlib
import json
import os
import re
import struct
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import za_bgm  # noqa

BANK_PATH = 'audio/wwise/bin/Switch/BGM.bnk'
COMMAND_PATH = 'world/exl/audio/bgm_command/bgm_command.bin'
ALGORITHM = 'za202-bgm-leaf-shuffle-v1'
MIN_SONG_MS = 30000.0
CATEGORIES = ['town', 'zone', 'battle', 'boss']
FIELD_EVENTS = ['PLAY_BGM_PLACEMENT', 'PLAY_BGM_PLACEMENT_SA', 'PLAY_BGM_SA_FI_T4_SP']
BATTLE_EVENTS = ['PLAY_BGM_VS_TRAINER', 'PLAY_VS_TRAINER_SA', 'PLAY_BGM_VS_WILD_EVENT', 'PLAY_VS_WILD_EVENT_SUB',
                 'PLAY_VS_WILD_EVENT_SA', 'SET_STATE_ZONE_WILD_IN', 'SET_STATE_T3_IN', 'SET_STATE_T4_IN']
BOSS_EVENTS = ['PLAY_BGM_VS_BOSS_01', 'PLAY_BGM_VS_BOSS_02', 'PLAY_BGM_VS_BOSS_04', 'PLAY_BGM_VS_BOSS_05',
               'PLAY_VS_BOSS_SA', 'PLAY_VS_WILD_MEGA_SA', 'PLAY_VS_WILD_SP']
ZONE_STATE_EVENTS = ['SET_STATE_ZONE_WILD_IN', 'SET_STATE_ZONE_BATTLE_IN']


def romfs_file(path, want):
    """(absolute offset, size) of a RomFS file, and its bytes"""
    with open(path, 'rb') as f:
        h = struct.unpack('<10Q', f.read(80))
        f.seek(h[3]); dm = f.read(h[4])
        f.seek(h[7]); fm = f.read(h[8])

        def dirpath(d):
            parts = []
            while d:
                parent, = struct.unpack_from('<I', dm, d)
                nl, = struct.unpack_from('<I', dm, d + 0x14)
                parts.append(dm[d + 0x18:d + 0x18 + nl].decode())
                d = parent
            return '/'.join(reversed(parts))
        o = 0
        while o + 0x20 <= len(fm):
            parent, _, off, size, _, nl = struct.unpack_from('<IIQQII', fm, o)
            name = fm[o + 0x20:o + 0x20 + nl].decode()
            d = dirpath(parent)
            if (d + '/' if d else '') + name == want:
                f.seek(h[9] + off)
                return h[9] + off, size, f.read(size)
            o += 0x20 + ((nl + 3) & ~3)
    raise KeyError(want)


def packed_file(romfs, path):
    sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
    import za_romfs  # read-only Trinity pack reader (ooz)
    return za_romfs.Game(romfs).read(path)


def build(romfs):
    bank_off, bank_size, data = romfs_file(romfs, BANK_PATH)
    commands = packed_file(romfs, COMMAND_PATH)
    names = sorted({m.group().decode() for m in re.finditer(rb'[A-Z][A-Z0-9_]{2,}', commands)})
    b = za_bgm.Bank(data)
    by_id = {}
    for n in names:
        by_id.setdefault(za_bgm.fnv1_32(n), n)
    event_id = {n: za_bgm.fnv1_32(n) for n in names}
    # states set by named events: (group, state) -> event names
    state_events = defaultdict(set)
    for eid, acts in b.events.items():
        for a in acts:
            if a['kind'] == 'SetState':
                state_events[(a['group'], a['state'])].add(by_id.get(eid, ''))
    # states that only zone-entry events set (ZONE_WILD_IN also resets shared groups such as the district state)
    zone_states = {gs for gs, evs in state_events.items() if evs and evs <= set(ZONE_STATE_EVENTS)}
    # switches played by each named event, with descendants (switch leaves that are switches)
    def played(ev):
        eid = event_id.get(ev)
        if eid is None or eid not in b.events:
            raise KeyError('event %s not in BGM.bnk' % ev)
        return [a['target'] for a in b.events[eid] if a['kind'] == 'Play' and b.type_of(a['target']) == za_bgm.SWITCH]

    def with_children(sw, seen=None):
        seen = seen if seen is not None else []
        if sw in seen:
            return seen
        seen.append(sw)
        for keys, x, off in za_bgm.switch_leaves(b.music[sw]):
            if b.type_of(x) == za_bgm.SWITCH:
                with_children(x, seen)
        return seen
    switch_category, switch_event = {}, {}
    for cat, evs in (('field', FIELD_EVENTS), ('battle', BATTLE_EVENTS), ('boss', BOSS_EVENTS)):
        for ev in evs:
            for top in played(ev):
                for sw in with_children(top):
                    if sw in switch_category and switch_category[sw] != cat:
                        raise ValueError('switch %08x in two categories' % sw)
                    switch_category[sw] = cat
                    switch_event.setdefault(sw, ev)
    # leaves -> slots
    excluded = defaultdict(int)
    songs = {}
    slots = []
    leaf_category = {}
    for sw in sorted(switch_category):
        cat_base = switch_category[sw]
        groups = b.music[sw]['groups']
        for keys, x, off in za_bgm.switch_leaves(b.music[sw]):
            if b.type_of(x) != za_bgm.PLAYLIST:
                if b.type_of(x) not in (za_bgm.SWITCH, None):
                    excluded['leaf_not_playlist'] += 1
                continue
            info = songs.get(x) or b.playlist_info(x)
            songs[x] = info
            labels = set()
            for g, k in zip(groups, keys):
                labels |= state_events.get((g, k), set())
            if info['silent']:
                excluded['silence'] += 1
                continue
            if not info['infinite'] or info['missing']:
                excluded['not_looping'] += 1
                continue
            if info['duration_ms'] < MIN_SONG_MS:
                excluded['short_loop'] += 1
                continue
            if any('WIN' in n for n in labels):
                excluded['victory'] += 1
                continue
            if info['user_cues']:
                # a marker between a segment's entry and exit cues is a sync point the game can listen for (the
                # city's first-play intro advances the T1 state from its cue); such songs never move
                excluded['user_cue'] += 1
                continue
            if cat_base == 'field':
                in_zone = any((g, k) in zone_states for g, k in zip(groups, keys))
                cat = 'zone' if in_zone else 'town'
            else:
                cat = cat_base
            prev = leaf_category.get(x)
            if prev and prev != cat:
                raise ValueError('song %08x in categories %s and %s' % (x, prev, cat))
            leaf_category[x] = cat
            file_off = b.objects[sw][1] + off
            if struct.unpack_from('<I', data, file_off)[0] != x:
                raise ValueError('slot offset')
            slots.append(dict(offset=file_off, song='%08x' % x, switch='%08x' % sw, category=cat))
    # units: same category, same switch, same structure
    unit_of = {}
    units = []
    for cat in CATEGORIES:
        groups = defaultdict(list)
        for x, c in leaf_category.items():
            if c != cat:
                continue
            sws = sorted({s['switch'] for s in slots if s['song'] == '%08x' % x})
            info = songs[x]
            key = (tuple(sws), info['segments'], tuple(info['loops']), round(info['duration_ms']))
            groups[key].append(x)
        for key in sorted(groups, key=lambda k: min(groups[k])):
            members = sorted(groups[key])
            uid = len(units)
            for m in members:
                unit_of[m] = uid
            units.append(dict(category=cat, switches=list(key[0]),
                              event=switch_event[int(key[0][0], 16)],
                              members=['%08x' % m for m in members],
                              duration_s=round(songs[members[0]]['duration_ms'] / 1000, 1),
                              segments=songs[members[0]]['segments']))
    slots.sort(key=lambda s: s['offset'])
    plan = dict(schema=1, algorithm=ALGORITHM, game='2.0.2', build_id='b1f12fd919eae86ab8a978317677e64bce443d1f',
                bank=dict(path=BANK_PATH, romfs_image_offset=bank_off, bytes=bank_size,
                          sha256=hashlib.sha256(data).hexdigest(), version=b.version, music_objects=len(b.music)),
                names_source=dict(path=COMMAND_PATH, sha256=hashlib.sha256(commands).hexdigest()),
                min_song_seconds=MIN_SONG_MS / 1000, categories=CATEGORIES,
                rules=dict(field_events=FIELD_EVENTS, battle_events=BATTLE_EVENTS, boss_events=BOSS_EVENTS,
                           zone_state_events=ZONE_STATE_EVENTS,
                           unchanged=['event/story folder', 'demo (cutscene) folder', 'ST/NET folder',
                                      'PLAY_BGM_VS_BOSS_03 adaptive switch', 'victory (WIN) leaves',
                                      'silence', 'one-shot', 'loops under 30 s', 'songs with user cues',
                                      'direct event Play targets']),
                excluded_leaves=dict(sorted(excluded.items())),
                units=[dict(u, unit=i) for i, u in enumerate(units)],
                slots=[dict(offset=s['offset'], song=s['song'], unit=unit_of[int(s['song'], 16)]) for s in slots])
    return plan


def main():
    romfs, out = sys.argv[1], os.path.abspath(sys.argv[2])
    plan = build(romfs)
    text = json.dumps(plan, indent=1, sort_keys=True) + '\n'
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(text)
    counts = defaultdict(lambda: [0, 0, 0])
    for u in plan['units']:
        counts[u['category']][0] += 1
        counts[u['category']][1] += len(u['members'])
    for s in plan['slots']:
        counts[plan['units'][s['unit']]['category']][2] += 1
    print('plan', out, hashlib.sha256(text.encode()).hexdigest())
    for c in CATEGORIES:
        print('  %-6s units=%d songs=%d slots=%d' % (c, *counts[c]))
    print('  excluded leaves', plan['excluded_leaves'])


if __name__ == '__main__':
    main()
