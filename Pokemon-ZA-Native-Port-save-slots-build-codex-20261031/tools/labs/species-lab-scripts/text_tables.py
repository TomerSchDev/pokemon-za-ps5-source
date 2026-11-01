"""Read-only: line counts of species-related English message tables (names / dex entries), and whether absent species
(national 10, 1011, 1025) have name/dex lines. Prints counts and a few species names only."""
import sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/hebrew-lab/tools')
import za_romfs, gfmsg
GAME = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/romfs.bin'
g = za_romfs.Game(GAME)
def text(units): return ''.join(chr(u) if u >= 32 else '?' for u in units)
for name in ('monsname', 'zukan_comment_A', 'zukan_comment_B', 'zkn_form', 'zukan_form', 'zkn_type', 'tokusei', 'wazaname'):
    for ext in ('.dat',):
        p = f'ik_message/dat/English/common/{name}{ext}'
        if not g.has(p):
            print('missing', p); continue
        m = gfmsg.MsgFile(g.read(p))
        n = len(m.lines)
        nonempty = sum(1 for l in m.lines if l)
        info = f'{p}: lines {n}, non-empty {nonempty}'
        if name == 'monsname':
            info += ' | ' + ', '.join(f'{i}={text(m.lines[i])}' for i in (10, 925, 1000, 1010, 1011, 1025) if i < n)
        if name.startswith('zukan_comment'):
            info += ' | lens ' + ', '.join(f'{i}:{len(m.lines[i])}' for i in (10, 25, 1000, 1010, 1011, 1025) if i < n)
        print(info)
