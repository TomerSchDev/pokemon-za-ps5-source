"""Story-structure research: extract the ik_event tables and the Lua event scripts from the RomFS (read-only)
into OUT (a scratch folder OUTSIDE git - game data never goes into git), then dump them schema-less to JSON.

usage: py -3 story_extract.py OUT [--paths ikpaths.txt]
  ikpaths.txt: the 73 'ik_event/...' path strings the game binary references
  (`zw atlas --all str "ik_event/"`, last column). Default: a built-in list of the story tables.
Afterwards run, from OUT:  phase_summary.py j/phase.json > phase.txt ; quest_summary.py j/main_quest.json ;
  chapter_graph.py ; trig_stats.py ; cond_inventory.py ; lua_ph.py ; lua_deps.py  (copy or put this folder on PYTHONPATH)
"""
import argparse, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
HL = os.path.join(HERE, '..', '..', '..', '..', 'hebrew-lab')
sys.path.insert(0, os.path.join(HL, 'tools'))
sys.path.insert(0, HERE)
import za_romfs  # noqa: E402
import fbdump  # noqa: E402
import luadump  # noqa: E402

DEFAULT = ['ik_event/bin/phase/phase', 'ik_event/bin/phase/dlc_phase', 'ik_event/bin/quest/main_quest',
           'ik_event/bin/quest/sub_quest', 'ik_event/bin/quest/momiji_quest', 'ik_event/bin/quest/dlc_quest',
           'ik_event/bin/event_control/event_control', 'ik_event/bin/trigger/global/trigger_global',
           'ik_event/bin/trigger/map/trigger_map_t2', 'ik_event/bin/trainer_rank/trainer_rank',
           'ik_event/bin/royale_app_matching_info/royale_app_matching_info', 'ik_event/bin/npc_talk_data/npc_talk_data',
           'ik_event/bin/return_point/fiexd_return_point', 'ik_event/bin/menu_visible_type/menu_visible_type',
           'ik_event/bin/destination_data/destination_data', 'ik_event/bin/flag/event_flag',
           'ik_event/bin/flag/system_flag', 'ik_event/bin/flag/system_work', 'ik_event/bin/flag/quest_work',
           'ik_event/bin/trigger/boss_battle/trigger_boss_battle_global',
           'ik_event/bin/trigger/trainer_battle/trigger_trainer_battle_global',
           'ik_event/bin/trigger/wild_battle/trigger_wild_battle_global'] + \
          ['ik_event/bin/trigger/main/trigger_main_%02d' % i for i in range(11)] + \
          ['ik_event/bin/trigger/dlc/trigger_dlc_%02d' % i for i in range(1, 10)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('out')
    ap.add_argument('--romfs', default=os.path.join(HL, 'qa-game-reference-20261030', 'romfs.bin'))
    a = ap.parse_args()
    out = os.path.abspath(a.out)
    if os.path.commonpath([out, os.path.abspath(os.path.join(HERE, '..', '..', '..'))]) == os.path.abspath(os.path.join(HERE, '..', '..', '..')):
        sys.exit('OUT must be outside the repository (game data never goes into git)')
    g = za_romfs.Game(a.romfs)
    os.makedirs(os.path.join(out, 'j'), exist_ok=True)
    inv = {}
    for base in DEFAULT:
        p = base + '.bin'
        if not g.has(p): continue
        d = g.read(p)
        dst = os.path.join(out, 'x', p); os.makedirs(os.path.dirname(dst), exist_ok=True)
        open(dst, 'wb').write(d)
        json.dump(fbdump.dump(d), open(os.path.join(out, 'j', os.path.basename(base) + '.json'), 'w', encoding='utf-8'), ensure_ascii=False, indent=1)
        inv[p] = len(d)
    os.makedirs(os.path.join(out, 'lua'), exist_ok=True)
    for name, recs in g.packs:
        if not name.startswith('arc/scriptluabinrelease'): continue
        tag = name[len('arc/scriptluabinrelease'):].split('.')[0]
        for i, r in enumerate(recs):
            d = g.unpack(r)
            fn = os.path.join(out, 'lua', '%s_%04d_%016x.blua' % (tag, i, r['hash']))
            open(fn, 'wb').write(d)
            inv[fn] = len(d)
            if tag.startswith('event_ik'):
                rows = []
                luadump.walk(luadump.load(d), 'root', rows)
                json.dump(rows, open(os.path.join(out, 'event_ik.json'), 'w', encoding='utf-8'), ensure_ascii=False)
    json.dump(inv, open(os.path.join(out, 'inventory.json'), 'w'), indent=1)
    print(len(inv), 'files ->', out)


if __name__ == '__main__':
    main()
