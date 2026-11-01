"""Read-only: resolve animation file names (.tranm/.traef) in Pokemon model folders by probing a motion-name vocabulary
(names from the NSO strings + pack names + common Trinity stems) over ids 0000-0999 and groups 0/1/2.
Usage: anim_inventory.py pm0025/pm0025_00_00 [more folders]"""
import collections, json, re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
S = r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/species-lab'
g = za_romfs.Game(GAME)
stems = set()
base_words = ['defaultwait01', 'defaultwait02', 'battlewait01', 'battlewait02', 'defaultidle01', 'defaultidle02', 'defaultidle03',
              'walk01', 'walk02', 'run01', 'run02', 'dash01', 'stepin01', 'stepout01', 'jumpdown01', 'jumpup01', 'jump01', 'land01', 'land02',
              'wild_bool01', 'wild_bool02', 'wildbool01', 'wildbool02', 'rest01', 'rest02', 'sleep01', 'sleep02', 'eat01', 'eat02',
              'refresh01', 'roar01', 'roar02', 'lookaround01', 'search01', 'wild_shot01', 'wild_shot02', 'wildshot01', 'wildshot02',
              'attack01', 'attack02', 'attack03', 'rangeattack01', 'rangeattack02', 'rangeattack03', 'charge01', 'charge02', 'damage01',
              'damage02', 'damage03', 'stun01', 'down01', 'down02', 'notice01', 'notice02', 'glad01', 'glad02', 'hate01', 'formchange01',
              'formchange02', 'directionattack01', 'directionattack02', 'directionattack03', 'uniquewait01', 'uniquewait02', 'loop01',
              'merge_default_battle01', 'merge_default_battle02', 'fly01', 'hover01', 'swim01', 'dive01', 'float01', 'surprise01',
              'happy01', 'sad01', 'angry01', 'escape01', 'threat01', 'appeal01', 'capture01', 'ball01', 'ballout01', 'ballin01',
              'pet01', 'touch01', 'play01', 'dance01', 'turn', 'turnmove01', 'turnmove02', 'buttobi01', 'faint01', 'dead01', 'getup01',
              'shake01', 'shake02', 'scratch01', 'yawn01', 'sniff01', 'dig01', 'climb01', 'hide01', 'appear01', 'disappear01',
              'move01', 'special01', 'special02', 'special03', 'win01', 'lose01', 'mega01', 'megaevo01', 'evolution01', 'gimmick01']
sufs = ['', '_start', '_loop', '_end']
turns = ['_r000', '_r090', '_l090', '_r180', '_l180', '_r045', '_l045', '_r135', '_l135']
for w in base_words:
    for s in (turns if w.startswith('turn') else sufs): stems.add(w + s)
for name, recs in g.packs:
    m = re.search(r'pm\d{4}_\d\d_\d\d_\d(\d{4})_([a-z0-9_]+?)\.(traef|tranm)\.trpak$', name)
    if m: stems.add(m.group(2))
nso = ['0631_directionattack02', '0512_stun01_end', '0560_notice01', '0272_wild_bool01_end', '0632_directionattack03', '0501_damage02',
       '0300_roar01', '0626_formchange02', '0340_wild_shot02', '0340_wildshot02', '0520_down01_start', '0281_sleep01_loop', '0400_attack01',
       '0260_wild_bool02_start', '0625_formchange01', '0001_battlewait01_loop', '0294_eat02_loop', '0630_directionattack01', '0291_eat01_loop',
       '0010_defaultidle01', '0290_eat01_start', '0511_stun01_loop', '0282_sleep01_end', '0460_rangeattack02_start', '0147_stepout01_end',
       '0270_wild_bool01_start', '0261_wildbool02_loop', '0295_eat02_end', '0563_hate01', '0292_eat01_end', '0462_rangeattack02_end',
       '0510_stun01_start', '0461_rangeattack02_loop', '0280_sleep01_start', '0410_attack02', '0500_damage01', '0261_wild_bool02_loop',
       '0320_refresh01', '0450_rangeattack01', '0000_defaultwait01_loop', '0011_defaultidle02', '0330_lookaround01', '0550_glad01',
       '0271_wild_bool01_loop', '0701_uniquewait01_loop', '0271_rest01_loop', '0521_down01_loop', '0330_wild_shot01', '0522_down01_end',
       '0293_eat02_start', '0262_wild_bool02_end']
for x in nso: stems.add(x[5:])
stems = sorted(stems)
print('vocabulary stems', len(stems))

M = 0xFFFFFFFFFFFFFFFF
def fnv_cont(h, s):
    for c in s.encode():
        h = ((h ^ c) * 0x100000001B3) & M
    return h
suffixes = [(st + ext).encode() for st in stems for ext in ('.tranm', '.traef')]

def scan(folder):
    pm, stem = folder.split('/')
    base = f'ik_pokemon/data/{pm}/{stem}/{stem}_'
    files = g.files
    found = {}
    for grp in '012':
        for i in range(1000):
            pre = f'{grp}{i:04d}_'
            h0 = fnv_cont(0xCBF29CE484222645, base + pre)
            for suf in suffixes:
                h = h0
                for c in suf:
                    h = ((h ^ c) * 0x100000001B3) & M
                if h in files: found[pre + suf.decode()] = files[h]['size']
    return found

res = {}
for folder in sys.argv[1:]:
    f = scan(folder)
    stem = folder.split('/')[1]
    packs = collections.Counter()
    for name, recs in g.packs:
        if stem in name: packs[name] = len(recs)
    tranm = sorted(k for k in f if k.endswith('.tranm'))
    traef = sorted(k for k in f if k.endswith('.traef'))
    print(folder, 'packs', dict(packs), 'tranm', len(tranm), 'traef', len(traef))
    by = collections.Counter(k[0] for k in tranm)
    print('  tranm by group', dict(by))
    print('  ', [k[:-6] for k in tranm])
    res[folder] = f
json.dump(res, open(S + '/out/anim-inventory.json', 'w'), indent=1)
