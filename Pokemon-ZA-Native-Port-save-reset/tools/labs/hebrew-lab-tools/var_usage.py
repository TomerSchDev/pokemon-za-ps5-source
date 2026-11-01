"""Count control-code types per language (aggregate numbers only)."""
import collections, glob, os, re, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gfmsg import MsgFile, decode_units
VAR = re.compile(r'\{VAR ([0-9A-F]{4})')
for lang in sys.argv[2:]:
    c = collections.Counter()
    for p in glob.glob(os.path.join(sys.argv[1], 'romfs/ik_message/dat', lang, '*/*.dat')):
        for u in MsgFile(open(p, 'rb').read()).lines:
            c.update(VAR.findall(decode_units(u)))
    print(lang, sum(c.values()), ' '.join('%s:%d' % kv for kv in sorted(c.items(), key=lambda x: -x[1])[:40]))
