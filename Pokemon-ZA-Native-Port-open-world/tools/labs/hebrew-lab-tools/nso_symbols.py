"""List exported / imported symbols of the game's NSO modules matching a pattern (read-only)."""
import re, sys
sys.path.insert(0, r'C:/Users/Tomer/Documents/ChatGPT/פריצות/PS5-13.60/pokeza-recomp-ps5/tools')
from nso import Nso
G = r'C:/Users/Tomer/Documents/Codex/2026-10-22/ns2jb-nintendo-switch-2-switch-1/research/pokeza-pc/update-2.0.2-20261025/game/exefs/'
pat = re.compile(sys.argv[1])
for mod in ('main', 'sdk'):
    n = Nso(G + mod)
    ex = n.exports(); im = n.imports()
    exl = ex if isinstance(ex, (list, tuple)) else list(ex.items()) if isinstance(ex, dict) else list(ex)
    iml = im if isinstance(im, (list, tuple)) else list(im.items()) if isinstance(im, dict) else list(im)
    def name(x): return x[0] if isinstance(x, tuple) else (x.get('name') if isinstance(x, dict) else str(x))
    e = [name(x) for x in exl]; i = [name(x) for x in iml]
    me = [s for s in e if pat.search(s)]; mi = [s for s in i if pat.search(s)]
    print(mod, 'exports', len(e), 'imports', len(i), 'matching exports', len(me), 'matching imports', len(mi))
    for s in sorted(set(me))[:int(sys.argv[2]) if len(sys.argv) > 2 else 40]: print('  E', s)
    for s in sorted(set(mi))[:int(sys.argv[2]) if len(sys.argv) > 2 else 40]: print('  I', s)
